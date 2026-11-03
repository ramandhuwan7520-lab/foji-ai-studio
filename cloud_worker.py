# -*- coding: utf-8 -*-
# pyright: reportOptionalMemberAccess=false, reportGeneralTypeIssues=false
import os
import sys
import json
import time
import subprocess
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_POST_SLOTS = ["06:30", "12:30", "18:30"]
NIGHT_BATCH_TIME = "02:30"


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
            json.dump({
                "generated_count": 0,
                "track_parts": {},
                "recent_tracks": [],
                "failed_dialogues": [],
                "deleted_ids": [],
                "history": []
            }, f, indent=4)

    if not os.path.exists("data/schedule_config.json"):
        with open("data/schedule_config.json", "w", encoding="utf-8") as f:
            json.dump({
                "enabled": True,
                "times": DEFAULT_POST_SLOTS,
                "night_batch_time": NIGHT_BATCH_TIME,
                "fallback_gen_times": ["06:00", "12:00", "18:00"],
                "button_locked": True,
                "night_batch_log": {},
                "gen_tried_log": {},
                "completed_slots_log": {},
                "missed_slots_log": {}
            }, f, indent=4)


def get_ready_reels_for_today(hist):
    deleted_ids = set(str(x) for x in hist.get("deleted_ids", []))
    return [
        r for r in hist.get("history", [])
        if str(r.get("video_id", "")) not in deleted_ids
        and r.get("video_completed")
        and r.get("status") in ("scheduled", "pending_approval")
    ]


