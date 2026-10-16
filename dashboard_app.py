import os
import re
import json
import time
import glob
import socket
import random
import threading
import subprocess
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, jsonify, send_from_directory, Response
from dotenv import load_dotenv, set_key

load_dotenv()

app = Flask(__name__)

HISTORY_FILE = "data/history.json"
SCHEDULE_CONFIG_FILE = "data/schedule_config.json"
INSTA_CACHE_FILE = "data/insta_live_posts.json"
ENV_FILE = ".env"

RUNTIME_STATE = {
    "is_running_pipeline": False,
    "stage_index": 0,
    "stage_percent": 0,
    "current_step": "STANDBY • WAITING FOR SCHEDULE OR USER COMMAND",
    "active_episode_title": "",
    "started_at_ts": 0,
    "last_error": None,
    "public_tunnel_url": None,
    "self_heal_log": ["💎 Play-Store Branded 3D OS Ready (Auto-Reload Active • No Boot Auto-Gen)."],
    "internet_online": True,
    "last_pre_gen_slot": ""
}

def log_heal(msg):
    ts = datetime.now().strftime("%I:%M:%S %p")
    RUNTIME_STATE["self_heal_log"].insert(0, f"[{ts}] {msg}")
    RUNTIME_STATE["self_heal_log"] = RUNTIME_STATE["self_heal_log"][:40]

def check_internet():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=2.0)
        RUNTIME_STATE["internet_online"] = True
        return True
    except OSError:
        RUNTIME_STATE["internet_online"] = False
        return False

def get_all_local_ips():
    """Finds all Wi-Fi / Hotspot IPv4 addresses of your laptop so Mobile always connects!"""
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips if ips else ["127.0.0.1"]

def auto_open_windows_firewall_port():
    """Automatically opens Port 5000 in Windows Firewall so Mobile Phone can connect over Wi-Fi/Hotspot."""
    if os.name == "nt":
        try:
            subprocess.run(
                'netsh advfirewall firewall add rule name="Foji3DApp5000" dir=in action=allow protocol=TCP localport=5000',
                shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except Exception:
            pass

def start_working_mobile_tunnel():
    """
    Starts a zero-key public HTTPS tunnel using Pinggy (more reliable than localhost.run on mobile)
    so you can open the app on your phone from anywhere!
    """
    def _tunnel_worker():
        cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ServerAliveInterval=30",
            "-p", "443", "-R0:127.0.0.1:5000", "a.pinggy.io"
        ]
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                 stdin=subprocess.PIPE, text=True,
                creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            )
            for line in proc.stdout:
                m = re.search(r"(https://[a-zA-Z0-9.-]+\.pinggy\.link|https://[a-zA-Z0-9.-]+\.a\.free\.pinggy\.link)", line)
                if m:
                    RUNTIME_STATE["public_tunnel_url"] = m.group(1)
                    log_heal(f"🌐 Global Mobile App Link Ready: {RUNTIME_STATE['public_tunnel_url']}")
                    print(f"\n🌍 [GLOBAL MOBILE LINK]: {RUNTIME_STATE['public_tunnel_url']}\n")
                    break
        except Exception:
            pass

    threading.Thread(target=_tunnel_worker, daemon=True).start()

def load_schedule_config():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(SCHEDULE_CONFIG_FILE):
        default_cfg = {
            "enabled": True,
            "lead_minutes": 15,
            "slots": ["11:00", "16:00", "20:30"]
        }
        with open(SCHEDULE_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_cfg, f, indent=4)
        return default_cfg
    with open(SCHEDULE_CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_schedule_config(cfg):
    with open(SCHEDULE_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)

def load_strict_clean_history():
    """
    STRICT CLEANUP:
    Only returns history items whose actual MP4 file EXISTS in output/final_reels or output/raw_videos!
    If a video was deleted, its caption and card are 100% gone forever!
    """
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(HISTORY_FILE):
        return {"generated_count": 0, "recent_tracks": [], "history": []}

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    clean_items = []
    recent_tracks = []
    changed = False

    for idx, item in enumerate(data.get("history", []), start=1):
        vid_id = int(item.get("video_id", idx))
        item["video_id"] = vid_id
        final_p = os.path.abspath(f"output/final_reels/final_reel_{vid_id}.mp4")
        raw_p = os.path.abspath(f"output/raw_videos/raw_video_{vid_id}.mp4")

        # If explicitly deleted OR neither video file exists on disk -> REMOVE IT COMPLETELY!
        if item.get("deleted") is True or (not os.path.exists(final_p) and not os.path.exists(raw_p)):
            changed = True
            continue

        clean_items.append(item)
        t_id = item.get("track_id") or item.get("emotion_id")
        if t_id:
            recent_tracks.append(t_id)

    cleaned = {
        "generated_count": max([i.get("video_id", 0) for i in clean_items], default=0),
        "recent_tracks": recent_tracks,
        "history": clean_items
    }
    if changed:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=4, ensure_ascii=False)
    return cleaned

