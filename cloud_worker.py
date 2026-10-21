import os
import sys
import json
import time
import subprocess
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_SLOTS = ["08:00", "14:00", "20:00"]

def pull_latest_from_github():
    if os.environ.get("GITHUB_ACTIONS") == "true":
        try:
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

def ensure_required_folders_and_files():
    os.makedirs("data", exist_ok=True)
    os.makedirs("output/raw_videos", exist_ok=True)
    os.makedirs("output/final_reels", exist_ok=True)
    os.makedirs("assets/characters", exist_ok=True)

    if not os.path.exists("data/history.json"):
        with open("data/history.json", "w", encoding="utf-8") as f:
            json.dump({"generated_count": 0, "track_parts": {}, "recent_tracks": [], "deleted_ids": [], "history": []}, f, indent=4)

    if not os.path.exists("data/schedule_config.json"):
        with open("data/schedule_config.json", "w", encoding="utf-8") as f:
            json.dump({
                "enabled": True,
                "nightly_batch_time": "02:30",
                "times": DEFAULT_SLOTS,
                "button_locked": True,
                "nightly_230am_tried_date": "",
                "pre_slot_30m_tried": {},
                "missed_slots_log": {},
                "completed_slots_log": {}
            }, f, indent=4)

    if not os.path.exists("data/notifications.json"):
        with open("data/notifications.json", "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)

def interactive_pro_login_and_save_cookies():
    import gemini_bot
    print("\n🔐 Opening Chrome for Gemini PRO Account Login...")
    driver = gemini_bot.create_direct_chrome_driver(os.path.abspath("output/raw_videos"))
    try:
        gemini_bot.load_and_ensure_login(driver)
        gemini_bot.save_cookies_from_driver(driver)
        print("🎉 Login & Cookie Export 100% Complete!")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

def get_today_ready_reels_count(hist, today_str):
    deleted_ids = set(str(x) for x in hist.get("deleted_ids", []))
    return sum(
        1 for item in hist.get("history", [])
        if str(item.get("video_id", "")) not in deleted_ids
        and item.get("video_completed")
        and (item.get("batch_date") == today_str or item.get("status") in ("pending_approval", "scheduled"))
    )

def try_building_missing_reels(target_missing, today_str):
    import dashboard_app
    for _ in range(target_missing):
        try:
            pull_latest_from_github()
            dashboard_app.generate_single_reel_package(send_for_approval=True, batch_date=today_str)
            time.sleep(3)
        except Exception as e:
            print(f"⏸️ Generation stopped: {e}")
            break

def run_autonomous_schedule_cycle():
    """
    STRICT SCHEDULE ENGINE:
    1. Posts any scheduled reel when its slot time arrives.
    2. At 02:30 AM IST: Tries ONCE to generate all 3 daily reels.
    3. At 30 Minutes Before Each Schedule Slot (T - 30m): Tries ONCE if < 3 reels are ready.
    """
    import dashboard_app

    pull_latest_from_github()
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")

    with open("data/schedule_config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if not cfg.get("enabled", True):
        return

    slots = sorted(cfg.get("times") or DEFAULT_SLOTS)
    completed_runs = cfg.get("completed_slots_log", {})
    missed_runs = cfg.get("missed_slots_log", {})
    pre30_map = cfg.get("pre_slot_30m_tried", {}).get(today_str, [])
    done_today = completed_runs.get(today_str, [])
    missed_today = missed_runs.get(today_str, [])

    hist = dashboard_app.load_history()

    # 1. PUBLISH SCHEDULED REELS AT SLOT TIME
    for slot in slots:
        if slot in done_today or slot in missed_today:
            continue
        slot_dt = datetime.strptime(f"{today_str} {slot}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        diff_mins = (now_ist - slot_dt).total_seconds() / 60.0

        if -2 <= diff_mins <= 30:
            candidates = [
                r for r in hist.get("history", [])
                if r.get("status") == "scheduled" and (r.get("scheduled_slot") == slot or not r.get("scheduled_slot"))
            ]
            if candidates:
                target = sorted(candidates, key=lambda x: x.get("schedule_click_order", 9999))[0]
                reel_id = target.get("video_id") or target.get("id")
                ok, _ = dashboard_app.publish_reel_item_to_instagram(reel_id)
                if ok:
                    done_today.append(slot)
                    completed_runs[today_str] = done_today
                    cfg["completed_slots_log"] = completed_runs
                    with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=4)
                    return

        elif diff_mins > 30:
            missed_today.append(slot)
            missed_runs[today_str] = missed_today
            cfg["missed_slots_log"] = missed_runs
            with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)

    # 2. CHECK IF 3 REELS ARE ALREADY READY
    ready_count = get_today_ready_reels_count(hist, today_str)
    if ready_count >= 3:
        return

    # 3. 02:30 AM IST DAILY BATCH — STRICTLY ONE TRY AT 2:30 AM!
    if now_ist.hour == 2 and 25 <= now_ist.minute <= 45 and cfg.get("nightly_230am_tried_date") != today_str:
        cfg["nightly_230am_tried_date"] = today_str
        with open("data/schedule_config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        try_building_missing_reels(3 - ready_count, today_str)
        return

    # 4. ONLY ONE RETRY 30 MINUTES BEFORE EACH SCHEDULE TIME!
    for slot in slots:
        if slot in done_today or slot in missed_today or slot in pre30_map:
            continue
        slot_dt = datetime.strptime(f"{today_str} {slot}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        mins_before_slot = (slot_dt - now_ist).total_seconds() / 60.0

        if 24 <= mins_before_slot <= 36:
            pre30_map.append(slot)
            cfg.setdefault("pre_slot_30m_tried", {})[today_str] = pre30_map
            with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            try_building_missing_reels(3 - ready_count, today_str)
            return

def run_single_cloud_video_job():
    print("🎬 Starting AutoReels 3D Worker Job...")
    ensure_required_folders_and_files()
    pull_latest_from_github()
    event_name = os.environ.get("CLOUD_EVENT_NAME", "workflow_dispatch")
    action_type = os.environ.get("CLOUD_ACTION_TYPE", "generate_only")
    custom_topic = os.environ.get("CLOUD_CUSTOM_TOPIC", "").strip()
    today_str = datetime.now(IST).strftime("%Y-%m-%d")

    try:
        import dashboard_app
        if event_name == "schedule":
            run_autonomous_schedule_cycle()
            return

        if custom_topic.startswith("REGEN_ID:"):
            vid_id = int(custom_topic.split(":")[1])
            dashboard_app.generate_single_reel_package(
                send_for_approval=True,
                replace_video_id=vid_id,
                batch_date=today_str
            )
            return

        item = dashboard_app.generate_single_reel_package(
            custom_topic=custom_topic if custom_topic else None,
            send_for_approval=True,
            batch_date=today_str
        )
        if item and action_type == "generate_and_publish":
            reel_id = item.get("video_id") or item.get("id")
            dashboard_app.publish_reel_item_to_instagram(reel_id)

    except Exception as e:
        import gemini_bot
        err_msg = str(e)
        print(f"❌ Worker Notice: {err_msg}")
        gemini_bot.update_3d_telemetry(0, "Notice", err_msg[:180], "error", 0)

if __name__ == "__main__":
    os.environ["IS_CLOUD_WORKER"] = "1"
    try:
        if "--login" in sys.argv or "--export-cookies" in sys.argv:
            interactive_pro_login_and_save_cookies()
        else:
            run_single_cloud_video_job()
    finally:
        os._exit(0)