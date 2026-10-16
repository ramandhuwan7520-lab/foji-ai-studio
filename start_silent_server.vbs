Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d D:\foji_ai_automation && venv\Scripts\pythonw.exe dashboard_app.py", 0, False