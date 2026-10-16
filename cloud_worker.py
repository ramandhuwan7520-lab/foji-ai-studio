import os
import sys
import json
import time
import traceback
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

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
    """Pre-checks all required folders and JSON files so Cloud Worker NEVER crashes with FileNotFoundError!"""
    os.makedirs("data", exist_ok=True)
    os.makedirs("output/raw_videos", exist_ok=True)
    os.makedirs("output/final_reels", exist_ok=True)
    os.makedirs("assets/characters", exist_ok=True)

    hist_path = "data/history.json"
    if not os.path.exists(hist_path):
        with open(hist_path, "w", encoding="utf-8") as f:
            json.dump({"generated_count": 0, "recent_tracks": [], "history": []}, f, indent=4)

    sched_path = "data/schedule_config.json"
    if not os.path.exists(sched_path):
        with open(sched_path, "w", encoding="utf-8") as f:
            json.dump({"enabled": True, "times": ["11:00", "14:00"], "completed_slots_log": {}}, f, indent=4)

def export_local_chrome_cookies():
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
    cfg_path = "data/schedule_config.json"
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if not cfg.get("enabled", True):
        print("⏸️ Auto-Scheduler is disabled in schedule_config.json.")
        return False, None

    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")
    current_hm = now_ist.strftime("%H:%M")

    slots = cfg.get("times") or ([cfg.get("time")] if cfg.get("time") else ["11:00", "14:00"])
    completed_runs = cfg.get("completed_slots_log", {})
    done_today = completed_runs.get(today_str, [])

    for slot in sorted(slots):
        if not slot or slot in done_today:
            continue
        try:
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
        except Exception:
            pass

    print(f"⏰ [IST {current_hm}] Waiting for next slot. Slots: {slots} | Done Today: {done_today}")
    return False, None

def run_single_cloud_video_job():
    ensure_required_folders_and_files()
    event_name = os.environ.get("CLOUD_EVENT_NAME", "workflow_dispatch")
    action_type = os.environ.get("CLOUD_ACTION_TYPE", "generate_and_publish")
    custom_topic = os.environ.get("CLOUD_CUSTOM_TOPIC", "").strip()

    if event_name == "schedule":
        due, slot_name = is_schedule_slot_due_now()
        if not due:
            return
        print(f"🎯 Scheduled Slot '{slot_name}' is DUE NOW! Starting 7GB Cloud Reel Generation...")
        action_type = "generate_and_publish"

    try:
        write_live_3d_state(1, "BOOTING 7GB CLOUD ENGINE", f"Mode: {action_type}", "active", 12)
        import dashboard_app
        print(f"🚀 [7GB CLOUD ENGINE] Action: {action_type} | Custom Topic: {custom_topic or 'Auto Story'}")

        if hasattr(dashboard_app, "generate_single_reel_package"):
            item = dashboard_app.generate_single_reel_package(custom_topic=custom_topic if custom_topic else None)
            if item and action_type == "generate_and_publish" and hasattr(dashboard_app, "publish_reel_item_to_instagram"):
                reel_id = item.get("id") or item.get("video_id")
                print(f"📤 Auto-Publishing Reel #{reel_id} to Instagram...")
                dashboard_app.publish_reel_item_to_instagram(reel_id)
        else:
            import gemini_bot
            out_vid = gemini_bot.generate_video_in_gemini()
            print(f"✅ Video generated directly via gemini_bot: {out_vid}")

        write_live_3d_state(6, "3D REEL PIPELINE COMPLETE", "Reel generated & synced to Cloud!", "completed", 100)
        print("✅ [7GB CLOUD ENGINE COMPLETE] Task finished cleanly!")

    except Exception as e:
        err_msg = str(e)
        tb_str = traceback.format_exc()
        print(f"\n⚠️ [CLOUD WORKER DIAGNOSTIC LOG]:\n{err_msg}\n{tb_str}")
        write_live_3d_state(0, "CLOUD ENGINE NOTICE", err_msg[:140], "warning", 0)
        # Do NOT crash GitHub Actions with exit code 1 so telemetry & history still get committed!
        sys.exit(0)

if __name__ == "__main__":
    if "--export-cookies" in sys.argv:
        export_local_chrome_cookies()
    else:
        run_single_cloud_video_job()