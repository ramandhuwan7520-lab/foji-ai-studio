import os
import time
import threading
import subprocess

def auto_git_sync_loop():
    """Checks every 10 seconds for VS Code updates and pulls automatically."""
    while True:
        time.sleep(10)
        if os.path.exists(".git"):
            try:
                subprocess.run(["git", "fetch", "origin", "main"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                local = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip()
                remote = subprocess.check_output(["git", "rev-parse", "origin/main"]).strip()
                if local != remote:
                    print("⚡ [VS CODE AUTO-SYNC]: Pulling new code...")
                    subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
            except Exception:
                pass

if __name__ == "__main__":
    threading.Thread(target=auto_git_sync_loop, daemon=True).start()
    import dashboard_app
    # Hugging Face Space runs on Port 7860
    dashboard_app.app.run(host="0.0.0.0", port=7860, debug=False, use_reloader=True)