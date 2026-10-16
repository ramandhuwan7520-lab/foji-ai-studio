import time
import subprocess

print("⚡ VS Code -> Cloud Live Auto-Sync Active!")
print("Jo bhi code file (Ctrl+S) save karoge, woh 3 second mein Cloud par live ho jayegi...\n")

last_status = ""
while True:
    time.sleep(3)
    try:
        status = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        if status and status != last_status:
            print("📤 Code change detected in VS Code! Pushing to Hugging Face Cloud...")
            subprocess.run(["git", "add", "*.py", "requirements.txt", "packages.txt", "README.md", ".gitignore", "data/schedule_config.json"], check=False)
            subprocess.run(["git", "commit", "-m", "VS Code Auto-Live Sync"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "push", "origin", "main"], check=False)
            print("✅ Live Updated on Cloud (https://raman17-foji-ai-studio.hf.space)!\n")
            last_status = ""
        else:
            last_status = status
    except Exception:
        pass