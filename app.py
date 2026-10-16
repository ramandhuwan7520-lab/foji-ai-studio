import os
import time
import threading
import subprocess
import importlib
import urllib.request

# Safe fallback for @spaces so it works on both CPU-Basic and ZeroGPU without errors
try:
    import spaces
    gpu_decorator = spaces.GPU
except ImportError:
    def gpu_decorator(func):
        return func

@gpu_decorator
def zero_gpu_engine_ping():
    return "Engine Ready"

import dashboard_app

# Enable Instant Frontend HTML/Template Auto-Reload without restarting server
dashboard_app.app.config["TEMPLATES_AUTO_RELOAD"] = True
dashboard_app.app.jinja_env.auto_reload = True

def keep_alive_24_7_pinger():
    """
    Pings our own Hugging Face Live URL every 4 minutes 24/7
    so Hugging Face NEVER pauses or sleeps the Space!
    """
    space_url = "https://raman17-foji-ai-studio.hf.space/api/live_status"
    local_url = "http://127.0.0.1:7860/api/live_status"
    while True:
        time.sleep(240)  # Every 4 minutes
        for url in (local_url, space_url):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Foji-KeepAlive/1.0"})
                urllib.request.urlopen(req, timeout=10)
            except Exception:
                pass

def hot_reload_vs_code_sync_loop():
    """
    Checks every 8 seconds for VS Code changes.
    Pulls new code and HOT-RELOADS Python modules in-memory WITHOUT crashing or stopping the container!
    """
    while True:
        time.sleep(8)
        if os.path.exists(".git"):
            try:
                subprocess.run(["git", "fetch", "origin", "main"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
                local = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip()
                remote = subprocess.check_output(["git", "rev-parse", "origin/main"]).strip()
                if local != remote:
                    print("⚡ [INSTANT HOT-SYNC]: Pulling new VS Code update without stopping server...")
                    subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
                    # Hot-reload backend modules in-place (Zero Downtime!)
                    for mod_name in ["brain", "gemini_bot", "studio", "telegram_bot", "dashboard_app"]:
                        if mod_name in globals():
                            try:
                                importlib.reload(globals()[mod_name])
                            except Exception as e:
                                print(f"Reload notice for {mod_name}: {e}")
                    print("✅ [LIVE UPDATED]: Frontend & Backend updated instantly!")
            except Exception:
                pass

if __name__ == "__main__":
    threading.Thread(target=keep_alive_24_7_pinger, daemon=True).start()
    threading.Thread(target=hot_reload_vs_code_sync_loop, daemon=True).start()
    print("🚀 Starting Foji 3D Studio 24/7 (Never-Pause + Instant Hot-Reload Active)...")
    dashboard_app.app.run(host="0.0.0.0", port=7860, debug=False, use_reloader=False, threaded=True)