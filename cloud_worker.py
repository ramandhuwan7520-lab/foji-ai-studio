# -*- coding: utf-8 -*-
# pyright: reportOptionalMemberAccess=false, reportGeneralTypeIssues=false
import os
import sys
import json
import time
import subprocess
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_POST_SLOTS = ["06:00", "12:30", "18:00"]


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
                "gen_times": ["05:30", "12:00", "17:30"],
                "button_locked": True,
                "gen_tried_log": {},
                "completed_slots_log": {},
                "missed_slots_log": {}
            }, f, indent=4)


def run_autonomous_schedule_cycle():
    import dashboard_app

    pull_latest_from_github()
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")

    with open("data/schedule_config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if not cfg.get("enabled", True):
        return

    post_slots = sorted(cfg.get("times") or DEFAULT_POST_SLOTS)
    done_today = cfg.get("completed_slots_log", {}).get(today_str, [])
    gen_done_today = cfg.get("gen_tried_log", {}).get(today_str, [])

    hist = dashboard_app.load_history()
    deleted_ids = set(str(x) for x in hist.get("deleted_ids", []))

    ready_reels = [
        r for r in hist.get("history", [])
        if str(r.get("video_id", "")) not in deleted_ids
        and r.get("video_completed")
        and r.get("status") in ("scheduled", "pending_approval")
    ]

    for post_slot in post_slots:
        if post_slot in done_today:
            continue

        post_dt = datetime.strptime(f"{today_str} {post_slot}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        gen_dt = post_dt - timedelta(minutes=30)

        mins_since_gen = (now_ist - gen_dt).total_seconds() / 60.0
        mins_since_post = (now_ist - post_dt).total_seconds() / 60.0

        # PHASE A: 30 MINUTES BEFORE POST TIME (05:30, 12:00, 17:30) -> GENERATE 1 FRESH VIDEO!
        if -5 <= mins_since_gen <= 22 and post_slot not in gen_done_today:
            gen_done_today.append(post_slot)
            cfg.setdefault("gen_tried_log", {})[today_str] = gen_done_today
            with open("data/schedule_config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            dashboard_app.push_file_to_github_api("data/schedule_config.json", f"Mark gen slot {post_slot}", blocking=True)

            print(f"🎬 [Scheduled Generation] Building fresh video for {post_slot} IST slot...")
            item = dashboard_app.generate_single_reel_package(send_for_approval=True, batch_date=today_str)
            if item:
                dashboard_app.assign_reel_to_specific_slot(item["video_id"], post_slot)
            return

        # PHASE B: AT POST TIME (06:00, 12:30, 18:00) -> AUTO-POST TO INSTAGRAM + FACEBOOK!
        if -3 <= mins_since_post <= 40:
            if not ready_reels:
                print(f"⚡ [Instant Catch-Up] Generating & Posting immediately for {post_slot} IST...")
                item = dashboard_app.generate_single_reel_package(send_for_approval=True, batch_date=today_str)
                if item:
                    ready_reels = [item]

            if ready_reels:
                target = sorted(ready_reels, key=lambda x: x.get("video_id", 0))[0]
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
    print("🎬 Starting AutoReels 3D Google Flow Worker...")
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