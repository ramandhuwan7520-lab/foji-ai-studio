import re
import os
import sys
import shutil
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import os
import shutil
# -*- coding: utf-8 -*-
# pyright: reportOptionalMemberAccess=false, reportGeneralTypeIssues=false
import os
import gc
import json
import time
import base64
import random
import ctypes
import urllib.parse
import subprocess
import threading
import requests
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_SLOTS = ["06:00", "12:30", "18:00"]

IG_SESSION_FILE = "data/ig_session.json"
NOTIF_FILE = "data/notifications.json"
DELETED_IDS_FILE = "data/deleted_ids.json"

UPLOAD_PROGRESS_MAP = {}
GLOBAL_DELETED_IDS = set()
FILE_LOCK = threading.Lock()
TG_LAST_UPDATE_ID = 0

SERIES_TRACKS = [
    {"id": "romantic", "name": "Foji & Fojan Love Saga", "bgm": "romantic", "loc": "Snowy Kashmir Valley & Army Cantt"},
    {"id": "border_action", "name": "LOC Vigil & Braveheart", "bgm": "patriotic", "loc": "High Altitude Siachen & Border Outpost"},
    {"id": "emotional", "name": "Chithi & Homecoming", "bgm": "emotional", "loc": "Haryana Village Courtyard & Railway Station"},
    {"id": "comedy", "name": "Foji Nok-Jhok & Chai", "bgm": "upbeat", "loc": "Army Canteen & Festive Bazaar"},
    {"id": "patriotic", "name": "Tiranga Shaan & Duty", "bgm": "patriotic", "loc": "Regiment Parade Ground & War Memorial"}
]

# 25+ Fresh Story Situations so AI NEVER repeats old scripts!
DYNAMIC_STORY_SITUATIONS = [
    "Foji Makra surprises Fojan Meera by arriving home unannounced during Diwali festival with sweets",
    "Video call at midnight while Foji Makra is guarding a snowy bunker in Ladakh and Meera shows him the full moon",
    "Fojan Meera teasing Foji Makra about his strict morning PT routine while making hot adrak chai in the kitchen",
    "Foji Makra tying Fojan Meera's shoelace or fixing her dupatta before leaving at the railway station",
    "Rainy evening at the Army Cantonment garden where Foji Makra shares his umbrella with Fojan Meera",
    "Fojan Meera proudly pinning a bravery medal on Foji Makra's uniform before the Regiment Parade",
    "Foji Makra trying to cook rotis in the kitchen during leave and Fojan Meera laughing at his round map-shaped rotis",
    "Karwa Chauth night where Fojan Meera looks at Foji Makra through a sieve over a live video call from the border",
    "Foji Makra teaching Fojan Meera how to salute like a commando and both bursting into laughter",
    "Emotional goodbye at the village bus stand where Fojan Meera hands Foji Makra a tiffin of homemade desi ghee churma",
    "Holi celebration at the Army Camp where Foji Makra puts gulal on Fojan Meera's cheeks",
    "Foji Makra reading a handwritten love letter from Fojan Meera by a bonfire at a high-altitude post"
]


def trim_system_memory():
    try:
        gc.collect()
        if os.name != "nt":
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        # Auto-clean temporary ig_ready copies (>45 mins old) & candidate frame jpgs so disk NEVER fills up!
        now_t = time.time()
        if os.path.exists("output/ig_ready"):
            for fn in os.listdir("output/ig_ready"):
                fp = os.path.join("output/ig_ready", fn)
                if os.path.isfile(fp) and (now_t - os.path.getmtime(fp)) > 2700:
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
        if os.path.exists("output/raw_videos"):
            for fn in os.listdir("output/raw_videos"):
                if "_cand_" in fn and fn.endswith(".jpg"):
                    try:
                        os.remove(os.path.join("output/raw_videos", fn))
                    except Exception:
                        pass
    except Exception:
        pass


def start_memory_guard_daemon():
    def _mem_loop():
        while True:
            time.sleep(45)
            trim_system_memory()
    threading.Thread(target=_mem_loop, daemon=True).start()


if not os.environ.get("IS_CLOUD_WORKER"):
    start_memory_guard_daemon()


def ensure_data_files():
    global GLOBAL_DELETED_IDS
    os.makedirs("data", exist_ok=True)
    os.makedirs("output/raw_videos", exist_ok=True)
    os.makedirs("output/final_reels", exist_ok=True)

    if os.path.exists(DELETED_IDS_FILE):
        try:
            with open(DELETED_IDS_FILE, "r", encoding="utf-8") as f:
                GLOBAL_DELETED_IDS.update(str(x) for x in json.load(f))
        except Exception:
            pass
    else:
        with open(DELETED_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(GLOBAL_DELETED_IDS), f)

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
                "times": DEFAULT_SLOTS,
                "gen_times": ["05:30", "12:00", "17:30"],
                "button_locked": True,
                "gen_tried_log": {},
                "missed_slots_log": {},
                "completed_slots_log": {}
            }, f, indent=4)

    if not os.path.exists(NOTIF_FILE):
        with open(NOTIF_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)


def push_file_to_github_api(rel_path, commit_message, blocking=False):
    def _sync_worker():
        gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or "").strip()
        repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
        full_local = os.path.abspath(rel_path)
        if not os.path.exists(full_local):
            return

        if gh_pat:
            try:
                with open(full_local, "rb") as f:
                    content_b64 = base64.b64encode(f.read()).decode("utf-8")
                api_url = f"https://api.github.com/repos/{repo}/contents/{rel_path}"
                headers = {"Authorization": f"Bearer {gh_pat}", "Accept": "application/vnd.github+json"}
                get_r = requests.get(api_url, headers=headers, timeout=8)
                sha = get_r.json().get("sha") if get_r.status_code == 200 else None
                body = {"message": commit_message, "content": content_b64, "branch": "main"}
                if sha:
                    body["sha"] = sha
                put_r = requests.put(api_url, headers=headers, json=body, timeout=10)
                if put_r.status_code in (200, 201):
                    return
            except Exception:
                pass

        try:
            subprocess.run(["git", "config", "user.name", "AutoReels3D"], check=False)
            subprocess.run(["git", "config", "user.email", "engine@autoreels3d.ai"], check=False)
            subprocess.run(["git", "add", rel_path], check=False)
            subprocess.run(["git", "commit", "-m", commit_message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if gh_pat:
                remote_url = f"https://x-access-token:{gh_pat}@github.com/{repo}.git"
                subprocess.run(["git", "push", remote_url, "HEAD:main", "--force"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(["git", "push", "origin", "HEAD:main", "--force"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    if blocking:
        _sync_worker()
    else:
        threading.Thread(target=_sync_worker, daemon=True).start()


def log_notification(notif_type, title, message, status="info"):
    ensure_data_files()
    with FILE_LOCK:
        items = []
        if os.path.exists(NOTIF_FILE):
            try:
                with open(NOTIF_FILE, "r", encoding="utf-8") as f:
                    items = json.load(f)
            except Exception:
                items = []
        now_ist = datetime.now(IST)
        new_entry = {
            "id": f"notif_{int(time.time() * 1000)}_{random.randint(100, 999)}",
            "type": notif_type,
            "title": title,
            "message": message,
            "status": status,
            "time_str": now_ist.strftime("%I:%M %p"),
            "date_str": now_ist.strftime("%d %b %Y"),
            "timestamp": time.time()
        }
        items.insert(0, new_entry)
        items = items[:60]
        with open(NOTIF_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
    push_file_to_github_api("data/notifications.json", f"Log: {title[:30]}")
    return new_entry


def recalculate_track_parts(history_list):
    parts = {}
    for item in history_list:
        tid = item.get("track_id")
        if tid and item.get("video_completed"):
            parts[tid] = max(parts.get(tid, 0), int(item.get("part_number", 1)))
    return parts


def load_history():
    global GLOBAL_DELETED_IDS
    ensure_data_files()
    with FILE_LOCK:
        try:
            with open("data/history.json", "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"generated_count": 0, "track_parts": {}, "recent_tracks": [], "failed_dialogues": [], "deleted_ids": [], "history": []}

        GLOBAL_DELETED_IDS.update(str(x) for x in data.get("deleted_ids", []))
        valid_history = []
        for item in data.get("history", []):
            vid_str = str(item.get("video_id", item.get("id", "")))
            if vid_str in GLOBAL_DELETED_IDS:
                continue
            if item.get("video_completed") or item.get("status") in ("posted", "scheduled", "pending_approval"):
                valid_history.append(item)

        data["deleted_ids"] = list(GLOBAL_DELETED_IDS)
        data["history"] = valid_history
        data["track_parts"] = recalculate_track_parts(valid_history)
        return data


def save_history(data, sync_cloud=True, msg="Update reel history", blocking=False):
    global GLOBAL_DELETED_IDS
    with FILE_LOCK:
        GLOBAL_DELETED_IDS.update(str(x) for x in data.get("deleted_ids", []))
        data["deleted_ids"] = list(GLOBAL_DELETED_IDS)
        data["track_parts"] = recalculate_track_parts(data.get("history", []))
        with open(DELETED_IDS_FILE, "w", encoding="utf-8") as df:
            json.dump(list(GLOBAL_DELETED_IDS), df)
        with open("data/history.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    if sync_cloud:
        push_file_to_github_api(DELETED_IDS_FILE, msg, blocking=blocking)
        push_file_to_github_api("data/history.json", msg, blocking=blocking)


# ==============================================================================
# 🧠 100% DYNAMIC AI SCRIPT ENGINE (NO OLD REPEATED STATIC SCRIPTS!)
# ==============================================================================
def call_live_gemini_ai_brain(system_prompt, user_prompt):
    combined_prompt = f"{system_prompt}\n\nTask:\n{user_prompt}"
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if api_key:
        for m_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m_name}:generateContent?key={api_key}"
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": combined_prompt}]}],
                    "generationConfig": {"temperature": 0.95}
                }
                r = requests.post(url, json=payload, timeout=15)
                if r.status_code == 200:
                    cands = r.json().get("candidates", [])
                    if cands:
                        txt = cands[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        if txt:
                            return txt
            except Exception:
                continue

    for post_url in ["https://text.pollinations.ai/openai", "https://text.pollinations.ai/"]:
        try:
            r2 = requests.post(
                post_url,
                headers={"Content-Type": "application/json"},
                json={
                    "model": "openai",
                    "seed": random.randint(1000, 999999),
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                },
                timeout=15
            )
            if r2.status_code == 200:
                if post_url.endswith("/openai") or r2.text.strip().startswith("{"):
                    choices = r2.json().get("choices", [])
                    if choices:
                        txt = choices[0].get("message", {}).get("content", "").strip()
                        if txt:
                            return txt
                elif len(r2.text.strip()) > 10:
                    return r2.text.strip()
        except Exception:
            continue
    return ""


def get_next_track_and_part(history_data, forced_track_id=None):
    track_parts = recalculate_track_parts(history_data.get("history", []))
    recent = history_data.get("recent_tracks", [])
    chosen_track = SERIES_TRACKS[0]

    if forced_track_id:
        for t in SERIES_TRACKS:
            if t["id"] == forced_track_id:
                chosen_track = t
                break
    else:
        last_tid = recent[-1] if recent else None
        for idx, t in enumerate(SERIES_TRACKS):
            if t["id"] == last_tid:
                chosen_track = SERIES_TRACKS[(idx + 1) % len(SERIES_TRACKS)]
                break

    tid = chosen_track["id"]
    completed_part = track_parts.get(tid, 0)
    return chosen_track, completed_part + 1


def build_fresh_prompt_package(track, part_num, video_id, recent_dialogues=None):
    recent_dialogues = [d for d in (recent_dialogues or []) if d][-15:]
    now_ist = datetime.now(IST)
    situation_seed = random.choice(DYNAMIC_STORY_SITUATIONS)

    sys_instruction = (
        "You are an award-winning Indian 3D Pixar-style Cinema Director creating a brand new, unseen "
        "viral Instagram & Facebook Reel episode starring 'Foji Makra' (Indian Army Jawan with plain soldier shoulder straps, NO stars) "
        "and 'Fojan Meera' (his loving, expressive Indian wife). "
        "Write 100% original, heart-touching or witty Hinglish dialogues (6-8 words per character) that have NEVER been used before."
    )
    user_req = (
        f"Series Track: {track['name']} - Episode Part {part_num}.\n"
        f"Unique Story Situation for this Episode: {situation_seed} (Random Seed #{random.randint(10000,99999)}).\n"
        f"STRICTLY FORBIDDEN DIALOGUES (Never repeat these): {json.dumps(recent_dialogues, ensure_ascii=False)}\n"
        "Return ONLY valid JSON with keys: new_location, visual_action, dialogue_line_1_hinglish, dialogue_line_2_hinglish, music_direction, caption"
    )

    d1 = ""
    d2 = ""
    visual_action = situation_seed
    scene_setting = track["loc"]
    music_cue = f"Add soulful Bollywood {track['bgm']} instrumental background music."
    caption = ""

    for _ in range(3):
        try:
            ai_raw = call_live_gemini_ai_brain(sys_instruction, user_req)
            s_idx, e_idx = ai_raw.find("{"), ai_raw.rfind("}") + 1
            if s_idx != -1 and e_idx > s_idx:
                parsed = json.loads(ai_raw[s_idx:e_idx])
                cand_d1 = (parsed.get("dialogue_line_1_hinglish") or "").strip()
                cand_d2 = (parsed.get("dialogue_line_2_hinglish") or "").strip()
                if cand_d1 and cand_d1 not in recent_dialogues:
                    d1 = cand_d1
                    d2 = cand_d2
                    visual_action = parsed.get("visual_action") or visual_action
                    scene_setting = parsed.get("new_location") or scene_setting
                    music_cue = parsed.get("music_direction") or music_cue
                    caption = parsed.get("caption") or ""
                    break
        except Exception:
            pass

    if not d1:
        # Dynamic procedural generator if offline
        openers = [
            f"Meera, is bar chutti par tere hath ka churma pakka khayenge!",
            f"Fojan ji, border ki thand me bhi teri muskan garmi deti hai!",
            f"Dekh Meera, tirange ki shaan aur tera pyar hi meri taqat hai!",
            f"Meera, agli post se sidha gaon wali train pakad ke aa raha hu!"
        ]
        replies = [
            f"Jaldi aao Foji sahab, darwaze par diya jalaye baithi hu!",
            f"Aap salamat raho Foji ji, mera harpal aapke naam hai!",
            f"Batao kab aaoge, pura gaon apne Foji ka intezar kar raha hai!",
            f"Foji sahab, aapki vardi ki chamak se hi mera sindoor mahakta hai!"
        ]
        idx_pick = (video_id + int(time.time())) % len(openers)
        d1 = openers[idx_pick]
        d2 = replies[idx_pick]

    if not caption:
        caption = (
            f"❤️ {track['name']} • Part {part_num} 🇮🇳✨\n"
            f"🪖 \"{d1}\"\n"
            f"💖 \"{d2}\"\n.\n"
            f"#FojiFojan #IndianArmy #FojiLoveStory #3DAnimation #ArmyWife #DesiLove #ReelsIndia"
        )

    prompt = (
        f"Create a 9:16 vertical 3D Pixar Disney style 720p cinematic animated video using the two uploaded character images. "
        f"Character 1 is Foji Makra (handsome Indian Army Soldier/Jawan in camouflage uniform with plain shoulder straps, strictly NO stars). "
        f"Character 2 is Fojan Meera (beautiful young Indian woman in traditional attire). Keep their exact facial identity. "
        f"Setting: {scene_setting}. Action: {visual_action}. "
        f"From 0 to 4 seconds, Foji Makra speaks in Hindi with natural lip-sync and expression: \"{d1}\". "
        f"From 4 to 8 seconds, Fojan Meera replies in Hindi with emotional lip-sync: \"{d2}\". "
        f"Audio: {music_cue}"
    )

    return {
        "id": video_id,
        "video_id": video_id,
        "track_id": track["id"],
        "emotion_name": f"{track['name']} • Part {part_num}",
        "part_number": part_num,
        "bgm_folder": track["bgm"],
        "new_location": scene_setting,
        "dialogue_speaker_1": "Foji Makra",
        "dialogue_line_1_hinglish": d1,
        "dialogue_speaker_2": "Fojan Meera",
        "dialogue_line_2_hinglish": d2,
        "gemini_video_prompt": prompt,
        "caption": caption,
        "video_completed": False,
        "status": "pending_approval",
        "scheduled_slot": None,
        "created_at": now_ist.strftime("%d %b %Y, %I:%M %p")
    }


def send_telegram_approval_card(pkg, mp4_path=None):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    vid_id = pkg.get("video_id")
    caption_text = (
        f"🎬 *{pkg.get('emotion_name')}*\n"
        f"📍 {pkg.get('new_location')}\n\n"
        f"{pkg.get('caption')}"
    )
    keyboard = json.dumps({
        "inline_keyboard": [
            [
                {"text": "✅ Approve & Post (IG+FB)", "callback_data": f"approve_post:{vid_id}"},
                {"text": "⏰ Approve & Schedule", "callback_data": f"approve_sched:{vid_id}"}
            ],
            [
                {"text": "🔄 Regenerate", "callback_data": f"regen:{vid_id}"},
                {"text": "🗑️ Delete", "callback_data": f"delete:{vid_id}"}
            ]
        ]
    })
    try:
        if mp4_path and os.path.exists(mp4_path):
            with open(mp4_path, "rb") as vf:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendVideo",
                    data={"chat_id": chat_id, "caption": caption_text[:1000], "parse_mode": "Markdown", "reply_markup": keyboard},
                    files={"video": vf},
                    timeout=60
                )
                return
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": caption_text, "parse_mode": "Markdown", "reply_markup": json.loads(keyboard)},
            timeout=15
        )
    except Exception:
        pass


def generate_single_reel_package(custom_topic=None, send_for_approval=True, force_track_id=None, replace_video_id=None, batch_date=None):
    import gemini_bot
    hist = load_history()
    today_str = batch_date or datetime.now(IST).strftime("%Y-%m-%d")
    used_lines = [item.get("dialogue_line_1_hinglish", "") for item in hist.get("history", [])]
    used_lines.extend(hist.get("failed_dialogues", []))

    if replace_video_id is not None:
        target_pkg = next((i for i in hist["history"] if int(i.get("video_id", 0)) == int(replace_video_id)), None)
        tid = target_pkg.get("track_id", "romantic") if target_pkg else "romantic"
        pnum = int(target_pkg.get("part_number", 1)) if target_pkg else 1
        track = next((t for t in SERIES_TRACKS if t["id"] == tid), SERIES_TRACKS[0])
        candidate_pkg = build_fresh_prompt_package(track, pnum, int(replace_video_id), used_lines)
        raw_p = os.path.abspath(f"output/raw_videos/raw_video_{replace_video_id}.mp4")
        if os.path.exists(raw_p):
            try:
                os.remove(raw_p)
            except Exception:
                pass
    else:
        track, next_part = get_next_track_and_part(hist, forced_track_id=force_track_id)
        new_id = int(hist.get("generated_count", 0)) + 1
        candidate_pkg = build_fresh_prompt_package(track, next_part, new_id, used_lines)

    candidate_pkg["batch_date"] = today_str

    # Immediately record track & dialogue so even if generation fails, next attempt uses NEXT title & NEW script!
    hist.setdefault("recent_tracks", []).append(candidate_pkg.get("track_id", "romantic"))
    hist.setdefault("failed_dialogues", []).append(candidate_pkg.get("dialogue_line_1_hinglish", ""))
    save_history(hist, sync_cloud=False)

    out_path = gemini_bot.generate_video_in_gemini(pending_pkg=candidate_pkg)
    if not out_path or not gemini_bot.is_valid_mp4(out_path):
        raise RuntimeError("Video verification failed.")

    hist = load_history()
    candidate_pkg["video_completed"] = True
    candidate_pkg["video_url"] = f"/videos/raw_video_{candidate_pkg['video_id']}.mp4?t={int(time.time())}"
    candidate_pkg["file_size_kb"] = round(os.path.getsize(out_path) / 1024, 1)

    GLOBAL_DELETED_IDS.discard(str(candidate_pkg["video_id"]))
    hist["deleted_ids"] = list(GLOBAL_DELETED_IDS)

    if replace_video_id is not None:
        replaced = False
        for idx, item in enumerate(hist["history"]):
            if int(item.get("video_id", 0)) == int(replace_video_id):
                hist["history"][idx] = candidate_pkg
                replaced = True
                break
        if not replaced:
            hist["history"].append(candidate_pkg)
    else:
        hist["generated_count"] = max(int(hist.get("generated_count", 0)), int(candidate_pkg["video_id"]))
        hist["history"].append(candidate_pkg)

    save_history(hist, sync_cloud=True, msg=f"Add verified Flow reel #{candidate_pkg['video_id']}", blocking=True)
    log_notification("generated", "New Reel Ready", f"{candidate_pkg['emotion_name']} is ready.", "success")
    if send_for_approval:
        send_telegram_approval_card(candidate_pkg, mp4_path=out_path)
    trim_system_memory()
    return candidate_pkg


# ==============================================================================
# 🚀 INSTAGRAM + FACEBOOK REEL PUBLISHER (@ai_foji_lovelife + Connected FB Page)
# ==============================================================================
def _ensure_reel_thumbnail(video_file_path):
    """
    Smart Best-Frame Thumbnail Extractor:
    Extracts multiple candidate frames from the actual video (1.5s to 6.8s),
    scores each frame on Sharpness (edge variance), Brightness, Contrast, and Color Vibrancy,
    and saves the highest-scoring HD frame as the Reel thumbnail.
    NEVER uses the static character image unless the video file itself is unreadable.
    """
    import os
    import shutil
    import subprocess
    from PIL import Image, ImageStat, ImageFilter

    thumb_p = str(video_file_path) + ".jpg"
    # Always delete any old cached thumbnail so we fresh-pick from the video
    if os.path.exists(thumb_p):
        try:
            os.remove(thumb_p)
        except Exception:
            pass

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_bin = None

    best_img = None
    best_score = -1.0
    best_ts = "00:00:02.50"

    if ffmpeg_bin and os.path.exists(str(video_file_path)):
        candidate_timestamps = ["00:00:01.50", "00:00:02.80", "00:00:04.10", "00:00:05.40", "00:00:06.70"]
        for idx, ts in enumerate(candidate_timestamps):
            cand_path = f"{video_file_path}_cand_{idx}.jpg"
            try:
                subprocess.run(
                    [
                        ffmpeg_bin, "-y",
                        "-ss", ts,
                        "-i", str(video_file_path),
                        "-frames:v", "1",
                        "-q:v", "2",
                        cand_path
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=12
                )
                if os.path.exists(cand_path) and os.path.getsize(cand_path) > 5000:
                    with Image.open(cand_path) as im:
                        rgb = im.convert("RGB")
                        # 1. Brightness & Contrast check (avoid black/fade-in/washed-out frames)
                        gray = rgb.convert("L")
                        stat_g = ImageStat.Stat(gray)
                        mean_lum = stat_g.mean[0]       # Ideal: 60 to 200
                        std_contrast = stat_g.stddev[0] # Higher = better dynamic range

                        # Penalize very dark (<35) or overexposed (>235) frames
                        lum_penalty = 0.2 if (mean_lum < 35 or mean_lum > 235) else 1.0

                        # 2. Sharpness check (Laplacian/Edge variance)
                        edges = gray.filter(ImageFilter.FIND_EDGES)
                        sharpness = ImageStat.Stat(edges).stddev[0]

                        # 3. Color vibrancy check
                        stat_rgb = ImageStat.Stat(rgb)
                        color_spread = sum(stat_rgb.stddev) / 3.0

                        total_score = (sharpness * 2.2 + std_contrast * 1.5 + color_spread * 1.2) * lum_penalty
                        if total_score > best_score:
                            best_score = total_score
                            best_img = rgb.copy()
                            best_ts = ts
            except Exception:
                pass
            finally:
                if os.path.exists(cand_path):
                    try:
                        os.remove(cand_path)
                    except Exception:
                        pass

    if best_img is not None:
        best_img = best_img.resize((1080, 1920), Image.Resampling.LANCZOS)
        best_img.save(thumb_p, "JPEG", quality=95)
        print(f"🖼️ [Smart Thumbnail] Selected best video frame at {best_ts} (Score: {best_score:.1f}) -> { os.path.basename(thumb_p) }")
        return thumb_p

    # Emergency fallback only if video had 0 readable frames
    from PIL import Image
    fb = "assets/characters/foji_character.jpg"
    img = Image.open(fb).convert("RGB").resize((1080, 1920)) if os.path.exists(fb) else Image.new("RGB", (1080, 1920), (18, 18, 24))
    img.save(thumb_p, "JPEG", quality=92)
    return thumb_p


def get_authenticated_ig_client():
    import os
    import sys
    import json
    import time
    import urllib.parse
    import requests
    from instagrapi import Client

    ig_user = os.getenv("INSTAGRAM_USERNAME", "ai_foji_lovelife").strip().lstrip("@")
    ig_pass = os.getenv("INSTAGRAM_PASSWORD", "").strip()
    ig_sess_id = os.getenv("INSTAGRAM_SESSIONID", "").strip()

    MODERN_BLOKS = "ce5588ef227687c7fd27de3f190c0ec0fb21b2b10cd0f1b902122f1f1f7216b2"
    MODERN_DEVICE = {
        "app_version": "368.0.0.45.96",
        "android_version": 34,
        "android_release": "14.0",
        "dpi": "480dpi",
        "resolution": "1080x2400",
        "manufacturer": "Samsung",
        "device": "dm1q",
        "model": "SM-S911B",
        "cpu": "qcom",
        "version_code": "674523890"
    }
    MODERN_UA = (
        "Instagram 368.0.0.45.96 Android (34/14.0; 480dpi; 1080x2400; "
        "Samsung; SM-S911B; dm1q; qcom; en_US; 674523890)"
    )

    def _create_client():
        c = Client()
        c.delay_range = [1, 2]
        c.set_device(MODERN_DEVICE)
        c.set_user_agent(MODERN_UA)
        c.usdid_registered = True
        c.bloks_versioning_id = MODERN_BLOKS
        if hasattr(c, "settings") and isinstance(c.settings, dict):
            c.settings["bloks_versioning_id"] = MODERN_BLOKS
            c.settings.setdefault("device_settings", {}).update(MODERN_DEVICE)
            c.settings["device_settings"]["bloks_versioning_id"] = MODERN_BLOKS
        return c

    def _authenticate_with_sessionid_and_save(raw_sid, extra_cookies=None):
        clean_sid = urllib.parse.unquote(raw_sid.strip()).strip("\"'")
        cl = _create_client()

        if extra_cookies and isinstance(extra_cookies, dict):
            for k, v in extra_cookies.items():
                cl.private.cookies.set(k, v, domain=".instagram.com")
            if extra_cookies.get("csrftoken"):
                cl.private.headers.update({"X-CSRFToken": extra_cookies["csrftoken"]})

        cl.login_by_sessionid(clean_sid)

        os.makedirs("data", exist_ok=True)
        cl.dump_settings(IG_SESSION_FILE)

        try:
            with open(IG_SESSION_FILE, "r", encoding="utf-8") as f:
                sdata = json.load(f)
            sdata["bloks_versioning_id"] = MODERN_BLOKS
            sdata.setdefault("device_settings", {}).update(MODERN_DEVICE)
            sdata["device_settings"]["bloks_versioning_id"] = MODERN_BLOKS
            sdata.setdefault("authorization_data", {})["sessionid"] = clean_sid
            sdata.setdefault("cookies", {})["sessionid"] = clean_sid
            if extra_cookies and isinstance(extra_cookies, dict):
                sdata["cookies"].update(extra_cookies)
            with open(IG_SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(sdata, f, indent=2)
        except Exception:
            pass
        return cl

    def _capture_full_ig_cookies_via_real_chrome():
        import gemini_bot
        print("\n" + "=" * 75)
        print("📸 OPENING REAL CHROME FOR INSTAGRAM SESSION CAPTURE...")
        print("👉 Chrome mein Instagram khul raha hai. Apne naye password se Log In kar do!")
        print("👉 Jaise hi Instagram khulega, Bot khud `sessionid` + `csrftoken` save kar lega!")
        print("=" * 75 + "\n")

        driver, proc = gemini_bot.launch_resilient_chrome_session(os.path.abspath("output/raw_videos"), start_blank=False)
        try:
            driver.get("https://www.instagram.com/accounts/login/")
            time.sleep(3.5)
            filled_once = False

            for _ in range(120):
                time.sleep(2)
                try:
                    cookies = driver.get_cookies()
                    cookie_map = {c["name"]: urllib.parse.unquote(c["value"]) for c in cookies if "name" in c and "value" in c}
                    if cookie_map.get("sessionid") and len(cookie_map["sessionid"]) > 10:
                        print(f"\n🎉 CAPTURED LIVE INSTAGRAM SESSIONID & CSRFTOKEN FROM CHROME!")
                        return cookie_map["sessionid"], cookie_map

                    if not filled_once and ig_user and ig_pass:
                        filled = driver.execute_script(
                            """
                            const u = document.querySelector('input[name="username"], input[name="email"]');
                            const p = document.querySelector('input[name="password"], input[name="pass"]');
                            if (u && p && !u.value) {
                                const setVal = (el, val) => {
                                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                    setter.call(el, val);
                                    el.dispatchEvent(new Event('input', {bubbles: true}));
                                };
                                setVal(u, arguments[0]);
                                setVal(p, arguments[1]);
                                return true;
                            }
                            return false;
                            """,
                            ig_user,
                            ig_pass
                        )
                        if filled:
                            filled_once = True
                            print("   ✍️ Auto-filled username & password in Chrome! Click 'Log in' in Chrome window...")
                except Exception:
                    pass
        finally:
            try:
                driver.quit()
            except Exception:
                pass
            try:
                proc.terminate()
            except Exception:
                pass
        raise RuntimeError("Could not capture Instagram sessionid from Chrome within 4 minutes.")

    # 1. Use saved `data/ig_session.json` (Works on both Laptop & Render/GitHub Cloud!)
    if os.path.exists(IG_SESSION_FILE):
        try:
            with open(IG_SESSION_FILE, "r", encoding="utf-8") as f:
                sess_data = json.load(f)
            saved_sid = (
                sess_data.get("authorization_data", {}).get("sessionid")
                or sess_data.get("cookies", {}).get("sessionid")
                or ig_sess_id
            )
            saved_cookies = sess_data.get("cookies", {})
            if saved_sid and len(saved_sid) > 10:
                cl = _create_client()
                cl.load_settings(IG_SESSION_FILE, override_app_version=True)
                cl.usdid_registered = True
                cl.bloks_versioning_id = MODERN_BLOKS
                for k, v in saved_cookies.items():
                    cl.private.cookies.set(k, v, domain=".instagram.com")
                if saved_cookies.get("csrftoken"):
                    cl.private.headers.update({"X-CSRFToken": saved_cookies["csrftoken"]})
                cl.login_by_sessionid(urllib.parse.unquote(saved_sid))
                return cl
        except Exception as e:
            print(f"⚠️ Saved IG session note ({e}), refreshing...")

    # 2. Try INSTAGRAM_SESSIONID from .env / Environment
    if ig_sess_id and len(ig_sess_id) > 10:
        try:
            cl = _authenticate_with_sessionid_and_save(ig_sess_id)
            push_file_to_github_api(IG_SESSION_FILE, "Save verified IG session")
            return cl
        except Exception as e:
            print(f"⚠️ .env INSTAGRAM_SESSIONID note: {e}")

    # 3. On Windows Laptop: Open Real Chrome once and capture live `sessionid` + `csrftoken`!
    if os.name == "nt":
        live_sid, all_ig_cookies = _capture_full_ig_cookies_via_real_chrome()
        cl = _authenticate_with_sessionid_and_save(live_sid, all_ig_cookies)
        push_file_to_github_api(IG_SESSION_FILE, "Save verified IG session from Chrome")
        return cl

    raise RuntimeError(
        "Instagram session (`data/ig_session.json`) is missing or expired on Cloud! "
        "Run the Instagram login command once on your laptop and push `data/ig_session.json`."
    )

def publish_reel_item_to_instagram(video_id):
    """
    Uploads the Reel to Instagram (@ai_foji_lovelife) with `share_to_facebook` enabled
    so it automatically cross-posts to the linked Facebook Page!
    """
    vid_key = str(video_id)
    UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 15, "stage": "Verifying 720p MP4 file...", "status": "uploading", "error": ""}

    hist = load_history()
    target = next((i for i in hist.get("history", []) if str(i.get("video_id", "")) == vid_key), None)
    if not target:
        err = "Reel not found in queue."
        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 0, "stage": "Error", "status": "error", "error": err}
        return False, err

    raw_mp4 = os.path.abspath(f"output/raw_videos/raw_video_{video_id}.mp4")
    if not os.path.exists(raw_mp4):
        err = "Video file missing on server. Click Regenerate."
        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 0, "stage": "Missing File", "status": "error", "error": err}
        log_notification("error", "Upload Failed", err, "error")
        return False, err

    try:
        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 45, "stage": "Authenticating Instagram & Facebook...", "status": "uploading", "error": ""}
        cl = get_authenticated_ig_client()

        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 78, "stage": "Uploading Reel to Instagram + Facebook...", "status": "uploading", "error": ""}
        caption_txt = target.get("caption", "")
        try:
            media = cl.clip_upload(raw_mp4,
                caption=caption_txt,
                extra_data={
                    "share_to_facebook": "1",
                    "share_to_fb_reels": "1",
                    "crosspost_to_facebook": "1"
                }
            , thumbnail=_ensure_reel_thumbnail(raw_mp4))
        except TypeError:
            media = cl.clip_upload(raw_mp4, caption=caption_txt, thumbnail=_ensure_reel_thumbnail(raw_mp4))

        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 96, "stage": "Finalizing IG + FB post...", "status": "uploading", "error": ""}
        target["ig_media_id"] = str(media.id)
        target["code"] = str(media.code)
        target["permalink"] = f"https://www.instagram.com/reel/{media.code}/"
        target["status"] = "posted"
        target["scheduled_slot"] = None
        target["posted_at"] = datetime.now(IST).strftime("%d %b %Y, %I:%M %p")
        save_history(hist, sync_cloud=True, msg=f"Published Reel #{video_id} to IG+FB", blocking=True)

        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 100, "stage": "Published to IG + FB!", "status": "done", "error": ""}
        log_notification("posted", "Published to IG & Facebook", f"{target.get('emotion_name')} is now live.", "success")
        trim_system_memory()
        return True, "POSTED DONE"

    except Exception as e:
        err_msg = str(e)[:140]
        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 0, "stage": "Failed", "status": "error", "error": err_msg}
        log_notification("error", "Upload Failed", err_msg, "error")
        trim_system_memory()
        return False, err_msg


