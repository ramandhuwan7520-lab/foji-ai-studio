import time
import subprocess

print("⚡ VS Code Live Auto-Sync Active! Jo bhi file Ctrl+S karoge, woh 3 second mein Cloud par live ho jayegi...")

last_status = ""
while True:
    time.sleep(3)
    try:
        status = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
        if status and status != last_status:
            print("📤 Change detected in VS Code! Syncing to Live Cloud...")
            subprocess.run(["git", "add", "."], check=False)
            subprocess.run(["git", "commit", "-m", "VS Code Auto-Live Update"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["git", "push", "origin", "main"], check=False)
            print("✅ Live Updated on Cloud & Frontend!")
            last_status = ""
        else:
            last_status = status
    except Exception:
        pass