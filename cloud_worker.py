import os
import sys
import json
import time
import subprocess
import traceback
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_SLOTS = ["08:00", "14:00", "20:00"]

def pull_latest_from_github():
    """Bug #5 Fix: Always pulls latest deletions from GitHub before reading/writing history.json!"""
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
                "nightly_batch_time": "02:00",
                "times": DEFAULT_SLOTS,
                "button_locked": True,
                "nightly_2am_tried_date": "",
                "quota_reopen_time_str": "",
                "pre_slot_attempts": {},
                "missed_slots_log": {},
                "completed_slots_log": {}
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

def get_today_ready_reels_count(hist, today_str):
    deleted_ids = set(str(x) for x in hist.get("deleted_ids", []))
    return sum(
        1 for item in hist.get("history", [])
        if str(item.get("video_id", "")) not in deleted_ids
        and item.get("video_completed")
        and (item.get("batch_date") == today_str or item.get("status") in ("pending_approval", "scheduled"))
    )

def try_building_missing_reels(target_missing, today_str, cfg, reason_label):
    """Tries generating 1st reel -> if successful, immediately chains 2nd -> then 3rd!"""
    import dashboard_app
    import gemini_bot
    print(f"🎬 [{reason_label}] Attempting to build {target_missing} reel(s)...")

    for i in range(target_missing):
        try:
            pull_latest_from_github()
            dashboard_app.generate_single_reel_package(send_for_approval=True, batch_date=today_str)
            cfg["quota_reopen_time_str"] = ""
            with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            time.sleep(3)
        except Exception as e:
            print(f"⏸️ Generation stopped during '{reason_label}': {e}")
            break

