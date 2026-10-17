import os
import sys
import json
import time
import traceback
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_SLOTS = ["08:00", "14:00", "20:00"]

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
                "times": DEFAULT_SLOTS,
                "missed_slots_log": {},
                "completed_slots_log": {},
                "last_failure_reason": ""
            }, f, indent=4)

    if not os.path.exists("data/notifications.json"):
        with open("data/notifications.json", "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)

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

def get_today_completed_reels_count(hist, today_str):
    return sum(
        1 for item in hist.get("history", [])
        if item.get("batch_date") == today_str and item.get("video_completed")
    )

def run_autonomous_schedule_cycle():
    """
    Implements Points 10, 11, 12, 13, 14:
    - Reads live user-configured slot times from `data/schedule_config.json` (Default: 08:00, 14:00, 20:00).
    - Tries building 3 reels starting at 02:00 AM IST, retrying every hour while active slots remain today.
    - Point 12 Rollover Logic:
      * If a slot time (e.g., 08:00 AM) passes and no reel was ready/posted, logs a notification and rolls over to next slot (02:00 PM).
      * If the final slot of the day (e.g., 08:00 PM) also passes without any reel built/posted, sends a final End-of-Day notification with the exact reason and cleanly resets for tomorrow!
    """
    import dashboard_app
    import gemini_bot

    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")

    with open("data/schedule_config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if not cfg.get("enabled", True):
        print("⏸️ Auto-Scheduler is disabled.")
        return

    slots = sorted(cfg.get("times") or DEFAULT_SLOTS)
    completed_runs = cfg.get("completed_slots_log", {})
    missed_runs = cfg.get("missed_slots_log", {})
    done_today = completed_runs.get(today_str, [])
    missed_today = missed_runs.get(today_str, [])

    with open("data/history.json", "r", encoding="utf-8") as f:
        hist = json.load(f)

    # STEP A: Check if any scheduled reel is due for posting right now
    for idx, slot in enumerate(slots):
        if slot in done_today or slot in missed_today:
            continue
        slot_dt = datetime.strptime(f"{today_str} {slot}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        diff_mins = (now_ist - slot_dt).total_seconds() / 60.0

        # Within 0 to 45 minutes of slot time -> Publish queued reel if available!
        if 0 <= diff_mins <= 45:
            candidates = [
                r for r in hist.get("history", [])
                if r.get("status") == "scheduled" and (r.get("scheduled_slot") == slot or not r.get("scheduled_slot"))
            ]
            if candidates:
                target = sorted(candidates, key=lambda x: x.get("schedule_click_order", 9999))[0]
                reel_id = target.get("video_id") or target.get("id")
                ok, err = dashboard_app.publish_reel_item_to_instagram(reel_id)
                if ok:
                    done_today.append(slot)
                    completed_runs[today_str] = done_today
                    cfg["completed_slots_log"] = completed_runs
                    with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=4)
                    return

        # POINT 12: Slot window expired (> 45 mins past slot) and no reel was posted!
        if diff_mins > 45:
            missed_today.append(slot)
            missed_runs[today_str] = missed_today
            cfg["missed_slots_log"] = missed_runs
            reason = cfg.get("last_failure_reason") or "Gemini Video Limit / No Approved Reel Ready"

            if idx < len(slots) - 1:
                next_slot = slots[idx + 1]
                msg = f"⏰ Slot {slot} IST time-up! Reel ready nahi ho payi ({reason}). Ab system next schedule slot ({next_slot} IST) ke liye work karega."
                gemini_bot.push_app_notification("slot_missed", f"Slot {slot} Missed -> Shifting to {next_slot}", msg, "warning")
                gemini_bot.send_alert(msg)
            else:
                # Final slot of the day also missed!
                msg = (
                    f"🌙 Aaj ({today_str}) ka last schedule slot ({slot} IST) bhi nikal gaya aur reel nahi ban/post ho payi.\n"
                    f"📌 Reason: {reason}\n"
                    f"✅ Aaj ka cycle skip kar diya gaya hai — kal subah naye schedule se automatic kaam shuru hoga!"
                )
                gemini_bot.push_app_notification("slot_missed", "Today's All Slots Ended — Reset for Tomorrow", msg, "error")
                gemini_bot.send_alert(msg)

            with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)

    # STEP B: If all slots for today are either done or missed, wait cleanly for tomorrow!
    if len(done_today) + len(missed_today) >= len(slots):
        print("🌙 All schedule slots for today have concluded. Standing by for tomorrow's 02:00 AM cycle!")
        return

    # STEP C: 02:00 AM Nightly Batch + Hourly Auto-Retry until 3 Reels are built (or 1-Hour Pre-Slot Deficit)
    if now_ist.hour >= 2:
        built_today = get_today_completed_reels_count(hist, today_str)
        remaining_slots_count = len(slots) - (len(done_today) + len(missed_today))
        target_to_build = min(3, max(built_today, remaining_slots_count))

        last_attempt_ts = cfg.get("last_batch_attempt_ts", 0)
        mins_since_last_try = (time.time() - last_attempt_ts) / 60.0

        if built_today < 3 and (now_ist.hour == 2 or mins_since_last_try >= 50):
            cfg["last_batch_attempt_ts"] = time.time()
            with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)

            missing = 3 - built_today
            for i in range(missing):
                try:
                    dashboard_app.generate_single_reel_package(send_for_approval=True, batch_date=today_str)
                    cfg["last_failure_reason"] = ""
                    with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=4)
                    time.sleep(4)
                except Exception as gen_err:
                    cfg["last_failure_reason"] = str(gen_err)[:160]
                    with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=4)
                    break

def run_single_cloud_video_job():
    ensure_required_folders_and_files()
    event_name = os.environ.get("CLOUD_EVENT_NAME", "workflow_dispatch")
    action_type = os.environ.get("CLOUD_ACTION_TYPE", "generate_only")
    custom_topic = os.environ.get("CLOUD_CUSTOM_TOPIC", "").strip()
    today_str = datetime.now(IST).strftime("%Y-%m-%d")

    try:
        import dashboard_app
        import gemini_bot
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
        print(f"\n⚠️ [CLOUD WORKER ERROR]: {err_msg}\n{traceback.format_exc()}")
        gemini_bot.update_3d_telemetry(0, "PIPELINE STOPPED / ALERT", err_msg[:220], "error", 0)
        sys.exit(0)

if __name__ == "__main__":
    if "--export-cookies" in sys.argv:
        export_local_chrome_cookies()
    else:
        run_single_cloud_video_job()