def save_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_insta_live_posts():
    if os.path.exists(INSTA_CACHE_FILE):
        try:
            with open(INSTA_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def sync_instagram_insights():
    """
    100% ACCURATE MATCHING + INSTAGRAM EDITS ANALYTICS:
    Matches each local reel to its exact `insta_media_pk` (or exact caption title) so one video's views
    NEVER appear on another video! Also fetches live viewer comments so you can read & reply from the App!
    """
    if not check_internet():
        return False, "📡 Offline Mode: Showing cached analytics."

    load_dotenv(override=True)
    ig_user = os.getenv("INSTAGRAM_USERNAME")
    ig_pass = os.getenv("INSTAGRAM_PASSWORD")

    if not ig_user or not ig_pass or "your_" in ig_user.lower():
        return False, "⚠️ Pehle Setup tab mein Instagram Username & Password save karo!"

    try:
        from instagrapi import Client
        cl = Client()
        session_file = "data/insta_session.json"
        if os.path.exists(session_file):
            try:
                cl.load_settings(session_file)
            except Exception:
                pass
        cl.login(ig_user, ig_pass)
        cl.dump_settings(session_file)

        user_info = cl.user_info_by_username(ig_user)
        followers_count = getattr(user_info, "follower_count", 0)
        medias = cl.user_clips(user_info.pk, amount=30)

        history_data = load_strict_clean_history()
        live_insta_list = []
        media_by_pk = {}

        for m in medias:
            pk_str = str(m.pk)
            views = int(getattr(m, "play_count", 0) or getattr(m, "view_count", 0) or 0)
            likes = int(getattr(m, "like_count", 0) or 0)
            comments_cnt = int(getattr(m, "comment_count", 0) or 0)
            shares = int(getattr(m, "reshare_count", 0) or 0)
            caption_txt = (getattr(m, "caption_text", "") or "").strip()
            code = getattr(m, "code", "")
            taken_at = getattr(m, "taken_at", None)
            date_str = taken_at.strftime("%d %b %Y, %I:%M %p") if taken_at else "Live Reel"

            # Fetch top 5 recent comments for Instagram Edits style interaction
            recent_comments = []
            if comments_cnt > 0:
                try:
                    raw_comms = cl.media_comments(m.pk, amount=5)
                    for c in raw_comms:
                        recent_comments.append({
                            "pk": str(c.pk),
                            "user": getattr(c.user, "username", "viewer"),
                            "text": getattr(c, "text", "")
                        })
                except Exception:
                    pass

            eng_rate = round(((likes + comments_cnt + shares) / max(views, 1)) * 100, 1) if views > 0 else 0.0

            post_obj = {
                "pk": pk_str,
                "code": code,
                "url": f"https://www.instagram.com/reel/{code}/" if code else "",
                "caption": caption_txt[:140],
                "full_caption": caption_txt,
                "views": views,
                "likes": likes,
                "comments": comments_cnt,
                "shares": shares,
                "engagement_rate": eng_rate,
                "recent_comments": recent_comments,
                "followers": followers_count,
                "date": date_str,
                "is_viral": views >= 1000 or likes >= 100
            }
            live_insta_list.append(post_obj)
            media_by_pk[pk_str] = post_obj

        # STRICT 1-TO-1 MATCHING FOR STUDIO REELS (Never mix up views between videos!)
        for item in history_data.get("history", []):
            saved_pk = str(item.get("insta_media_pk", ""))
            matched = None

            # 1. Match by exact saved Instagram Media PK
            if saved_pk and saved_pk in media_by_pk:
                matched = media_by_pk[saved_pk]
            # 2. Match ONLY if the reel is marked POSTED and its unique title/dialogue is inside the Instagram caption
            elif "POSTED" in (item.get("post_status") or ""):
                title_key = (item.get("emotion_name") or "").lower().strip()
                for p_obj in live_insta_list:
                    if title_key and title_key in p_obj["full_caption"].lower():
                        matched = p_obj
                        item["insta_media_pk"] = p_obj["pk"]
                        break

            if matched:
                item["views_count"] = matched["views"]
                item["likes_count"] = matched["likes"]
                item["comments_count"] = matched["comments"]
                item["shares_count"] = matched["shares"]
                item["insta_url"] = matched["url"]
                item["recent_comments"] = matched["recent_comments"]
            elif "POSTED" not in (item.get("post_status") or ""):
                # Unposted videos MUST strictly show 0 views!
                item["views_count"] = 0
                item["likes_count"] = 0
                item["comments_count"] = 0
                item["shares_count"] = 0

        save_history(history_data)
        with open(INSTA_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(live_insta_list, f, indent=4, ensure_ascii=False)

        log_heal(f"📊 Synced {len(live_insta_list)} Live Instagram Reels (2-Min Auto-Telemetry Active).")
        return True, f"✅ Live Synced {len(live_insta_list)} Reels & Comments from @{ig_user}!"
    except Exception as e:
        return False, f"❌ Sync Error: {e}"

def resume_existing_raw_video_pipeline():
    if RUNTIME_STATE["is_running_pipeline"]:
        return False, "Pipeline abhi busy hai!"

    RUNTIME_STATE["is_running_pipeline"] = True
    RUNTIME_STATE["started_at_ts"] = time.time()
    RUNTIME_STATE["last_error"] = None
    RUNTIME_STATE["stage_index"] = 3
    RUNTIME_STATE["stage_percent"] = 80
    RUNTIME_STATE["current_step"] = "⚡ Mastering Existing Raw Video..."

    try:
        import studio
        vid_num, raw_path = studio.find_unprocessed_raw_video()
        if not raw_path:
            return False, "Koi unprocessed raw video nahi mili!"

        studio.build_final_reel(video_num_override=vid_num)
        RUNTIME_STATE["stage_index"] = 4
        RUNTIME_STATE["stage_percent"] = 100
        RUNTIME_STATE["current_step"] = f"✅ Reel #{vid_num} Ready for Approval!"
        log_heal(f"⚡ Recovered & Mastered Raw Video #{vid_num}!")

        if check_internet():
            import telegram_bot
            threading.Thread(target=telegram_bot.send_reel_for_approval, daemon=True).start()

        return True, f"🎉 Video #{vid_num} Ready ho gayi hai!"
    except Exception as e:
        RUNTIME_STATE["last_error"] = str(e)
        return False, f"Error: {e}"
    finally:
        RUNTIME_STATE["is_running_pipeline"] = False

def run_full_pipeline_background(
    target_slot_dt=None,
    force_track_id=None,
    force_part_number=None,
    is_regenerate=False,
    old_rejected_line=None,
    reuse_video_id=None
):
    """
    Runs ONLY when triggered by Schedule (15 mins before slot) OR User click!
    Uses Pre-Buffered True Gemini 3D Video if offline so quality is ALWAYS 100% Genuine Gemini 3D!
    """
    if RUNTIME_STATE["is_running_pipeline"]:
        return

    RUNTIME_STATE["is_running_pipeline"] = True
    RUNTIME_STATE["started_at_ts"] = time.time()
    RUNTIME_STATE["last_error"] = None
    RUNTIME_STATE["stage_index"] = 1
    RUNTIME_STATE["stage_percent"] = 15

    try:
        os.makedirs("output/buffer_3d_vault", exist_ok=True)
        RUNTIME_STATE["current_step"] = "🧠 [STAGE 1/4] AI Director Writing Episodic Script..."

        import brain
        pkg = brain.generate_video_package(
            force_track_id=force_track_id,
            force_part_number=force_part_number,
            is_regenerate=is_regenerate,
            old_rejected_line=old_rejected_line,
            reuse_video_id=reuse_video_id
        )
        ep_name = pkg.get("emotion_name", "New Episode")
        vid_id = pkg.get("video_id")
        RUNTIME_STATE["active_episode_title"] = ep_name

        # STAGE 2: True Gemini 3D Video Render (Or Pull from True Gemini 3D Offline Buffer Vault!)
        RUNTIME_STATE["stage_index"] = 2
        RUNTIME_STATE["stage_percent"] = 48
        raw_out = os.path.abspath(f"output/raw_videos/raw_video_{vid_id}.mp4")

        if check_internet():
            RUNTIME_STATE["current_step"] = f"🎬 [STAGE 2/4] Gemini Flash-Lite Rendering 3D Pixar Video: {ep_name}..."
            import gemini_bot
            gemini_bot.generate_video_in_gemini()
        else:
            # Check if we have a pre-rendered TRUE Gemini 3D video in the Buffer Vault!
            buffered_3d = sorted(glob.glob(os.path.abspath("output/buffer_3d_vault/*.mp4")))
            if buffered_3d:
                import shutil
                shutil.move(buffered_3d[0], raw_out)
                log_heal(f"💎 Internet Offline -> Pulled 100% Genuine Pre-Rendered Gemini 3D Video from Buffer Vault!")
            else:
                RUNTIME_STATE["current_step"] = "📡 Waiting for Internet so Genuine Gemini 3D Video can render without quality drop..."
                log_heal("📡 Internet Offline: Waiting for connection to render 100% Genuine Gemini 3D Video...")
                while not check_internet():
                    time.sleep(5)
                import gemini_bot
                gemini_bot.generate_video_in_gemini()

        # STAGE 3: Studio Mastering
        RUNTIME_STATE["stage_index"] = 3
        RUNTIME_STATE["stage_percent"] = 85
        RUNTIME_STATE["current_step"] = f"🎵 [STAGE 3/4] Studio HD Mastering: {ep_name}..."
        import studio
        studio.build_final_reel(video_num_override=vid_id)

        # STAGE 4: Ready for Approval
        RUNTIME_STATE["stage_index"] = 4
        RUNTIME_STATE["stage_percent"] = 100
        slot_str_display = None

        hist = load_strict_clean_history()
        for h_item in hist.get("history", []):
            if h_item.get("video_id") == vid_id:
                h_item["video_completed"] = True
                if target_slot_dt:
                    h_item["target_schedule_slot"] = target_slot_dt.strftime("%Y-%m-%d %H:%M:%S")
                    slot_str_display = target_slot_dt.strftime("%I:%M %p")
                h_item["post_status"] = "READY_FOR_APPROVAL"
                break
        save_history(hist)

        RUNTIME_STATE["current_step"] = f"✅ [STAGE 4/4] Reel Ready for Approval: {ep_name}!"
        log_heal(f"🎉 Completed {ep_name} (Video #{vid_id})! Sent for Approval.")

        if check_internet():
            import telegram_bot
            threading.Thread(target=telegram_bot.send_reel_for_approval, args=(slot_str_display,), daemon=True).start()

    except Exception as e:
        err_str = str(e)
        RUNTIME_STATE["last_error"] = err_str
        RUNTIME_STATE["current_step"] = "⚠️ Alert / Quota Notice Updated"
        log_heal(f"⚠️ Notice: {err_str[:200]}")
    finally:
        time.sleep(2)
        RUNTIME_STATE["is_running_pipeline"] = False

def master_24_7_autonomous_daemon():
    """
    1. Auto-Syncs Instagram Views, Likes & Comments every 2 MINUTES (120s)!
    2. Auto-Generates Reels 15 mins before scheduled slots (with Auto-Retry & Chat Recovery!).
    3. Auto-Posts Scheduled Reels on time!
    """
    last_insta_sync = 0
    while True:
        time.sleep(15)
        is_online = check_internet()
        try:
            # A. AUTO-REFRESH INSTAGRAM INSIGHTS EVERY 2 MINUTES (120 SECONDS)
            if is_online and (time.time() - last_insta_sync >= 120):
                last_insta_sync = time.time()
                threading.Thread(target=sync_instagram_insights, daemon=True).start()

            cfg = load_schedule_config()
            now = datetime.now()

            # B. 15-Minute Advance Schedule Trigger
            if cfg.get("enabled", True) and not RUNTIME_STATE["is_running_pipeline"]:
                lead_mins = int(cfg.get("lead_minutes", 15))
                for t_str in cfg.get("slots", ["11:00", "16:00", "20:30"]):
                    try:
                        hh, mm = map(int, t_str.split(":"))
                        slot_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                        pre_gen_dt = slot_dt - timedelta(minutes=lead_mins)
                        slot_key = slot_dt.strftime("%Y-%m-%d_%H:%M")

                        if pre_gen_dt <= now < slot_dt and RUNTIME_STATE["last_pre_gen_slot"] != slot_key:
                            RUNTIME_STATE["last_pre_gen_slot"] = slot_key
                            log_heal(f"⏰ Schedule Trigger ({t_str}): Creating Reel {lead_mins}m in advance...")
                            threading.Thread(target=run_full_pipeline_background, args=(slot_dt,), daemon=True).start()
                            break
                    except Exception:
                        pass

            # C. Execute Approved Scheduled Reels
            history_data = load_strict_clean_history()
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            changed = False

            for item in history_data.get("history", []):
                status = item.get("post_status", "")
                sched_time = item.get("scheduled_time", "")

                if status == "SCHEDULED" and sched_time and now_str >= sched_time and is_online:
                    vid_num = item.get("video_id", 1)
                    reel_path = os.path.abspath(f"output/final_reels/final_reel_{vid_num}.mp4")
                    caption = f"{item.get('insta_title', '')}\n\n{item.get('insta_caption', '')}\n\n{item.get('insta_hashtags', '')}"
                    if os.path.exists(reel_path):
                        import telegram_bot
                        ok, msg, media_pk, media_code = telegram_bot.post_reel_to_instagram(reel_path, caption)
                        if ok:
                            item["post_status"] = "POSTED LIVE ✅"
                            item["insta_media_pk"] = media_pk
                            item["insta_url"] = f"https://www.instagram.com/reel/{media_code}/" if media_code else ""
                        else:
                            item["post_status"] = "POST_ERROR"
                        log_heal(f"🚀 Scheduled Reel #{vid_num} Posted: {msg[:80]}")
                        changed = True

            if changed:
                save_history(history_data)
        except Exception:
            pass

# Start background daemon only once (prevents duplicate threads during Flask auto-reload)
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
    auto_open_windows_firewall_port()
    start_working_mobile_tunnel()
    threading.Thread(target=master_24_7_autonomous_daemon, daemon=True).start()

PLAYSTORE_BRANDED_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#03040a">
    <link rel="manifest" href="/manifest.json">
    <title>FOJI 3D EDITS OS</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800;900&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        body {
            margin: 0; padding: 0 0 120px 0;
            background: #03040a;
            background-image:
                radial-gradient(circle at 12% 8%, rgba(245, 158, 11, 0.16) 0%, transparent 38%),
                radial-gradient(circle at 88% 15%, rgba(99, 102, 241, 0.22) 0%, transparent 42%);
            color: #f8fafc;
            font-family: 'Outfit', system-ui, sans-serif;
            overflow-x: hidden;
        }
        .num-font { font-family: 'Space Grotesk', monospace; }
        .app-shell { max-width: 520px; margin: 0 auto; padding: 12px 14px; }

        /* Premium 3D Glass Toast & Modal System (No Ugly Browser Alerts!) */
        #lux-modal-backdrop {
            position: fixed; inset: 0; z-index: 9999;
            background: rgba(2, 4, 12, 0.82); backdrop-filter: blur(16px);
            display: none; align-items: center; justify-content: center; padding: 20px;
        }
        .lux-modal-card {
            width: 100%; max-width: 360px;
            background: linear-gradient(155deg, rgba(22, 31, 62, 0.96), rgba(8, 11, 24, 0.98));
            border: 1px solid rgba(245, 176, 65, 0.45);
            border-radius: 28px; padding: 24px 20px; text-align: center;
            box-shadow: 0 25px 60px rgba(0,0,0,0.95), 0 0 35px rgba(245, 158, 11, 0.2);
            animation: popIn 0.28s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        @keyframes popIn { from { transform: scale(0.85); opacity: 0; } to { transform: scale(1); opacity: 1; } }
        .modal-spinner {
            width: 54px; height: 54px; margin: 0 auto 14px auto;
            border-radius: 50%; border: 4px solid rgba(255,255,255,0.1);
            border-top-color: #f59e0b; border-right-color: #ec4899;
            animation: spin 1s linear infinite;
        }
        @keyframes spin { 100% { transform: rotate(360deg); } }

        .top-bar {
            position: sticky; top: 8px; z-index: 100;
            background: rgba(12, 17, 36, 0.92); backdrop-filter: blur(24px);
            border: 1px solid rgba(245, 176, 65, 0.35); border-radius: 24px;
            padding: 12px 16px; margin-bottom: 16px;
            display: flex; align-items: center; justify-content: space-between;
            box-shadow: 0 15px 35px rgba(0,0,0,0.85);
        }
        .logo-box {
            width: 44px; height: 44px; border-radius: 14px;
            background: linear-gradient(135deg, #f59e0b, #ec4899, #6366f1);
            display: flex; align-items: center; justify-content: center; font-size: 22px;
        }
        .brand-title {
            font-size: 17px; font-weight: 900; letter-spacing: 0.5px;
            background: linear-gradient(90deg, #fff, #fde68a, #38bdf8);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .lux-card {
            background: linear-gradient(155deg, rgba(20, 28, 56, 0.86) 0%, rgba(8, 11, 24, 0.96) 100%);
            border: 1px solid rgba(255, 255, 255, 0.11); border-radius: 28px;
            padding: 18px; margin-bottom: 18px;
            box-shadow: 0 22px 45px -12px rgba(0,0,0,0.9); position: relative; overflow: hidden;
        }
        .lux-card.viral-celebration {
            border: 2px solid #fbbf24;
            box-shadow: 0 0 35px rgba(245, 158, 11, 0.35);
        }
        .viral-crown-banner {
            background: linear-gradient(90deg, #b45309, #fbbf24, #fef08a, #fbbf24, #b45309);
            color: #000; font-weight: 900; font-size: 11px; text-align: center;
            padding: 6px; border-radius: 12px; margin-bottom: 12px; letter-spacing: 0.6px;
        }
        .phone-reel-frame {
            position: relative; width: 100%; max-width: 300px; margin: 14px auto;
            border-radius: 34px; padding: 8px;
            background: linear-gradient(145deg, #334155, #0f172a, #fbbf24);
            box-shadow: 0 20px 50px rgba(0,0,0,0.95);
        }
        .phone-notch {
            position: absolute; top: 15px; left: 50%; transform: translateX(-50%);
            width: 72px; height: 16px; background: #000; border-radius: 99px; z-index: 10;
        }
        .phone-screen {
            position: relative; border-radius: 26px; overflow: hidden;
            background: #000; aspect-ratio: 9 / 16;
        }
        .phone-screen video { width: 100%; height: 100%; object-fit: cover; display: block; }
        .reel-Watermark {
            position: absolute; top: 16px; right: 12px; z-index: 8;
            background: rgba(0,0,0,0.65); border: 1px solid rgba(245, 176, 65, 0.5);
            color: #fde68a; font-size: 9px; font-weight: 900; padding: 4px 8px; border-radius: 99px;
        }
        .reel-floating-stats {
            position: absolute; right: 10px; bottom: 58px; z-index: 8;
            display: flex; flex-direction: column; gap: 8px; pointer-events: none;
        }
        .float-stat-pill {
            background: rgba(0, 0, 0, 0.75); border: 1px solid rgba(255,255,255,0.2);
            border-radius: 14px; padding: 5px 8px; text-align: center; font-size: 10px; font-weight: 800;
        }
        .btn {
            width: 100%; border: none; cursor: pointer; padding: 13px 16px;
            border-radius: 16px; font-weight: 800; font-size: 13px; color: #fff;
            display: flex; align-items: center; justify-content: center; gap: 8px;
            font-family: 'Outfit', sans-serif; transition: all 0.2s ease;
        }
        .btn:active { transform: scale(0.97); }
        .btn:disabled, .btn-disabled {
            background: rgba(255,255,255,0.06) !important;
            color: #64748b !important; border: 1px solid rgba(255,255,255,0.08) !important;
            box-shadow: none !important; cursor: not-allowed !important; transform: none !important;
        }
        .btn-cyber { background: linear-gradient(135deg, #6366f1, #a855f7, #ec4899); box-shadow: 0 8px 25px rgba(168,85,247,0.45); }
        .btn-gold { background: linear-gradient(135deg, #f59e0b, #fbbf24); color: #000; box-shadow: 0 8px 25px rgba(245,158,11,0.45); }
        .btn-emerald { background: linear-gradient(135deg, #10b981, #059669); }
        .btn-glass { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.16); color: #e2e8f0; }
        .btn-danger { background: rgba(239,68,68,0.2); border: 1px solid rgba(239,68,68,0.5); color: #fca5a5; }
        .grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
        .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
        .stat-box {
            background: rgba(6, 9, 20, 0.9); border: 1px solid rgba(255,255,255,0.09);
            border-radius: 16px; padding: 10px 4px; text-align: center;
        }
        .stat-num { font-size: 18px; font-weight: 900; margin-top: 3px; }
        .input-lux {
            width: 100%; background: #060914; border: 1px solid rgba(255,255,255,0.16);
            color: #fff; padding: 11px 14px; border-radius: 14px; font-size: 13px; font-weight: 600;
            font-family: 'Outfit', sans-serif;
        }
        .step-pill {
            background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1);
            border-radius: 14px; padding: 9px 4px; text-align: center; font-size: 10px; font-weight: 800; color: #94a3b8;
        }
        .step-pill.active { border-color: #00f2fe; background: rgba(0,242,254,0.18); color: #fff; box-shadow: 0 0 16px rgba(0,242,254,0.4); }
        .step-pill.done { border-color: #10b981; background: rgba(16,185,129,0.2); color: #6ee7b7; }
        .bottom-dock {
            position: fixed; bottom: 12px; left: 50%; transform: translateX(-50%);
            width: calc(100% - 24px); max-width: 460px; z-index: 200;
            background: rgba(11, 16, 34, 0.95); backdrop-filter: blur(24px);
            border: 1px solid rgba(255,255,255,0.18); border-radius: 26px;
            padding: 8px 12px; display: flex; justify-content: space-around;
            box-shadow: 0 20px 50px rgba(0,0,0,0.95);
        }
        .dock-item {
            background: none; border: none; color: #94a3b8; font-size: 10px; font-weight: 800;
            display: flex; flex-direction: column; align-items: center; gap: 2px;
            padding: 6px 12px; border-radius: 14px; cursor: pointer; font-family: 'Outfit', sans-serif;
        }
        .dock-item.active { color: #fff; background: rgba(255,255,255,0.12); }
        .tab-pane { display: none; }
        .tab-pane.active { display: block; }
    </style>
</head>
<body>

    <!-- PREMIUM 3D MODAL / PROGRESS POPUP (REPLACES ALL UGLY BROWSER ALERTS!) -->
    <div id="lux-modal-backdrop">
        <div class="lux-modal-card">
            <div id="modal-spinner-el" class="modal-spinner" style="display:none;"></div>
            <div id="modal-icon-el" style="font-size:38px; margin-bottom:10px;">💎</div>
            <h3 id="modal-title-el" style="margin:0 0 8px 0; font-size:18px; font-weight:900; color:#fff;">Processing...</h3>
            <p id="modal-desc-el" style="margin:0 0 18px 0; font-size:13px; color:#cbd5e1; line-height:1.45;"></p>
            <div id="modal-btn-row" class="grid-2" style="display:none;">
                <button id="modal-cancel-btn" class="btn btn-glass" style="padding:11px;">Cancel</button>
                <button id="modal-confirm-btn" class="btn btn-gold" style="padding:11px;">Confirm</button>
            </div>
            <button id="modal-ok-btn" onclick="closeLuxModal()" class="btn btn-cyber" style="padding:11px; display:none;">Got It ✨</button>
        </div>
    </div>

    <div class="app-shell">

        <!-- TOP HEADER -->
        <div class="top-bar">
            <div style="display:flex; align-items:center; gap:10px;">
                <div class="logo-box">🪖</div>
                <div>
                    <div class="brand-title">FOJI 3D EDITS OS</div>
                    <div style="font-size:10px; font-weight:700; color:#10b981;">
                        ● Auto-Refresh: Every 2 Mins • Next Slot Armed
                    </div>
                </div>
            </div>
            <button onclick="liveInstantRefresh()" class="btn-gold" style="width:auto; padding:7px 12px; border-radius:12px; font-size:11px; font-weight:900; cursor:pointer;">
                ⚡ Live Refresh
            </button>
        </div>

        <!-- TAB 1: STUDIO & BRANDED REELS VAULT -->
        <div id="pane-studio" class="tab-pane active">

            <div class="lux-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <span style="font-size:11px; font-weight:900; color:#38bdf8; letter-spacing:0.8px;">⚡ NEURAL 3D PRODUCTION CORE</span>
                    <span id="status-pill" style="font-size:10px; font-weight:900; padding:3px 9px; border-radius:99px; background:rgba(16,185,129,0.2); color:#6ee7b7;">
                        {{ 'RENDERING...' if state.is_running_pipeline else 'STANDBY' }}
                    </span>
                </div>

                <div id="live-step-msg" style="font-size:14px; font-weight:800; color:#fff; margin-bottom:10px;">
                    {{ state.current_step }}
                </div>

                <div class="grid-4" style="margin-bottom:14px;">
                    <div id="st-1" class="step-pill">🧠<br>1. Script</div>
                    <div id="st-2" class="step-pill">🎬<br>2. 3D Video</div>
                    <div id="st-3" class="step-pill">🎵<br>3. Master</div>
                    <div id="st-4" class="step-pill">📲<br>4. Ready</div>
                </div>

                <!-- Smart Recovery Button for Videos Already Rendered in Gemini Chat -->
                <button onclick="recoverFromGeminiChat()" class="btn btn-gold" style="margin-bottom:10px;">
                    🕵️ Recover Finished Video from Gemini Chat History
                </button>

                {% if has_unprocessed_raw %}
                <button onclick="resumeRaw()" class="btn btn-emerald" style="margin-bottom:10px;">
                    ⚡ Finalize Existing Raw Video on Disk (1-Sec)
                </button>
                {% endif %}

                <div style="margin-bottom:10px;">
                    <select id="force_track_select" class="input-lux">
                        <option value="">🎲 Smart Auto-Rotate Web-Series (Next Episode)</option>
                        <option value="romantic">❤️ Romantic Series (Next Part)</option>
                        <option value="fighting">🔥 Shaq & Haq Series (Next Part)</option>
                        <option value="naughty_double_meaning">😏 Shararati Raatein Series (Next Part)</option>
                        <option value="glamorous_bold">✨ Royal Swag Series (Next Part)</option>
                        <option value="emotional">🇮🇳 Chhutti & Farz Series (Next Part)</option>
                        <option value="funny">😂 Fauji vs Biwi Comedy (Next Part)</option>
                        <option value="sad">🌧️ Intezaar & Judaai Series (Next Part)</option>
                        <option value="love_feelings">💫 Izhaar-e-Mohabbat Series (Next Part)</option>
                    </select>
                </div>

                <button onclick="triggerGenerate()" class="btn btn-cyber">
                    🚀 Generate New 3D Reel Now (Flash-Lite)
                </button>
            </div>

            <!-- STUDIO REELS VAULT -->
            <div style="display:flex; justify-content:space-between; align-items:center; padding:2px 6px 10px 6px;">
                <span style="font-size:12px; font-weight:900; color:#e2e8f0;">📱 STUDIO REELS VAULT ({{ reels|length }})</span>
                <span style="font-size:11px; color:#fbbf24; font-weight:800;">Today Created: {{ totals.today_count }}</span>
            </div>

            {% for item in reels %}
            {% set is_posted = 'POSTED' in (item.post_status or '') %}
            {% set is_viral = (item.views_count or 0) >= 500 or (item.likes_count or 0) >= 50 %}
            <div class="lux-card {{ 'viral-celebration' if is_viral else '' }}" id="reel-card-{{ item.video_id }}">

                {% if is_viral %}
                <div class="viral-crown-banner">🏆🎉 VIRAL REEL CELEBRATION! TRENDING ON INSTAGRAM! 🎉🏆</div>
                {% endif %}

                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div>
                        <span style="font-size:10px; font-weight:900; padding:3px 9px; border-radius:99px; background:rgba(99,102,241,0.25); color:#c7d2fe;">
                            PART {{ item.part_number or 1 }} • {{ (item.track_id or item.emotion_id or 'SERIES')|upper }}
                        </span>
                        <h3 style="margin:7px 0 2px 0; font-size:16px; font-weight:900;">{{ item.emotion_name }}</h3>
                        <div style="font-size:11px; color:#94a3b8;">Reel #{{ item.video_id }} • {{ item.timestamp }}</div>
                        {% if item.scheduled_time and not is_posted %}
                        <div style="font-size:11px; color:#fbbf24; font-weight:800; margin-top:3px;">⏰ Scheduled Slot: {{ item.scheduled_time }}</div>
                        {% endif %}
                    </div>
                    <span style="font-size:10px; font-weight:900; padding:4px 10px; border-radius:99px; background:{{ 'rgba(16,185,129,0.25)' if is_posted else 'rgba(245,158,11,0.2)' }}; color:{{ '#6ee7b7' if is_posted else '#fde68a' }};">
                        {{ item.post_status or 'READY TO POST' }}
                    </span>
                </div>

                {% if item.has_final_file %}
                <div class="phone-reel-frame">
                    <div class="phone-notch"></div>
                    <div class="phone-screen">
                        <div class="reel-Watermark">🪖 FOJI 3D STUDIO</div>
                        <div class="reel-floating-stats num-font">
                            <div class="float-stat-pill">👁️<br>{{ item.views_count or 0 }}</div>
                            <div class="float-stat-pill">❤️<br>{{ item.likes_count or 0 }}</div>
                            <div class="float-stat-pill">💬<br>{{ item.comments_count or 0 }}</div>
                        </div>
                        <video controls preload="metadata" playsinline>
                            <source src="/video/{{ item.video_id }}?v={{ item.timestamp }}" type="video/mp4">
                        </video>
                    </div>
                </div>
                {% endif %}

                <div style="background:#060914; border:1px solid rgba(255,255,255,0.08); border-radius:14px; padding:10px 12px; font-size:12px; margin-bottom:10px;">
                    <div>🪖 <b style="color:#fde68a;">{{ item.dialogue_speaker_1 }}:</b> "{{ item.dialogue_line_1_hinglish }}"</div>
                    <div style="margin-top:4px;">🧕 <b style="color:#f472b6;">{{ item.dialogue_speaker_2 }}:</b> "{{ item.dialogue_line_2_hinglish }}"</div>
                </div>

                <div style="margin-bottom:12px;">
                    <textarea id="cap-{{ item.video_id }}" rows="2" class="input-lux" {% if is_posted %}disabled{% endif %} style="font-size:12px;">{{ item.insta_title }} — {{ item.insta_caption }} {{ item.insta_hashtags }}</textarea>
                </div>

                <!-- Action Buttons: Automatically DISABLED once Posted Live! -->
                {% if is_posted %}
                <div class="btn btn-disabled" style="margin-bottom:6px;">
                    🔒 LIVE ON INSTAGRAM (ALL ACTIONS LOCKED)
                </div>
                {% else %}
                <div class="grid-2" style="margin-bottom:8px;">
                    <button onclick="postReelNow({{ item.video_id }})" class="btn btn-emerald" style="padding:11px;">
                        ✅ Approve & Post Now
                    </button>
                    <button onclick="scheduleReel({{ item.video_id }})" class="btn btn-gold" style="padding:11px;">
                        ⏰ Approve for Schedule
                    </button>
                </div>
                <div class="grid-2">
                    <button onclick="regenerateSamePart({{ item.video_id }})" class="btn btn-glass" style="padding:10px; font-size:12px;">
                        🔄 Regenerate (Part {{ item.part_number or 1 }})
                    </button>
                    <button onclick="deleteReel({{ item.video_id }})" class="btn btn-danger" style="padding:10px; font-size:12px;">
                        🗑️ Delete Permanently
                    </button>
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>

        <!-- TAB 2: INSTAGRAM EDITS ANALYTICS DASHBOARD (REACH, OVERVIEW, AUDIENCE & LIVE COMMENT REPLY) -->
        <div id="pane-insta" class="tab-pane">
            <!-- Edits Style Overview Header Card -->
            <div class="lux-card" style="background:linear-gradient(145deg, #1e1b4b, #090d16); border-color:rgba(168,85,247,0.4);">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <div>
                        <span style="font-size:10px; font-weight:900; color:#e879f9; letter-spacing:1px;">✨ INSTAGRAM EDITS INSIGHTS HUB</span>
                        <h2 style="margin:2px 0 0 0; font-size:18px; font-weight:900;">Reels Performance & Reach</h2>
                    </div>
                    <button onclick="liveInstantRefresh()" class="btn-gold" style="width:auto; padding:7px 12px; border-radius:12px; font-size:11px; font-weight:900;">
                        🔄 Sync Now
                    </button>
                </div>

                <div class="grid-4 num-font" style="margin-bottom:10px;">
                    <div class="stat-box"><div style="font-size:9px; color:#94a3b8;">TOTAL REACH</div><div class="stat-num">{{ totals.views }}</div></div>
                    <div class="stat-box"><div style="font-size:9px; color:#94a3b8;">TOTAL LIKES</div><div class="stat-num" style="color:#f43f5e;">{{ totals.likes }}</div></div>
                    <div class="stat-box"><div style="font-size:9px; color:#94a3b8;">COMMENTS</div><div class="stat-num" style="color:#38bdf8;">{{ totals.comments }}</div></div>
                    <div class="stat-box"><div style="font-size:9px; color:#94a3b8;">SHARES</div><div class="stat-num" style="color:#10b981;">{{ totals.shares }}</div></div>
                </div>
                <div style="font-size:11px; color:#cbd5e1; display:flex; justify-content:space-between; padding:6px 4px 0 4px;">
                    <span>👥 Followers: <b class="num-font">{{ insta_posts[0].followers if insta_posts else 'Synced' }}</b></span>
                    <span>🔥 Avg Engagement: <b class="num-font" style="color:#fbbf24;">{{ ((totals.likes + totals.comments) / (totals.views if totals.views > 0 else 1) * 100)|round(1) }}%</b></span>
                </div>
            </div>

            <!-- Per-Reel Breakdown & Direct Comment Reply Hub -->
            {% for post in insta_posts %}
            <div class="lux-card {{ 'viral-celebration' if post.is_viral else '' }}" style="padding:15px;">
                {% if post.is_viral %}
                <div class="viral-crown-banner">🏆🔥 VIRAL HIT! {{ post.views }} VIEWS ON INSTAGRAM! 🔥🏆</div>
                {% endif %}

                <div style="display:flex; justify-content:space-between; font-size:11px; color:#94a3b8; margin-bottom:6px;">
                    <span>📅 {{ post.date }} • Eng: <b style="color:#fbbf24;">{{ post.engagement_rate }}%</b></span>
                    {% if post.url %}
                    <a href="{{ post.url }}" target="_blank" style="color:#38bdf8; font-weight:800; text-decoration:none;">🔗 Open Reel ↗</a>
                    {% endif %}
                </div>

                <div style="font-size:12px; font-weight:600; color:#e2e8f0; margin-bottom:10px;">{{ post.caption or 'Instagram Reel' }}</div>

                <div class="grid-4 num-font" style="margin-bottom:12px;">
                    <div class="stat-box"><div style="font-size:9px; color:#94a3b8;">👁️ VIEWS</div><div class="stat-num" style="font-size:15px;">{{ post.views }}</div></div>
                    <div class="stat-box"><div style="font-size:9px; color:#94a3b8;">❤️ LIKES</div><div class="stat-num" style="font-size:15px; color:#f43f5e;">{{ post.likes }}</div></div>
                    <div class="stat-box"><div style="font-size:9px; color:#94a3b8;">💬 COMM</div><div class="stat-num" style="font-size:15px; color:#38bdf8;">{{ post.comments }}</div></div>
                    <div class="stat-box"><div style="font-size:9px; color:#94a3b8;">🚀 SHARE</div><div class="stat-num" style="font-size:15px; color:#10b981;">{{ post.shares }}</div></div>
                </div>

                <!-- Live Viewer Comments & Instant Reply Box -->
                {% if post.recent_comments %}
                <div style="background:#060914; border-radius:14px; padding:10px; border:1px solid rgba(255,255,255,0.08);">
                    <div style="font-size:10px; font-weight:900; color:#38bdf8; margin-bottom:6px;">💬 RECENT VIEWER COMMENTS (REPLY DIRECTLY):</div>
                    {% for c in post.recent_comments %}
                    <div style="border-bottom:1px solid rgba(255,255,255,0.06); padding:6px 0; font-size:11px;">
                        <div><b style="color:#fde68a;">@{{ c.user }}:</b> {{ c.text }}</div>
                        <div style="display:flex; gap:6px; margin-top:5px;">
                            <input id="rep-{{ c.pk }}" type="text" placeholder="Write reply to @{{ c.user }}..." class="input-lux" style="padding:6px 10px; font-size:11px;">
                            <button onclick="sendCommentReply('{{ post.pk }}', '{{ c.pk }}')" class="btn-cyber" style="width:auto; padding:6px 12px; border-radius:10px; font-size:10px; font-weight:800; cursor:pointer; border:none; color:#fff;">
                                Reply
                            </button>
                        </div>
                    </div>
                    {% endfor %}
                </div>
                {% endif %}
            </div>
            {% else %}
            <div class="lux-card" style="text-align:center; padding:25px; color:#94a3b8; font-size:12px;">
                Upar <b>"🔄 Sync Now"</b> par tap karein taaki aapke Instagram page ki saari Reels, Views, Likes aur Viewer Comments yahan load ho jayein!
            </div>
            {% endfor %}
        </div>

        <!-- TAB 3: SCHEDULE -->
        <div id="pane-schedule" class="tab-pane">
            <div class="lux-card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <div>
                        <h2 style="margin:0; font-size:16px; font-weight:900;">⏰ 24/7 Smart Auto-Scheduler</h2>
                        <p style="margin:4px 0 0 0; font-size:11px; color:#94a3b8;">
                            Har slot se {{ sched.lead_minutes or 15 }} min pehle reel apne aap ban kar Approval ke liye aa jayegi!
                        </p>
                    </div>
                    <input id="sched_enabled" type="checkbox" {% if sched.enabled %}checked{% endif %} style="width:22px; height:22px; accent-color:#f59e0b;">
                </div>
                <div class="grid-3" style="margin-bottom:14px;">
                    <input id="slot_1" type="time" value="{{ sched.slots[0] if sched.slots|length > 0 else '11:00' }}" class="input-lux" style="text-align:center;">
                    <input id="slot_2" type="time" value="{{ sched.slots[1] if sched.slots|length > 1 else '16:00' }}" class="input-lux" style="text-align:center;">
                    <input id="slot_3" type="time" value="{{ sched.slots[2] if sched.slots|length > 2 else '20:30' }}" class="input-lux" style="text-align:center;">
                </div>
                <input id="lead_mins" type="number" value="{{ sched.lead_minutes or 15 }}" class="input-lux" style="margin-bottom:16px;">
                <button onclick="saveScheduleConfig()" class="btn btn-gold">💾 Save & Lock Schedule</button>
            </div>
        </div>

        <!-- TAB 4: PHONE CONNECT & CLOUD SETUP -->
        <div id="pane-connect" class="tab-pane">
            <div class="lux-card">
                <h2 style="margin:0 0 8px 0; font-size:16px; font-weight:900;">📱 Mobile Connect & Instagram Setup</h2>
                {% if state.public_tunnel_url %}
                <div style="background:rgba(16,185,129,0.15); border:1px solid #10b981; border-radius:14px; padding:12px; margin-bottom:12px;">
                    <div style="font-size:10px; font-weight:900; color:#6ee7b7;">🌍 GLOBAL 4G/5G MOBILE LINK:</div>
                    <a href="{{ state.public_tunnel_url }}" target="_blank" style="color:#fff; font-weight:900; font-size:14px; word-break:break-all;">{{ state.public_tunnel_url }}</a>
                </div>
                {% endif %}
                <div style="background:#060914; border:1px solid rgba(255,255,255,0.12); border-radius:14px; padding:12px; margin-bottom:14px;">
                    <div style="font-size:10px; font-weight:900; color:#fde68a; margin-bottom:6px;">🏠 LOCAL WI-FI / HOTSPOT LINKS:</div>
                    {% for ip in local_ips %}
                    <div class="num-font" style="font-size:14px; font-weight:900; color:#38bdf8; margin-bottom:4px;">http://{{ ip }}:5000</div>
                    {% endfor %}
                </div>
                <input id="ig_user" type="text" placeholder="Instagram Username" value="{{ ig_user }}" class="input-lux" style="margin-bottom:8px;">
                <input id="ig_pass" type="password" placeholder="Instagram Password" value="{{ ig_pass }}" class="input-lux" style="margin-bottom:12px;">
                <button onclick="saveInstaCreds()" class="btn btn-cyber">💾 Save Instagram Account</button>
            </div>

            <div class="lux-card">
                <h3 style="margin:0 0 8px 0; font-size:14px; font-weight:900;">🛠️ Live System Console</h3>
                <div style="background:#020307; border-radius:14px; padding:10px; font-family:monospace; font-size:11px; color:#34d399; max-height:220px; overflow-y:auto;">
                    {% for line in state.self_heal_log %}
                    <div>{{ line }}</div>
                    {% endfor %}
                </div>
            </div>
        </div>

    </div>

    <div class="bottom-dock">
        <button id="btn-studio" onclick="switchTab('studio')" class="dock-item active"><span style="font-size:18px;">🎬</span><span>Studio</span></button>
        <button id="btn-insta" onclick="switchTab('insta')" class="dock-item"><span style="font-size:18px;">📊</span><span>Insta Edits</span></button>
        <button id="btn-schedule" onclick="switchTab('schedule')" class="dock-item"><span style="font-size:18px;">⏰</span><span>Schedule</span></button>
        <button id="btn-connect" onclick="switchTab('connect')" class="dock-item"><span style="font-size:18px;">📱</span><span>Setup</span></button>
    </div>

    <script>
        let wasRunning = {{ 'true' if state.is_running_pipeline else 'false' }};

        // Premium Modal Helper (No Browser Alerts!)
        function showLuxModal({title, desc, icon='💎', loading=false, confirmCallback=null}) {
            const back = document.getElementById('lux-modal-backdrop');
            document.getElementById('modal-title-el').innerText = title;
            document.getElementById('modal-desc-el').innerText = desc;
            document.getElementById('modal-spinner-el').style.display = loading ? 'block' : 'none';
            document.getElementById('modal-icon-el').style.display = loading ? 'none' : 'block';
            document.getElementById('modal-icon-el').innerText = icon;

            const btnRow = document.getElementById('modal-btn-row');
            const okBtn = document.getElementById('modal-ok-btn');

            if (confirmCallback) {
                btnRow.style.display = 'grid';
                okBtn.style.display = 'none';
                document.getElementById('modal-confirm-btn').onclick = () => {
                    closeLuxModal();
                    confirmCallback();
                };
                document.getElementById('modal-cancel-btn').onclick = closeLuxModal;
            } else {
                btnRow.style.display = 'none';
                okBtn.style.display = loading ? 'none' : 'flex';
            }
            back.style.display = 'flex';
        }

        function closeLuxModal() {
            document.getElementById('lux-modal-backdrop').style.display = 'none';
        }

        function switchTab(name) {
            document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.dock-item').forEach(el => el.classList.remove('active'));
            document.getElementById('pane-' + name).classList.add('active');
            document.getElementById('btn-' + name).classList.add('active');
        }

        async function pollStatus() {
            try {
                const res = await fetch('/api/live_status');
                const s = await res.json();
                document.getElementById('live-step-msg').innerText = s.current_step;

                if (s.is_running_pipeline) {
                    wasRunning = true;
                    document.getElementById('status-pill').innerText = 'RENDERING (' + s.elapsed_sec + 's)';
                    for (let i = 1; i <= 4; i++) {
                        const el = document.getElementById('st-' + i);
                        el.classList.remove('active', 'done');
                        if (i < s.stage_index) el.classList.add('done');
                        else if (i === s.stage_index) el.classList.add('active');
                    }
                } else if (wasRunning) {
                    wasRunning = false;
                    location.reload();
                }
            } catch (e) {}
        }
        setInterval(pollStatus, 2000);
        // Auto-refresh UI every 2 minutes (120,000 ms) when idle
        setInterval(() => { if (!wasRunning) location.reload(); }, 120000);

        async function liveInstantRefresh() {
            showLuxModal({title: 'Syncing Live Instagram Data...', desc: 'Fetching real-time Views, Likes, Reach & Comments from your Instagram profile...', loading: true});
            const res = await fetch('/api/sync_insta', {method: 'POST'});
            const d = await res.json();
            showLuxModal({title: 'Live Sync Complete!', desc: d.message, icon: '📊'});
            setTimeout(() => location.reload(), 1200);
        }

        async function recoverFromGeminiChat() {
            showLuxModal({title: 'Searching Gemini Chats...', desc: 'Opening Gemini chat history in background to locate & download your finished 3D video...', loading: true});
            const res = await fetch('/api/recover_from_chat', {method: 'POST'});
            const d = await res.json();
            closeLuxModal();
            wasRunning = true;
            pollStatus();
        }

        async function resumeRaw() {
            showLuxModal({title: 'Finalizing Raw Video...', desc: 'Mastering existing MP4 into Final Reel...', loading: true});
            const res = await fetch('/api/resume_stuck', {method: 'POST'});
            const d = await res.json();
            showLuxModal({title: 'Reel Ready!', desc: d.message, icon: '🎉'});
            setTimeout(() => location.reload(), 1200);
        }

        async function triggerGenerate() {
            const track = document.getElementById('force_track_select').value;
            await fetch('/api/generate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({force_track_id: track})
            });
            showLuxModal({title: '3D Generation Started!', desc: 'Gemini Flash-Lite is crafting your episodic reel in invisible background mode.', icon: '🚀'});
            wasRunning = true;
            pollStatus();
        }

        function deleteReel(vid) {
            showLuxModal({
                title: 'Delete Reel #' + vid + '?',
                desc: 'Yeh video aur iska caption 100% permanently delete ho jayega aur Part Number wapas reset ho jayega.',
                icon: '🗑️',
                confirmCallback: async () => {
                    showLuxModal({title: 'Deleting...', desc: 'Removing video & caption files...', loading: true});
                    await fetch('/api/delete/' + vid, {method: 'POST'});
                    location.reload();
                }
            });
        }

        function regenerateSamePart(vid) {
            showLuxModal({
                title: 'Regenerate Same Part?',
                desc: 'Yeh video usi exact Part Number par ek bilkul naye creative scene aur naye dialogues ke sath dobara banegi.',
                icon: '🔄',
                confirmCallback: async () => {
                    await fetch('/api/regenerate/' + vid, {method: 'POST'});
                    wasRunning = true;
                    window.scrollTo({top: 0, behavior: 'smooth'});
                    pollStatus();
                }
            });
        }

        async function postReelNow(vid) {
            const cap = document.getElementById('cap-' + vid).value;
            showLuxModal({
                title: 'Uploading to Instagram Live...',
                desc: 'Generating HD FFmpeg Thumbnail & publishing Reel #' + vid + ' directly to your Instagram page. Please wait 15-25 seconds...',
                loading: true
            });
            const res = await fetch('/api/post/' + vid, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({caption: cap})
            });
            const d = await res.json();
            showLuxModal({
                title: d.ok ? '🎉 Posted Live on Instagram!' : '⚠️ Upload Notice',
                desc: d.message,
                icon: d.ok ? '🏆' : '⚠️'
            });
            if (d.ok) setTimeout(() => location.reload(), 1800);
        }

        async function scheduleReel(vid) {
            const cap = document.getElementById('cap-' + vid).value;
            showLuxModal({title: 'Locking Schedule Slot...', desc: 'Saving approval for next viral slot...', loading: true});
            const res = await fetch('/api/schedule/' + vid, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({caption: cap})
            });
            const d = await res.json();
            showLuxModal({title: 'Scheduled Successfully!', desc: d.message, icon: '⏰'});
            setTimeout(() => location.reload(), 1400);
        }

        async function sendCommentReply(mediaPk, commentPk) {
            const txt = document.getElementById('rep-' + commentPk).value;
            showLuxModal({title: 'Posting Reply...', desc: 'Sending your reply to Instagram comment...', loading: true});
            const res = await fetch('/api/reply_comment', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({media_pk: mediaPk, comment_pk: commentPk, text: txt})
            });
            const d = await res.json();
            showLuxModal({title: 'Comment Reply Status', desc: d.message, icon: '💬'});
        }

        async function saveScheduleConfig() {
            const enabled = document.getElementById('sched_enabled').checked;
            const s1 = document.getElementById('slot_1').value;
            const s2 = document.getElementById('slot_2').value;
            const s3 = document.getElementById('slot_3').value;
            const lead = document.getElementById('lead_mins').value;
            const res = await fetch('/api/save_schedule', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({enabled, slots: [s1, s2, s3].filter(Boolean), lead_minutes: parseInt(lead || 15)})
            });
            const d = await res.json();
            showLuxModal({title: 'Schedule Locked!', desc: d.message, icon: '⏰'});
        }

        async function saveInstaCreds() {
            const u = document.getElementById('ig_user').value;
            const p = document.getElementById('ig_pass').value;
            const res = await fetch('/api/save_insta', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: u, password: p})
            });
            const d = await res.json();
            showLuxModal({title: 'Instagram Connected!', desc: d.message, icon: '📸'});
        }
    </script>
</body>
</html>
"""

@app.route("/manifest.json")
def pwa_manifest():
    return Response(json.dumps({
        "name": "Foji AI Studio Pro",
        "short_name": "Foji3D",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#03040a",
        "theme_color": "#03040a"
    }), mimetype="application/json")

@app.route("/")
def index():
    history_data = load_strict_clean_history()
    sched = load_schedule_config()
    insta_posts = load_insta_live_posts()
    items = history_data.get("history", [])

    import studio
    stuck_id, _ = studio.find_unprocessed_raw_video()

    today_str = datetime.now().strftime("%Y-%m-%d")

    # Combine stats from live Instagram profile posts (if synced) or local items
    if insta_posts:
        total_v = sum(p.get("views", 0) for p in insta_posts)
        total_l = sum(p.get("likes", 0) for p in insta_posts)
        total_c = sum(p.get("comments", 0) for p in insta_posts)
        total_s = sum(p.get("shares", 0) for p in insta_posts)
    else:
        total_v = sum(int(i.get("views_count", 0)) for i in items)
        total_l = sum(int(i.get("likes_count", 0)) for i in items)
        total_c = sum(int(i.get("comments_count", 0)) for i in items)
        total_s = sum(int(i.get("shares_count", 0)) for i in items)

    totals = {
        "views": total_v,
        "likes": total_l,
        "comments": total_c,
        "shares": total_s,
        "total_videos": len(items),
        "today_count": sum(1 for i in items if i.get("timestamp", "").startswith(today_str)),
        "scheduled_count": sum(1 for i in items if "SCHEDULED" in (i.get("post_status") or ""))
    }

    reels_view = []
    for item in items:
        vid_id = int(item.get("video_id", 1))
        final_file = os.path.abspath(f"output/final_reels/final_reel_{vid_id}.mp4")
        if os.path.exists(final_file):
            item_copy = dict(item)
            item_copy["has_final_file"] = True
            reels_view.append(item_copy)

    reels_view.reverse()

    return render_template_string(
        PLAYSTORE_BRANDED_HTML,
        state=RUNTIME_STATE,
        totals=totals,
        reels=reels_view,
        insta_posts=insta_posts,
        sched=sched,
        has_unprocessed_raw=(stuck_id is not None),
        local_ips=get_all_local_ips(),
        ig_user=os.getenv("INSTAGRAM_USERNAME", ""),
        ig_pass=os.getenv("INSTAGRAM_PASSWORD", "")
    )

@app.route("/api/resume_stuck", methods=["POST"])
def api_resume_stuck():
    ok, msg = resume_existing_raw_video_pipeline()
    return jsonify({"message": msg})

@app.route("/api/live_status")
def api_live_status():
    elapsed = int(time.time() - RUNTIME_STATE["started_at_ts"]) if RUNTIME_STATE["is_running_pipeline"] else 0
    if RUNTIME_STATE["is_running_pipeline"] and RUNTIME_STATE["stage_index"] == 2:
        RUNTIME_STATE["stage_percent"] = min(80, 35 + int(elapsed / 3))

    return jsonify({
        "is_running_pipeline": RUNTIME_STATE["is_running_pipeline"],
        "stage_index": RUNTIME_STATE["stage_index"],
        "stage_percent": RUNTIME_STATE["stage_percent"],
        "current_step": RUNTIME_STATE["current_step"],
        "active_episode_title": RUNTIME_STATE["active_episode_title"],
        "elapsed_sec": elapsed,
        "last_error": RUNTIME_STATE["last_error"]
    })

@app.route("/video/<int:vid_id>")
def serve_video(vid_id):
    folder = os.path.abspath("output/final_reels")
    return send_from_directory(folder, f"final_reel_{vid_id}.mp4")

@app.route("/api/generate", methods=["POST"])
def api_generate():
    if RUNTIME_STATE["is_running_pipeline"]:
        return jsonify({"message": "⚠️ Engine abhi busy hai!"})
    data = request.json or {}
    force_track = data.get("force_track_id") or None
    threading.Thread(
        target=run_full_pipeline_background,
        kwargs={"force_track_id": force_track},
        daemon=True
    ).start()
    return jsonify({"message": "🚀 3D Generation Started!"})

@app.route("/api/delete/<int:vid_id>", methods=["POST"])
def api_delete(vid_id):
    """
    100% COMPLETE PURGE:
    Deletes the MP4 files AND completely removes the entry (caption, title, metadata) from history.json!
    """
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    else:
        raw_data = {"generated_count": 0, "recent_tracks": [], "history": []}

    new_hist = []
    for idx, item in enumerate(raw_data.get("history", []), start=1):
        current_id = int(item.get("video_id", idx))
        if current_id == int(vid_id):
            continue  # Completely drop this item!
        new_hist.append(item)

    raw_data["history"] = new_hist
    save_history(raw_data)

    for p in [
        f"output/raw_videos/raw_video_{vid_id}.mp4",
        f"output/final_reels/final_reel_{vid_id}.mp4",
        f"output/final_reels/final_reel_{vid_id}_thumb.jpg"
    ]:
        abs_p = os.path.abspath(p)
        if os.path.exists(abs_p):
            try:
                os.remove(abs_p)
            except Exception:
                pass

    log_heal(f"🗑️ Permanently deleted Video #{vid_id} + Caption + Card!")
    return jsonify({"message": f"🗑️ Video #{vid_id} aur uska Caption 100% delete ho gaya!"})

@app.route("/api/regenerate/<int:vid_id>", methods=["POST"])
def api_regenerate(vid_id):
    if RUNTIME_STATE["is_running_pipeline"]:
        return jsonify({"message": "⚠️ Engine busy hai!"})

    history_data = load_strict_clean_history()
    target_item = None
    for idx, item in enumerate(history_data.get("history", []), start=1):
        if int(item.get("video_id", idx)) == int(vid_id):
            target_item = item
            break

    if not target_item:
        return jsonify({"message": "❌ Video nahi mili!"})

    track_id = target_item.get("track_id") or target_item.get("emotion_id") or "romantic"
    part_num = int(target_item.get("part_number", 1))
    old_line = target_item.get("dialogue_line_1_hinglish", "")

    for p in [
        f"output/raw_videos/raw_video_{vid_id}.mp4",
        f"output/final_reels/final_reel_{vid_id}.mp4"
    ]:
        abs_p = os.path.abspath(p)
        if os.path.exists(abs_p):
            try:
                os.remove(abs_p)
            except Exception:
                pass

    history_data["history"] = [h for h in history_data.get("history", []) if int(h.get("video_id", 0)) != int(vid_id)]
    save_history(history_data)

    log_heal(f"🔄 Regenerating {track_id.upper()} - PART {part_num} in new style...")
    threading.Thread(
        target=run_full_pipeline_background,
        kwargs={
            "force_track_id": track_id,
            "force_part_number": part_num,
            "is_regenerate": True,
            "old_rejected_line": old_line,
            "reuse_video_id": vid_id
        },
        daemon=True
    ).start()

    return jsonify({"message": f"🔄 Regenerating '{track_id} - Part {part_num}' with a brand new scene!"})

@app.route("/api/telemetry_3d", methods=["GET"])
def api_telemetry_3d():
    t_path = "data/live_telemetry.json"
    if os.path.exists(t_path):
        try:
            with open(t_path, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        except Exception:
            pass
    return jsonify({
        "step_num": 0,
        "step_title": "STANDBY — 3D CLOUD CORE READY",
        "sub_detail": "Waiting for Scheduled Slot or Manual Trigger...",
        "status": "idle",
        "progress": 0,
        "timestamp": time.strftime("%H:%M:%S")
    })

@app.route("/api/remix_caption/<int:vid_id>", methods=["POST"])
def api_remix_caption(vid_id):
    history_data = load_strict_clean_history()
    target = None
    for item in history_data.get("history", []):
        if int(item.get("video_id", 0)) == int(vid_id):
            target = item
            break
    if not target:
        return jsonify({"new_caption": ""})

    part_num = target.get("part_number", 1)
    ep_name = target.get("emotion_name", "Foji & Fojan")
    hooks = [
        f"🔥 {ep_name} ❤️ Fauji ki mohabbat aur fojan ke nakhre! Agle Part {part_num+1} mein kya hoga? Comment karo 👇 #foji #indianarmy #reelsindia #faujilove #viralreels #part{part_num}",
        f"🪖 Wait for the end! 😍 {ep_name} — Kya aapki jodi bhi aisi hi hai? Tag your partner ❤️👇 #faujidil #couplegoals #indianarmylovers #pixaranimation #trendingreels #part{part_num}",
        f"❤️ Ek Fauji ki Zindagi! {ep_name} 🔥 Part {part_num+1} dekhne ke liye abhi Follow kar lo! 👇 #fojimakra #fojanmeera #desilove #armylife #hindireels #part{part_num}"
    ]
    chosen = random.choice(hooks)
    target["insta_caption"] = chosen
    save_history(history_data)
    return jsonify({"new_caption": chosen})

@app.route("/api/recover_from_chat", methods=["POST"])
def api_recover_from_chat():
    """Finds the video that already finished rendering inside Gemini Chrome chat history and completes it!"""
    if RUNTIME_STATE["is_running_pipeline"]:
        return jsonify({"ok": False, "message": "⚠️ Engine abhi busy hai!"})

    def _recover_job():
        RUNTIME_STATE["is_running_pipeline"] = True
        RUNTIME_STATE["stage_index"] = 2
        RUNTIME_STATE["stage_percent"] = 60
        RUNTIME_STATE["current_step"] = "🕵️ Searching Gemini Chat History for Finished Video..."
        try:
            import gemini_bot
            import studio
            out_raw = gemini_bot.generate_video_in_gemini(recover_only=True)
            RUNTIME_STATE["stage_index"] = 3
            RUNTIME_STATE["stage_percent"] = 90
            RUNTIME_STATE["current_step"] = "🎵 Mastering Recovered Video..."
            studio.build_final_reel()
            RUNTIME_STATE["stage_index"] = 4
            RUNTIME_STATE["stage_percent"] = 100
            RUNTIME_STATE["current_step"] = "✅ Recovered Video Ready in Vault!"
            log_heal("🎉 Recovered finished video from Gemini chat history!")
        except Exception as e:
            RUNTIME_STATE["last_error"] = str(e)
            RUNTIME_STATE["current_step"] = "⚠️ Recovery Notice: See Alert"
        finally:
            RUNTIME_STATE["is_running_pipeline"] = False

    threading.Thread(target=_recover_job, daemon=True).start()
    return jsonify({"ok": True, "message": "🕵️ Searching Gemini Chats in Background & Downloading Video..."})

@app.route("/api/reply_comment", methods=["POST"])
def api_reply_comment():
    data = request.json or {}
    media_pk = data.get("media_pk")
    comment_pk = data.get("comment_pk")
    text = data.get("text", "").strip()
    if not media_pk or not comment_pk or not text:
        return jsonify({"ok": False, "message": "Reply text खाली hai!"})
    import telegram_bot
    ok, msg = telegram_bot.reply_to_instagram_comment(media_pk, comment_pk, text)
    log_heal(f"💬 Replied to comment on Reel {media_pk}: {text[:40]}")
    return jsonify({"ok": ok, "message": msg})

@app.route("/api/post/<int:vid_id>", methods=["POST"])
def api_post(vid_id):
    data = request.json or {}
    custom_caption = data.get("caption")

    history_data = load_strict_clean_history()
    target = None
    for item in history_data.get("history", []):
        if int(item.get("video_id", 0)) == int(vid_id):
            target = item
            break
    if not target and history_data.get("history"):
        target = history_data["history"][-1]

    if "POSTED" in (target.get("post_status") or ""):
        return jsonify({"ok": False, "message": "✅ Yeh video pehle hi Instagram par POST ho chuki hai!"})

    final_path = os.path.abspath(f"output/final_reels/final_reel_{vid_id}.mp4")
    caption = custom_caption or f"{target.get('insta_title', '')}\n\n{target.get('insta_caption', '')}\n\n{target.get('insta_hashtags', '')}"

    import telegram_bot
    ok, msg, media_pk, media_code = telegram_bot.post_reel_to_instagram(final_path, caption)
    if ok:
        target["post_status"] = "POSTED LIVE ✅"
        target["insta_media_pk"] = media_pk
        if media_code:
            target["insta_url"] = f"https://www.instagram.com/reel/{media_code}/"
    else:
        target["post_status"] = "POST_ERROR"

    save_history(history_data)
    log_heal(f"📤 Posted Reel #{vid_id}: {msg}")
    return jsonify({"ok": ok, "message": msg})

@app.route("/api/schedule/<int:vid_id>", methods=["POST"])
def api_schedule(vid_id):
    import telegram_bot
    slot_dt = telegram_bot.get_next_viral_slot()
    history_data = load_strict_clean_history()
    sched_str = slot_dt.strftime("%Y-%m-%d %H:%M:%S")

    for item in history_data.get("history", []):
        if int(item.get("video_id", 0)) == int(vid_id):
            sched_str = item.get("target_schedule_slot") or sched_str
            item["post_status"] = "SCHEDULED"
            item["scheduled_time"] = sched_str
            break
    save_history(history_data)
    log_heal(f"⏰ Reel #{vid_id} Locked for Schedule: {sched_str}")
    return jsonify({"message": f"✅ Approved & Scheduled for {sched_str}!"})

@app.route("/api/save_schedule", methods=["POST"])
def api_save_schedule():
    data = request.json or {}
    cfg = {
        "enabled": bool(data.get("enabled", True)),
        "slots": data.get("slots", ["11:00", "16:00", "20:30"]),
        "lead_minutes": int(data.get("lead_minutes", 15))
    }
    save_schedule_config(cfg)
    log_heal(f"⏰ Updated Schedule: {cfg['slots']} (Lead: {cfg['lead_minutes']}m)")
    return jsonify({"message": "✅ 24/7 Schedule Locked!"})

@app.route("/api/save_insta", methods=["POST"])
def api_save_insta():
    data = request.json or {}
    u = data.get("username", "").strip()
    p = data.get("password", "").strip()
    if not os.path.exists(ENV_FILE):
        open(ENV_FILE, "a").close()
    set_key(ENV_FILE, "INSTAGRAM_USERNAME", u)
    set_key(ENV_FILE, "INSTAGRAM_PASSWORD", p)
    load_dotenv(override=True)
    log_heal(f"✅ Connected Instagram @{u}")
    return jsonify({"message": f"✅ Instagram @{u} saved!"})

@app.route("/api/sync_insta", methods=["POST"])
def api_sync_insta():
    ok, msg = sync_instagram_insights()
    return jsonify({"message": msg})

if __name__ == "__main__":
    ips = get_all_local_ips()
    print("\n" + "="*72)
    print("💎 FOJI AI STUDIO PRO (AUTO-RELOAD ON • NO BOOT AUTO-GEN)")
    print(f"👉 Laptop Link:           http://127.0.0.1:5000")
    for ip in ips:
        print(f"👉 Mobile Wi-Fi Link:     http://{ip}:5000")
    print("="*72 + "\n")
    # use_reloader=True automatically applies any code changes the second you press Ctrl+S!
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=True)