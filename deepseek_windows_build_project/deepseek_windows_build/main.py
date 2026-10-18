import os
import sys
import time
import threading
import tempfile
import winsound
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QColor, QPainter, QLinearGradient, QBrush, QPen
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QDialog, QMessageBox, QFormLayout
)
import keyboard
import sounddevice as sd
import soundfile as sf
import numpy as np
import pyperclip
import keyring
from openai import OpenAI

APP_NAME = "ChatGPT Island"
KEYRING_SERVICE = "ChatGPTIsland"
KEYRING_USERNAME = "deepseek_api_key"
CONFIG_DIR = Path(os.getenv("APPDATA", str(Path.home()))) / "ChatGPTIsland"
CONFIG_FILE = CONFIG_DIR / "settings.json"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

def get_saved_api_key():
    # Windows Credential Manager via keyring; do not store the key in the source code.
    try:
        key = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if key:
            return key
    except Exception:
        pass
    # Migration/fallback for environments where Credential Manager is unavailable.
    try:
        import json
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return data.get("deepseek_api_key", "")
    except Exception:
        pass
    return ""

def save_api_key(api_key):
    api_key = api_key.strip()
    if not api_key:
        raise ValueError("API Key 不能为空。")
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, api_key)
        # Remove a legacy fallback file if present.
        if CONFIG_FILE.exists():
            try:
                CONFIG_FILE.unlink()
            except Exception:
                pass
        return
    except Exception:
        # Fallback: user-only config file, with a warning shown in UI.
        import json
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            json.dumps({"deepseek_api_key": api_key}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except Exception:
            pass

class ApiKeyDialog(QDialog):
    def __init__(self, parent=None, existing=False):
        super().__init__(parent)
        self.setWindowTitle("配置 DeepSeek API Key")
        self.setModal(True)
        self.setMinimumWidth(470)
        self.api_key = ""
        layout = QVBoxLayout(self)
        intro = QLabel(
            "首次使用需要配置 DeepSeek API Key。\\n"
            "Key 会保存在这台电脑上，下次启动无需再次输入。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("粘贴 DeepSeek API Key")
        form.addRow("API Key：", self.key_edit)
        layout.addLayout(form)

        self.show_key = QPushButton("显示 Key")
        self.show_key.setCheckable(True)
        self.show_key.toggled.connect(
            lambda checked: self.key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        layout.addWidget(self.show_key)

        buttons = QHBoxLayout()
        self.confirm = QPushButton("确认并保存")
        self.cancel = QPushButton("退出")
        self.confirm.clicked.connect(self.accept_key)
        self.cancel.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.confirm)
        layout.addLayout(buttons)

        self.setStyleSheet("""
            QDialog { background: #f4f5f7; color: #16181d; }
            QLabel { font-size: 13px; }
            QLineEdit { padding: 10px; border: 1px solid #c8ccd3; border-radius: 8px; background: white; }
            QPushButton { padding: 9px 14px; border-radius: 8px; }
        """)

    def accept_key(self):
        value = self.key_edit.text().strip()
        if not value:
            QMessageBox.warning(self, "缺少 API Key", "请先输入 DeepSeek API Key。")
            return
        self.api_key = value
        self.accept()

class Signals(QObject):
    state = Signal(str, str)
    reply = Signal(str)
    error = Signal(str)

class Island(QWidget):
    def __init__(self, signals):
        super().__init__()
        self.signals = signals
        self.mode = "idle"
        self.drag_pos = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(390, 52)
        self._build_ui()
        self.position_top_center()
        self.hide()
        signals.state.connect(self.set_state)
        signals.reply.connect(self.show_reply)
        signals.error.connect(self.show_error)

    def _build_ui(self):
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(18, 10, 18, 10)
        self.header = QHBoxLayout()
        self.icon = QLabel("")
        self.icon.setStyleSheet("color:#ffffff;font-size:17px;background:transparent;")
        self.title = QLabel("")
        self.title.setStyleSheet("color:#ffffff;font-size:13px;background:transparent;")
        self.status = QLabel("")
        self.status.setStyleSheet("color:rgba(255,255,255,220);font-size:12px;background:transparent;")
        self.header.addWidget(self.icon)
        self.header.addWidget(self.title)
        self.header.addStretch()
        self.header.addWidget(self.status)
        self.outer.addLayout(self.header)

        self.wave = QLabel("")
        self.wave.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wave.setStyleSheet("color:#8ce8ff;font-size:20px;letter-spacing:3px;background:transparent;")
        self.outer.addWidget(self.wave)

        self.answer = QTextEdit()
        self.answer.setReadOnly(True)
        self.answer.setMinimumHeight(90)
        self.answer.setMaximumHeight(300)
        self.answer.setStyleSheet("""
            QTextEdit { color: rgba(255,255,255,245); background: transparent;
              border: none; font-size: 14px; selection-background-color: #3478f6; }
            QScrollBar:vertical { width: 4px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(255,255,255,100); border-radius: 2px; }
        """)
        self.answer.hide()
        self.outer.addWidget(self.answer)

        self.footer = QLabel("F13 按住说话 · F14 显示/隐藏 · F15 停止 · F16 发送剪贴板")
        self.footer.setStyleSheet("color:rgba(255,255,255,145);font-size:10px;background:transparent;")
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.outer.addWidget(self.footer)

    def position_top_center(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.x() + (screen.width()-self.width())//2, screen.y()+18)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        # Translucent liquid-glass-inspired gradient. True desktop blur depends on Windows compositor.
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QColor(16, 18, 25, 218))
        grad.setColorAt(0.48, QColor(12, 14, 20, 196))
        grad.setColorAt(1, QColor(75, 83, 100, 162))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 78), 1))
        radius = min(38, self.height()/2)
        p.drawRoundedRect(rect, radius, radius)
        p.setPen(QPen(QColor(255,255,255,35), 1))
        p.drawLine(30, 3, self.width()-30, 3)
        p.end()

    def set_state(self, state, detail=""):
        self.mode = state
        if state == "idle":
            self.title.setText("")
            self.status.setText("")
            self.icon.setText("")
            self.wave.setText("")
            self.answer.hide()
            self.footer.hide()
            self.resize(390, 52)
            self.outer.setContentsMargins(18, 8, 18, 8)
            self.show()
            self.position_top_center()
            QTimer.singleShot(1800, self.hide_if_idle)
        elif state == "recording":
            self.resize(470, 82)
            self.outer.setContentsMargins(18, 10, 18, 10)
            self.icon.setText("●")
            self.title.setText("正在聆听")
            self.status.setText("按住 F13")
            self.wave.show()
            self.wave.setText("▂  ▄  ▆  ▇  ▅  ▃  ▅  ▇  ▆  ▄  ▂")
            self.answer.hide()
            self.footer.show()
            self.show()
            self.position_top_center()
        elif state == "thinking":
            self.resize(430, 68)
            self.icon.setText("✦")
            self.title.setText("DeepSeek")
            self.status.setText("正在思考…")
            self.wave.show()
            self.wave.setText("·   ·   ·   ·   ·")
            self.answer.hide()
            self.footer.show()
            self.show()
            self.position_top_center()
        elif state == "reply":
            self.resize(590, 300)
            self.icon.setText("✦")
            self.title.setText("DeepSeek")
            self.status.setText("回答")
            self.wave.hide()
            self.answer.show()
            self.footer.show()
            self.show()
            self.position_top_center()
        elif state == "error":
            self.resize(520, 135)
            self.icon.setText("!")
            self.title.setText("ChatGPT Island")
            self.status.setText("需要检查")
            self.wave.setText(detail[:180])
            self.answer.hide()
            self.footer.show()
            self.show()
            self.position_top_center()
        self.update()

    def hide_if_idle(self):
        if self.mode == "idle":
            self.hide()

    def show_reply(self, text):
        self.answer.setPlainText(text)
        self.set_state("reply")

    def show_error(self, text):
        self.set_state("error", text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

class Controller:
    def __init__(self, signals, api_key):
        self.signals = signals
        self.client = OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL)
        self.recording = False
        self.audio_chunks = []
        self.audio_lock = threading.Lock()
        self.stream = None
        self.history = []
        self.request_generation = 0

    def start(self):
        # Macro pad should send F13-F16. If unsupported, remap these in main.py.
        keyboard.on_press_key("f13", self.on_f13_down, suppress=False)
        keyboard.on_release_key("f13", self.on_f13_up, suppress=False)
        keyboard.add_hotkey("f14", lambda: self.signals.state.emit("idle", ""))
        keyboard.add_hotkey("f15", self.stop)
        keyboard.add_hotkey("f16", self.send_clipboard)

    def on_f13_down(self, event):
        if self.recording:
            return
        self.recording = True
        self.audio_chunks = []
        self.signals.state.emit("recording", "")
        try:
            self.stream = sd.InputStream(
                samplerate=16000, channels=1, dtype="float32",
                callback=self.audio_callback
            )
            self.stream.start()
        except Exception as e:
            self.recording = False
            self.signals.error.emit("麦克风启动失败：" + str(e))

    def audio_callback(self, indata, frames, time_info, status):
        if self.recording:
            with self.audio_lock:
                self.audio_chunks.append(indata.copy())

    def on_f13_up(self, event):
        if not self.recording:
            return
        self.recording = False
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None
        except Exception:
            pass
        threading.Thread(target=self.process_audio, daemon=True).start()

    def process_audio(self):
        try:
            # DeepSeek Chat API does not itself transcribe microphone audio.
            # This prototype uses the Windows speech recognizer via SpeechRecognition's Google backend.
            # For fully local/offline transcription, replace this with faster-whisper.
            with self.audio_lock:
                chunks = self.audio_chunks[:]
            if not chunks:
                raise RuntimeError("没有录到音频，请检查麦克风权限。")
            audio = np.concatenate(chunks, axis=0)
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            tmp.close()
            sf.write(tmp.name, audio, 16000)
            self.signals.state.emit("thinking", "")
            try:
                import speech_recognition as sr
                recognizer = sr.Recognizer()
                with sr.AudioFile(tmp.name) as source:
                    audio_data = recognizer.record(source)
                prompt = recognizer.recognize_google(audio_data, language="zh-CN")
            finally:
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
            if not prompt.strip():
                raise RuntimeError("没有识别到文字。")
            self.ask(prompt.strip())
        except Exception as e:
            self.signals.error.emit("语音识别失败：" + str(e))

    def ask(self, prompt):
        generation = self.request_generation + 1
        self.request_generation = generation
        try:
            self.signals.state.emit("thinking", "")
            self.history.append({"role": "user", "content": prompt})
            response = self.client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=self.history[-12:],
                stream=False
            )
            answer = response.choices[0].message.content or ""
            self.history.append({"role": "assistant", "content": answer})
            self.signals.reply.emit("你： " + prompt + "\n\nDeepSeek：\n" + answer)
        except Exception as e:
            self.signals.error.emit(
                "DeepSeek 请求失败。请检查 API Key、网络和账户余额。\\n" + str(e)
            )

    def send_clipboard(self):
        try:
            text = pyperclip.paste().strip()
            if text:
                threading.Thread(target=self.ask, args=(text,), daemon=True).start()
            else:
                self.signals.error.emit("剪贴板没有文字。")
        except Exception as e:
            self.signals.error.emit(str(e))

    def stop(self):
        try:
            if self.stream:
                self.recording = False
                self.stream.stop()
                self.stream.close()
                self.stream = None
        except Exception:
            pass
        self.signals.state.emit("idle", "")

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    api_key = get_saved_api_key()
    if not api_key:
        dialog = ApiKeyDialog()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return 0
        api_key = dialog.api_key
        try:
            save_api_key(api_key)
        except Exception as e:
            QMessageBox.critical(None, "保存失败", f"无法保存 API Key：{e}")
            return 1

    signals = Signals()
    island = Island(signals)
    controller = Controller(signals, api_key)
    controller.start()

    def toggle():
        if island.isVisible():
            island.hide()
        else:
            signals.state.emit("idle", "")
            island.show()
            island.position_top_center()

    keyboard.clear_all_hotkeys()
    keyboard.on_press_key("f13", controller.on_f13_down, suppress=False)
    keyboard.on_release_key("f13", controller.on_f13_up, suppress=False)
    keyboard.add_hotkey("f14", toggle)
    keyboard.add_hotkey("f15", controller.stop)
    keyboard.add_hotkey("f16", controller.send_clipboard)

    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
