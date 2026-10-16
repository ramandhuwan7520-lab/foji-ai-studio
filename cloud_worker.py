import os
import sys
import json
import time

def export_local_chrome_cookies():
    """
    Run ONCE on your laptop: `python cloud_worker.py --export-cookies`
    Extracts your logged-in Google/Gemini cookies from `chrome_profile` so Cloud Chrome never asks for OTP!
    """
    import gemini_bot
    print("🔐 Opening local Chrome profile to export Google/Gemini login cookies...")
    driver = gemini_bot.get_chrome_driver( os.path.abspath("output/raw_videos") )
    try:
        driver.get("https://gemini.google.com/app")
        time.sleep(6)
        cookies = driver.get_cookies()
        essential = []
        for c in cookies:
            if any(k in c.get("domain", "") for k in ["google", "gemini"]):
                essential.append({
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c["domain"],
                    "path": c.get("path", "/"),
                    "secure": c.get("secure", True)
                })
        with open("gemini_cookies_secret.txt", "w", encoding="utf-8") as f:
            f.write(json.dumps(essential))
        print("\n✅ SUCCESS! Tumhari Google Login Cookies `gemini_cookies_secret.txt` mein save ho gayi hain!")
        print("👉 Ab is file ka text copy karke GitHub Secrets mein `GEMINI_COOKIES_JSON` naam se paste kar do!")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

def run_single_cloud_video_job():
    """
    Runs on GitHub 7GB RAM Server at the EXACT scheduled time.
    Generates ONLY 1 video (NO extra/pre-buffer videos!).
    """
    import dashboard_app
    action_type = os.environ.get("CLOUD_ACTION_TYPE", "generate_only")
    custom_topic = os.environ.get("CLOUD_CUSTOM_TOPIC", "").strip()

    print(f"🚀 [7GB CLOUD ENGINE STARTED] Action: {action_type} | Custom Topic: {custom_topic or 'Auto Story'}")
    # Strictly generate ONLY 1 live reel right now
    item = dashboard_app.generate_single_reel_package(custom_topic=custom_topic if custom_topic else None)

    if item and action_type == "generate_and_publish":
        print(f"📤 Auto-Publishing Reel #{item.get('id')} to Instagram...")
        dashboard_app.publish_reel_item_to_instagram(item.get("id"))

    print("✅ [7GB CLOUD ENGINE COMPLETE] Single video task finished cleanly!")

if __name__ == "__main__":
    if "--export-cookies" in sys.argv:
        export_local_chrome_cookies()
    else:
        run_single_cloud_video_job()