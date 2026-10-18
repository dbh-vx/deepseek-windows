# PyInstaller spec for building DeepSeek as a Windows GUI executable.
# Build on Windows; PyInstaller does not cross-compile Windows executables from Linux.
from PyInstaller.utils.hooks import collect_all

_datas = []
_binaries = []
_hiddenimports = [
    'speech_recognition',
    'keyring.backends.Windows',
    'sounddevice',
    'soundfile',
]
for package in ['PySide6', 'sounddevice', 'soundfile', 'keyring', 'speech_recognition']:
    try:
        d, b, h = collect_all(package)
        _datas += d
        _binaries += b
        _hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='deepseek',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
