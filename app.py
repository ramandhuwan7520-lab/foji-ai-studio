import os
import sys
import time
import threading
import subprocess
import importlib
import urllib.request
import dashboard_app

# Instant Frontend HTML/Template Auto-Reload
dashboard_app.app.config["TEMPLATES_AUTO_RELOAD"] = True
dashboard_app.app.jinja_env.auto_reload = True

def keep_alive_24_7_pinger():
    """
    Pings our live cloud URL every 4 minutes so the free server NEVER sleeps 24/7!
    """
    while True:
        time.sleep(240)
        render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
        urls = ["http://127.0.0.1:" + str(os.environ.get("PORT", 7860)) + "/api/live_status"]
        if render_url:
            urls.append(render_url.rstrip("/") + "/api/live_status")
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass

def hot_reload_vs_code_sync_loop():
    """
    Checks every 8 seconds for VS Code changes and hot-reloads modules without restarting!
    """
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
    threading.Thread(target=keep_alive_24_7_pinger, daemon=True).start()
    threading.Thread(target=hot_reload_vs_code_sync_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 7860))
    print(f"🚀 Starting Foji 3D Studio 24/7 on Port {port}...")
    dashboard_app.app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)