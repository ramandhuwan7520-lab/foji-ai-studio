import os
import json
import time
import socket
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import requests
import imageio_ffmpeg
import urllib3.util.connection as urllib3_cn
from dotenv import load_dotenv

load_dotenv()

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

def allowed_gai_family():
    return socket.AF_INET

urllib3_cn.allowed_gai_family = allowed_gai_family

def generate_video_thumbnail_ffmpeg(video_path):
    """
    Extracts a high-quality JPEG thumbnail from the video at 1.0s using FFmpeg.
    Completely eliminates the instagrapi MoviePy thumbnail error!
    """
    thumb_path = video_path.replace(".mp4", "_thumb.jpg")
    cmd = [
        FFMPEG_EXE, "-y",
        "-ss", "00:00:01.000",
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        thumb_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000:
        return thumb_path
    return None

def get_next_viral_slot():
    """Returns the next scheduled slot from settings or default viral times (11:00 AM, 4:00 PM, 8:30 PM)."""
    now = datetime.now()
    custom_times = ["11:00", "16:00", "20:30"]
    if os.path.exists("data/schedule_config.json"):
        try:
            with open("data/schedule_config.json", "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if cfg.get("slots"):
                    custom_times = cfg["slots"]
        except Exception:
            pass

    slots = []
    for t_str in sorted(custom_times):
        try:
            hh, mm = map(int, t_str.split(":"))
            slots.append(now.replace(hour=hh, minute=mm, second=0, microsecond=0))
        except Exception:
            pass

    for s in slots:
        if s > now + timedelta(minutes=2):
            return s

    # Otherwise first slot tomorrow
    hh, mm = map(int, sorted(custom_times)[0].split(":"))
    return (now + timedelta(days=1)).replace(hour=hh, minute=mm, second=0, microsecond=0)

def post_reel_to_instagram(video_path, caption_text):
    """
    Uploads the MP4 reel + FFmpeg Thumbnail to Instagram and returns (Success, Message, Media_PK, Code).
    """
    load_dotenv(override=True)
    ig_user = os.getenv("INSTAGRAM_USERNAME")
    ig_pass = os.getenv("INSTAGRAM_PASSWORD")

    if not ig_user or not ig_pass or "your_" in ig_user.lower():
        return False, "⚠️ Pehle Settings tab mein Instagram Username aur Password save karo!", None, None

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

        thumb_file = generate_video_thumbnail_ffmpeg(video_path)
        print("📤 Uploading Reel to Instagram...")
        if thumb_file and os.path.exists(thumb_file):
            media = cl.clip_upload(Path(video_path), caption=caption_text, thumbnail=Path(thumb_file))
        else:
            media = cl.clip_upload(Path(video_path), caption=caption_text)

        media_pk = str(media.pk)
        media_code = getattr(media, "code", "")
        return True, f"🎉 INSTAGRAM REEL LIVE HO GAYI! (ID: {media_pk})", media_pk, media_code
    except Exception as e:
        return False, f"❌ Instagram Upload Error: {e}", None, None

def reply_to_instagram_comment(media_pk, comment_pk, reply_text):
    """Replies directly to a viewer's comment on an Instagram Reel from the Dashboard App."""
    load_dotenv(override=True)
    ig_user = os.getenv("INSTAGRAM_USERNAME")
    ig_pass = os.getenv("INSTAGRAM_PASSWORD")
    try:
        from instagrapi import Client
        cl = Client()
        session_file = "data/insta_session.json"
        if os.path.exists(session_file):
            cl.load_settings(session_file)
        cl.login(ig_user, ig_pass)
        cl.media_comment(media_pk, reply_text, replied_to_comment_id=int(comment_pk))
        return True, "✅ Comment Reply Posted Live on Instagram!"
    except Exception as e:
        return False, f"❌ Comment Reply Failed: {e}"

def send_reel_for_approval(target_slot_str=None):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return "NO_TELEGRAM_CONFIG"

    with open("data/history.json", "r", encoding="utf-8") as f:
        history_data = json.load(f)

    latest_pkg = history_data["history"][-1]
    video_num = latest_pkg.get("video_id", history_data["generated_count"])
    final_reel_path = os.path.abspath(f"output/final_reels/final_reel_{video_num}.mp4")

    if not os.path.exists(final_reel_path):
        raise FileNotFoundError(f"❌ Final reel nahi mili: {final_reel_path}")

    full_insta_caption = (
        f"{latest_pkg.get('insta_title', '')}\n\n"
        f"{latest_pkg.get('insta_caption', '')}\n\n"
        f"{latest_pkg.get('insta_hashtags', '')}"
    )

    limit_note = latest_pkg.get("quota_reopen_note", "Quota Available ✅")
    next_slot_dt = get_next_viral_slot()
    slot_label = target_slot_str or next_slot_dt.strftime("%I:%M %p")

    tg_caption = (
        f"🎬 *NEW 3D REEL READY (Video #{video_num})*\n"
        f"🎭 *Series:* {latest_pkg.get('emotion_name')} (Part {latest_pkg.get('part_number', 1)})\n"
        f"🗣️ *{latest_pkg.get('dialogue_speaker_1')}:* _{latest_pkg.get('dialogue_line_1_hinglish')}_\n"
        f"🗣️ *{latest_pkg.get('dialogue_speaker_2')}:* _{latest_pkg.get('dialogue_line_2_hinglish')}_\n"
        f"📊 *Gemini Status:* {limit_note}\n\n"
        f"💡 *Note:* Aap yahan Telegram se ya Mobile App se—kisi bhi ek jagah se Approve kar sakte ho!"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Post Now on Insta", "callback_data": f"post_now_{video_num}"},
                {"text": f"⏰ Approve for {slot_label}", "callback_data": f"schedule_{video_num}"}
            ],
            [
                {"text": "❌ Reject Video", "callback_data": f"reject_{video_num}"}
            ]
        ]
    }

    url = f"https://api.telegram.org/bot{token}/sendVideo"
    with open(final_reel_path, "rb") as vf:
        res = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "caption": tg_caption,
                "parse_mode": "Markdown",
                "reply_markup": json.dumps(keyboard)
            },
            files={"video": vf},
            timeout=120
        )

    if res.status_code != 200:
        return "TELEGRAM_SEND_ERROR"

    updates_url = f"https://api.telegram.org/bot{token}/getUpdates"
    last_update_id = 0
    try:
        init_u = requests.get(updates_url, timeout=10).json().get("result", [])
        if init_u:
            last_update_id = init_u[-1]["update_id"] + 1
    except Exception:
        pass

    # Dual-Sync Listener: Checks both Telegram clicks AND Frontend App actions!
    for _ in range(360):
        time.sleep(4)

        # 1. Check if user ALREADY approved/posted/scheduled from the Mobile Frontend App!
        try:
            with open("data/history.json", "r", encoding="utf-8") as f:
                live_hist = json.load(f)
            for item in live_hist.get("history", []):
                if item.get("video_id") == video_num:
                    st = item.get("post_status", "")
                    if st in ["POSTED", "SCHEDULED", "REJECTED"]:
                        print(f"✅ Reel #{video_num} already handled via Mobile App ({st}). Closing Telegram listener.")
                        return st
        except Exception:
            pass

        # 2. Check if user clicked a button on Telegram
        try:
            u_res = requests.get(updates_url, params={"offset": last_update_id, "timeout": 3}, timeout=8).json()
            for item in u_res.get("result", []):
                last_update_id = item["update_id"] + 1
                cb = item.get("callback_query")
                if not cb:
                    continue

                data_clicked = cb.get("data", "")
                cb_id = cb.get("id")
                requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id})

                with open("data/history.json", "r", encoding="utf-8") as f:
                    history_data = json.load(f)
                target_item = history_data["history"][-1]
                for h_item in history_data["history"]:
                    if h_item.get("video_id") == video_num:
                        target_item = h_item
                        break

                if data_clicked == f"post_now_{video_num}":
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": "🚀 *Uploading Reel to Instagram (with Auto-Thumbnail)...*"},
                        timeout=10
                    )
                    ok, msg, *rest = post_reel_to_instagram(final_reel_path, full_insta_caption)
                    target_item["post_status"] = "POSTED" if ok else f"POST_ERROR"
                    with open("data/history.json", "w", encoding="utf-8") as f:
                        json.dump(history_data, f, indent=4, ensure_ascii=False)

                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                        timeout=10
                    )
                    return "POSTED"

                elif data_clicked == f"schedule_{video_num}":
                    slot_dt = get_next_viral_slot()
                    target_item["post_status"] = "SCHEDULED"
                    target_item["scheduled_time"] = slot_dt.strftime("%Y-%m-%d %H:%M:%S")
                    with open("data/history.json", "w", encoding="utf-8") as f:
                        json.dump(history_data, f, indent=4, ensure_ascii=False)

                    sched_msg = (
                        f"✅ *Approved & Scheduled!*\n\n"
                        f"⏰ Yeh reel exact `{slot_dt.strftime('%I:%M %p (%d %b)')}` par apne aap Instagram par post ho jayegi!"
                    )
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": sched_msg, "parse_mode": "Markdown"},
                        timeout=10
                    )
                    return "SCHEDULED"

                elif data_clicked == f"reject_{video_num}":
                    target_item["post_status"] = "REJECTED"
                    with open("data/history.json", "w", encoding="utf-8") as f:
                        json.dump(history_data, f, indent=4, ensure_ascii=False)
                    requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": "❌ *Video Rejected!*"},
                        timeout=10
                    )
                    return "REJECTED"
        except Exception:
            pass

    return "PENDING"

if __name__ == "__main__":
    send_reel_for_approval()