def trigger_github_7gb_worker(action_type="generate_only", custom_topic=""):
    gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or "").strip()
    repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
    if not gh_pat:
        return False
    try:
        r = requests.post(
            f"https://api.github.com/repos/{repo}/actions/workflows/cloud_video_engine.yml/dispatches",
            headers={"Authorization": f"Bearer {gh_pat}", "Accept": "application/vnd.github+json"},
            json={"ref": "main", "inputs": {"action_type": action_type, "custom_topic": custom_topic}},
            timeout=12
        )
        return r.status_code in (200, 201, 204)
    except Exception:
        return False


def assign_reel_to_specific_slot(vid_id, slot_str):
    vid_str = str(vid_id)
    hist = load_history()
    dt_obj = datetime.strptime(slot_str, "%H:%M")
    slot_label = dt_obj.strftime("%I:%M %p")
    for item in hist.get("history", []):
        if str(item.get("video_id", "")) == vid_str:
            item["status"] = "scheduled"
            item["scheduled_slot"] = slot_str
            item["scheduled_label"] = slot_label
            item["schedule_click_order"] = int(time.time())
            break
    save_history(hist, sync_cloud=True, msg=f"Auto-Schedule Reel #{vid_str} for {slot_str}", blocking=True)
    return slot_label


def assign_reel_to_next_schedule_slot(vid_id):
    vid_str = str(vid_id)
    hist = load_history()
    with open("data/schedule_config.json", "r", encoding="utf-8") as f:
        sched_cfg = json.load(f)
    slots = sched_cfg.get("times") or DEFAULT_SLOTS
    already_scheduled = [r for r in hist.get("history", []) if r.get("status") == "scheduled"]
    used_slots = [r.get("scheduled_slot") for r in already_scheduled]
    assigned_slot = slots[len(already_scheduled) % len(slots)]
    for s in sorted(slots):
        if s not in used_slots:
            assigned_slot = s
            break
    return assign_reel_to_specific_slot(vid_str, assigned_slot)


def delete_reel_permanently(vid_id):
    global GLOBAL_DELETED_IDS
    vid_str = str(vid_id)
    hist = load_history()
    deleted_title = f"Reel #{vid_str}"
    GLOBAL_DELETED_IDS.add(vid_str)
    hist["deleted_ids"] = list(GLOBAL_DELETED_IDS)

    new_hist = []
    for r in hist.get("history", []):
        if str(r.get("video_id", r.get("id", ""))) == vid_str:
            deleted_title = r.get("emotion_name", deleted_title)
        else:
            new_hist.append(r)
    hist["history"] = new_hist
    save_history(hist, sync_cloud=True, msg=f"Delete Reel #{vid_str}", blocking=True)

    raw_p = os.path.abspath(f"output/raw_videos/raw_video_{vid_str}.mp4")
    if os.path.exists(raw_p):
        try:
            os.remove(raw_p)
        except Exception:
            pass
    log_notification("deleted", "Post Deleted", f"{deleted_title} removed permanently.", "warning")
    return deleted_title


def trigger_reel_regeneration(vid_id):
    import gemini_bot
    vid_str = str(vid_id)
    gemini_bot.update_3d_telemetry(1, "Regenerating", "Opening Google Flow...", "active", 15)
    log_notification("generated", "Regenerating Reel", f"Creating fresh version for Reel #{vid_str}.", "info")

    def _regen_bg():
        if os.name != "nt" and not os.path.exists("/usr/bin/google-chrome"):
            if not trigger_github_7gb_worker(action_type="generate_only", custom_topic=f"REGEN_ID:{vid_str}"):
                gemini_bot.update_3d_telemetry(0, "Trigger Failed", "Check GITHUB_PAT.", "error", 0)
            return
        try:
            generate_single_reel_package(send_for_approval=True, replace_video_id=int(vid_str))
        except Exception as e:
            gemini_bot.update_3d_telemetry(0, "Paused", str(e)[:140], "error", 0)

    threading.Thread(target=_regen_bg, daemon=True).start()


def start_telegram_callback_listener():
    def _tg_loop():
        global TG_LAST_UPDATE_ID
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return
        while True:
            try:
                r = requests.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"offset": TG_LAST_UPDATE_ID + 1, "timeout": 10},
                    timeout=15
                )
                if r.status_code == 200:
                    for upd in r.json().get("result", []):
                        TG_LAST_UPDATE_ID = max(TG_LAST_UPDATE_ID, int(upd.get("update_id", 0)))
                        cb = upd.get("callback_query")
                        if not cb:
                            continue
                        cb_id = cb.get("id")
                        data_str = cb.get("data", "")
                        chat_id = cb.get("message", {}).get("chat", {}).get("id")
                        if ":" not in data_str:
                            continue
                        act, vid_id = data_str.split(":", 1)

                        if act == "approve_post":
                            requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "🚀 Uploading to IG + Facebook..."}, timeout=10)
                            def _post_notify(v=vid_id, cid=chat_id):
                                ok, msg = publish_reel_item_to_instagram(v)
                                txt = f"✅ *Reel #{v} Published to Instagram & Facebook!*" if ok else f"❌ *Upload Failed:* {msg}"
                                requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": cid, "text": txt, "parse_mode": "Markdown"}, timeout=10)
                            threading.Thread(target=_post_notify, daemon=True).start()

                        elif act == "approve_sched":
                            slot_lbl = assign_reel_to_next_schedule_slot(vid_id)
                            requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": f"⏰ Scheduled for {slot_lbl} IST"}, timeout=10)
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": f"⏰ *Reel #{vid_id} Scheduled* for `{slot_lbl} IST`!", "parse_mode": "Markdown"}, timeout=10)

                        elif act == "regen":
                            trigger_reel_regeneration(vid_id)
                            requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "🔄 Regenerating Reel..."}, timeout=10)
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": f"🔄 *Regenerating Reel #{vid_id}...*", "parse_mode": "Markdown"}, timeout=10)

                        elif act == "delete":
                            delete_reel_permanently(vid_id)
                            requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "🗑️ Reel Deleted"}, timeout=10)
                            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": f"🗑️ *Reel #{vid_id} Deleted Permanently.*", "parse_mode": "Markdown"}, timeout=10)
            except Exception:
                pass
            time.sleep(4)

    threading.Thread(target=_tg_loop, daemon=True).start()


if not os.environ.get("IS_CLOUD_WORKER"):
    start_telegram_callback_listener()


