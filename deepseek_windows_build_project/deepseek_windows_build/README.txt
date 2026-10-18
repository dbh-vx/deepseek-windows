DeepSeek Windows EXE build project

IMPORTANT
This archive is the source/build project, not the compiled Windows executable.
The executable must be built on Windows (or by the included GitHub Actions workflow).
A Linux environment cannot directly produce a native Windows .exe with PyInstaller.

Recommended way to get the EXE without installing Python on the target PC:
1. Upload these files to a GitHub repository.
2. Open the repository's Actions tab.
3. Run the workflow named "Build DeepSeek for Windows" (or push to main).
4. Open the completed workflow run and download the artifact named deepseek-windows-x64.
5. Extract deepseek-windows-x64.zip and double-click deepseek.exe.

The target Windows PC does not need Python or pip once you have the compiled EXE.
The first launch asks for a DeepSeek API Key; it is stored locally using Windows Credential Manager when available.
No startup shortcut is installed by this project. Run deepseek.exe manually when needed.

Notes:
- Internet is required for DeepSeek API requests and the current Google online speech-to-text service.
- The app's global hotkeys use F13-F16; the keyboard/macro pad must be able to send these keys.
- This project has not yet been tested on the user's specific PC.