def run_autonomous_schedule_cycle():
    """
    MASTER SAAS SCHEDULE ENGINE (IST):
      1. 02:30 AM Batch Mode: Generates up to 3 videos one-by-one for ['06:30', '12:30', '18:30'].
         If Gemini daily limit is hit, stops immediately and notifies user.
      2. 30-Min Pre-Slot Fallback (06:00, 12:00, 18:00): If the upcoming slot STILL doesn't have
         a generated video (because 02:30 AM had a limit or didn't finish), generates ONLY 1 video
         specifically for that upcoming slot!
      3. Slot Publish Time (06:30, 12:30, 18:30): Publishes the slot's video to Instagram + Facebook!
    """
    import dashboard_app
    import gemini_bot

    pull_latest_from_github()
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")

    with open("data/schedule_config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if not cfg.get("enabled", True):
        return

    post_slots = sorted(cfg.get("times") or DEFAULT_POST_SLOTS)
    done_today = cfg.get("completed_slots_log", {}).get(today_str, [])
    gen_tried_today = cfg.get("gen_tried_log", {}).get(today_str, [])
    night_batch_done = cfg.get("night_batch_log", {}).get(today_str, False)

    # ==========================================================================
    # PHASE 1: 02:30 AM IST NIGHT BATCH -> GENERATE ALL 3 VIDEOS ONE-BY-ONE!
    # ==========================================================================
    night_dt = datetime.strptime(f"{today_str} {NIGHT_BATCH_TIME}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    mins_since_night = (now_ist - night_dt).total_seconds() / 60.0

    if -5 <= mins_since_night <= 55 and not night_batch_done:
        cfg.setdefault("night_batch_log", {})[today_str] = True
        with open("data/schedule_config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
        dashboard_app.push_file_to_github_api("data/schedule_config.json", f"Start 2:30 AM batch {today_str}", blocking=True)

        print("🌙 [02:30 AM Batch Mode] Checking slots to generate up to 3 videos one-by-one...")
        for slot_str in post_slots:
            if slot_str in done_today:
                continue
            hist = dashboard_app.load_history()
            ready_list = get_ready_reels_for_today(hist)
            already_has_for_slot = any(r.get("scheduled_slot") == slot_str for r in ready_list)
            if already_has_for_slot:
                print(f"   ✅ Slot {slot_str} already has a scheduled video.")
                continue

            print(f"🎬 [02:30 AM Batch] Generating video for slot {slot_str} IST...")
            try:
                item = dashboard_app.generate_single_reel_package(send_for_approval=True, batch_date=today_str)
                if item:
                    dashboard_app.assign_reel_to_specific_slot(item["video_id"], slot_str)
                    print(f"   ✅ Assigned Reel #{item['video_id']} to {slot_str} IST!")
                    time.sleep(5)
            except gemini_bot.GeminiLimitReachedError as lim_err:
                print(f"🛑 [02:30 AM Batch Stopped] Gemini Limit Reached: {lim_err}")
                print("   👉 Remaining slots will automatically retry 30 minutes before their schedule time!")
                break
            except Exception as e:
                print(f"⚠️ [02:30 AM Batch Error on {slot_str}]: {e}")
                continue
        return

    # ==========================================================================
    # PHASE 2 & 3: CHECK EACH SLOT (06:30, 12:30, 18:30)
    #   - 30 mins before (06:00, 12:00, 18:00): Generate ONLY 1 video if missing!
    #   - At slot time (06:30, 12:30, 18:30): Auto-Post to Instagram + Facebook!
    # ==========================================================================
    for post_slot in post_slots:
        if post_slot in done_today:
            continue

        post_dt = datetime.strptime(f"{today_str} {post_slot}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        fallback_gen_dt = post_dt - timedelta(minutes=30)

        mins_since_fallback_gen = (now_ist - fallback_gen_dt).total_seconds() / 60.0
        mins_since_post = (now_ist - post_dt).total_seconds() / 60.0

        hist = dashboard_app.load_history()
        ready_reels = get_ready_reels_for_today(hist)
        slot_reel = next((r for r in ready_reels if r.get("scheduled_slot") == post_slot), None)

        # PHASE 2: 30 MINUTES BEFORE SLOT (06:00, 12:00, 18:00) -> FALLBACK SINGLE VIDEO GENERATION
        if -5 <= mins_since_fallback_gen <= 24 and post_slot not in gen_tried_today:
            gen_tried_today.append(post_slot)
            cfg.setdefault("gen_tried_log", {})[today_str] = gen_tried_today
            with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            dashboard_app.push_file_to_github_api("data/schedule_config.json", f"Fallback check {post_slot}", blocking=True)

            if slot_reel or len(ready_reels) > 0:
                print(f"✅ [30-Min Check for {post_slot}] Video is already generated & ready! Skipping generation.")
                if not slot_reel and ready_reels:
                    dashboard_app.assign_reel_to_specific_slot(ready_reels[0]["video_id"], post_slot)
                return

            print(f"⚡ [30-Min Fallback Mode] 2:30 AM video missing for {post_slot} IST! Generating 1 video now...")
            item = dashboard_app.generate_single_reel_package(send_for_approval=True, batch_date=today_str)
            if item:
                dashboard_app.assign_reel_to_specific_slot(item["video_id"], post_slot)
            return

        # PHASE 3: AT POST TIME (06:30, 12:30, 18:30) -> UPLOAD TO INSTAGRAM + FACEBOOK!
        if -3 <= mins_since_post <= 45:
            target = slot_reel or (sorted(ready_reels, key=lambda x: x.get("video_id", 0))[0] if ready_reels else None)

            if not target:
                print(f"⚡ [Post-Time Catch-Up for {post_slot}] No ready reel found, generating 1 reel right now...")
                target = dashboard_app.generate_single_reel_package(send_for_approval=True, batch_date=today_str)

            if target:
                reel_id = target.get("video_id") or target.get("id")
                ok, _ = dashboard_app.publish_reel_item_to_instagram(reel_id)
                if ok:
                    done_today.append(post_slot)
                    cfg.setdefault("completed_slots_log", {})[today_str] = done_today
                    with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                        json.dump(cfg, f, indent=4)
                    dashboard_app.push_file_to_github_api("data/schedule_config.json", f"Completed slot {post_slot}", blocking=True)
                    return


def run_single_cloud_video_job():
    print("🎬 Starting AutoReels 3D Google Gemini SaaS Worker...")
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
        run_single_cloud_video_job()
    finally:
        os._exit(0)