def compute_next_schedule_countdown(sched_cfg, scheduled_reels):
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")
    slots = sorted(sched_cfg.get("times") or DEFAULT_SLOTS)

    next_dt = None
    next_slot_label = ""
    for s in slots:
        try:
            dt = datetime.strptime(f"{today_str} {s}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
            if dt > now_ist:
                next_dt = dt
                next_slot_label = dt.strftime("%I:%M %p IST")
                break
        except Exception:
            pass

    if not next_dt:
        tomorrow_str = (now_ist + timedelta(days=1)).strftime("%Y-%m-%d")
        first_s = slots[0] if slots else "06:00"
        next_dt = datetime.strptime(f"{tomorrow_str} {first_s}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        next_slot_label = f"Tomorrow {next_dt.strftime('%I:%M %p IST')}"

    rem_sec = max(0, int((next_dt - now_ist).total_seconds()))
    return {
        "next_slot_label": next_slot_label,
        "remaining_seconds": rem_sec,
        "queued_count": len(scheduled_reels),
        "status_banner": "CLOUD AUTO-PILOT LIVE (5:30->6:00 AM • 12:00->12:30 PM • 5:30->6:00 PM)"
    }


def _stream_mp4_instantly(filename):
    from flask import request, Response, send_file
    safe_name = os.path.basename(str(filename))
    raw_dir = os.path.abspath("output/raw_videos")
    os.makedirs(raw_dir, exist_ok=True)
    p = os.path.join(raw_dir, safe_name)

    # If file was generated on Cloud and not yet on local/Render disk, fetch it once and cache it!
    if not os.path.exists(p) or os.path.getsize(p) < 1000:
        try:
            _fud.pull_latest_cloud_state_for_frontend()
        except Exception:
            pass
    if not os.path.exists(p) or os.path.getsize(p) < 1000:
        try:
            import requests as _req
            gh_raw_url = f"https://raw.githubusercontent.com/ramandhuwan7520-lab/foji-ai-studio/main/output/raw_videos/{safe_name}"
            r = _req.get(gh_raw_url, timeout=20)
            if r.status_code == 200 and len(r.content) > 10000:
                with open(p, "wb") as vf:
                    vf.write(r.content)
        except Exception:
            pass

    if not os.path.exists(p):
        return ("Video not found", 404)

    file_size = os.path.getsize(p)
    range_header = request.headers.get("Range", None)
    if range_header:
        m = re.search(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            byte1 = int(m.group(1))
            byte2 = int(m.group(2)) if m.group(2) else file_size - 1
            byte2 = min(byte2, file_size - 1)
            length = byte2 - byte1 + 1
            with open(p, "rb") as f:
                f.seek(byte1)
                data = f.read(length)
            rv = Response(data, 206, mimetype="video/mp4", direct_passthrough=True)
            rv.headers.add("Content-Range", f"bytes {byte1}-{byte2}/{file_size}")
            rv.headers.add("Accept-Ranges", "bytes")
            rv.headers.add("Content-Length", str(length))
            rv.headers.add("Cache-Control", "public, max-age=86400")
            return rv

    rv = send_file(p, mimetype="video/mp4", conditional=True, max_age=86400)
    rv.headers["Accept-Ranges"] = "bytes"
    return rv


@app.route("/videos/<path:filename>")
def serve_video(filename):
    return _stream_mp4_instantly(filename)


@app.route("/api/telemetry_3d", methods=["GET"])
def api_telemetry_3d():
    t_path = "data/live_telemetry.json"
    if os.path.exists(t_path):
        try:
            with open(t_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            age = time.time() - float(data.get("epoch", os.path.getmtime(t_path)))
            if data.get("status") in ("error", "completed", "idle"):
                data["step_num"] = 0
            elif data.get("status") == "active" and age > 180:
                data["status"] = "idle"
                data["step_num"] = 0
            return jsonify(data)
        except Exception:
            pass
    return jsonify({"step_num": 0, "step_title": "STANDBY", "sub_detail": "Ready", "status": "idle", "progress": 0})


@app.route("/api/reset_telemetry", methods=["POST"])
def api_reset_telemetry():
    t_path = "data/live_telemetry.json"
    idle_state = {"step_num": 0, "step_title": "STANDBY", "sub_detail": "Ready", "status": "idle", "progress": 0, "epoch": time.time()}
    with open(t_path, "w", encoding="utf-8") as f:
        json.dump(idle_state, f, indent=2)
    push_file_to_github_api(t_path, "Reset telemetry")
    return jsonify({"ok": True})


@app.route("/api/upload_status/<video_id>", methods=["GET"])
def api_upload_status(video_id):
    return jsonify(UPLOAD_PROGRESS_MAP.get(str(video_id), {"pct": 0, "stage": "Starting...", "status": "idle", "error": ""}))


@app.route("/api/state", methods=["GET"])
def api_state():
    hist = load_history()
    with open("data/schedule_config.json", "r", encoding="utf-8") as f:
        sched = json.load(f)
    next_track, next_part = get_next_track_and_part(hist)

    daily_reels = [
        r for r in reversed(hist.get("history", []))
        if r.get("video_completed") and r.get("status") != "posted"
    ]
    posted_history = [
        r for r in reversed(hist.get("history", []))
        if r.get("status") == "posted"
    ]
    scheduled_reels = [r for r in hist.get("history", []) if r.get("status") == "scheduled"]

    now_ist = datetime.now(IST)
    countdown_info = compute_next_schedule_countdown(sched, scheduled_reels)
    track_parts = hist.get("track_parts", {})

    return jsonify({
        "server_ist_time": now_ist.strftime("%I:%M:%S %p"),
        "server_ist_date": now_ist.strftime("%d %b %Y"),
        "countdown": countdown_info,
        "next_episode": {
            "track_id": next_track["id"],
            "series_name": next_track["name"],
            "next_part": next_part,
            "location": next_track["loc"],
            "all_tracks": [
                {"id": t["id"], "name": t["name"], "next_part": track_parts.get(t["id"], 0) + 1}
                for t in SERIES_TRACKS
            ]
        },
        "daily_reels": daily_reels,
        "posted_history": posted_history,
        "scheduled_reels": scheduled_reels,
        "schedule_config": sched
    })


@app.route("/api/generate_manual", methods=["POST"])
def api_generate_manual():
    import gemini_bot
    gemini_bot.update_3d_telemetry(1, "Opening Google Flow", "Starting Google Flow 720p pipeline...", "active", 15)
    log_notification("generated", "Generation Started", "Creating new 3D episode in Google Flow.", "info")

    def _bg():
        if os.name != "nt" and not os.path.exists("/usr/bin/google-chrome"):
            if not trigger_github_7gb_worker(action_type="generate_only"):
                err = "GITHUB_PAT missing in Render Environment!"
                log_notification("error", "Cloud Trigger Failed", err, "error")
                gemini_bot.update_3d_telemetry(0, "Trigger Failed", err, "error", 0)
            return
        try:
            generate_single_reel_package(send_for_approval=True)
        except Exception as e:
            err = str(e)[:180]
            log_notification("error", "Flow Notice", err, "error")
            gemini_bot.update_3d_telemetry(0, "Paused", err, "error", 0)

    threading.Thread(target=_bg, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/api/reel_action", methods=["POST"])
def api_reel_action():
    body = request.json or {}
    action = body.get("action")
    vid_id = str(body.get("video_id", ""))

    if action == "approve_post":
        UPLOAD_PROGRESS_MAP[vid_id] = {"pct": 10, "stage": "Starting IG + FB upload...", "status": "uploading", "error": ""}
        threading.Thread(target=lambda: publish_reel_item_to_instagram(vid_id), daemon=True).start()
        return jsonify({"ok": True, "started": True})

    elif action == "approve_schedule":
        slot_label = assign_reel_to_next_schedule_slot(vid_id)
        return jsonify({"ok": True, "slot_time": slot_label})

    elif action == "delete":
        delete_reel_permanently(vid_id)
        return jsonify({"ok": True})

    elif action == "regenerate":
        trigger_reel_regeneration(vid_id)
        return jsonify({"ok": True})

    return jsonify({"ok": False}), 400


@app.route("/api/save_schedule", methods=["POST"])
def api_save_schedule():
    body = request.json or {}
    times = body.get("times", DEFAULT_SLOTS)
    with open("data/schedule_config.json", "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["times"] = times
    cfg["enabled"] = True
    cfg["button_locked"] = True
    with open("data/schedule_config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)
    push_file_to_github_api("data/schedule_config.json", f"Lock schedule {times}", blocking=True)
    return jsonify({"ok": True, "times": times, "button_locked": True})


@app.route("/")
def index():
    return render_template_string(CLEAN_FAST_HTML)


CLEAN_FAST_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>

<script>
// 🛡️ GLOBAL FETCH JSON GUARD: Prevents "SyntaxError: Unexpected token '<'" if proxy returns HTML during heavy work
(function() {
    if (window.__fojiSafeJsonPatched) return;
    window.__fojiSafeJsonPatched = true;
    const origJson = Response.prototype.json;
    Response.prototype.json = async function() {
        const text = await this.text();
        try {
            return JSON.parse(text);
        } catch (err) {
            console.warn("Non-JSON response intercepted safely:", text.slice(0, 120));
            return {
                ok: false,
                status: "error",
                error: "Server busy or restarting — operation continues in background. Check Live Status!",
                message: "Server processing in background..."
            };
        }
    };
})();
</script>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AutoReels 3D AI — Google Flow Live Engine</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Space+Grotesk:wght@700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --gold: #f59e0b;
    --emerald: #10b981;
    --danger: #ef4444;
    --glass: rgba(15, 23, 42, 0.88);
    --border: rgba(255, 255, 255, 0.12);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Plus Jakarta Sans', sans-serif; background: #040711; color: #f8fafc; min-height: 100vh; }
  .lux-navbar {
    max-width: 1120px; margin: 16px auto; padding: 14px 22px;
    background: var(--glass); border: 1px solid var(--border); border-radius: 20px;
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;
  }
  .brand-title { font-family: 'Space Grotesk', sans-serif; font-size: 1.35rem; font-weight: 800; color: #fde68a; }
  .nav-tabs { display: flex; gap: 10px; }
  .nav-tab {
    padding: 10px 18px; border-radius: 12px; font-weight: 700; font-size: 0.9rem;
    color: #94a3b8; background: rgba(255,255,255,0.05); border: 1px solid transparent; cursor: pointer;
  }
  .nav-tab.active { color: #fff; background: rgba(16, 185, 129, 0.2); border-color: var(--emerald); }
  .ist-clock {
    font-family: 'Space Grotesk', monospace; font-size: 0.95rem; font-weight: 800;
    color: #fde68a; background: rgba(0,0,0,0.45); padding: 8px 14px; border-radius: 12px;
    border: 1px solid rgba(245, 158, 11, 0.4);
  }
  .container { max-width: 1120px; margin: 0 auto 60px; padding: 0 18px; }
  .page-section { display: none; }
  .page-section.active { display: block; }
  .lux-card { background: var(--glass); border: 1px solid var(--border); border-radius: 20px; padding: 22px; margin-bottom: 20px; }
  .btn-3d {
    cursor: pointer; border: none; font-family: inherit; font-weight: 700; font-size: 0.88rem;
    border-radius: 12px; padding: 11px 18px; color: #fff;
    background: linear-gradient(135deg, #10b981, #059669);
    display: inline-flex; align-items: center; gap: 8px;
  }
  .btn-3d:disabled { opacity: 0.45; cursor: not-allowed; }
  .btn-gold { background: linear-gradient(135deg, #f59e0b, #d97706); }
  .btn-danger { background: linear-gradient(135deg, #ef4444, #dc2626); }
  .btn-glass { background: rgba(255,255,255,0.09); border: 1px solid rgba(255,255,255,0.16); }
  .part-badge {
    display: inline-block; padding: 5px 12px; border-radius: 99px;
    background: rgba(245, 158, 11, 0.18); border: 1px solid var(--gold);
    color: #fde68a; font-weight: 800; font-size: 0.78rem;
  }
  .daily-card {
    display: grid; grid-template-columns: 230px 1fr; gap: 22px;
    background: rgba(15, 23, 42, 0.92); border: 1px solid var(--border);
    border-radius: 18px; padding: 18px; margin-bottom: 16px;
  }
  @media (max-width: 768px) { .daily-card { grid-template-columns: 1fr; } }
  .daily-card video { width: 100%; aspect-ratio: 9/16; border-radius: 12px; background: #000; object-fit: cover; }
  #pipeline-box {
    display: none; margin-bottom: 20px; padding: 20px;
    background: rgba(6, 78, 59, 0.35); border: 1px solid var(--emerald); border-radius: 18px;
  }
  .prog-track { width: 100%; height: 12px; background: rgba(255,255,255,0.1); border-radius: 99px; overflow: hidden; margin: 12px 0; }
  .prog-fill { height: 100%; width: 15%; background: linear-gradient(90deg, #10b981, #f59e0b); transition: width 0.4s; }
  .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 18px; }
  .modal-backdrop {
    position: fixed; inset: 0; z-index: 9999; background: rgba(3, 6, 14, 0.85);
    display: none; align-items: center; justify-content: center; padding: 16px;
  }
  .modal-backdrop.show { display: flex; }
  .modal-card {
    width: 100%; max-width: 420px; padding: 24px; border-radius: 20px;
    background: #0f172a; border: 1.5px solid var(--gold); text-align: center;
  }
</style>
</head>
<body>

<nav class="lux-navbar">
  <div>
    <div class="brand-title">🎬 AutoReels 3D AI (Google Flow 720p)</div>
    <div style="font-size:0.75rem;color:#94a3b8;">Instagram + Facebook Auto-Pilot • 6:00 AM • 12:30 PM • 6:00 PM</div>
  </div>
  <div class="nav-tabs">
    <button class="nav-tab active" onclick="switchPage('dashboard', this)">🎬 Generate & Approve</button>
    <button class="nav-tab" onclick="switchPage('schedule', this)">⏰ Schedule Slots</button>
  </div>
  <div class="ist-clock" id="ist-live-clock">--:--:-- IST</div>
</nav>

<div class="container">

  <section id="page-dashboard" class="page-section active">

    <div class="lux-card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;padding:16px 22px;">
      <div>
        <strong style="color:#34d399;font-size:0.92rem;" id="cd-status-banner">CLOUD AUTO-PILOT LIVE (5:30->6:00 AM • 12:00->12:30 PM • 5:30->6:00 PM)</strong>
        <div style="font-size:0.82rem;color:#cbd5e1;margin-top:2px;" id="cd-next-slot-txt">Next Post Slot: 06:00 AM IST</div>
      </div>
      <div style="font-family:'Space Grotesk',monospace;font-size:1.1rem;font-weight:800;color:#fde68a;" id="cd-reverse-timer">00h : 00m : 00s</div>
    </div>

    <div id="pipeline-box">
      <div style="display:flex;justify-content:space-between;font-weight:800;">
        <span id="pipe-title" style="color:#fde68a;">STEP 1: Opening Google Flow...</span>
        <span id="pipe-pct" style="color:#34d399;">15%</span>
      </div>
      <div class="prog-track"><div class="prog-fill" id="pipe-bar"></div></div>
      <div id="pipe-subdetail" style="font-size:0.82rem;color:#cbd5e1;">Initializing...</div>
    </div>

    <div class="lux-card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:18px;">
      <div>
        <span class="part-badge" id="next-ep-part">NEXT EPISODE • PART 1</span>
        <h2 style="font-size:1.4rem;font-weight:800;margin-top:8px;" id="next-ep-title">Foji & Fojan Love Saga</h2>
        <p style="color:#94a3b8;font-size:0.86rem;margin-top:4px;" id="next-ep-loc">📍 Snowy Kashmir Valley</p>
      </div>
      <button class="btn-3d btn-gold" onclick="triggerManualGenerate()" style="font-size:0.98rem;padding:14px 26px;">
        ⚡ Generate New 3D Reel (Flow 720p)
      </button>
    </div>

    <h3 style="margin-bottom:14px;font-size:1.15rem;">🎬 Approval & Scheduled Queue (<span id="badge-daily-cnt">0</span>)</h3>
    <div id="vault-daily-view"></div>

    <h3 style="margin:26px 0 14px;font-size:1.1rem;color:#94a3b8;">✅ Recently Posted on IG & Facebook (<span id="badge-posted-cnt">0</span>)</h3>
    <div id="vault-posted-view"></div>

  </section>

  <section id="page-schedule" class="page-section">
    <div class="lux-card">
      <h2 style="font-size:1.3rem;font-weight:800;margin-bottom:6px;">⏰ Daily Cloud Schedule (IST) — Works with Laptop OFF</h2>
      <p style="color:#94a3b8;font-size:0.84rem;margin-bottom:16px;">
        • Morning: Generates at <strong>05:30 AM</strong> &rarr; Posts at <strong>06:00 AM IST</strong> (IG + FB)<br>
        • Afternoon: Generates at <strong>12:00 PM</strong> &rarr; Posts at <strong>12:30 PM IST</strong> (IG + FB)<br>
        • Evening: Generates at <strong>05:30 PM</strong> &rarr; Posts at <strong>06:00 PM IST</strong> (IG + FB)
      </p>
      <div class="kpi-grid">
        <div style="background:rgba(0,0,0,0.4);padding:16px;border-radius:14px;border:1px solid var(--border);">
          <label style="color:#fde68a;font-weight:700;font-size:0.8rem;">🌅 MORNING POST (Gen @ 05:30)</label>
          <input type="time" id="slot-1" value="06:00" oninput="onScheduleTimeInputChanged()"
                 style="width:100%;margin-top:8px;padding:10px;border-radius:10px;background:#0f172a;color:#fff;border:1px solid #334155;font-size:1.05rem;font-weight:700;">
        </div>
        <div style="background:rgba(0,0,0,0.4);padding:16px;border-radius:14px;border:1px solid var(--border);">
          <label style="color:#fde68a;font-weight:700;font-size:0.8rem;">☀️ AFTERNOON POST (Gen @ 12:00)</label>
          <input type="time" id="slot-2" value="12:30" oninput="onScheduleTimeInputChanged()"
                 style="width:100%;margin-top:8px;padding:10px;border-radius:10px;background:#0f172a;color:#fff;border:1px solid #334155;font-size:1.05rem;font-weight:700;">
        </div>
        <div style="background:rgba(0,0,0,0.4);padding:16px;border-radius:14px;border:1px solid var(--border);">
          <label style="color:#fde68a;font-weight:700;font-size:0.8rem;">🌙 EVENING POST (Gen @ 17:30)</label>
          <input type="time" id="slot-3" value="18:00" oninput="onScheduleTimeInputChanged()"
                 style="width:100%;margin-top:8px;padding:10px;border-radius:10px;background:#0f172a;color:#fff;border:1px solid #334155;font-size:1.05rem;font-weight:700;">
        </div>
      </div>
      <button class="btn-3d btn-gold" id="btn-save-schedule" disabled onclick="saveScheduleConfig()" style="width:100%;padding:14px;justify-content:center;">
        Schedule Saved
      </button>
    </div>

    <div class="lux-card">
      <h3 style="font-size:1.1rem;margin-bottom:14px;">⏳ Scheduled Reels</h3>
      <div id="scheduled-pending-list"></div>
    </div>
  </section>

</div>

<div class="modal-backdrop" id="lux-modal">
  <div class="modal-card">
    <h3 id="modal-title" style="font-size:1.25rem;color:#fde68a;margin-bottom:8px;"></h3>
    <p id="modal-body" style="color:#cbd5e1;font-size:0.92rem;margin-bottom:18px;white-space:pre-line;"></p>
    <div id="modal-actions" style="display:flex;justify-content:center;gap:12px;"></div>
  </div>
</div>

<script>
  let appState = null;
  let lastHandledTelemetryEpoch = 0;
  let remainingCountdownSec = 0;
  let savedScheduleTimes = ["06:00", "12:30", "18:00"];
  let scheduleInputsDirty = false;

  setInterval(() => {
    const now = new Date();
    const istTime = now.toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
    document.getElementById('ist-live-clock').innerText = `🇮🇳 ${istTime.toUpperCase()} IST`;

    if (remainingCountdownSec > 0) {
      remainingCountdownSec--;
      const hrs = String(Math.floor(remainingCountdownSec / 3600)).padStart(2, '0');
      const mins = String(Math.floor((remainingCountdownSec % 3600) / 60)).padStart(2, '0');
      const secs = String(remainingCountdownSec % 60).padStart(2, '0');
      document.getElementById('cd-reverse-timer').innerText = `${hrs}h : ${mins}m : ${secs}s`;
    }
  }, 1000);

  function switchPage(pageId, btn) {
    document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.getElementById('page-' + pageId).classList.add('active');
    if (btn) btn.classList.add('active');
  }

  function showModal(title, body, buttons = [{ label: "OK", cls: "btn-gold", onClick: closeModal }]) {
    document.getElementById('modal-title').innerText = title;
    document.getElementById('modal-body').innerText = body;
    const act = document.getElementById('modal-actions');
    act.innerHTML = '';
    buttons.forEach(b => {
      const el = document.createElement('button');
      el.className = 'btn-3d ' + (b.cls || '');
      el.innerText = b.label;
      el.onclick = b.onClick;
      act.appendChild(el);
    });
    document.getElementById('lux-modal').classList.add('show');
  }

  function closeModal() {
    document.getElementById('lux-modal').classList.remove('show');
  }

  function triggerManualGenerate() {
    fetch('/api/generate_manual', { method: 'POST' }).then(() => {
      showModal("🚀 Google Flow Pipeline Started", "Uploading Foji & Fojan + Fresh Dynamic AI Script in Google Flow (720p).");
      pollTelemetryLoop();
    });
  }

  function handleApproveAndPost(videoId) {
    showModal("🚀 Publishing...", "Uploading Reel to Instagram & Linked Facebook Page...", []);
    fetch('/api/reel_action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ action: 'approve_post', video_id: videoId })
    }).then(() => {
      const pollIv = setInterval(async () => {
        try {
          const r = await fetch('/api/upload_status/' + videoId);
          const st = await r.json();
          document.getElementById('modal-body').innerText = `${st.stage || 'Uploading...'} (${st.pct || 15}%)`;
          if (st.status === 'done') {
            clearInterval(pollIv);
            fetchAppState();
            showModal("✅ Published!", "Reel is now live on Instagram & Facebook!");
          } else if (st.status === 'error') {
            clearInterval(pollIv);
            fetchAppState();
            showModal("❌ Upload Failed", st.error || "Failed to upload reel.");
          }
        } catch (e) {}
      }, 1000);
    });
  }

  function handleApproveAndSchedule(videoId) {
    fetch('/api/reel_action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ action: 'approve_schedule', video_id: videoId })
    }).then(r => r.json()).then(res => {
      fetchAppState();
      showModal("⏰ Scheduled", `Reel will auto-post to IG + FB at ${res.slot_time || 'Next Slot'} IST.`);
    });
  }

  function handleRegenerateReel(videoId) {
    fetch('/api/reel_action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ action: 'regenerate', video_id: videoId })
    }).then(() => {
      showModal("🔄 Regenerating...", "Creating fresh 720p video with a brand new script in Google Flow.");
      pollTelemetryLoop();
    });
  }

  function handleDeleteReel(videoId) {
    showModal("Delete Reel?", "Remove this reel permanently?", [
      {
        label: "YES, DELETE",
        cls: "btn-danger",
        onClick: () => {
          closeModal();
          fetch('/api/reel_action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ action: 'delete', video_id: videoId })
          }).then(() => fetchAppState());
        }
      },
      { label: "CANCEL", cls: "btn-glass", onClick: closeModal }
    ]);
  }

  function onScheduleTimeInputChanged() {
    const t1 = document.getElementById('slot-1').value;
    const t2 = document.getElementById('slot-2').value;
    const t3 = document.getElementById('slot-3').value;
    const btn = document.getElementById('btn-save-schedule');
    const changed = (t1 !== savedScheduleTimes[0] || t2 !== savedScheduleTimes[1] || t3 !== savedScheduleTimes[2]);
    scheduleInputsDirty = changed;
    btn.disabled = !changed;
    btn.innerText = changed ? "Save Schedule" : "Schedule Saved";
  }

  function saveScheduleConfig() {
    const t1 = document.getElementById('slot-1').value || "06:00";
    const t2 = document.getElementById('slot-2').value || "12:30";
    const t3 = document.getElementById('slot-3').value || "18:00";
    fetch('/api/save_schedule', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ times: [t1, t2, t3] })
    }).then(() => {
      savedScheduleTimes = [t1, t2, t3];
      scheduleInputsDirty = false;
      const sBtn = document.getElementById('btn-save-schedule');
      sBtn.disabled = true;
      sBtn.innerText = "Schedule Saved";
      fetchAppState();
      showModal("✅ Schedule Saved", `Locked at ${t1} • ${t2} • ${t3} IST`);
    });
  }

  async function fetchAppState() {
    try {
      const r = await fetch('/api/state');
      appState = await r.json();

      if (appState.countdown) {
        remainingCountdownSec = appState.countdown.remaining_seconds || 0;
        document.getElementById('cd-status-banner').innerText = appState.countdown.status_banner;
        document.getElementById('cd-next-slot-txt').innerText = `Next Slot: ${appState.countdown.next_slot_label} • Scheduled: ${appState.countdown.queued_count}`;
      }

      const ne = appState.next_episode;
      document.getElementById('next-ep-part').innerText = `NEXT EPISODE • PART ${ne.next_part}`;
      document.getElementById('next-ep-title').innerText = ne.series_name;
      document.getElementById('next-ep-loc').innerText = `📍 ${ne.location}`;

      const dailyList = appState.daily_reels || [];
      const postedList = appState.posted_history || [];
      document.getElementById('badge-daily-cnt').innerText = dailyList.length;
      document.getElementById('badge-posted-cnt').innerText = postedList.length;

      document.getElementById('vault-daily-view').innerHTML = dailyList.map(item => {
        const isScheduled = (item.status === 'scheduled');
        return `
        <div class="daily-card">
          <video src="${item.video_url || ''}" controls playsinline preload="metadata"></video>
          <div style="display:flex;flex-direction:column;justify-content:space-between;">
            <div>
              <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                <span class="part-badge">${item.emotion_name || 'Episode'}</span>
                <span style="font-size:0.78rem;color:#94a3b8;">🕒 ${item.created_at || ''}</span>
                ${isScheduled
                  ? `<span style="background:rgba(16,185,129,0.2);border:1px solid #10b981;color:#6ee7b7;padding:4px 12px;border-radius:99px;font-weight:800;font-size:0.76rem;">
                       ⏰ Scheduled • ${item.scheduled_label || item.scheduled_slot} IST
                     </span>`
                  : `<span style="background:rgba(245,158,11,0.2);color:#fde68a;padding:4px 12px;border-radius:99px;font-weight:800;font-size:0.76rem;">
                       Waiting for Approval
                     </span>`
                }
              </div>
              <p style="margin-top:12px;background:rgba(0,0,0,0.45);padding:14px;border-radius:12px;font-size:0.88rem;color:#e2e8f0;white-space:pre-line;">${item.caption || ''}</p>
            </div>
            <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;">
              <button class="btn-3d" onclick="handleApproveAndPost('${item.video_id}')">✅ Approve & Post (IG+FB)</button>
              ${!isScheduled ? `
                <button class="btn-3d btn-gold" onclick="handleApproveAndSchedule('${item.video_id}')">⏰ Approve & Schedule</button>
              ` : ''}
              <button class="btn-3d btn-glass" onclick="handleRegenerateReel('${item.video_id}')">🔄 Regenerate</button>
              <button class="btn-3d btn-danger" onclick="handleDeleteReel('${item.video_id}')">🗑️ Delete</button>
            </div>
          </div>
        </div>`;
      }).join('') || `<div class="lux-card" style="color:#94a3b8;text-align:center;">No reels in queue. Click 'Generate New 3D Reel' above!</div>`;

      document.getElementById('vault-posted-view').innerHTML = postedList.map(item => `
        <div class="daily-card">
          <video src="${item.video_url || ''}" controls playsinline preload="metadata"></video>
          <div>
            <span class="part-badge">${item.emotion_name || 'Posted Reel'}</span>
            <span style="color:#34d399;font-weight:800;font-size:0.84rem;margin-left:10px;">✅ Posted (IG+FB) • ${item.posted_at || ''}</span>
            <p style="margin-top:12px;background:rgba(0,0,0,0.45);padding:14px;border-radius:12px;font-size:0.88rem;color:#e2e8f0;white-space:pre-line;">${item.caption || ''}</p>
          </div>
        </div>
      `).join('') || `<div class="lux-card" style="color:#94a3b8;text-align:center;">No posted reels yet.</div>`;

      if (!scheduleInputsDirty && appState.schedule_config && appState.schedule_config.times) {
        savedScheduleTimes = appState.schedule_config.times;
        document.getElementById('slot-1').value = savedScheduleTimes[0] || "06:00";
        document.getElementById('slot-2').value = savedScheduleTimes[1] || "12:30";
        document.getElementById('slot-3').value = savedScheduleTimes[2] || "18:00";
        const sBtn = document.getElementById('btn-save-schedule');
        sBtn.disabled = true;
        sBtn.innerText = "Schedule Saved";
      }

      document.getElementById('scheduled-pending-list').innerHTML = (appState.scheduled_reels || []).map(item => `
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;padding:14px;background:rgba(255,255,255,0.05);border:1px solid var(--emerald);border-radius:14px;margin-bottom:10px;">
          <div>
            <strong style="color:#fde68a;">🎬 ${item.emotion_name}</strong>
            <div style="font-size:0.82rem;color:#cbd5e1;margin-top:4px;">
              Auto-Post Time: <strong style="color:#34d399;">${item.scheduled_label || item.scheduled_slot} IST</strong>
            </div>
          </div>
          <div style="display:flex;gap:8px;">
            <button class="btn-3d" onclick="handleApproveAndPost('${item.video_id}')">🚀 Post Now (IG+FB)</button>
            <button class="btn-3d btn-danger" onclick="handleDeleteReel('${item.video_id}')">🗑️ Delete</button>
          </div>
        </div>
      `).join('') || `<p style="color:#94a3b8;">No scheduled reels waiting.</p>`;
    } catch (e) {}
  }

  async function pollTelemetryLoop() {
    try {
      const r = await fetch('/api/telemetry_3d');
      const t = await r.json();
      const box = document.getElementById('pipeline-box');
      const tEpoch = parseFloat(t.epoch || 0);

      if (t.status === 'active' && t.step_num >= 1) {
        box.style.display = 'block';
        const pct = t.progress || 15;
        document.getElementById('pipe-title').innerText = `STEP ${t.step_num}/6: ${t.step_title || 'Processing...'}`;
        document.getElementById('pipe-pct').innerText = pct + '%';
        document.getElementById('pipe-bar').style.width = pct + '%';
        document.getElementById('pipe-subdetail').innerText = t.sub_detail || '';
      } else {
        box.style.display = 'none';
        if (t.status === 'completed' && tEpoch > lastHandledTelemetryEpoch) {
          lastHandledTelemetryEpoch = tEpoch;
          fetch('/api/reset_telemetry', { method: 'POST' });
          fetchAppState();
          showModal("🎬 3D Reel Ready!", "720p Video downloaded from Google Flow & added to Queue!");
        } else if (t.status === 'error' && t.sub_detail && tEpoch > lastHandledTelemetryEpoch) {
          lastHandledTelemetryEpoch = tEpoch;
          fetch('/api/reset_telemetry', { method: 'POST' });
          fetchAppState();
          showModal("💬 Flow Notice", t.sub_detail);
        }
      }
    } catch (e) {}
  }

  setInterval(pollTelemetryLoop, 2500);
  setInterval(fetchAppState, 12000);
  fetchAppState();
</script>
</body>
</html>
"""

# ==============================================================================
# 🎖️ FOJI UNIVERSE DIRECTOR — ZERO-LAG PIPELINE + POPUP MODAL + MASTER VAULT UI
# ==============================================================================
import threading as _threading
import foji_universe_director as _fud
from flask import send_file as _send_file

_orig_build_fresh_prompt_package = globals().get("build_fresh_prompt_package")

def build_fresh_prompt_package(track=None, next_part=1, new_id=1, used_lines=None):
    return _fud.build_real_foji_universe_package(video_id=new_id, is_preview=False)


def _execute_single_or_batch_generation(count=1, reason_label="Manual Trigger", custom_idea=""):
    def _worker():
        for i in range(1, int(count) + 1):
            try:
                import gemini_bot
                gemini_bot.update_3d_telemetry(
                    1,
                    f"Stage 1: AI Script ({i}/{count})",
                    f"Writing fresh script via .env API ({reason_label})...",
                    "active",
                    12
                )
                pkg = _fud.build_real_foji_universe_package(
                    video_id=int(time.time()) % 100000,
                    custom_idea=custom_idea if i == 1 else "",
                    is_preview=False
                )
                gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or "").strip()
                repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
                dispatched_cloud = False
                if os.name != "nt" and gh_pat:
                    headers = {"Authorization": f"Bearer {gh_pat}", "Accept": "application/vnd.github+json"}
                    wf_url = f"https://api.github.com/repos/{repo}/actions/workflows/cloud_video_engine.yml/dispatches"
                    r = requests.post(wf_url, headers=headers, json={"ref": "main"}, timeout=15)
                    if r.status_code in (200, 201, 204):
                        dispatched_cloud = True
                        gemini_bot.update_3d_telemetry(
                            2,
                            "Stage 2: Cloud Engine Dispatched",
                            "GitHub Actions Chrome Worker is starting Cookie Login...",
                            "active",
                            24
                        )

                if not dispatched_cloud:
                    vid_path = gemini_bot.generate_video_in_gemini(pkg)
                    if vid_path and os.path.exists(vid_path):
                        _fud.mark_episode_part_completed(pkg["track_id"], pkg["part_number"])
                        _fud.sync_raw_videos_into_unapproved_queue()
            except Exception as ex:
                try:
                    import gemini_bot
                    gemini_bot.update_3d_telemetry(1, "Pipeline Error", str(ex)[:200], "error", 0)
                    gemini_bot.push_app_notification("error", "Pipeline Failed", str(ex)[:200], "error")
                except Exception:
                    pass
    _threading.Thread(target=_worker, daemon=True).start()


def _sanitize_mp4_for_instagram_no_green_line(input_mp4_path):
    """
    Ultra-fast Instagram Reel optimizer: ensures faststart header and 720x1280 yuv420p compatibility
    without crashing Render RAM or hitting 30s worker timeout.
    """
    if not input_mp4_path or not os.path.exists(input_mp4_path):
        return input_mp4_path

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        try:
            import imageio_ffmpeg
            ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_bin = None
    if not ffmpeg_bin:
        return input_mp4_path

    clean_dir = os.path.abspath("output/ig_ready")
    os.makedirs(clean_dir, exist_ok=True)
    base_name = os.path.basename(input_mp4_path)
    clean_out_path = os.path.join(clean_dir, f"ig_clean_{base_name}")

    if os.path.exists(clean_out_path) and os.path.getsize(clean_out_path) > 50 * 1024:
        return clean_out_path

    try:
        # On Render Cloud (limited RAM/CPU), do a 0.3s lossless stream copy + faststart first
        # so the HTTP request never times out after 30s!
        if os.environ.get("RENDER") or os.name != "nt":
            cmd_fast = [
                ffmpeg_bin, "-y", "-i", input_mp4_path,
                "-c", "copy", "-movflags", "+faststart", clean_out_path
            ]
            r = subprocess.run(cmd_fast, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
            if r.returncode == 0 and os.path.exists(clean_out_path) and os.path.getsize(clean_out_path) > 50 * 1024:
                return clean_out_path

        cmd = [
            ffmpeg_bin, "-y",
            "-i", input_mp4_path,
            "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-threads", "1",
            "-profile:v", "high",
            "-level:v", "4.0",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-movflags", "+faststart",
            clean_out_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        if os.path.exists(clean_out_path) and os.path.getsize(clean_out_path) > 50 * 1024:
            return clean_out_path
    except Exception as e:
        print(f"⚠️ Fast IG Sanitizer note: {e}")

    return input_mp4_path



def _publish_specific_video_to_ig(video_file, custom_caption=""):
    vname = os.path.basename(str(video_file))
    vpath = os.path.abspath(os.path.join("output/raw_videos", vname))
    if not os.path.exists(vpath):
        try:
            _fud.pull_latest_cloud_state_for_frontend()
        except Exception:
            pass
    if not os.path.exists(vpath):
        try:
            import requests as _req
            gh_raw_url = f"https://raw.githubusercontent.com/ramandhuwan7520-lab/foji-ai-studio/main/output/raw_videos/{vname}"
            r = _req.get(gh_raw_url, timeout=20)
            if r.status_code == 200 and len(r.content) > 10000:
                os.makedirs(os.path.dirname(vpath), exist_ok=True)
                with open(vpath, "wb") as vf:
                    vf.write(r.content)
        except Exception:
            pass
    if not os.path.exists(vpath):
        raise FileNotFoundError(f"Video file {vname} not found in output/raw_videos!")

    if not custom_caption:
        for it in _fud.build_master_all_reels_vault():
            if it.get("video_file") == vname and it.get("caption"):
                custom_caption = it["caption"]
                break
    if not custom_caption:
        custom_caption = "🎖️ Foji & Fojan 3D Story | Follow @ai_foji_lovelife 🇮🇳🔥 #indianarmy #faujilife #agniveer #armyreels"

    try:
        import gemini_bot
        gemini_bot.update_3d_telemetry(3, "Preparing IG Reel", f"Optimizing {vname} for Instagram...", "active", 40)
    except Exception:
        pass

    ig_safe_vpath = _sanitize_mp4_for_instagram_no_green_line(vpath)
    thumb_path = _ensure_reel_thumbnail(ig_safe_vpath)

    try:
        import gemini_bot
        gemini_bot.update_3d_telemetry(6, "Uploading to Instagram", f"Publishing {vname} to @ai_foji_lovelife...", "active", 75)
    except Exception:
        pass

    # DIRECT CALL to verified get_authenticated_ig_client() (User ID: 22494488394) — NO circular insta_bot loop!
    cl = get_authenticated_ig_client()
    try:
        media = cl.clip_upload(
            ig_safe_vpath,
            caption=custom_caption,
            thumbnail=thumb_path,
            extra_data={
                "share_to_facebook": "1",
                "share_to_fb_reels": "1",
                "crosspost_to_facebook": "1"
            }
        )
    except TypeError:
        media = cl.clip_upload(ig_safe_vpath, caption=custom_caption, thumbnail=thumb_path)

    media_pk = getattr(media, "pk", None) or getattr(media, "id", None)
    media_code = getattr(media, "code", "")
    if not media_pk:
        raise RuntimeError("Instagram did not return a valid Media PK! Reel kept safely in Unposted Vault.")

    pub_item = _fud.mark_video_as_published_in_vault(vname, custom_caption, media_pk=str(media_pk))
    if isinstance(pub_item, dict) and media_code:
        pub_item["code"] = str(media_code)
        pub_item["permalink"] = f"https://www.instagram.com/reel/{media_code}/"

    try:
        import gemini_bot
        gemini_bot.update_3d_telemetry(8, "Reel LIVE on Instagram!", f"✅ {vname} Published (ID: {media_pk})!", "completed", 100)
        gemini_bot.push_app_notification("success", "📸 Reel Posted on Instagram!", f"{vname} is now LIVE on @ai_foji_lovelife!", "success")
        gemini_bot.send_alert(f"📸 Reel Published on Instagram! Video: {vname} | Permalink: https://www.instagram.com/reel/{media_code}/")
    except Exception:
        pass
    return pub_item


# Bridge any legacy Telegram Bot schedule function into our Unified Sequential Scheduler!
for _legacy_sched_fn in ["schedule_video_for_next_slot", "add_to_schedule_queue", "schedule_reel", "queue_video_for_schedule"]:
    if _legacy_sched_fn in globals():
        def _unified_tg_schedule_bridge(video_path=None, caption="", *args, **kwargs):
            vfile = os.path.basename(str(video_path)) if video_path else None
            item = _fud.approve_and_schedule_video_item(video_file=vfile, custom_caption=caption, source_label="Telegram Bot")
            return item["scheduled_display"]
        globals()[_legacy_sched_fn] = _unified_tg_schedule_bridge

def _background_master_scheduler_daemon():
    while True:
        try:
            now_ist = datetime.now(_fud.IST)
            today_str = now_ist.strftime("%Y-%m-%d")
            curr_hm = now_ist.strftime("%H:%M")

            cfg = _fud.get_schedule_config()
            if cfg.get("auto_pilot_enabled", True):
                triggered = set(cfg.get("last_triggered_keys", []))

                night_hm = cfg.get("night_batch_time", "02:30")
                night_key = f"NIGHT_BATCH_{today_str}_{night_hm}"
                if curr_hm == night_hm and night_key not in triggered:
                    triggered.add(night_key)
                    cfg["last_triggered_keys"] = list(triggered)[-60:]
                    _fud.save_schedule_config(cfg)
                    batch_cnt = int(cfg.get("night_batch_count", 3))
                    _execute_single_or_batch_generation(count=batch_cnt, reason_label=f"02:30 AM Night Batch ({batch_cnt} Videos)")

                pre_mins = int(cfg.get("pre_slot_minutes", 30))
                for slot_hm in cfg.get("daily_slots", ["07:00", "13:30", "19:30"]):
                    try:
                        sh, sm = [int(x) for x in slot_hm.split(":")]
                        slot_dt = now_ist.replace(hour=sh, minute=sm, second=0, microsecond=0)
                        pre_dt = slot_dt - timedelta(minutes=pre_mins)
                        pre_hm = pre_dt.strftime("%H:%M")
                        pre_key = f"PRE30_{today_str}_{slot_hm}"
                        if curr_hm == pre_hm and pre_key not in triggered:
                            triggered.add(pre_key)
                            cfg["last_triggered_keys"] = list(triggered)[-60:]
                            _fud.save_schedule_config(cfg)
                            _execute_single_or_batch_generation(count=1, reason_label=f"T-30 Min Pre-Schedule Trigger (Before {slot_hm})")
                    except Exception:
                        pass

                q = _fud.get_scheduled_queue()
                sched_list = list(q.get("scheduled_posts", []))
                for post in sched_list:
                    due_epoch = float(post.get("scheduled_epoch", 0))
                    if due_epoch > 0 and time.time() >= due_epoch:
                        vfile = post.get("video_file", "")
                        vpath = os.path.join("output/raw_videos", vfile)
                        if os.path.exists(vpath):
                            try:
                                media = _publish_specific_video_to_ig(vpath, post.get("caption", ""))
                                pk_val = getattr(media, "pk", "LIVE")
                                _fud.mark_video_as_published_in_vault(vfile, post.get("caption", ""), pk_val)
                                import gemini_bot
                                gemini_bot.push_app_notification(
                                    "success",
                                    "📲 Scheduled Reel Posted to IG!",
                                    f"{post.get('title', vfile)} published on @ai_foji_lovelife!",
                                    "success"
                                )
                            except Exception as pub_err:
                                import gemini_bot
                                gemini_bot.push_app_notification("error", "❌ Scheduled IG Post Failed", str(pub_err)[:180], "error")
        except Exception:
            pass
        time.sleep(20)

if not globals().get("_FOJI_MASTER_SCHEDULER_STARTED"):
    globals()["_FOJI_MASTER_SCHEDULER_STARTED"] = True
    _threading.Thread(target=_background_master_scheduler_daemon, daemon=True).start()


@app.route("/api/universe/status", methods=["GET"])
def api_universe_status():
    from flask import jsonify
    try:
        _fud.pull_latest_cloud_state_for_frontend()
    except Exception:
        pass
    health = _fud.get_real_system_health()
    q = _fud.sync_raw_videos_into_unapproved_queue()
    vault = _fud.build_master_all_reels_vault()
    cfg = _fud.get_schedule_config()
    next_open_slot = _fud.calculate_next_available_slot_ist()

    notifs = []
    if os.path.exists("data/notifications.json"):
        try:
            with open("data/notifications.json", "r", encoding="utf-8") as f:
                notifs = json.load(f)[:25]
        except Exception:
            pass

    health["notifications"] = notifs
    health["schedule"] = cfg
    health["queue"] = q
    health["master_vault"] = vault
    health["next_open_slot"] = next_open_slot
    health["server_time_ist"] = datetime.now(_fud.IST).strftime("%I:%M:%S %p IST")
    return jsonify(health)


@app.route("/api/universe/select_track", methods=["POST"])
def api_universe_select_track():
    from flask import request, jsonify
    data = request.get_json(force=True, silent=True) or {}
    st = _fud.get_director_state()
    for k in ["active_mode", "selected_track_id", "custom_idea", "bgm_volume", "dialog_volume"]:
        if k in data:
            st[k] = data[k]
    _fud.save_director_state(st)
    return jsonify({"ok": True, "state": st})


@app.route("/api/universe/generate_preview_script", methods=["POST"])
def api_universe_generate_preview_script():
    from flask import request, jsonify
    try:
        data = request.get_json(force=True, silent=True) or {}
        track_id = data.get("track_id")
        custom_idea = data.get("custom_idea", "")
        pkg = _fud.build_real_foji_universe_package(video_id=999, force_track_id=track_id, custom_idea=custom_idea, is_preview=True)
        return jsonify({"ok": True, "package": pkg})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



@app.route("/api/universe/stop_pipeline", methods=["POST"])
def api_universe_stop_pipeline():
    from flask import jsonify
    try:
        globals()["_FOJI_CANCEL_REQUESTED"] = True
        # 1. Reset telemetry immediately to idle so UI stops right away
        t_path = "data/live_telemetry.json"
        idle_state = {
            "step_num": 0,
            "step_title": "STANDBY",
            "sub_detail": "Generation stopped by user — Foji back on guard duty",
            "status": "idle",
            "progress": 0,
            "epoch": time.time()
        }
        with open(t_path, "w", encoding="utf-8") as f:
            json.dump(idle_state, f, indent=2)
        push_file_to_github_api(t_path, "User stopped pipeline")

        # 2. If running on GitHub Actions Cloud Worker, cancel any in_progress workflow runs!
        gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or "").strip()
        repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
        if gh_pat:
            def _cancel_gh_runs():
                try:
                    headers = {"Authorization": f"Bearer {gh_pat}", "Accept": "application/vnd.github+json"}
                    r = requests.get(f"https://api.github.com/repos/{repo}/actions/runs?status=in_progress", headers=headers, timeout=8)
                    if r.status_code == 200:
                        for run in r.json().get("workflow_runs", []):
                            rid = run.get("id")
                            if rid:
                                requests.post(f"https://api.github.com/repos/{repo}/actions/runs/{rid}/cancel", headers=headers, timeout=8)
                except Exception:
                    pass
            threading.Thread(target=_cancel_gh_runs, daemon=True).start()

        log_notification("stopped", "Generation Stopped", "Video generation cancelled by user.", "warning")
        return jsonify({"ok": True, "message": "Pipeline stopped cleanly."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200


@app.route("/api/universe/trigger_pipeline", methods=["POST"])
def api_universe_trigger_pipeline():
    from flask import request, jsonify
    try:
        data = request.get_json(force=True, silent=True) or {}
        twist = (data.get("custom_idea") or "").strip()
        batch_count = int(data.get("count", 1))
        if twist:
            st = _fud.get_director_state()
            st["custom_idea"] = twist
            _fud.save_director_state(st)

        _execute_single_or_batch_generation(
            count=batch_count,
            reason_label=f"Dashboard Manual Trigger ({batch_count} Video{'s' if batch_count > 1 else ''})",
            custom_idea=twist
        )
        return jsonify({
            "ok": True,
            "message": f"🚀 13-Step Video Engine Started ({batch_count} Video{'s' if batch_count > 1 else ''})!"
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/universe/approve_and_schedule", methods=["POST"])
def api_universe_approve_and_schedule():
    from flask import request, jsonify
    try:
        data = request.get_json(force=True, silent=True) or {}
        vfile = data.get("video_file")
        cap = (data.get("caption") or "").strip()
        item = _fud.approve_and_schedule_video_item(video_file=vfile, custom_caption=cap)
        return jsonify({
            "ok": True,
            "message": f"📅 Video ({item['video_file']}) Permanently Locked into Schedule Slot: {item['scheduled_display']}!",
            "scheduled_item": item
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/universe/remove_scheduled", methods=["POST"])
def api_universe_remove_scheduled():
    from flask import request, jsonify
    data = request.get_json(force=True, silent=True) or {}
    item_id = data.get("id")
    q = _fud.get_scheduled_queue()
    removed = None
    new_sched = []
    for it in q.get("scheduled_posts", []):
        if it.get("id") == item_id or it.get("video_file") == item_id:
            removed = it
        else:
            new_sched.append(it)
    q["scheduled_posts"] = new_sched
    if removed:
        removed["status"] = "awaiting_approval"
        q.setdefault("unapproved_videos", []).insert(0, removed)
    _fud.save_scheduled_queue(q, sync_cloud=True)
    return jsonify({"ok": True})


@app.route("/api/universe/publish_latest_reel", methods=["POST"])
def api_universe_publish_latest_reel():
    from flask import request, jsonify
    try:
        data = request.get_json(force=True, silent=True) or {}
        custom_caption = (data.get("caption") or "").strip()
        vfile = (data.get("video_file") or "").strip()

        raw_dir = "output/raw_videos"
        os.makedirs(raw_dir, exist_ok=True)
        if vfile:
            newest_vid = os.path.join(raw_dir, os.path.basename(vfile))
        else:
            mp4s = [os.path.join(raw_dir, f) for f in os.listdir(raw_dir) if f.endswith(".mp4")]
            if not mp4s:
                return jsonify({"ok": False, "error": "No generated MP4 video found in output/raw_videos yet!"}), 200
            newest_vid = max(mp4s, key=os.path.getmtime)

        vname = os.path.basename(newest_vid)
        if not custom_caption:
            for v_it in _fud.build_master_all_reels_vault():
                if v_it.get("video_file") == vname and v_it.get("caption"):
                    custom_caption = v_it["caption"]
                    break
        if not custom_caption:
            custom_caption = "🎖️ Foji Life 3D Story | Follow @ai_foji_lovelife for Next Part! 🇮🇳🔥 #indianarmy #faujilife #armyreels"

        # Execute real Instagram upload and ONLY return ok: True if Instagram returns a real Media PK!
        pub_item = _publish_specific_video_to_ig(newest_vid, custom_caption)
        pk_val = pub_item.get("media_pk", "LIVE") if isinstance(pub_item, dict) else "LIVE"
        permalink = pub_item.get("permalink", "https://www.instagram.com/ai_foji_lovelife/") if isinstance(pub_item, dict) else ""

        return jsonify({
            "ok": True,
            "video_file": vname,
            "media_pk": pk_val,
            "permalink": permalink,
            "published_item": pub_item,
            "message": f"🎉 100% CONFIRMED! Reel ({vname}) is LIVE on Instagram (@ai_foji_lovelife)!"
        }), 200
    except Exception as e:
        try:
            import gemini_bot
            gemini_bot.update_3d_telemetry(0, "IG Upload Error", str(e)[:180], "error", 0)
        except Exception:
            pass
        return jsonify({
            "ok": False,
            "status": "error",
            "error": f"Instagram Upload Failed: {str(e)}",
            "message": f"❌ Instagram Upload Failed: {str(e)}"
        }), 200



@app.route("/api/universe/save_schedule", methods=["POST"])
def api_universe_save_schedule():
    from flask import request, jsonify
    data = request.get_json(force=True, silent=True) or {}
    cfg = _fud.get_schedule_config()
    if "daily_slots" in data:
        cfg["daily_slots"] = data["daily_slots"]
    if "night_batch_time" in data:
        cfg["night_batch_time"] = data["night_batch_time"]
    if "night_batch_count" in data:
        cfg["night_batch_count"] = int(data["night_batch_count"])
    if "pre_slot_minutes" in data:
        cfg["pre_slot_minutes"] = int(data["pre_slot_minutes"])
    _fud.save_schedule_config(cfg)
    return jsonify({"ok": True, "schedule": cfg})


@app.route("/api/universe/live_screenshot", methods=["GET"])
def api_universe_live_screenshot():
    for snap in ["data/gemini_step_problem.png", "data/gemini_started.png", "data/gemini_login_status.png", "data/flow_started.png"]:
        if os.path.exists(snap):
            return _send_file(os.path.abspath(snap), mimetype="image/png")
    return ("No screenshot yet", 404)


@app.route("/api/universe/char_img/<name>", methods=["GET"])
def api_universe_char_img(name):
    safe = "foji" if "foji" in name.lower() else "fojan"
    for ext in ["jpg", "png", "jpeg", "webp"]:
        p = os.path.join("assets/characters", f"{safe}_character.{ext}")
        if os.path.exists(p):
            return _send_file(os.path.abspath(p))
        p2 = os.path.join("assets/characters", f"{safe}.{ext}")
        if os.path.exists(p2):
            return _send_file(os.path.abspath(p2))
    return ("Not found", 404)


@app.route("/api/universe/video_file/<filename>", methods=["GET"])
def api_universe_video_file(filename):
    return _stream_mp4_instantly(filename)



@app.route("/api/universe/latest_video", methods=["GET"])
def api_universe_latest_video():
    raw_dir = "output/raw_videos"
    if os.path.exists(raw_dir):
        mp4s = [os.path.join(raw_dir, f) for f in os.listdir(raw_dir) if f.endswith(".mp4")]
        if mp4s:
            newest = max(mp4s, key=os.path.getmtime)
            return _stream_mp4_instantly(os.path.basename(newest))
    return ("No video yet", 404)


@app.route("/app-icon.svg", methods=["GET"])
def pwa_app_icon():
    from flask import Response
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
      <defs>
        <radialGradient id="bg" cx="50%" cy="40%" r="60%">
          <stop offset="0%" stop-color="#0f2942"/>
          <stop offset="100%" stop-color="#040814"/>
        </radialGradient>
        <linearGradient id="ring" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#10b981"/>
          <stop offset="50%" stop-color="#06b6d4"/>
          <stop offset="100%" stop-color="#f59e0b"/>
        </linearGradient>
      </defs>
      <rect width="512" height="512" rx="115" fill="url(#bg)"/>
      <circle cx="256" cy="256" r="210" fill="none" stroke="url(#ring)" stroke-width="18"/>
      <circle cx="256" cy="256" r="175" fill="#071324" stroke="rgba(16,185,129,0.35)" stroke-width="4"/>
      <!-- Stylized Tactical Beret & Star -->
      <path d="M145 215 C155 145, 340 135, 375 205 C330 190, 190 195, 145 215 Z" fill="#10b981"/>
      <polygon points="256,152 264,170 284,172 269,185 273,204 256,194 239,204 243,185 228,172 248,170" fill="#fbbf24"/>
      <!-- Play Shield Emblem -->
      <path d="M210 235 L330 295 L210 355 Z" fill="url(#ring)"/>
    </svg>"""
    return Response(svg, mimetype="image/svg+xml")


@app.route("/manifest.json", methods=["GET"])
def pwa_manifest():
    from flask import jsonify
    return jsonify({
        "name": "Foji AI Studio",
        "short_name": "Foji Studio",
        "description": "3D Tactical AI Reels Studio & Auto-Scheduler",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#040814",
        "theme_color": "#040814",
        "orientation": "portrait-primary",
        "icons": [
            {"src": "/app-icon.svg", "sizes": "192x192 512x512", "type": "image/svg+xml", "purpose": "any maskable"}
        ]
    })


@app.route("/sw.js", methods=["GET"])
def pwa_service_worker():
    from flask import Response
    sw_js = """
    self.addEventListener('install', e => self.skipWaiting());
    self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
    self.addEventListener('fetch', e => {
      e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    });
    """
    return Response(sw_js, mimetype="application/javascript")


@app.after_request
def _inject_foji_universe_command_hub(response):
    try:
        if response.content_type and "text/html" in response.content_type and response.status_code == 200:
            html_text = response.get_data(as_text=True)
            if "</body>" in html_text and "id=\"foji-nextgen-studio-shell\"" not in html_text:
                widget_html = """
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#040814">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="apple-touch-icon" href="/app-icon.svg">

<style>
body > *:not(#foji-nextgen-studio-shell):not(#fns-center-modal-backdrop):not(#fns-app-splash):not(#fns-blast-overlay):not(script):not(style):not(link) { display: none !important; }
:root {
    --bg-main: #050a14;
    --bg-card: rgba(13, 22, 40, 0.84);
    --border-subtle: rgba(255, 255, 255, 0.09);
    --primary: #10b981;
    --cyan: #06b6d4;
    --gold: #f59e0b;
    --danger: #ef4444;
    --text-main: #f8fafc;
    --text-muted: #94a3b8;
}
html, body {
    margin: 0 !important; padding: 0 !important;
    background: var(--bg-main) !important; color: var(--text-main) !important;
    font-family: 'Plus Jakarta Sans', 'Inter', system-ui, -apple-system, sans-serif !important;
    min-height: 100vh; overflow-x: hidden; -webkit-tap-highlight-color: transparent;
}

/* 🎬 1.8s APP LAUNCH SPLASH SCREEN */
#fns-app-splash {
    position: fixed; inset: 0; z-index: 999999;
    background: radial-gradient(circle at 50% 40%, #0d253f 0%, #040812 75%);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    transition: opacity 0.45s ease, transform 0.45s ease;
}
#fns-app-splash.hide { opacity: 0; transform: scale(1.06); pointer-events: none; }
.fns-splash-avatar-ring {
    width: 118px; height: 118px; border-radius: 32px; padding: 4px;
    background: linear-gradient(135deg, #10b981, #06b6d4, #f59e0b);
    box-shadow: 0 0 45px rgba(16, 185, 129, 0.55);
    animation: fnsSplashPulse 1.2s infinite alternate ease-in-out;
}
@keyframes fnsSplashPulse {
    0% { transform: scale(0.96) rotate(-2deg); box-shadow: 0 0 25px rgba(16,185,129,0.4); }
    100% { transform: scale(1.04) rotate(2deg); box-shadow: 0 0 55px rgba(6,182,212,0.85); }
}
.fns-splash-bar {
    width: 190px; height: 6px; background: rgba(255,255,255,0.1);
    border-radius: 99px; overflow: hidden; margin-top: 18px;
}
.fns-splash-fill {
    height: 100%; width: 0%;
    background: linear-gradient(90deg, #10b981, #06b6d4, #f59e0b);
    animation: fnsSplashLoad 1.5s cubic-bezier(0.4, 0, 0.2, 1) forwards;
}
@keyframes fnsSplashLoad { to { width: 100%; } }

/* 💥 FULL-SCREEN BOMB BLAST & CONFETTI CELEBRATION OVERLAY */
#fns-blast-overlay {
    display: none; position: fixed; inset: 0; z-index: 99998; pointer-events: none;
    align-items: center; justify-content: center; overflow: hidden;
}
.fns-shockwave {
    position: absolute; width: 40px; height: 40px; border-radius: 50%;
    background: radial-gradient(circle, rgba(251,191,36,0.9), rgba(239,68,68,0.6), rgba(16,185,129,0.2), transparent 70%);
    animation: fnsExplodeWave 1.1s ease-out forwards;
}
@keyframes fnsExplodeWave {
    0% { transform: scale(0.2); opacity: 1; }
    70% { opacity: 0.9; }
    100% { transform: scale(45); opacity: 0; }
}
.fns-screen-shake { animation: fnsShakeAnim 0.55s cubic-bezier(.36,.07,.19,.97) both; }
@keyframes fnsShakeAnim {
    10%, 90% { transform: translate3d(-4px, 2px, 0); }
    20%, 80% { transform: translate3d(6px, -3px, 0); }
    30%, 50%, 70% { transform: translate3d(-8px, 4px, 0); }
    40%, 60% { transform: translate3d(8px, -4px, 0); }
}

#foji-nextgen-studio-shell {
    background: radial-gradient(circle at 15% 0%, rgba(14, 165, 233, 0.12) 0%, transparent 45%),
                radial-gradient(circle at 85% 10%, rgba(16, 185, 129, 0.1) 0%, transparent 45%),
                #050a14;
    min-height: 100vh; width: 100%; display: flex; flex-direction: column; box-sizing: border-box;
}

/* 👆 REAL TACTILE 3D PUSH BUTTONS (FEEL EVERY CLICK!) */
.fns-tab-btn, .fns-cta-generate, .fns-cta-stop, .fns-cta-schedule, .fns-cta-post, .fns-mnav-item {
    position: relative; overflow: hidden;
    transition: transform 0.12s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.15s ease, filter 0.15s ease !important;
    user-select: none; -webkit-user-select: none;
}
.fns-tab-btn:active, .fns-cta-generate:active, .fns-cta-stop:active, .fns-cta-schedule:active, .fns-cta-post:active, .fns-mnav-item:active {
    transform: translateY(3px) scale(0.95) !important;
    filter: brightness(1.22) !important;
}
.fns-click-ripple {
    position: absolute; border-radius: 50%; transform: scale(0);
    background: rgba(255, 255, 255, 0.45); pointer-events: none;
    animation: fnsRippleAnim 0.5s ease-out;
}
@keyframes fnsRippleAnim { to { transform: scale(3.5); opacity: 0; } }

/* TOP NAVIGATION */
.fns-topbar {
    display: flex; justify-content: space-between; align-items: center;
    gap: 12px; padding: 12px 24px; background: rgba(7, 13, 26, 0.9);
    backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--border-subtle); position: sticky; top: 0; z-index: 1000;
}
.fns-brand { display: flex; align-items: center; gap: 12px; }
.fns-logo-orb {
    width: 42px; height: 42px; border-radius: 12px; overflow: hidden;
    border: 2px solid #10b981;
    box-shadow: 0 4px 16px rgba(16, 185, 129, 0.4); flex-shrink: 0;
    background: #071426; display: flex; align-items: center; justify-content: center;
}
.fns-logo-orb img { width: 100%; height: 100%; object-fit: cover; }
.fns-tabs { display: flex; gap: 6px; background: rgba(15, 23, 42, 0.78); padding: 5px; border-radius: 13px; border: 1px solid var(--border-subtle); }
.fns-tab-btn {
    background: transparent; border: 1px solid transparent;
    color: var(--text-muted); padding: 8px 14px; border-radius: 9px;
    font-size: 0.8rem; font-weight: 700; cursor: pointer;
    display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
}
.fns-tab-btn:hover { color: #fff; background: rgba(255,255,255,0.05); }
.fns-tab-btn.active {
    background: rgba(16, 185, 129, 0.18);
    border-color: rgba(16, 185, 129, 0.5); color: #34d399;
    box-shadow: 0 3px 10px rgba(16, 185, 129, 0.2);
}

/* ACTION BUTTONS (3D DEPTH) */
.fns-cta-generate {
    background: linear-gradient(135deg, #10b981, #059669); color: #fff;
    border: none; border-bottom: 3px solid #047857; padding: 9px 17px; border-radius: 11px;
    font-size: 0.82rem; font-weight: 800; cursor: pointer;
    box-shadow: 0 6px 18px rgba(16, 185, 129, 0.35);
}
.fns-cta-stop {
    background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff;
    border: none; border-bottom: 3px solid #991b1b; padding: 9px 17px; border-radius: 11px;
    font-size: 0.82rem; font-weight: 900; cursor: pointer;
    box-shadow: 0 0 22px rgba(239, 68, 68, 0.65);
    animation: fnsStopPulse 1s infinite alternate;
}
@keyframes fnsStopPulse {
    from { box-shadow: 0 0 12px rgba(239,68,68,0.5); }
    to { box-shadow: 0 0 26px rgba(239,68,68,0.95); }
}
.fns-cta-schedule {
    background: linear-gradient(135deg, #8b5cf6, #7c3aed); color: #fff;
    border: none; border-bottom: 3px solid #5b21b6; padding: 9px 15px; border-radius: 11px;
    font-size: 0.8rem; font-weight: 700; cursor: pointer;
}
.fns-cta-post {
    background: rgba(16, 185, 129, 0.16); color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.45); border-bottom: 3px solid rgba(16, 185, 129, 0.6);
    padding: 8px 15px; border-radius: 11px; font-size: 0.8rem; font-weight: 700; cursor: pointer;
}
.fns-cta-post:hover { background: #10b981; color: #04130e; }

/* LAYOUT BODY */
.fns-body { display: grid; grid-template-columns: 240px 1fr; flex: 1; max-width: 1600px; width: 100%; margin: 0 auto; }
.fns-sidebar {
    background: rgba(8, 13, 26, 0.65); border-right: 1px solid var(--border-subtle);
    padding: 18px 16px; display: flex; flex-direction: column; gap: 14px;
}
.fns-side-box {
    background: var(--bg-card); border: 1px solid var(--border-subtle);
    border-radius: 14px; padding: 14px;
}
.fns-badge-live {
    background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.4);
    color: #34d399; font-size: 0.68rem; font-weight: 800; padding: 3px 9px; border-radius: 99px;
}
.fns-main-panel { padding: 20px 24px; overflow-y: auto; flex: 1; }
.fns-screen { display: none; animation: fnsFadeIn 0.2s ease; }
.fns-screen.active { display: block; }
@keyframes fnsFadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

.fns-s1-grid { display: grid; grid-template-columns: 1fr 320px; gap: 22px; align-items: start; }
.fns-s2-grid { display: grid; grid-template-columns: 1fr 1fr 320px; gap: 18px; align-items: start; }
.fns-s4-grid { display: grid; grid-template-columns: 280px 1fr; gap: 18px; align-items: start; }

.fns-pipeline-card {
    background: var(--bg-card); border: 1px solid var(--border-subtle);
    backdrop-filter: blur(12px); border-radius: 18px; padding: 20px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.4);
}

/* =========================================================================
   🎖️ 3D TACTICAL FOJI BATTLEFIELD PIPELINE ARENA
   ========================================================================= */
.fns-battlefield-arena {
    position: relative; margin: 16px 0; padding: 20px 16px 18px 16px;
    background: radial-gradient(circle at 50% 30%, rgba(16, 185, 129, 0.14), rgba(5, 10, 22, 0.96) 75%);
    border: 1px solid rgba(16, 185, 129, 0.32); border-radius: 18px;
    box-shadow: inset 0 0 35px rgba(0,0,0,0.8), 0 12px 30px rgba(0,0,0,0.45);
    perspective: 900px; overflow: hidden;
}
/* Tactical Radar Grid Overlay */
.fns-battlefield-arena::before {
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background-image: linear-gradient(rgba(16, 185, 129, 0.05) 1px, transparent 1px),
                      linear-gradient(90deg, rgba(16, 185, 129, 0.05) 1px, transparent 1px);
    background-size: 24px 24px;
}

/* Active Foji Commander Status Bar inside Arena */
.fns-commander-hud {
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    padding: 10px 14px; margin-bottom: 16px; border-radius: 13px;
    background: rgba(8, 17, 32, 0.9); border: 1px solid rgba(6, 182, 212, 0.3);
    position: relative; z-index: 3; flex-wrap: wrap;
}
.fns-foji-hero-unit {
    display: flex; align-items: center; gap: 12px;
}
.fns-foji-avatar-3d {
    position: relative; width: 52px; height: 52px; border-radius: 14px;
    border: 2px solid #10b981; background: #061224;
    box-shadow: 0 0 18px rgba(16, 185, 129, 0.5);
    animation: fnsPatrolBob 2s infinite ease-in-out; flex-shrink: 0;
}
.fns-foji-avatar-3d img { width: 100%; height: 100%; object-fit: cover; border-radius: 12px; }
.fns-foji-weapon-badge {
    position: absolute; bottom: -5px; right: -8px;
    background: #0f172a; border: 1.5px solid #f59e0b; border-radius: 8px;
    padding: 1px 5px; font-size: 0.78rem; box-shadow: 0 0 10px rgba(245,158,11,0.6);
}
@keyframes fnsPatrolBob {
    0%, 100% { transform: translateY(0px) rotate(0deg); }
    50% { transform: translateY(-4px) rotate(1.5deg); }
}

/* Muzzle Flash & Bullet Stream When Pipeline is Active */
.fns-bullet-track {
    flex: 1; min-width: 120px; height: 18px; position: relative; overflow: hidden;
    background: rgba(255,255,255,0.03); border-radius: 99px; border: 1px solid rgba(255,255,255,0.06);
    display: flex; align-items: center; padding: 0 10px;
}
.fns-laser-bullet {
    position: absolute; width: 28px; height: 4px; border-radius: 99px;
    background: linear-gradient(90deg, transparent, #fbbf24, #ef4444);
    box-shadow: 0 0 12px #f59e0b; opacity: 0;
}
.fns-battlefield-arena.firing .fns-laser-bullet {
    opacity: 1; animation: fnsBulletFly 0.65s linear infinite;
}
@keyframes fnsBulletFly {
    0% { left: 5%; transform: scaleX(0.7); opacity: 1; }
    90% { opacity: 1; }
    100% { left: 92%; transform: scaleX(1.3); opacity: 0; }
}

/* 8 Tactical Bunker Checkpoints Grid */
.fns-steps-grid {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
    position: relative; z-index: 3;
}
.fns-road-node {
    position: relative;
    background: linear-gradient(160deg, rgba(19, 30, 54, 0.92), rgba(10, 17, 32, 0.95));
    border: 1.5px solid rgba(255, 255, 255, 0.1);
    border-bottom: 4px solid rgba(255, 255, 255, 0.14);
    border-radius: 13px; padding: 12px; text-align: left;
    transform: rotateX(6deg); transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.fns-road-node.duty-guard {
    border-color: rgba(16, 185, 129, 0.65);
    border-bottom-color: #059669;
    box-shadow: 0 6px 20px rgba(16, 185, 129, 0.22);
}
.fns-road-node.done {
    border-color: #10b981; border-bottom-color: #047857;
    background: linear-gradient(160deg, rgba(16, 185, 129, 0.22), rgba(10, 24, 38, 0.95));
    box-shadow: 0 6px 18px rgba(16, 185, 129, 0.25);
}
.fns-road-node.active {
    border-color: #f59e0b; border-bottom-color: #b45309;
    background: linear-gradient(160deg, rgba(245, 158, 11, 0.26), rgba(20, 28, 48, 0.96));
    box-shadow: 0 0 28px rgba(245, 158, 11, 0.55);
    transform: rotateX(0deg) translateY(-4px) scale(1.03);
}
.fns-road-node.error {
    border-color: #ef4444; border-bottom-color: #991b1b;
    background: rgba(127, 29, 29, 0.35);
}
.fns-node-soldier-pin {
    position: absolute; top: -10px; right: 8px;
    background: linear-gradient(135deg, #f59e0b, #ef4444);
    color: #fff; font-size: 0.65rem; font-weight: 900;
    padding: 2px 7px; border-radius: 99px;
    box-shadow: 0 4px 12px rgba(239, 68, 68, 0.6);
    animation: fnsPinBounce 0.6s infinite alternate;
}
@keyframes fnsPinBounce { from { transform: translateY(0); } to { transform: translateY(-4px); } }

/* Step Cleared Celebration Pop Animation */
.fns-step-celebrate { animation: fnsCelebratePop 0.65s ease-out; }
@keyframes fnsCelebratePop {
    0% { transform: scale(1); }
    40% { transform: scale(1.12); box-shadow: 0 0 35px #10b981; }
    100% { transform: scale(1); }
}

.fns-error-box {
    display: none; margin-top: 14px; padding: 14px 16px; border-radius: 12px;
    background: rgba(127, 29, 29, 0.35); border: 1px solid #ef4444; color: #fecaca;
}

/* PHONE PREVIEW */
.fns-iphone-frame {
    background: #050914; border: 3px solid #1e293b; border-radius: 28px; padding: 10px;
    box-shadow: 0 18px 40px rgba(0,0,0,0.65); display: flex; flex-direction: column; align-items: center;
}
.fns-iphone-notch { width: 70px; height: 12px; background: #0f172a; border-radius: 99px; margin-bottom: 8px; }
.fns-iphone-screen {
    width: 100%; aspect-ratio: 9/16; max-height: 430px; background: #000; border-radius: 20px;
    overflow: hidden; position: relative; display: flex; align-items: center; justify-content: center;
}
.fns-iphone-overlay {
    position: absolute; bottom: 10px; left: 10px; right: 10px;
    background: rgba(5, 10, 20, 0.78); backdrop-filter: blur(8px);
    padding: 8px 12px; border-radius: 10px; font-size: 0.73rem; color: #fff; pointer-events: none;
    border: 1px solid rgba(255,255,255,0.08);
}

/* TRACKS & QUEUE CARDS */
.fns-track-item {
    background: rgba(20, 30, 52, 0.7); border: 1px solid var(--border-subtle);
    border-radius: 11px; padding: 11px 13px; cursor: pointer; transition: all 0.2s;
}
.fns-track-item:hover { border-color: rgba(255,255,255,0.22); }
.fns-track-item.active {
    border-color: #10b981; background: rgba(16, 185, 129, 0.12);
}
.fns-queue-card {
    background: rgba(17, 26, 46, 0.82); border: 1px solid var(--border-subtle);
    border-radius: 13px; padding: 13px; margin-bottom: 10px;
    display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
}

/* ALL REELS VAULT GRID */
.fns-vault-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 18px; margin-top: 16px;
}
.fns-vault-card {
    background: rgba(13, 21, 38, 0.92); border: 1px solid var(--border-subtle);
    border-radius: 16px; overflow: hidden; display: flex; flex-direction: column;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
}
.fns-vault-card.published { border-color: rgba(16, 185, 129, 0.55); }
.fns-vault-card.scheduled { border-color: rgba(139, 92, 246, 0.55); }

/* MODAL POPUP */
#fns-center-modal-backdrop {
    display: none; position: fixed; inset: 0; background: rgba(3, 7, 18, 0.82);
    backdrop-filter: blur(8px); z-index: 99999; align-items: center; justify-content: center; padding: 16px;
}
.fns-center-modal {
    background: #0d1629; border: 1.5px solid rgba(16, 185, 129, 0.5);
    border-radius: 20px; max-width: 440px; width: 100%;
    padding: 24px; text-align: center; box-shadow: 0 24px 60px rgba(0,0,0,0.85);
}

/* MOBILE BOTTOM NAVIGATION BAR */
.fns-mobile-bottom-nav {
    display: none; position: fixed; bottom: 0; left: 0; right: 0;
    background: rgba(8, 13, 26, 0.96); backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
    border-top: 1px solid rgba(255,255,255,0.1); z-index: 9999;
    justify-content: space-around; align-items: center;
    padding: 8px 6px calc(8px + env(safe-area-inset-bottom));
}
.fns-mnav-item {
    background: none; border: none; color: #64748b;
    display: flex; flex-direction: column; align-items: center; gap: 3px;
    font-size: 0.68rem; font-weight: 700; cursor: pointer; padding: 4px 10px; border-radius: 10px;
}
.fns-mnav-item.active { color: #10b981; }
.fns-mnav-icon { font-size: 1.15rem; }

/* MOBILE BREAKPOINTS */
@media (max-width: 1024px) {
    .fns-body { grid-template-columns: 1fr; }
    .fns-sidebar { display: none; }
    .fns-s1-grid, .fns-s2-grid, .fns-s4-grid { grid-template-columns: 1fr; }
    .fns-steps-grid { grid-template-columns: repeat(2, 1fr); }
    .fns-main-panel { padding: 14px 14px 92px 14px; }
    .fns-topbar { padding: 10px 14px; }
    .fns-tabs { display: none; }
    .fns-mobile-bottom-nav { display: flex; }
    .fns-vault-grid { grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
}
@media (max-width: 480px) {
    .fns-vault-grid { grid-template-columns: 1fr; }
    .fns-topbar-actions .fns-cta-schedule { display: none; }
}
</style>

<!-- 🎬 1.8-SECOND NATIVE APP BOOT SPLASH SCREEN -->
<div id="fns-app-splash">
  <div class="fns-splash-avatar-ring">
    <img src="/api/universe/char_img/foji" onerror="this.src='/app-icon.svg'" style="width:100%;height:100%;object-fit:cover;border-radius:28px;" />
  </div>
  <div style="font-size:1.35rem;font-weight:900;color:#fff;margin-top:16px;letter-spacing:0.02em;">FOJI AI STUDIO</div>
  <div style="font-size:0.75rem;color:#34d399;font-weight:700;margin-top:4px;">3D TACTICAL ENGINE • @ai_foji_lovelife</div>
  <div class="fns-splash-bar"><div class="fns-splash-fill"></div></div>
</div>

<!-- 💥 BOMB BLAST CELEBRATION OVERLAY -->
<div id="fns-blast-overlay"></div>

<!-- CENTER MODAL (SUPPORTS CONFIRMATION BUTTONS TOO) -->
<div id="fns-center-modal-backdrop">
  <div class="fns-center-modal" id="fns-center-modal-box">
    <div id="fns-modal-icon" style="font-size:2.3rem;margin-bottom:8px;">✨</div>
    <div id="fns-modal-title" style="font-size:1.14rem;font-weight:800;color:#fff;margin-bottom:6px;">Update</div>
    <div id="fns-modal-body" style="font-size:0.86rem;color:#cbd5e1;line-height:1.5;margin-bottom:18px;word-break:break-word;"></div>
    <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;" id="fns-modal-actions">
      <button class="fns-cta-generate" style="min-width:110px;" onclick="fnsCloseModal()">Done</button>
    </div>
  </div>
</div>

<div id="foji-nextgen-studio-shell">
  <!-- TOP BAR -->
  <div class="fns-topbar">
    <div class="fns-brand">
      <div class="fns-logo-orb">
        <img src="/api/universe/char_img/foji" onerror="this.src='/app-icon.svg'" alt="Foji" />
      </div>
      <div>
        <div style="font-size:1.05rem;font-weight:900;color:#fff;letter-spacing:-0.01em;">Foji AI Studio</div>
        <div style="font-size:0.7rem;color:#34d399;font-weight:600;" id="fns-top-clock-sub">@ai_foji_lovelife • Command Hub</div>
      </div>
    </div>

    <div class="fns-tabs">
      <button class="fns-tab-btn active" id="fns-btn-tab1" onclick="fnsSwitchTab(1)">🎬 Studio</button>
      <button class="fns-tab-btn" id="fns-btn-tab2" onclick="fnsSwitchTab(2)">📅 Schedule (<span id="fns-q-badge">0</span>)</button>
      <button class="fns-tab-btn" id="fns-btn-tab3" onclick="fnsSwitchTab(3)">🎞️ All Reels (<span id="fns-vault-badge">0</span>)</button>
      <button class="fns-tab-btn" id="fns-btn-tab4" onclick="fnsSwitchTab(4)">📚 Tracks</button>
    </div>

    <div class="fns-topbar-actions" style="display:flex;gap:8px;align-items:center;">
      <button class="fns-tab-btn" id="fns-pwa-install-btn" style="display:none;border-color:#06b6d4;color:#22d3ee;" onclick="fnsInstallPwaApp()">📲 Install App</button>
      <!-- DYNAMIC GENERATE / STOP BUTTON -->
      <button class="fns-cta-generate" id="fns-primary-gen-btn" onclick="fnsHandlePrimaryGenOrStopClick()">🚀 Generate Reel</button>
      <button class="fns-cta-schedule" onclick="fnsApproveAndScheduleLatest()">📅 Schedule</button>
      <button class="fns-cta-post" onclick="fnsPublishLatestReel()">📲 Post</button>
    </div>
  </div>

  <div class="fns-body">
    <!-- DESKTOP LEFT SIDEBAR -->
    <div class="fns-sidebar">
      <div class="fns-side-box">
        <div style="font-size:0.74rem;font-weight:800;color:#34d399;margin-bottom:6px;">⏱️ LIVE SCHEDULE</div>
        <div style="font-size:0.72rem;color:#cbd5e1;line-height:1.5;">
          Next Slot: <b id="fns-next-slot-sidebar" style="color:#fff;">--:--</b><br/>
          IST Time: <b id="fns-server-clock" style="color:#38bdf8;">--:--</b>
        </div>
      </div>

      <div class="fns-side-box">
        <div style="font-size:0.74rem;font-weight:800;color:#94a3b8;margin-bottom:8px;">QUICK COMMANDS</div>
        <button class="fns-tab-btn" id="fns-side-gen-btn" style="width:100%;margin-bottom:6px;justify-content:flex-start;color:#34d399;" onclick="fnsHandlePrimaryGenOrStopClick()">🚀 Generate Reel</button>
        <button class="fns-tab-btn" style="width:100%;margin-bottom:6px;justify-content:flex-start;" onclick="fnsStartFullVideoGeneration(3)">🌙 Generate 3 Reels</button>
        <button class="fns-tab-btn" style="width:100%;margin-bottom:6px;justify-content:flex-start;" onclick="fnsApproveAndScheduleLatest()">📅 Schedule Latest</button>
        <button class="fns-tab-btn" style="width:100%;justify-content:flex-start;" onclick="fnsSwitchTab(3)">🎞️ All Reels (<span id="fns-ep-total">0</span>)</button>
      </div>

      <div class="fns-side-box" style="margin-top:auto;">
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <span style="font-size:0.72rem;color:#94a3b8;font-weight:700;">Auto-Cleaner & IG</span>
          <span class="fns-badge-live">Protected</span>
        </div>
      </div>
    </div>

    <!-- MAIN CONTENT -->
    <div class="fns-main-panel">
      <div id="fns-action-toast" style="display:none;margin-bottom:14px;padding:11px 15px;border-radius:11px;background:rgba(16,185,129,0.16);border:1px solid #10b981;color:#fff;font-weight:700;font-size:0.83rem;"></div>

      <!-- TAB 1: 3D TACTICAL STUDIO & PREVIEW -->
      <div class="fns-screen active" id="fns-screen-1">
        <div class="fns-s1-grid">
          <div class="fns-pipeline-card">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
              <div>
                <div style="font-size:1.04rem;font-weight:900;color:#fff;">🎖️ 3D Foji Tactical Pipeline</div>
                <div style="font-size:0.78rem;color:#34d399;margin-top:2px;" id="fns-radar-subtitle">Foji Makra on Guard Duty at Post #1</div>
              </div>
              <div style="display:flex;gap:8px;align-items:center;">
                <a href="/api/universe/live_screenshot" target="_blank" class="fns-tab-btn" style="text-decoration:none;font-size:0.74rem;border-color:rgba(255,255,255,0.12);">📸 Cloud View ↗</a>
              </div>
            </div>

            <!-- 🎖️ 3D TACTICAL BATTLEFIELD ARENA -->
            <div class="fns-battlefield-arena" id="fns-battle-arena">
              <!-- Live Foji Commando Unit Bar -->
              <div class="fns-commander-hud">
                <div class="fns-foji-hero-unit">
                  <div class="fns-foji-avatar-3d" id="fns-foji-hero-box">
                    <img src="/api/universe/char_img/foji" onerror="this.src='/app-icon.svg'" alt="Foji Makra" />
                    <span class="fns-foji-weapon-badge" id="fns-foji-weapon-icon">🛡️</span>
                  </div>
                  <div>
                    <div style="font-size:0.82rem;font-weight:900;color:#fff;" id="fns-foji-soldier-title">🪖 Commando Makra • Guard Duty (Post #1)</div>
                    <div style="font-size:0.71rem;color:#34d399;font-weight:700;" id="fns-foji-soldier-sub">Standing by — Click "Generate Reel" to start mission</div>
                  </div>
                </div>

                <!-- Animated Laser Bullet Stream -->
                <div class="fns-bullet-track" id="fns-bullet-stream">
                  <div class="fns-laser-bullet"></div>
                  <span style="font-size:0.68rem;font-weight:800;color:#94a3b8;margin-left:auto;" id="fns-mission-pct-badge">READY</span>
                </div>
              </div>

              <!-- 8 3D Tactical Bunker Checkpoints -->
              <div class="fns-steps-grid">
                <div class="fns-road-node duty-guard" id="fns-pnode-1">
                  <div style="font-size:0.63rem;color:#94a3b8;font-weight:700;">POST 1</div>
                  <div style="font-size:0.76rem;font-weight:800;color:#fff;margin-top:2px;">📝 AI Script</div>
                </div>
                <div class="fns-road-node" id="fns-pnode-2">
                  <div style="font-size:0.63rem;color:#94a3b8;font-weight:700;">POST 2</div>
                  <div style="font-size:0.76rem;font-weight:800;color:#fff;margin-top:2px;">🔐 Auth Lock</div>
                </div>
                <div class="fns-road-node" id="fns-pnode-3">
                  <div style="font-size:0.63rem;color:#94a3b8;font-weight:700;">POST 3</div>
                  <div style="font-size:0.76rem;font-weight:800;color:#fff;margin-top:2px;">📐 9:16 Setup</div>
                </div>
                <div class="fns-road-node" id="fns-pnode-4">
                  <div style="font-size:0.63rem;color:#94a3b8;font-weight:700;">POST 4</div>
                  <div style="font-size:0.76rem;font-weight:800;color:#fff;margin-top:2px;">👫 Characters</div>
                </div>
                <div class="fns-road-node" id="fns-pnode-5">
                  <div style="font-size:0.63rem;color:#94a3b8;font-weight:700;">POST 5</div>
                  <div style="font-size:0.76rem;font-weight:800;color:#fff;margin-top:2px;">🎯 Scene Prompt</div>
                </div>
                <div class="fns-road-node" id="fns-pnode-6">
                  <div style="font-size:0.63rem;color:#94a3b8;font-weight:700;">POST 6</div>
                  <div style="font-size:0.76rem;font-weight:800;color:#fff;margin-top:2px;">🎬 3D Render</div>
                </div>
                <div class="fns-road-node" id="fns-pnode-7">
                  <div style="font-size:0.63rem;color:#94a3b8;font-weight:700;">POST 7</div>
                  <div style="font-size:0.76rem;font-weight:800;color:#fff;margin-top:2px;">📥 MP4 Save</div>
                </div>
                <div class="fns-road-node" id="fns-pnode-8">
                  <div style="font-size:0.63rem;color:#94a3b8;font-weight:700;">POST 8</div>
                  <div style="font-size:0.76rem;font-weight:800;color:#fff;margin-top:2px;">💥 Mission Complete</div>
                </div>
              </div>
            </div>

            <!-- ERROR DIAGNOSTIC -->
            <div class="fns-error-box" id="fns-error-banner">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;">
                <div style="font-size:0.85rem;font-weight:800;color:#fca5a5;">⚠️ Pipeline Alert</div>
                <a href="/api/universe/live_screenshot" target="_blank" style="color:#fff;background:#ef4444;padding:4px 10px;border-radius:7px;text-decoration:none;font-size:0.72rem;font-weight:700;">View Screenshot ↗</a>
              </div>
              <div id="fns-error-reason-text" style="font-size:0.8rem;color:#fee2e2;margin-top:5px;"></div>
            </div>

            <!-- STORY TRACK SELECTOR -->
            <div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--border-subtle);">
              <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px;">
                <span style="font-size:0.83rem;font-weight:800;color:#e2e8f0;">Story Track</span>
                <button class="fns-tab-btn" id="fns-autorotate-btn" onclick="fnsSetAutoRotate()" style="padding:5px 11px;font-size:0.73rem;">🔄 Auto-Rotate</button>
              </div>
              <div id="fns-quick-tracks" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:8px;"></div>

              <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">
                <input type="text" id="fns-custom-twist" placeholder="Optional story idea or dialogue twist..." style="flex:1;min-width:180px;background:rgba(6,11,22,0.9);border:1px solid rgba(255,255,255,0.14);border-radius:10px;padding:10px 13px;color:#fff;font-size:0.81rem;" />
                <button class="fns-tab-btn active" onclick="fnsLockTwist()">Save Idea</button>
                <button class="fns-tab-btn" style="border-color:rgba(139,92,246,0.5);color:#c4b5fd;" onclick="fnsGenerateLiveScriptPreview()">Preview Script</button>
              </div>
              <div id="fns-live-script-output" style="display:none;margin-top:12px;background:rgba(6,11,22,0.9);border-left:3px solid #10b981;padding:12px;border-radius:10px;font-size:0.8rem;line-height:1.5;"></div>
            </div>

            <!-- RECENT ACTIVITY -->
            <div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-subtle);">
              <div style="font-size:0.76rem;font-weight:700;color:#94a3b8;margin-bottom:6px;">Recent Activity</div>
              <div id="fns-notif-feed" style="max-height:120px;overflow-y:auto;display:flex;flex-direction:column;gap:5px;font-size:0.74rem;"></div>
            </div>
          </div>

          <!-- RIGHT: 9:16 REEL PLAYER & CONTROLS -->
          <div style="display:flex;flex-direction:column;gap:12px;">
            <div class="fns-iphone-frame">
              <div class="fns-iphone-notch"></div>
              <div class="fns-iphone-screen">
                <video id="fns-preview-video" src="/api/universe/latest_video" controls playsinline preload="metadata" style="width:100%;height:100%;object-fit:cover;background:#000;" onerror="this.style.display='none';document.getElementById('fns-vid-fallback').style.display='flex';"></video>
                <div id="fns-vid-fallback" style="display:none;flex-direction:column;align-items:center;justify-content:center;padding:16px;text-align:center;">
                  <img src="/api/universe/char_img/foji" style="width:96px;height:96px;object-fit:cover;border-radius:50%;border:2px solid #10b981;margin-bottom:10px;" />
                  <div style="font-size:0.82rem;font-weight:800;color:#fff;">Foji AI Studio</div>
                  <div style="font-size:0.7rem;color:#94a3b8;margin-top:4px;">Select or generate a reel to preview</div>
                </div>
                <div class="fns-iphone-overlay">
                  <div style="font-weight:800;color:#34d399;font-size:0.74rem;" id="fns-phone-ep-title">@ai_foji_lovelife</div>
                  <div id="fns-phone-ep-diag" style="font-size:0.67rem;color:#cbd5e1;margin-top:1px;">9:16 HD Preview</div>
                </div>
              </div>
            </div>

            <div class="fns-pipeline-card" style="padding:14px;">
              <button class="fns-cta-schedule" style="width:100%;margin-bottom:8px;padding:11px;font-size:0.82rem;" onclick="fnsApproveAndScheduleLatest()">📅 Schedule Next Slot</button>
              <button class="fns-cta-post" style="width:100%;margin-bottom:8px;padding:11px;font-size:0.82rem;" id="fns-side-post-btn" onclick="fnsPublishLatestReel()">📲 Post to Instagram Now</button>
              <div style="display:flex;gap:8px;">
                <button class="fns-tab-btn" id="fns-card-gen-btn" style="flex:1;justify-content:center;font-size:0.75rem;border-color:rgba(255,255,255,0.1);" onclick="fnsHandlePrimaryGenOrStopClick()">🚀 Generate Reel</button>
                <a href="/api/universe/latest_video" download="foji_reel.mp4" class="fns-tab-btn" style="flex:1;justify-content:center;font-size:0.75rem;text-decoration:none;color:#34d399;border-color:rgba(16,185,129,0.3);">📥 Download</a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- TAB 2: SCHEDULE & QUEUE -->
      <div class="fns-screen" id="fns-screen-2">
        <div class="fns-s2-grid">
          <div class="fns-pipeline-card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
              <span style="font-size:0.92rem;font-weight:800;color:#fff;">Ready to Schedule</span>
              <span class="fns-badge-live" id="fns-unapproved-cnt">0 Ready</span>
            </div>
            <div id="fns-unapproved-list" style="max-height:520px;overflow-y:auto;"></div>
          </div>

          <div class="fns-pipeline-card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
              <span style="font-size:0.92rem;font-weight:800;color:#c4b5fd;">Scheduled Queue</span>
              <span class="fns-badge-live" id="fns-scheduled-cnt">0 Scheduled</span>
            </div>
            <div id="fns-scheduled-list" style="max-height:520px;overflow-y:auto;"></div>
          </div>

          <div class="fns-pipeline-card">
            <div style="font-size:0.92rem;font-weight:800;color:#38bdf8;margin-bottom:12px;">Daily Post Times (IST)</div>
            <div style="margin-bottom:12px;">
              <label style="font-size:0.74rem;color:#94a3b8;font-weight:700;">Night Auto-Batch (3 Reels):</label>
              <input type="time" id="fns-cfg-night-time" value="02:30" style="width:100%;box-sizing:border-box;margin-top:5px;background:#081020;border:1px solid rgba(255,255,255,0.14);color:#34d399;padding:9px;border-radius:9px;font-weight:700;" />
            </div>
            <div style="margin-bottom:14px;">
              <label style="font-size:0.74rem;color:#94a3b8;font-weight:700;">Publishing Slots:</label>
              <input type="time" id="fns-slot-1" value="07:00" style="width:100%;box-sizing:border-box;margin-top:6px;background:#081020;border:1px solid rgba(255,255,255,0.14);color:#fff;padding:9px;border-radius:9px;" />
              <input type="time" id="fns-slot-2" value="13:30" style="width:100%;box-sizing:border-box;margin-top:6px;background:#081020;border:1px solid rgba(255,255,255,0.14);color:#fff;padding:9px;border-radius:9px;" />
              <input type="time" id="fns-slot-3" value="19:30" style="width:100%;box-sizing:border-box;margin-top:6px;background:#081020;border:1px solid rgba(255,255,255,0.14);color:#fff;padding:9px;border-radius:9px;" />
            </div>
            <button class="fns-cta-generate" style="width:100%;padding:11px;" onclick="fnsSaveScheduleSlots()">Save Schedule</button>
          </div>
        </div>
      </div>

      <!-- TAB 3: ALL REELS VAULT -->
      <div class="fns-screen" id="fns-screen-3">
        <div class="fns-pipeline-card">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
            <div>
              <div style="font-size:1.05rem;font-weight:800;color:#fff;">All Reels Library</div>
              <div style="font-size:0.76rem;color:#94a3b8;margin-top:2px;">Click any reel to play immediately, schedule, or post to Instagram.</div>
            </div>
          </div>
          <div class="fns-vault-grid" id="fns-master-vault-grid"></div>
        </div>
      </div>

      <!-- TAB 4: CHARACTERS & TRACKS -->
      <div class="fns-screen" id="fns-screen-4">
        <div class="fns-s4-grid">
          <div class="fns-pipeline-card">
            <div style="font-size:0.88rem;font-weight:800;color:#34d399;margin-bottom:10px;">Lead Characters</div>
            <img src="/api/universe/char_img/foji" style="width:100%;height:150px;object-fit:cover;border-radius:10px;margin-bottom:6px;" />
            <div style="font-size:0.78rem;font-weight:700;color:#fff;margin-bottom:12px;">🪖 Foji Makra</div>
            <img src="/api/universe/char_img/fojan" style="width:100%;height:150px;object-fit:cover;border-radius:10px;margin-bottom:6px;" />
            <div style="font-size:0.78rem;font-weight:700;color:#fff;">🌸 Fojan Meera</div>
          </div>
          <div class="fns-pipeline-card">
            <div style="font-size:0.88rem;font-weight:800;color:#38bdf8;margin-bottom:10px;">Series Story Tracks</div>
            <div id="fns-s2-tracks-list"></div>
          </div>
        </div>
      </div>

    </div>
  </div>

  <!-- MOBILE STICKY BOTTOM BAR -->
  <nav class="fns-mobile-bottom-nav">
    <button class="fns-mnav-item active" id="fns-mnav-1" onclick="fnsSwitchTab(1)">
      <span class="fns-mnav-icon">🎬</span>
      <span>Studio</span>
    </button>
    <button class="fns-mnav-item" id="fns-mnav-2" onclick="fnsSwitchTab(2)">
      <span class="fns-mnav-icon">📅</span>
      <span>Schedule</span>
    </button>
    <button class="fns-mnav-item" id="fns-mnav-3" onclick="fnsSwitchTab(3)">
      <span class="fns-mnav-icon">🎞️</span>
      <span>All Reels</span>
    </button>
    <button class="fns-mnav-item" id="fns-mnav-4" onclick="fnsSwitchTab(4)">
      <span class="fns-mnav-icon">📚</span>
      <span>Tracks</span>
    </button>
  </nav>
</div>

<script>
let _fnsState = { active_mode: 'auto_rotate', selected_track_id: 'love_meera' };
let _fnsTracks = [];
let _fnsKnownVaultFiles = new Set();
let _fnsFirstLoadDone = false;
let _fnsLastErrorKey = '';
let _fnsActivePreviewFile = '';
let _fnsLastVaultSignature = '';
let _fnsLastQueueSignature = '';
let _fnsDeferredPwaPrompt = null;
let _fnsPipelineIsRunning = false;
let _fnsLastCompletedStep = 0;

// 🎬 Hide App Launch Splash Screen smoothly after 1.65 seconds
setTimeout(() => {
  const sp = document.getElementById('fns-app-splash');
  if (sp) {
    sp.classList.add('hide');
    setTimeout(() => { sp.style.display = 'none'; }, 500);
  }
}, 1650);

// 🔊 WebAudio Synthesizer for Button Clicks, Step Cleared Flare & Final Bomb Blast!
function fnsPlaySoundFX(type) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const now = ctx.currentTime;
    if (type === 'click') {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(520, now);
      osc.frequency.exponentialRampToValueAtTime(180, now + 0.045);
      g.gain.setValueAtTime(0.08, now);
      g.gain.linearRampToValueAtTime(0.01, now + 0.045);
      osc.connect(g); g.connect(ctx.destination);
      osc.start(now); osc.stop(now + 0.05);
    } else if (type === 'step_up') {
      [587.33, 880].forEach((freq, idx) => {
        const osc = ctx.createOscillator();
        const g = ctx.createGain();
        osc.type = 'triangle';
        osc.frequency.setValueAtTime(freq, now + idx * 0.08);
        g.gain.setValueAtTime(0.14, now + idx * 0.08);
        g.gain.exponentialRampToValueAtTime(0.001, now + idx * 0.08 + 0.18);
        osc.connect(g); g.connect(ctx.destination);
        osc.start(now + idx * 0.08); osc.stop(now + idx * 0.08 + 0.19);
      });
    } else if (type === 'bomb_blast') {
      // Deep explosion boom + victory chord
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(140, now);
      osc.frequency.exponentialRampToValueAtTime(28, now + 0.65);
      g.gain.setValueAtTime(0.32, now);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.7);
      osc.connect(g); g.connect(ctx.destination);
      osc.start(now); osc.stop(now + 0.72);
    }
  } catch (e) {}
}

// Global tactile ripple + click sound on every button tap
document.addEventListener('pointerdown', function(e) {
  const btn = e.target.closest('button, .fns-tab-btn, .fns-cta-generate, .fns-cta-stop, .fns-cta-schedule, .fns-cta-post');
  if (!btn) return;
  fnsPlaySoundFX('click');
  const rect = btn.getBoundingClientRect();
  const ripple = document.createElement('span');
  ripple.className = 'fns-click-ripple';
  const size = Math.max(rect.width, rect.height);
  ripple.style.width = ripple.style.height = size + 'px';
  ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
  ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
  btn.appendChild(ripple);
  setTimeout(() => ripple.remove(), 520);
});

// 💥 Trigger Grand Bomb Blast + Tiranga Confetti Celebration on Step 8 Completion!
function fnsTriggerGrandBombBlastCelebration(reelTitle) {
  fnsPlaySoundFX('bomb_blast');
  const ov = document.getElementById('fns-blast-overlay');
  const shell = document.getElementById('foji-nextgen-studio-shell');
  if (shell) {
    shell.classList.remove('fns-screen-shake');
    void shell.offsetWidth;
    shell.classList.add('fns-screen-shake');
  }
  if (ov) {
    ov.style.display = 'flex';
    ov.innerHTML = '<div class="fns-shockwave"></div>';
    const colors = ['#ff9933', '#ffffff', '#138808', '#10b981', '#06b6d4', '#fbbf24'];
    for (let i = 0; i < 55; i++) {
      const p = document.createElement('div');
      const col = colors[i % colors.length];
      const angle = (Math.PI * 2 * i) / 55;
      const dist = 140 + Math.random() * 380;
      const dx = Math.cos(angle) * dist;
      const dy = Math.sin(angle) * dist;
      p.style.cssText = `position:absolute;width:10px;height:10px;border-radius:3px;background:${col};box-shadow:0 0 10px ${col};transition:all 1.15s cubic-bezier(0.16,1,0.3,1);transform:translate(0,0) scale(1);opacity:1;`;
      ov.appendChild(p);
      requestAnimationFrame(() => {
        p.style.transform = `translate(${dx}px, ${dy}px) rotate(${Math.random()*520}deg) scale(0.2)`;
        p.style.opacity = '0';
      });
    }
    setTimeout(() => { ov.style.display = 'none'; ov.innerHTML = ''; }, 1350);
  }
  fnsOpenModal(
    '💥',
    'MISSION ACCOMPLISHED — REEL READY!',
    `<div style="font-weight:800;color:#34d399;font-size:0.95rem;margin-bottom:6px;">🎬 ${reelTitle || 'New 3D Foji Reel'}</div>
     <div style="font-size:0.82rem;color:#cbd5e1;">Commando Makra completed all 8 stages! Your reel is ready in the preview player and All Reels Vault.</div>`
  );
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  _fnsDeferredPwaPrompt = e;
  const btn = document.getElementById('fns-pwa-install-btn');
  if (btn) btn.style.display = 'inline-flex';
});

async function fnsInstallPwaApp() {
  if (_fnsDeferredPwaPrompt) {
    _fnsDeferredPwaPrompt.prompt();
    await _fnsDeferredPwaPrompt.userChoice;
    _fnsDeferredPwaPrompt = null;
    document.getElementById('fns-pwa-install-btn').style.display = 'none';
  } else {
    fnsOpenModal('📲', 'Install Foji Studio App', 'In Chrome mobile menu (⋮), tap <b>"Add to Home screen"</b> or <b>"Install app"</b> for fullscreen native mode.');
  }
}

function fnsOpenModal(icon, title, bodyHtml, isError=false, customButtons=null) {
  const bd = document.getElementById('fns-center-modal-backdrop');
  const box = document.getElementById('fns-center-modal-box');
  document.getElementById('fns-modal-icon').innerText = icon;
  document.getElementById('fns-modal-title').innerText = title;
  document.getElementById('fns-modal-title').style.color = isError ? '#f87171' : '#34d399';
  document.getElementById('fns-modal-body').innerHTML = bodyHtml;
  box.style.borderColor = isError ? '#ef4444' : 'rgba(16, 185, 129, 0.5)';

  const act = document.getElementById('fns-modal-actions');
  if (customButtons && Array.isArray(customButtons)) {
    act.innerHTML = '';
    customButtons.forEach(b => {
      const btn = document.createElement('button');
      btn.className = b.cls || 'fns-cta-generate';
      btn.style.minWidth = '115px';
      btn.innerHTML = b.label;
      btn.onclick = b.onClick;
      act.appendChild(btn);
    });
  } else {
    act.innerHTML = '<button class="fns-cta-generate" style="min-width:110px;" onclick="fnsCloseModal()">Done</button>';
  }
  bd.style.display = 'flex';
}

function fnsCloseModal() {
  document.getElementById('fns-center-modal-backdrop').style.display = 'none';
}

function fnsShowToast(msg, isError=false) {
  const t = document.getElementById('fns-action-toast');
  if (!t) return;
  t.style.display = 'block';
  t.style.borderColor = isError ? '#ef4444' : '#10b981';
  t.innerHTML = msg;
  setTimeout(() => { t.style.display = 'none'; }, 5000);
}

function fnsSwitchTab(num) {
  for (let i = 1; i <= 4; i++) {
    const scr = document.getElementById('fns-screen-' + i);
    const btn = document.getElementById('fns-btn-tab' + i);
    const mbtn = document.getElementById('fns-mnav-' + i);
    if (scr) scr.classList.toggle('active', i === num);
    if (btn) btn.classList.toggle('active', i === num);
    if (mbtn) mbtn.classList.toggle('active', i === num);
  }
}

document.addEventListener('play', function(e) {
  if (e.target && e.target.tagName === 'VIDEO') {
    document.querySelectorAll('video').forEach(v => {
      if (v !== e.target && !v.paused) v.pause();
    });
  }
}, true);

// 🔄 Sync Generate vs Stop Button State across Topbar, Sidebar & Card
function fnsSyncGenerateStopButtons(isActive) {
  _fnsPipelineIsRunning = isActive;
  const topBtn = document.getElementById('fns-primary-gen-btn');
  const sideBtn = document.getElementById('fns-side-gen-btn');
  const cardBtn = document.getElementById('fns-card-gen-btn');

  if (isActive) {
    if (topBtn) { topBtn.className = 'fns-cta-stop'; topBtn.innerHTML = '🛑 Stop Generation'; }
    if (sideBtn) { sideBtn.style.color = '#f87171'; sideBtn.innerHTML = '🛑 Stop Generation'; }
    if (cardBtn) { cardBtn.style.color = '#f87171'; cardBtn.innerHTML = '🛑 Stop'; }
  } else {
    if (topBtn) { topBtn.className = 'fns-cta-generate'; topBtn.innerHTML = '🚀 Generate Reel'; }
    if (sideBtn) { sideBtn.style.color = '#34d399'; sideBtn.innerHTML = '🚀 Generate Reel'; }
    if (cardBtn) { cardBtn.style.color = '#e2e8f0'; cardBtn.innerHTML = '🚀 Generate Reel'; }
  }
}

function fnsHandlePrimaryGenOrStopClick() {
  if (_fnsPipelineIsRunning) {
    fnsOpenModal(
      '🛑',
      'Stop Reel Generation?',
      'Do you want to stop the current video generation right now and return Commando Makra to Standby Duty?',
      true,
      [
        {
          label: '🛑 Yes, Stop Now',
          cls: 'fns-cta-stop',
          onClick: async () => {
            fnsCloseModal();
            fnsShowToast('Stopping pipeline...');
            await fetch('/api/universe/stop_pipeline', { method: 'POST' });
            fnsSyncGenerateStopButtons(false);
            fnsRefreshHub();
          }
        },
        {
          label: 'Continue Mission',
          cls: 'fns-tab-btn',
          onClick: fnsCloseModal
        }
      ]
    );
  } else {
    fnsStartFullVideoGeneration(1);
  }
}

function fnsUpdateConnectedPipelineRoad(telemetry, notifications, latestVideoFile) {
  const stepNum = parseInt(telemetry.step_num || 0, 10);
  const rawStatus = (telemetry.status || 'idle').toLowerCase();
  const epoch = parseFloat(telemetry.epoch || 0);
  const ageSeconds = epoch > 0 ? ((Date.now() / 1000) - epoch) : 999999;

  let status = rawStatus;
  if (status === 'active' && ageSeconds > 300) status = 'idle';
  if (stepNum === 0 && status !== 'error') status = 'idle';

  const isRunning = (status === 'active' && stepNum >= 1);
  fnsSyncGenerateStopButtons(isRunning);

  const arena = document.getElementById('fns-battle-arena');
  const soldierTitle = document.getElementById('fns-foji-soldier-title');
  const soldierSub = document.getElementById('fns-foji-soldier-sub');
  const weaponIcon = document.getElementById('fns-foji-weapon-icon');
  const pctBadge = document.getElementById('fns-mission-pct-badge');

  if (arena) arena.classList.toggle('firing', isRunning);

  if (status === 'idle') {
    _fnsLastCompletedStep = 0;
    document.getElementById('fns-radar-subtitle').innerText = 'Commando Makra on Guard Duty at Post #1';
    if (soldierTitle) soldierTitle.innerText = '🪖 Commando Makra • Guard Duty (Post #1)';
    if (soldierSub) soldierSub.innerText = 'Standing guard — Tap "Generate Reel" to launch mission';
    if (weaponIcon) weaponIcon.innerText = '🛡️';
    if (pctBadge) pctBadge.innerText = 'ON DUTY';
  } else if (status === 'active') {
    const title = telemetry.step_title || `Post #${stepNum}`;
    const detail = telemetry.sub_detail || 'Advancing...';
    document.getElementById('fns-radar-subtitle').innerText = `${title} • ${detail}`;
    if (soldierTitle) soldierTitle.innerText = `🔫 Commando Makra • Firing at Post #${stepNum} (${title})`;
    if (soldierSub) soldierSub.innerText = detail;
    if (weaponIcon) weaponIcon.innerText = '🔥';
    if (pctBadge) pctBadge.innerText = `${Math.min(99, Math.max(12, stepNum * 12))}%`;

    // Celebrate each newly cleared step!
    if (stepNum > _fnsLastCompletedStep && _fnsLastCompletedStep > 0) {
      fnsPlaySoundFX('step_up');
      const prevNode = document.getElementById('fns-pnode-' + (stepNum - 1));
      if (prevNode) {
        prevNode.classList.remove('fns-step-celebrate');
        void prevNode.offsetWidth;
        prevNode.classList.add('fns-step-celebrate');
      }
    }
    _fnsLastCompletedStep = stepNum;
  } else if (status === 'completed') {
    if (_fnsLastCompletedStep > 0 && _fnsLastCompletedStep < 8) {
      _fnsLastCompletedStep = 8;
      fnsTriggerGrandBombBlastCelebration(latestVideoFile);
    }
    if (soldierTitle) soldierTitle.innerText = '🏆 Commando Makra • Mission Accomplished!';
    if (soldierSub) soldierSub.innerText = 'Target Reel secured in Vault!';
    if (weaponIcon) weaponIcon.innerText = '🇮🇳';
    if (pctBadge) pctBadge.innerText = '100% DONE';
  } else if (status === 'error') {
    if (soldierTitle) soldierTitle.innerText = '⚠️ Mission Paused — Check Alert Below';
    if (soldierSub) soldierSub.innerText = telemetry.sub_detail || '';
    if (weaponIcon) weaponIcon.innerText = '⚠️';
    if (pctBadge) pctBadge.innerText = 'PAUSED';
  }

  for (let i = 1; i <= 8; i++) {
    const nd = document.getElementById('fns-pnode-' + i);
    if (!nd) continue;
    nd.className = 'fns-road-node';

    const oldPin = nd.querySelector('.fns-node-soldier-pin');
    if (oldPin) oldPin.remove();

    let badgeEl = nd.querySelector('.fns-stage-state-badge');
    if (!badgeEl) {
      badgeEl = document.createElement('div');
      badgeEl.className = 'fns-stage-state-badge';
      badgeEl.style.cssText = 'font-size:0.64rem;font-weight:800;margin-top:4px;';
      nd.appendChild(badgeEl);
    }

    if (status === 'idle') {
      if (i === 1) {
        nd.classList.add('duty-guard');
        badgeEl.innerText = '🪖 Foji On Duty';
        badgeEl.style.color = '#34d399';
        const pin = document.createElement('span');
        pin.className = 'fns-node-soldier-pin';
        pin.style.background = 'linear-gradient(135deg,#10b981,#059669)';
        pin.innerText = '🪖 GUARDING';
        nd.appendChild(pin);
      } else {
        badgeEl.innerText = 'Standby';
        badgeEl.style.color = '#64748b';
      }
    } else if (status === 'active') {
      if (i < stepNum) {
        nd.classList.add('done');
        badgeEl.innerText = '🎖️ Cleared!';
        badgeEl.style.color = '#34d399';
      } else if (i === stepNum) {
        nd.classList.add('active');
        badgeEl.innerText = '🔫 Firing Live...';
        badgeEl.style.color = '#fbbf24';
        const pin = document.createElement('span');
        pin.className = 'fns-node-soldier-pin';
        pin.innerText = '🪖🔥 FIRING';
        nd.appendChild(pin);
      } else {
        badgeEl.innerText = 'Locked';
        badgeEl.style.color = '#64748b';
      }
    } else if (status === 'completed') {
      nd.classList.add('done');
      badgeEl.innerText = '💥 Victory!';
      badgeEl.style.color = '#34d399';
    } else if (status === 'error') {
      const errStage = stepNum > 0 ? stepNum : 2;
      if (i < errStage) {
        nd.classList.add('done');
        badgeEl.innerText = '🎖️ Cleared';
        badgeEl.style.color = '#34d399';
      } else if (i === errStage) {
        nd.classList.add('error');
        badgeEl.innerText = '✕ Halted';
        badgeEl.style.color = '#fca5a5';
      } else {
        badgeEl.innerText = 'Standby';
        badgeEl.style.color = '#64748b';
      }
    }
  }

  const errBox = document.getElementById('fns-error-banner');
  const errTxt = document.getElementById('fns-error-reason-text');
  if (status === 'error') {
    errBox.style.display = 'block';
    errTxt.innerHTML = `<b>${telemetry.step_title || 'Notice'}:</b> ${telemetry.sub_detail || ''}`;
  } else {
    errBox.style.display = 'none';
  }

  const vidEl = document.getElementById('fns-preview-video');
  const fbEl = document.getElementById('fns-vid-fallback');
  if (latestVideoFile && _fnsActivePreviewFile !== latestVideoFile) {
    _fnsActivePreviewFile = latestVideoFile;
    if (fbEl) fbEl.style.display = 'none';
    if (vidEl) {
      vidEl.style.display = 'block';
      vidEl.src = '/api/universe/video_file/' + encodeURIComponent(latestVideoFile);
    }
    document.getElementById('fns-phone-ep-title').innerText = latestVideoFile;
  }
}

function fnsRenderMasterVault(vaultList) {
  document.getElementById('fns-vault-badge').innerText = vaultList.length;
  const epTotal = document.getElementById('fns-ep-total');
  if (epTotal) epTotal.innerText = vaultList.length;

  for (const item of vaultList) {
    const vf = item.video_file;
    if (vf && !_fnsKnownVaultFiles.has(vf)) {
      _fnsKnownVaultFiles.add(vf);
      if (_fnsFirstLoadDone) {
        fnsTriggerGrandBombBlastCelebration(item.title || vf);
      }
    }
  }

  const sig = JSON.stringify(vaultList.map(v => `${v.video_file}_${v.vault_status}_${v.status_badge}`));
  if (sig === _fnsLastVaultSignature) return;
  _fnsLastVaultSignature = sig;

  const grid = document.getElementById('fns-master-vault-grid');
  if (!grid) return;
  if (!vaultList.length) {
    grid.innerHTML = '<div style="padding:18px;color:#64748b;">No reels yet. Tap "Generate Reel" to start.</div>';
    return;
  }

  grid.innerHTML = vaultList.map(v => {
    const isPub = (v.vault_status === 'published');
    const isSch = (v.vault_status === 'scheduled');
    const badgeBg = isPub ? 'rgba(16,185,129,0.18)' : (isSch ? 'rgba(139,92,246,0.22)' : 'rgba(14,165,233,0.18)');
    const badgeCol = isPub ? '#34d399' : (isSch ? '#c4b5fd' : '#38bdf8');
    const cleanBadge = isPub ? '✓ Published' : (isSch ? '⏰ Scheduled' : '● Ready');
    const vidUrl = '/api/universe/video_file/' + encodeURIComponent(v.video_file) + '#t=0.1';

    return `
      <div class="fns-vault-card ${v.vault_status || ''}">
        <video src="${vidUrl}" controls playsinline preload="metadata" style="width:100%;aspect-ratio:9/16;max-height:340px;object-fit:cover;background:#000;"></video>
        <div style="padding:13px;display:flex;flex-direction:column;gap:6px;flex:1;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
            <span style="font-size:0.68rem;font-weight:800;padding:3px 9px;border-radius:99px;background:${badgeBg};color:${badgeCol};">${cleanBadge}</span>
            <span style="font-size:0.68rem;color:#64748b;">${v.created_at || ''}</span>
          </div>
          <div style="font-size:0.85rem;font-weight:800;color:#fff;">${v.title || v.video_file}</div>
          <div style="font-size:0.74rem;color:#94a3b8;line-height:1.4;">"${(v.dialogue || '').slice(0, 85)}"</div>
          <div style="display:flex;gap:6px;margin-top:auto;padding-top:10px;">
            ${!isPub ? `<button class="fns-cta-schedule" style="flex:1;padding:8px;font-size:0.74rem;" onclick="fnsApproveAndScheduleSpecific('${v.video_file}')">Schedule</button>` : ''}
            <button class="fns-cta-post" style="flex:1;padding:8px;font-size:0.74rem;" onclick="fnsPublishSpecificNow('${v.video_file}')">${isPub ? 'Repost' : 'Post Now'}</button>
            <a href="/api/universe/video_file/${encodeURIComponent(v.video_file)}" download="${v.video_file}" class="fns-tab-btn" style="padding:8px 10px;font-size:0.74rem;text-decoration:none;color:#34d399;border-color:rgba(255,255,255,0.1);">📥</a>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function fnsRenderQueueLists(q) {
  const unList = q.unapproved_videos || [];
  const scList = q.scheduled_posts || [];

  document.getElementById('fns-unapproved-cnt').innerText = unList.length + ' Ready';
  document.getElementById('fns-scheduled-cnt').innerText = scList.length + ' Scheduled';
  document.getElementById('fns-q-badge').innerText = scList.length;

  const qSig = JSON.stringify({
    u: unList.map(x => x.video_file),
    s: scList.map(x => `${x.id}_${x.video_file}_${x.scheduled_display}`)
  });
  if (qSig === _fnsLastQueueSignature) return;
  _fnsLastQueueSignature = qSig;

  const uBox = document.getElementById('fns-unapproved-list');
  if (uBox) {
    if (!unList.length) {
      uBox.innerHTML = '<div style="padding:12px;color:#64748b;font-size:0.78rem;">No unscheduled reels waiting.</div>';
    } else {
      uBox.innerHTML = unList.map(v => `
        <div class="fns-queue-card">
          <div style="flex:1;min-width:160px;">
            <div style="font-size:0.83rem;font-weight:800;color:#fff;">${v.title || v.video_file}</div>
            <div style="font-size:0.72rem;color:#94a3b8;margin-top:2px;">"${(v.dialogue || '').slice(0, 75)}"</div>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            <button class="fns-tab-btn" style="padding:7px 10px;font-size:0.73rem;border-color:rgba(255,255,255,0.12);" onclick="fnsPreviewSpecificVideo('${v.video_file}', '${(v.title||'').replace(/'/g, '')}')">▶ Play</button>
            <button class="fns-cta-schedule" style="padding:7px 12px;font-size:0.73rem;" onclick="fnsApproveAndScheduleSpecific('${v.video_file}')">Schedule</button>
            <button class="fns-cta-post" style="padding:7px 12px;font-size:0.73rem;" onclick="fnsPublishSpecificNow('${v.video_file}')">Post</button>
          </div>
        </div>
      `).join('');
    }
  }

  const sBox = document.getElementById('fns-scheduled-list');
  if (sBox) {
    if (!scList.length) {
      sBox.innerHTML = '<div style="padding:12px;color:#64748b;font-size:0.78rem;">No scheduled reels in queue.</div>';
    } else {
      sBox.innerHTML = scList.map((v, idx) => `
        <div class="fns-queue-card" style="border-color:rgba(139,92,246,0.45);background:rgba(28,18,52,0.45);">
          <div style="flex:1;min-width:160px;">
            <span style="background:rgba(139,92,246,0.25);color:#ddd6fe;font-size:0.66rem;font-weight:800;padding:2px 8px;border-radius:99px;">${v.scheduled_display}</span>
            <div style="font-size:0.83rem;font-weight:800;color:#fff;margin-top:5px;">${v.title || v.video_file}</div>
          </div>
          <div style="display:flex;gap:6px;">
            <button class="fns-cta-post" style="padding:6px 10px;font-size:0.72rem;" onclick="fnsPublishSpecificNow('${v.video_file}')">Post Now</button>
            <button class="fns-tab-btn" style="padding:6px 10px;font-size:0.72rem;color:#f87171;" onclick="fnsRemoveScheduled('${v.id}')">Remove</button>
          </div>
        </div>
      `).join('');
    }
  }
}

async function fnsRefreshHub() {
  try {
    const r = await fetch('/api/universe/status?t=' + Date.now());
    const d = await r.json();
    _fnsState = d.director_state || _fnsState;
    _fnsTracks = d.tracks || [];
    if (d.server_time_ist) {
      const clk = document.getElementById('fns-server-clock');
      if (clk) clk.innerText = d.server_time_ist;
    }
    if (d.next_open_slot) {
      const nslot = document.getElementById('fns-next-slot-sidebar');
      if (nslot) nslot.innerText = d.next_open_slot.display_time;
    }

    fnsUpdateConnectedPipelineRoad(d.telemetry || {}, d.notifications || [], d.latest_video_file || '');
    fnsRenderMasterVault(d.master_vault || []);
    fnsRenderTrackSelectors();
    fnsRenderNotifications(d.notifications || []);
    fnsRenderQueueLists(d.queue || {});
    _fnsFirstLoadDone = true;
  } catch (e) {}
}

function fnsPreviewSpecificVideo(vfile, title) {
  fnsSwitchTab(1);
  _fnsActivePreviewFile = vfile;
  const vid = document.getElementById('fns-preview-video');
  const fb = document.getElementById('fns-vid-fallback');
  if (fb) fb.style.display = 'none';
  if (vid) {
    vid.style.display = 'block';
    vid.src = '/api/universe/video_file/' + encodeURIComponent(vfile);
    vid.play().catch(() => {});
  }
  document.getElementById('fns-phone-ep-title').innerText = title || vfile;
}

async function fnsApproveAndScheduleLatest() {
  await fnsApproveAndScheduleSpecific('');
}

async function fnsApproveAndScheduleSpecific(vfile) {
  fnsShowToast('Scheduling reel...');
  try {
    const r = await fetch('/api/universe/approve_and_schedule', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ video_file: vfile })
    });
    const d = await r.json();
    if (d.ok) {
      const slotTxt = (d.scheduled_item && d.scheduled_item.scheduled_display) ? d.scheduled_item.scheduled_display : 'Next Slot';
      fnsOpenModal('📅', 'Scheduled', `Reel locked for <b>${slotTxt}</b>.`);
      fnsRefreshHub();
    } else {
      fnsOpenModal('⚠️', 'Schedule Notice', d.error || 'Could not schedule reel.', true);
    }
  } catch (e) {
    fnsOpenModal('⚠️', 'Connection Error', String(e), true);
  }
}

async function fnsRemoveScheduled(id) {
  await fetch('/api/universe/remove_scheduled', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ id: id })
  });
  fnsRefreshHub();
}

async function fnsPublishLatestReel() {
  await fnsPublishSpecificNow(_fnsActivePreviewFile || '');
}

async function fnsPublishSpecificNow(vfile) {
  fnsOpenModal('🚀', 'Publishing to Instagram...', 'Selecting best video frame and uploading to <b>@ai_foji_lovelife</b>...');
  try {
    const r = await fetch('/api/universe/publish_latest_reel', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ video_file: vfile })
    });
    const d = await r.json();
    if (d.ok) {
      const linkHtml = d.permalink ? `<div style="margin-top:10px;"><a href="${d.permalink}" target="_blank" style="color:#34d399;font-weight:800;">View on Instagram ↗</a></div>` : '';
      fnsOpenModal('✅', 'Published on Instagram', `Reel is now live on <b>@ai_foji_lovelife</b>.${linkHtml}`);
      fnsRefreshHub();
    } else {
      fnsOpenModal('❌', 'Upload Failed', d.error || 'Could not upload reel.', true);
    }
  } catch (e) {
    fnsOpenModal('❌', 'Upload Error', String(e), true);
  }
}

function fnsRenderTrackSelectors() {
  const qBox = document.getElementById('fns-quick-tracks');
  const s2Box = document.getElementById('fns-s2-tracks-list');
  const autoBtn = document.getElementById('fns-autorotate-btn');

  if (autoBtn) {
    if (_fnsState.active_mode === 'auto_rotate') {
      autoBtn.innerText = '🔄 Auto-Rotate: ON';
      autoBtn.classList.add('active');
    } else {
      autoBtn.innerText = '📌 Single Track Mode';
      autoBtn.classList.remove('active');
    }
  }

  if (qBox) {
    qBox.innerHTML = _fnsTracks.map(t => {
      const isSel = (_fnsState.active_mode === 'locked_track' && _fnsState.selected_track_id === t.id);
      return `<div class="fns-track-item ${isSel ? 'active' : ''}" onclick="fnsSelectTrack('${t.id}')">
        <div style="font-size:0.8rem;font-weight:800;color:#fff;">${t.name}</div>
        <div style="font-size:0.68rem;color:#34d399;margin-top:3px;">Part ${t.next_part} ${isSel ? '• Active' : ''}</div>
      </div>`;
    }).join('');
  }

  if (s2Box) {
    s2Box.innerHTML = _fnsTracks.map(t => {
      const isSel = (_fnsState.active_mode === 'locked_track' && _fnsState.selected_track_id === t.id);
      return `<div class="fns-track-item ${isSel ? 'active' : ''}" style="margin-bottom:8px;" onclick="fnsSelectTrack('${t.id}')">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="font-size:0.82rem;font-weight:800;color:#fff;">${t.name}</span>
          <span class="fns-badge-live">Part ${t.next_part}</span>
        </div>
      </div>`;
    }).join('');
  }
}

function fnsRenderNotifications(list) {
  const nBox = document.getElementById('fns-notif-feed');
  if (!nBox) return;
  if (!list.length) {
    nBox.innerHTML = '<div style="color:#64748b;">No recent activity.</div>';
    return;
  }
  nBox.innerHTML = list.slice(0, 8).map(n => `
    <div style="padding:7px 10px;background:rgba(15,23,42,0.65);border-radius:8px;border-left:3px solid ${n.status==='error'?'#ef4444':(n.status==='success'?'#10b981':'#06b6d4')};display:flex;justify-content:space-between;gap:10px;">
      <span><b>${n.title || 'Update'}:</b> ${n.message || ''}</span>
      <span style="color:#64748b;white-space:nowrap;">${n.time_str || ''}</span>
    </div>
  `).join('');
}

async function fnsSelectTrack(trackId) {
  await fetch('/api/universe/select_track', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ active_mode: 'locked_track', selected_track_id: trackId })
  });
  fnsRefreshHub();
}

async function fnsSetAutoRotate() {
  await fetch('/api/universe/select_track', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ active_mode: 'auto_rotate' })
  });
  fnsRefreshHub();
}

async function fnsLockTwist() {
  const val = document.getElementById('fns-custom-twist').value;
  await fetch('/api/universe/select_track', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ custom_idea: val })
  });
  fnsShowToast('Story idea saved ✓');
}

async function fnsStartFullVideoGeneration(cnt=1) {
  const twist = document.getElementById('fns-custom-twist').value;
  _fnsLastCompletedStep = 1;
  fnsUpdateConnectedPipelineRoad({
    step_num: 1,
    step_title: 'Generating Script',
    sub_detail: 'Commando Makra advancing to Post #1...',
    status: 'active',
    updated_at: 'Now',
    epoch: Date.now() / 1000
  }, [], '');

  fnsShowToast('🪖 Mission started! Commando Makra advancing...');
  try {
    const r = await fetch('/api/universe/trigger_pipeline', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ custom_idea: twist, count: cnt })
    });
    const d = await r.json();
    if (d.ok) fnsShowToast('Pipeline running ✓');
    else fnsOpenModal('⚠️', 'Could Not Start', d.error || 'Failed', true);
  } catch (e) {
    fnsOpenModal('⚠️', 'Request Error', String(e), true);
  }
}

async function fnsSaveScheduleSlots() {
  const nt = document.getElementById('fns-cfg-night-time').value || '02:30';
  const s1 = document.getElementById('fns-slot-1').value || '07:00';
  const s2 = document.getElementById('fns-slot-2').value || '13:30';
  const s3 = document.getElementById('fns-slot-3').value || '19:30';
  await fetch('/api/universe/save_schedule', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      night_batch_time: nt,
      night_batch_count: 3,
      pre_slot_minutes: 30,
      daily_slots: [s1, s2, s3]
    })
  });
  fnsOpenModal('✅', 'Schedule Saved', `Daily slots locked at <b>${s1}, ${s2}, ${s3} IST</b>.`);
  fnsRefreshHub();
}

async function fnsGenerateLiveScriptPreview() {
  const outBox = document.getElementById('fns-live-script-output');
  outBox.style.display = 'block';
  outBox.innerHTML = 'Writing script preview...';
  const twist = document.getElementById('fns-custom-twist').value;
  try {
    const r = await fetch('/api/universe/generate_preview_script', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ track_id: _fnsState.selected_track_id, custom_idea: twist })
    });
    const d = await r.json();
    if (d.ok && d.package) {
      const p = d.package;
      outBox.innerHTML = `
        <div style="color:#34d399;font-weight:800;margin-bottom:4px;">${p.emotion_name} (Part ${p.part_number})</div>
        <div style="color:#cbd5e1;margin-bottom:4px;"><b>Scene:</b> ${p.scene_summary}</div>
        <div style="color:#fff;"><b>Dialogue:</b> "${p.dialogue_line_1_hinglish}"</div>
      `;
    } else {
      outBox.innerHTML = '<span style="color:#f87171;">Error: ' + (d.error || 'Failed') + '</span>';
    }
  } catch (e) {
    outBox.innerHTML = '<span style="color:#f87171;">Error: ' + e + '</span>';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const shell = document.getElementById('foji-nextgen-studio-shell');
  if (shell && document.body.firstChild) {
    document.body.insertBefore(shell, document.body.firstChild);
  }
  fnsRefreshHub();
  setInterval(fnsRefreshHub, 3000);
});
</script>
"""
                html_text = html_text.replace("</body>", widget_html + "\n</body>", 1)
                response.set_data(html_text)
    except Exception:
        pass
    return response


@app.errorhandler(Exception)
def _handle_all_api_exceptions_as_json(e):
    from flask import request, jsonify
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "status": "error", "error": str(e), "message": str(e)}), 200
    raise e

@app.errorhandler(500)
@app.errorhandler(502)
@app.errorhandler(504)
def _handle_5xx_as_json(e):
    from flask import request, jsonify
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "status": "error", "error": str(e), "message": str(e)}), 200
    return str(e), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7860)), debug=False)