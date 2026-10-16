import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

def export_local_chrome_cookies():
    """Run ONCE on laptop: `python cloud_worker.py --export-cookies`"""
    import gemini_bot
    print("🔐 Opening local Chrome profile to export Google/Gemini login cookies...")
    driver = gemini_bot.get_chrome_driver(os.path.abspath("output/raw_videos"))
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
        try:
            if hasattr(driver, "_chrome_proc"):
                driver._chrome_proc.terminate()
        except Exception:
            pass

def is_schedule_slot_due_now():
    """
    Checks `data/schedule_config.json` in Indian Standard Time (IST).
    If a scheduled slot (e.g., 11:00 or 14:00) has arrived today and hasn't run yet, returns True!
    """
    cfg_path = "data/schedule_config.json"
    if not os.path.exists(cfg_path):
        return False, None

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if not cfg.get("enabled", True):
        print("⏸️ Auto-Scheduler is currently disabled in schedule_config.json.")
        return False, None

    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")
    current_hm = now_ist.strftime("%H:%M")

    # Supports both single `time` and multiple `times` list
    slots = cfg.get("times") or ([cfg.get("time")] if cfg.get("time") else ["11:00", "14:00"])
    completed_runs = cfg.get("completed_slots_log", {})
    done_today = completed_runs.get(today_str, [])

    for slot in sorted(slots):
        if not slot or slot in done_today:
            continue
        # If current IST time is >= slot time (and within 90 mins window so missed slots still fire!)
        slot_dt = datetime.strptime(f"{today_str} {slot}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        diff_mins = (now_ist - slot_dt).total_seconds() / 60.0
        if 0 <= diff_mins <= 90:
            done_today.append(slot)
            completed_runs[today_str] = done_today
            cfg["completed_slots_log"] = completed_runs
            cfg["last_run_date"] = f"{today_str} {slot}"
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            return True, slot

    print(f"⏰ [IST {current_hm}] Abhi kisi schedule slot ka time nahi hua hai. Slots: {slots} | Done Today: {done_today}")
    return False, None

def run_single_cloud_video_job():
    event_name = os.environ.get("CLOUD_EVENT_NAME", "workflow_dispatch")
    action_type = os.environ.get("CLOUD_ACTION_TYPE", "generate_and_publish")
    custom_topic = os.environ.get("CLOUD_CUSTOM_TOPIC", "").strip()

    if event_name == "schedule":
        due, slot_name = is_schedule_slot_due_now()
        if not due:
            return
        print(f"🎯 Scheduled Slot '{slot_name}' is DUE NOW! Starting 7GB Cloud Reel Generation...")
        action_type = "generate_and_publish"

    import dashboard_app
    print(f"🚀 [7GB CLOUD ENGINE] Action: {action_type} | Custom Topic: {custom_topic or 'Auto Story'}")
    item = dashboard_app.generate_single_reel_package(custom_topic=custom_topic if custom_topic else None)

    if item and action_type == "generate_and_publish":
        reel_id = item.get("id") or item.get("video_id")
        print(f"📤 Auto-Publishing Reel #{reel_id} to Instagram...")
        dashboard_app.publish_reel_item_to_instagram(reel_id)

    print("✅ [7GB CLOUD ENGINE COMPLETE] Task finished cleanly!")

if __name__ == "__main__":
    if "--export-cookies" in sys.argv:
        export_local_chrome_cookies()
    else:
        run_single_cloud_video_job()