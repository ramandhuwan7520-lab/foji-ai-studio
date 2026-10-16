import os
import sys
import json
import time
import traceback
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
FIXED_SLOTS = ["08:00", "14:00", "20:00"]  # 8:00 AM, 2:00 PM, 8:00 PM

def write_live_3d_state(step_num, title, detail, status="active", progress=10):
    os.makedirs("data", exist_ok=True)
    try:
        with open("data/live_telemetry.json", "w", encoding="utf-8") as f:
            json.dump({
                "step_num": step_num,
                "step_title": title,
                "sub_detail": detail,
                "status": status,
                "progress": progress,
                "timestamp": datetime.now(IST).strftime("%H:%M:%S IST")
            }, f, indent=2)
    except Exception:
        pass

def ensure_required_folders_and_files():
    os.makedirs("data", exist_ok=True)
    os.makedirs("output/raw_videos", exist_ok=True)
    os.makedirs("output/final_reels", exist_ok=True)
    os.makedirs("assets/characters", exist_ok=True)

    if not os.path.exists("data/history.json"):
        with open("data/history.json", "w", encoding="utf-8") as f:
            json.dump({"generated_count": 0, "track_parts": {}, "recent_tracks": [], "history": []}, f, indent=4)

    if not os.path.exists("data/schedule_config.json"):
        with open("data/schedule_config.json", "w", encoding="utf-8") as f:
            json.dump({
                "enabled": True,
                "nightly_batch_time": "02:00",
                "times": FIXED_SLOTS,
                "last_nightly_batch_date": "",
                "completed_slots_log": {}
            }, f, indent=4)

def export_local_chrome_cookies():
    import gemini_bot
    print("🔐 Opening local Chrome profile to export Google/Gemini login cookies...")
    driver = gemini_bot.get_chrome_driver(os.path.abspath("output/raw_videos"))
    try:
        driver.get("https://gemini.google.com/app")
        time.sleep(6)
        cookies = driver.get_cookies()
        essential = [
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path", "/"),
                "secure": c.get("secure", True)
            }
            for c in cookies if any(k in c.get("domain", "") for k in ["google", "gemini"])
        ]
        with open("gemini_cookies_secret.txt", "w", encoding="utf-8") as f:
            f.write(json.dumps(essential))
        print("\n✅ SUCCESS! Cookies saved in `gemini_cookies_secret.txt`!")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

def run_autonomous_schedule_cycle():
    """
    Implements Points 10, 11, 12:
    1. At 02:00 AM IST: Generates 3 reels one-by-one and sends them to Backend & Telegram for approval.
    2. At 08:00 AM, 02:00 PM, 08:00 PM: Publishes reels queued via 'Approve & Schedule' in click order.
    3. 1-Hour Pre-Slot Deficit Rule: If a slot is 1 hour away (07:00, 13:00, 19:00) and there is no
       scheduled/ready reel left for that slot (e.g. user posted one immediately via Approve & Post),
       automatically generates the missing 3rd reel 1 hour before its slot!
    """
    import dashboard_app
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")

    with open("data/schedule_config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if not cfg.get("enabled", True):
        print("⏸️ Auto-Scheduler is disabled.")
        return

    # 1. NIGHTLY 02:00 AM BATCH (Generates 3 Daily Reels One-by-One)
    if 2 <= now_ist.hour < 4 and cfg.get("last_nightly_batch_date") != today_str:
        print("🌙 [02:00 AM NIGHTLY FACTORY] Generating 3 Daily Reels One-by-One for Approval...")
        cfg["last_nightly_batch_date"] = today_str
        with open("data/schedule_config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)

        for batch_i in range(1, 4):
            print(f"🎬 Generating Daily Batch Reel {batch_i}/3...")
            dashboard_app.generate_single_reel_package(send_for_approval=True)
            time.sleep(5)
        return

    # 2. CHECK 1-HOUR PRE-SLOT DEFICIT BUILDER (Point 12: 07:00, 13:00, 19:00)
    with open("data/history.json", "r", encoding="utf-8") as f:
        hist = json.load(f)

    for slot in FIXED_SLOTS:
        slot_dt = datetime.strptime(f"{today_str} {slot}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        mins_until_slot = (slot_dt - now_ist).total_seconds() / 60.0
        # Between 45 and 75 minutes before slot (1 hour prior)
        if 40 <= mins_until_slot <= 75:
            queued_for_slot = [
                r for r in hist.get("history", [])
                if r.get("scheduled_slot") == slot and r.get("status") == "scheduled"
            ]
            unscheduled_ready = [
                r for r in hist.get("history", [])
                if r.get("status") == "pending_approval" and r.get("video_completed")
            ]
            if not queued_for_slot and not unscheduled_ready:
                print(f"⚡ [1-HOUR DEFICIT RULE] Slot {slot} has no reel ready! Generating replacement reel now...")
                dashboard_app.generate_single_reel_package(send_for_approval=True)
                return

    # 3. EXECUTE SCHEDULED POSTING AT 08:00 AM, 02:00 PM, 08:00 PM (Point 11)
    completed_runs = cfg.get("completed_slots_log", {})
    done_today = completed_runs.get(today_str, [])

    for slot in FIXED_SLOTS:
        if slot in done_today:
            continue
        slot_dt = datetime.strptime(f"{today_str} {slot}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        diff_mins = (now_ist - slot_dt).total_seconds() / 60.0
        if 0 <= diff_mins <= 60:
            # Find reel scheduled for this slot (or earliest scheduled reel by click order)
            candidates = [
                r for r in hist.get("history", [])
                if r.get("status") == "scheduled" and (r.get("scheduled_slot") == slot or not r.get("scheduled_slot"))
            ]
            if candidates:
                target = sorted(candidates, key=lambda x: x.get("schedule_click_order", 9999))[0]
                reel_id = target.get("video_id") or target.get("id")
                print(f"📤 [SLOT {slot} IST] Publishing Scheduled Reel #{reel_id} to Instagram...")
                dashboard_app.publish_reel_item_to_instagram(reel_id)
                done_today.append(slot)
                completed_runs[today_str] = done_today
                cfg["completed_slots_log"] = completed_runs
                with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=4)
                return

def run_single_cloud_video_job():
    ensure_required_folders_and_files()
    event_name = os.environ.get("CLOUD_EVENT_NAME", "workflow_dispatch")
    action_type = os.environ.get("CLOUD_ACTION_TYPE", "generate_only")
    custom_topic = os.environ.get("CLOUD_CUSTOM_TOPIC", "").strip()

    try:
        import dashboard_app
        if event_name == "schedule":
            run_autonomous_schedule_cycle()
            return

        print(f"🚀 [MANUAL CLOUD WORKER] Action: {action_type} | Topic: {custom_topic or 'Auto Next Episode'}")
        item = dashboard_app.generate_single_reel_package(
            custom_topic=custom_topic if custom_topic else None,
            send_for_approval=True
        )
        if item and action_type == "generate_and_publish":
            reel_id = item.get("video_id") or item.get("id")
            dashboard_app.publish_reel_item_to_instagram(reel_id)

    except Exception as e:
        err_msg = str(e)
        print(f"\n⚠️ [CLOUD WORKER ERROR]: {err_msg}\n{traceback.format_exc()}")
        write_live_3d_state(0, "PIPELINE STOPPED / ALERT", err_msg[:220], "error", 0)
        sys.exit(0)

if __name__ == "__main__":
    if "--export-cookies" in sys.argv:
        export_local_chrome_cookies()
    else:
        run_single_cloud_video_job()