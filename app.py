import os
import sys
import time
import threading
import subprocess
import importlib
import urllib.request
import dashboard_app

# Enable Instant Frontend HTML/Template Auto-Reload
dashboard_app.app.config["TEMPLATES_AUTO_RELOAD"] = True
dashboard_app.app.jinja_env.auto_reload = True

def anti_sleep_48h_guardian():
    """Pings the live space every 3 minutes so it never sleeps due to inactivity."""
    urls = [
        "https://raman17-foji-ai-studio.hf.space/api/live_status",
        "http://127.0.0.1:7860/api/live_status"
    ]
    while True:
        time.sleep(180)
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass

def hot_reload_vs_code_sync_loop():
    """Pulls VS Code changes every 8 seconds and reloads modules live in-memory!"""
    while True:
        time.sleep(8)
        if os.path.exists(".git"):
            try:
                subprocess.run(["git", "fetch", "origin", "main"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                local = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip()
                remote = subprocess.check_output(["git", "rev-parse", "origin/main"]).strip()
                if local != remote:
                    print("⚡ [INSTANT HOT-SYNC]: Pulling new VS Code update...")
                    subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
                    for mod_name in ["brain", "gemini_bot", "studio", "telegram_bot", "dashboard_app"]:
                        if mod_name in sys.modules:
                            try:
                                importlib.reload(sys.modules[mod_name])
                            except Exception as e:
                                print(f"Reload notice ({mod_name}): {e}")
                    print("✅ [LIVE UPDATED]: Frontend & Backend updated instantly!")
            except Exception:
                pass

if __name__ == "__main__":
    threading.Thread(target=anti_sleep_48h_guardian, daemon=True).start()
    threading.Thread(target=hot_reload_vs_code_sync_loop, daemon=True).start()
    print("🚀 Starting Foji 3D Studio 24/7 on Free CPU-Basic (16GB RAM)...")
    dashboard_app.app.run(host="0.0.0.0", port=7860, debug=False, use_reloader=False, threaded=True)