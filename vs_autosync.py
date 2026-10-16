import time
import subprocess

print("⚡ VS Code -> GitHub -> Render Live Auto-Sync Active!")
print("Ab VS Code mein kisi bhi file par Ctrl+S dabate hi Cloud apne aap update ho jayega!\n")

last_status = ""
while True:
    time.sleep(3)
    try:
        status = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        if status and status != last_status:
            print("📤 Change detected in VS Code! Syncing to GitHub & Render Cloud...")
            subprocess.run(
                ["git", "add", "*.py", "requirements.txt", "packages.txt", ".gitignore", "data/*.json", "assets/characters/*"],
                check=False
            )
            subprocess.run(["git", "commit", "-m", "VS Code Auto-Live Update"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "push", "origin", "main"], check=False)
            print("✅ Pushed! Render Cloud & Hot-Reload will update in 8 seconds!\n")
            last_status = ""
        else:
            last_status = status
    except Exception:
        pass