import os
import time
import threading
import subprocess

def auto_git_sync_loop():
    """
    Checks GitHub every 10 seconds for any code changes you saved in VS Code.
    The moment it sees a change, it pulls the new code -> Flask's use_reloader=True instantly updates the live site!
    """
    while True:
        time.sleep(10)
        if os.path.exists(".git"):
            try:
                subprocess.run(["git", "fetch", "origin", "main"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                local = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip()
                remote = subprocess.check_output(["git", "rev-parse", "origin/main"]).strip()
                if local != remote:
                    print("⚡ [VS CODE AUTO-SYNC]: New code change detected! Pulling live updates...")
                    subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
            except Exception:
                pass

if __name__ == "__main__":
    # Start background VS Code -> Cloud Auto-Pull watcher
    threading.Thread(target=auto_git_sync_loop, daemon=True).start()

    # Start main Dashboard App (Port 7860 for Cloud / Port 5000 for Local)
    import dashboard_app
    port = int(os.environ.get("PORT", 7860))
    print(f"🚀 Cloud Live Server Running on Port {port} with Auto-Reload Active!")
    dashboard_app.app.run(host="0.0.0.0", port=port, debug=False, use_reloader=True)