def rollover_overdue_scheduled_reels(hist, slots, now_ist, today_str):
    """Point #7: If a scheduled reel's slot time already passed, automatically attaches it to the next upcoming slot!"""
    import dashboard_app
    changed = False
    upcoming_slots = []
    for s in slots:
        s_dt = datetime.strptime(f"{today_str} {s}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        if (s_dt - now_ist).total_seconds() > -120:
            upcoming_slots.append(s)

    next_slot = upcoming_slots[0] if upcoming_slots else slots[0]
    dt_label = datetime.strptime(next_slot, "%H:%M").strftime("%I:%M %p")

    for item in hist.get("history", []):
        if item.get("status") == "scheduled" and item.get("scheduled_slot"):
            cur_s = item["scheduled_slot"]
            cur_dt = datetime.strptime(f"{today_str} {cur_s}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
            if (now_ist - cur_dt).total_seconds() > 1800 and cur_s != next_slot:
                item["scheduled_slot"] = next_slot
                item["scheduled_label"] = dt_label
                changed = True
                dashboard_app.log_notification(
                    "scheduled",
                    "Moved to Next Slot",
                    f"{item.get('emotion_name')} shifted to {dt_label} IST.",
                    "info"
                )
    if changed:
        dashboard_app.save_history(hist, sync_cloud=True, msg="Auto-rollover scheduled reel to next slot")

def run_autonomous_schedule_cycle():
    """
    STRICT POINT #7 SCHEDULE & PRECISION RETRY ENGINE:
    1. Syncs live Instagram profile & 7 reels into cache.
    2. At 02:00 AM IST: Tries ONCE to generate all 3 daily reels.
    3. If < 3 reels ready after 02:00 AM:
       - Does NOT blind-retry every hour!
       - Checks if `quota_reopen_time_str` is reached -> Tries immediately!
       - Otherwise, before each schedule slot (e.g. 08:00, 14:00, 20:00), tries at:
         * Stage 1: 1 Hour Before Slot (`T - 60m`)
         * Stage 2: 30 Mins Before Slot (`T - 30m`)
         * Stage 3: 5 Mins Before Slot (`T - 5m`)
       - Whenever 1st reel succeeds, immediately chains 2nd and 3rd!
    4. At Slot Time: Publishes approved/scheduled reel, or rolls over late reels to next slot.
    """
    import dashboard_app
    import gemini_bot

    pull_latest_from_github()
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")

    # Sync real Instagram profile & reels in background
    try:
        dashboard_app.fetch_real_instagram_data(force_refresh=True)
    except Exception:
        pass

    with open("data/schedule_config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if not cfg.get("enabled", True):
        return

    slots = sorted(cfg.get("times") or DEFAULT_SLOTS)
    completed_runs = cfg.get("completed_slots_log", {})
    missed_runs = cfg.get("missed_slots_log", {})
    pre_attempts = cfg.get("pre_slot_attempts", {}).get(today_str, {})
    done_today = completed_runs.get(today_str, [])
    missed_today = missed_runs.get(today_str, [])

    hist = dashboard_app.load_history()
    rollover_overdue_scheduled_reels(hist, slots, now_ist, today_str)

    # ==========================================================================
    # 1. POST DUE SCHEDULED REELS AT SLOT TIME (08:00, 14:00, 20:00)
    # ==========================================================================
    for idx, slot in enumerate(slots):
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

            if idx < len(slots) - 1:
                next_s = slots[idx + 1]
                dashboard_app.log_notification("slot_missed", f"Slot {slot} Skipped", f"Next target slot: {next_s} IST.", "warning")
            else:
                dashboard_app.log_notification("slot_missed", "Daily Cycle Concluded", "Moving to tomorrow's schedule.", "error")

    # ==========================================================================
    # 2. 02:00 AM NIGHTLY BATCH — STRICTLY ONE TRY AT 2:00 AM!
    # ==========================================================================
    ready_count = get_today_ready_reels_count(hist, today_str)
    if ready_count >= 3:
        return

    if now_ist.hour == 2 and cfg.get("nightly_2am_tried_date") != today_str:
        cfg["nightly_2am_tried_date"] = today_str
        with open("data/schedule_config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        try_building_missing_reels(3 - ready_count, today_str, cfg, "02:00 AM Daily Batch")
        return

    # ==========================================================================
    # 3. EXACT QUOTA REOPEN TIME TRIGGER (IF GEMINI GAVE REOPEN TIME)
    # ==========================================================================
    reopen_str = cfg.get("quota_reopen_time_str", "").strip()
    if reopen_str:
        try:
            # Parse time like "10:30 AM" or "14:00"
            for fmt in ("%I:%M %p", "%H:%M", "%I %p"):
                try:
                    t_parsed = datetime.strptime(reopen_str.upper(), fmt)
                    reopen_dt = now_ist.replace(hour=t_parsed.hour, minute=t_parsed.minute, second=0)
                    diff_reopen = (now_ist - reopen_dt).total_seconds() / 60.0
                    if 0 <= diff_reopen <= 20:
                        cfg["quota_reopen_time_str"] = ""
                        with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                            json.dump(cfg, f, indent=4)
                        try_building_missing_reels(3 - ready_count, today_str, cfg, f"Quota Reopen ({reopen_str})")
                        return
                    break
                except ValueError:
                    continue
        except Exception:
            pass

    # ==========================================================================
    # 4. PRE-SLOT 3-STAGE SNIPER: T-60m (1 Hr), T-30m (30 Min), T-5m (5 Min)!
    # ==========================================================================
    for slot in slots:
        if slot in done_today or slot in missed_today:
            continue
        slot_dt = datetime.strptime(f"{today_str} {slot}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        mins_before_slot = (slot_dt - now_ist).total_seconds() / 60.0
        slot_tries = pre_attempts.get(slot, [])

        stage_to_run = None
        if 48 <= mins_before_slot <= 66 and "T-60" not in slot_tries:
            stage_to_run = "T-60"
        elif 22 <= mins_before_slot <= 36 and "T-30" not in slot_tries:
            stage_to_run = "T-30"
        elif 2 <= mins_before_slot <= 12 and "T-5" not in slot_tries:
            stage_to_run = "T-5"

        if stage_to_run:
            slot_tries.append(stage_to_run)
            pre_attempts[slot] = slot_tries
            cfg.setdefault("pre_slot_attempts", {})[today_str] = pre_attempts
            with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)

            try_building_missing_reels(3 - ready_count, today_str, cfg, f"Pre-Slot {slot} ({stage_to_run})")
            return

def run_single_cloud_video_job():
    ensure_required_folders_and_files()
    pull_latest_from_github()
    event_name = os.environ.get("CLOUD_EVENT_NAME", "workflow_dispatch")
    action_type = os.environ.get("CLOUD_ACTION_TYPE", "generate_only")
    custom_topic = os.environ.get("CLOUD_CUSTOM_TOPIC", "").strip()
    today_str = datetime.now(IST).strftime("%Y-%m-%d")

    try:
        import dashboard_app
        if action_type == "sync_instagram":
            dashboard_app.fetch_real_instagram_data(force_refresh=True)
            return

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
        print(f"\n⚠️ [CLOUD WORKER NOTICE]: {err_msg}")
        gemini_bot.update_3d_telemetry(0, "Paused", err_msg[:140], "error", 0)
        sys.exit(0)

if __name__ == "__main__":
    if "--export-cookies" in sys.argv:
        export_local_chrome_cookies()
    elif "--sync-ig" in sys.argv:
        import dashboard_app
        print("📸 Syncing all 7 Real Instagram Reels & Profile from local machine...")
        data = dashboard_app.fetch_real_instagram_data(force_refresh=True)
        print(f"✅ Synced @{data.get('username')} | Followers: {data.get('followers')} | Reels Found: {len(data.get('posted_reels', []))}")
    else:
        run_single_cloud_video_job()