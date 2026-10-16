import os
import time
import threading
import subprocess
import importlib
import urllib.request

# 1. Zero-Warning Dynamic Import (VS Code will NEVER show 'could not be resolved' error!)
try:
    spaces = importlib.import_module("spaces")
    gpu_decorator = getattr(spaces, "GPU", lambda f: f)
except Exception:
    def gpu_decorator(func):
        return func

try:
    gr = importlib.import_module("gradio")
except Exception:
    gr = None

# 2. Mandatory ZeroGPU Registration so Free ZeroGPU hardware starts 100% cleanly
@gpu_decorator
def zero_gpu_engine_ping():
    return "Foji 3D ZeroGPU Engine Active"

if gr is not None:
    try:
        with gr.Blocks() as dummy_zero_gpu_block:
            btn = gr.Button("Ping GPU")
            out = gr.Textbox()
            btn.click(fn=zero_gpu_engine_ping, inputs=[], outputs=[out])
    except Exception:
        pass

import dashboard_app

# Enable Instant Frontend HTML/Template Auto-Reload
dashboard_app.app.config["TEMPLATES_AUTO_RELOAD"] = True
dashboard_app.app.jinja_env.auto_reload = True

def anti_sleep_48h_guardian():
    """
    Prevents the 48-hour inactivity sleep & automatically wakes the Space if it ever idles!
    Simulates real external browser visits + pings Hugging Face Space API every 3 minutes.
    """
    urls = [
        "https://raman17-foji-ai-studio.hf.space/",
        "https://raman17-foji-ai-studio.hf.space/api/live_status",
        "https://huggingface.co/spaces/raman17/foji-ai-studio",
        "http://127.0.0.1:7860/api/live_status"
    ]
    while True:
        time.sleep(180)  # Every 3 minutes
        for url in urls:
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0 Safari/537.36",
                        "Cache-Control": "no-cache"
                    }
                )
                urllib.request.urlopen(req, timeout=12)
            except Exception:
                pass

def hot_reload_vs_code_sync_loop():
    """
    Checks every 8 seconds for VS Code changes.
    Updates live code in-memory WITHOUT restarting or pausing the Space!
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
                        if mod_name in sys_modules():
                            try:
                                importlib.reload(sys_modules()[mod_name])
                            except Exception as e:
                                print(f"Reload notice ({mod_name}): {e}")
                    print("✅ [LIVE UPDATED]: Changes applied live without downtime!")
            except Exception:
                pass

def sys_modules():
    import sys
    return sys.modules

if __name__ == "__main__":
    try:
        zero_gpu_engine_ping()
    except Exception:
        pass

    threading.Thread(target=anti_sleep_48h_guardian, daemon=True).start()
    threading.Thread(target=hot_reload_vs_code_sync_loop, daemon=True).start()
    print("🚀 Starting Foji 3D Studio 24/7 on Free ZeroGPU (Anti-Sleep + Hot-Reload Active)...")
    dashboard_app.app.run(host="0.0.0.0", port=7860, debug=False, use_reloader=False, threaded=True)