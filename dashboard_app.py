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
    import os, subprocess
    thumb_p = str(video_file_path) + ".jpg"
    if not os.path.exists(thumb_p):
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", "00:00:01", "-i", str(video_file_path), "-frames:v", "1", "-q:v", "2", thumb_p],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15
            )
        except Exception:
            pass
    if not os.path.exists(thumb_p):
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


@app.route("/videos/<path:filename>")
def serve_video(filename):
    return send_from_directory(os.path.abspath("output/raw_videos"), filename)


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
            elif data.get("status") == "active" and age > 1200:
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
    Fixes the horizontal green line glitch on Instagram Reels by normalizing the MP4
    to macroblock-aligned 16x16 divisible dimensions (720x1280), 8-bit yuv420p color space,
    H.264 High Profile, and faststart header right before Instagram upload.
    """
    if not os.path.exists(input_mp4_path):
        return input_mp4_path

    # Find ffmpeg executable (system ffmpeg or imageio_ffmpeg)
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

    if os.path.exists(clean_out_path) and os.path.getsize(clean_out_path) > 100 * 1024:
        return clean_out_path

    try:
        import subprocess
        print(f"🛠️ [IG Anti-Green-Line Fix] Optimizing {base_name} to 720x1280 (16x16 macroblock aligned yuv420p)...")
        cmd = [
            ffmpeg_bin, "-y",
            "-i", input_mp4_path,
            "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,format=yuv420p",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-profile:v", "high",
            "-level", "4.1",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            clean_out_path
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90, check=True)
        if os.path.exists(clean_out_path) and os.path.getsize(clean_out_path) > 100 * 1024:
            print(f"✅ [IG Anti-Green-Line Fix] Ready: {clean_out_path}")
            return clean_out_path
    except Exception as e:
        print(f"⚠️ [IG Sanitizer Warning] Using original MP4 ({e})")

    return input_mp4_path


def _publish_specific_video_to_ig(video_file, custom_caption=""):
    vname = os.path.basename(str(video_file))
    vpath = os.path.abspath(os.path.join("output/raw_videos", vname))
    if not os.path.exists(vpath):
        _fud.pull_latest_cloud_state_for_frontend()
    if not os.path.exists(vpath):
        raise FileNotFoundError(f"Video file {vname} not found in output/raw_videos!")

    if not custom_caption:
        for it in _fud.build_master_all_reels_vault():
            if it.get("video_file") == vname and it.get("caption"):
                custom_caption = it["caption"]
                break
    if not custom_caption:
        custom_caption = "🎖️ Foji & Fojan 3D Story | Follow @ai_foji_lovelife 🇮🇳🔥 #indianarmy #faujilife #agniveer #armyreels"

    # Pass video through Anti-Green-Line Macroblock Sanitizer before uploading to Instagram!
    ig_safe_vpath = _sanitize_mp4_for_instagram_no_green_line(vpath)

    import insta_bot
    if hasattr(insta_bot, "upload_reel_to_instagram"):
        res = insta_bot.upload_reel_to_instagram(ig_safe_vpath, custom_caption)
    elif hasattr(insta_bot, "post_reel"):
        res = insta_bot.post_reel(ig_safe_vpath, custom_caption)
    elif hasattr(insta_bot, "upload_to_instagram"):
        res = insta_bot.upload_to_instagram(ig_safe_vpath, custom_caption)
    else:
        from instagrapi import Client
        cl = Client()
        sess_file = "data/ig_session.json"
        if os.path.exists(sess_file):
            cl.load_settings(sess_file)
        media = cl.clip_upload(ig_safe_vpath, custom_caption)
        res = getattr(media, "pk", "LIVE_ON_IG")

    pub_item = _fud.mark_video_as_published_in_vault(vname, custom_caption, media_pk=res)
    try:
        import gemini_bot
        gemini_bot.push_app_notification("success", "📸 Reel Posted on Instagram!", f"{vname} is now LIVE on @ai_foji_lovelife (Zero Green-Line HD)!", "success")
        gemini_bot.send_alert(f"📸 *Reel Published on Instagram!*\n🎬 Video: `{vname}`\n✅ Status: *LIVE ON @ai_foji_lovelife*")
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
        if vfile and os.path.exists(os.path.join(raw_dir, vfile)):
            newest_vid = os.path.join(raw_dir, vfile)
        else:
            mp4s = [os.path.join(raw_dir, f) for f in os.listdir(raw_dir) if f.endswith(".mp4")] if os.path.exists(raw_dir) else []
            if not mp4s:
                return jsonify({"ok": False, "error": "No generated MP4 video found in output/raw_videos yet!"}), 404
            newest_vid = max(mp4s, key=os.path.getmtime)

        vname = os.path.basename(newest_vid)
        if not custom_caption:
            for v_it in _fud.build_master_all_reels_vault():
                if v_it.get("video_file") == vname and v_it.get("caption"):
                    custom_caption = v_it["caption"]
                    break
        if not custom_caption:
            custom_caption = "🎖️ Foji Life 3D Story | Follow @ai_foji_lovelife for Next Part! 🇮🇳🔥 #indianarmy #faujilife #armyreels"

        media = _publish_specific_video_to_ig(newest_vid, custom_caption)
        pk_val = getattr(media, "pk", "LIVE")
        pub_item = _fud.mark_video_as_published_in_vault(vname, custom_caption, pk_val)

        try:
            import gemini_bot
            gemini_bot.push_app_notification("success", "📲 Reel Posted on Instagram!", f"{vname} is now LIVE on @ai_foji_lovelife!", "success")
        except Exception:
            pass

        return jsonify({
            "ok": True,
            "message": f"🎉 100% CONFIRMED! Reel ({vname}) Published on Instagram (@ai_foji_lovelife) at {pub_item['published_at']}!",
            "published_item": pub_item
        })
    except Exception as e:
        return jsonify({"ok": False, "error": f"Instagram Upload Failed: {str(e)}"}), 500


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
    safe_name = os.path.basename(filename)
    p = os.path.join("output/raw_videos", safe_name)
    if os.path.exists(p):
        return _send_file(os.path.abspath(p), mimetype="video/mp4")
    return ("Not found", 404)


@app.route("/api/universe/latest_video", methods=["GET"])
def api_universe_latest_video():
    raw_dir = "output/raw_videos"
    if os.path.exists(raw_dir):
        mp4s = [os.path.join(raw_dir, f) for f in os.listdir(raw_dir) if f.endswith(".mp4")]
        if mp4s:
            newest = max(mp4s, key=os.path.getmtime)
            return _send_file(os.path.abspath(newest), mimetype="video/mp4")
    return ("No video yet", 404)


@app.after_request
def _inject_foji_universe_command_hub(response):
    try:
        if response.content_type and "text/html" in response.content_type and response.status_code == 200:
            html_text = response.get_data(as_text=True)
            if "</body>" in html_text and "id=\"foji-nextgen-studio-shell\"" not in html_text:
                widget_html = """
<!-- 🎖️ FOJI AI STUDIO — ZERO-LAG PIPELINE + POPUP MODAL + MASTER REELS VAULT -->
<style>
body > *:not(#foji-nextgen-studio-shell):not(#fns-center-modal-backdrop):not(script):not(style) { display: none !important; }
html, body {
    margin: 0 !important; padding: 0 !important;
    background: #040812 !important; color: #e2e8f0 !important;
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    min-height: 100vh; overflow-x: hidden;
}
#foji-nextgen-studio-shell {
    background: radial-gradient(circle at 12% 10%, #0d2235 0%, #060c17 55%, #03060c 100%);
    min-height: 100vh; width: 100%; display: flex; flex-direction: column; box-sizing: border-box;
}
.fns-topbar {
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;
    gap: 12px; padding: 13px 24px; background: rgba(7, 13, 25, 0.96);
    border-bottom: 1px solid rgba(0, 245, 212, 0.25); position: sticky; top: 0; z-index: 1000;
}
.fns-brand { display: flex; align-items: center; gap: 12px; }
.fns-logo-orb {
    width: 42px; height: 42px; border-radius: 12px;
    background: linear-gradient(135deg, #00f5d4, #0ea5e9);
    display: flex; align-items: center; justify-content: center;
    font-weight: 900; font-size: 1.25rem; color: #031117;
    box-shadow: 0 0 22px rgba(0, 245, 212, 0.5);
}
.fns-tabs { display: flex; gap: 7px; flex-wrap: wrap; }
.fns-tab-btn {
    background: rgba(24, 35, 56, 0.78); border: 1px solid rgba(255,255,255,0.1);
    color: #94a3b8; padding: 9px 15px; border-radius: 11px;
    font-size: 0.81rem; font-weight: 700; cursor: pointer; transition: all 0.2s;
}
.fns-tab-btn:hover { color: #fff; border-color: rgba(0, 245, 212, 0.45); }
.fns-tab-btn.active {
    background: linear-gradient(135deg, rgba(0, 245, 212, 0.22), rgba(14, 165, 233, 0.22));
    border-color: #00f5d4; color: #00f5d4; box-shadow: 0 0 18px rgba(0, 245, 212, 0.25);
}
.fns-cta-generate {
    background: linear-gradient(90deg, #00f5d4, #0ea5e9); color: #021017;
    border: none; padding: 10px 16px; border-radius: 11px;
    font-size: 0.82rem; font-weight: 900; cursor: pointer;
    box-shadow: 0 0 20px rgba(0, 245, 212, 0.4);
}
.fns-cta-schedule {
    background: linear-gradient(90deg, #a855f7, #ec4899); color: #fff;
    border: none; padding: 10px 15px; border-radius: 11px;
    font-size: 0.81rem; font-weight: 800; cursor: pointer;
}
.fns-cta-post {
    background: linear-gradient(90deg, #10b981, #059669); color: #fff;
    border: none; padding: 10px 15px; border-radius: 11px;
    font-size: 0.81rem; font-weight: 800; cursor: pointer;
}
.fns-body { display: grid; grid-template-columns: 255px 1fr; flex: 1; }
@media (max-width: 1100px) { .fns-body { grid-template-columns: 1fr; } }
.fns-sidebar {
    background: rgba(6, 11, 22, 0.94); border-right: 1px solid rgba(255,255,255,0.07);
    padding: 18px; display: flex; flex-direction: column; gap: 14px;
}
.fns-side-box {
    background: rgba(13, 21, 38, 0.82); border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px; padding: 13px;
}
.fns-badge-live {
    background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981;
    color: #34d399; font-size: 0.65rem; font-weight: 800; padding: 2px 8px; border-radius: 99px;
}
.fns-main-panel { padding: 20px 24px; overflow-y: auto; }
.fns-screen { display: none; }
.fns-screen.active { display: block; }
.fns-s1-grid { display: grid; grid-template-columns: 1fr 330px; gap: 22px; }
@media (max-width: 1020px) { .fns-s1-grid { grid-template-columns: 1fr; } }
.fns-pipeline-card {
    background: rgba(11, 19, 35, 0.9); border: 1px solid rgba(0, 245, 212, 0.24);
    border-radius: 18px; padding: 20px; box-shadow: 0 12px 35px rgba(0,0,0,0.45);
}

/* CONNECTED S-CURVE PIPELINE ROAD */
.fns-road-wrap {
    margin: 16px 0 12px 0; padding: 18px 16px;
    background: radial-gradient(circle at 50% 50%, rgba(0,245,212,0.07), rgba(6,12,24,0.95));
    border: 1px solid rgba(0,245,212,0.2); border-radius: 16px;
}
.fns-road-row { display: flex; align-items: center; justify-content: space-between; gap: 0; position: relative; }
.fns-road-node {
    flex: 1; background: rgba(17, 28, 48, 0.92); border: 2px solid rgba(255,255,255,0.14);
    border-radius: 13px; padding: 10px; text-align: center; position: relative; z-index: 2;
    transition: all 0.25s; min-width: 105px;
}
.fns-road-node.done {
    border-color: #10b981; background: linear-gradient(135deg, rgba(16,185,129,0.2), rgba(13,25,43,0.95));
    box-shadow: 0 0 14px rgba(16,185,129,0.28);
}
.fns-road-node.active {
    border-color: #00f5d4; background: linear-gradient(135deg, rgba(0,245,212,0.32), rgba(14,165,233,0.25));
    box-shadow: 0 0 28px rgba(0,245,212,0.75); transform: scale(1.04);
    animation: fnsNodeGlow 1.1s infinite alternate;
}
.fns-road-node.error {
    border-color: #ef4444; background: linear-gradient(135deg, rgba(239,68,68,0.32), rgba(40,12,18,0.95));
    box-shadow: 0 0 28px rgba(239,68,68,0.75);
}
@keyframes fnsNodeGlow {
    0% { box-shadow: 0 0 12px rgba(0,245,212,0.4); }
    100% { box-shadow: 0 0 30px rgba(0,245,212,0.95); }
}
.fns-road-connector { height: 5px; width: 30px; background: rgba(255,255,255,0.12); transition: all 0.25s; }
.fns-road-connector.done { background: linear-gradient(90deg, #10b981, #00f5d4); box-shadow: 0 0 12px #00f5d4; }
.fns-road-connector.error { background: #ef4444; box-shadow: 0 0 12px #ef4444; }
.fns-road-turn { height: 26px; width: 5px; margin-left: auto; margin-right: 55px; background: rgba(255,255,255,0.12); }
.fns-road-turn.done { background: #10b981; box-shadow: 0 0 12px #10b981; }

.fns-error-box {
    display: none; margin-top: 14px; padding: 14px 16px; border-radius: 13px;
    background: linear-gradient(135deg, rgba(127, 29, 29, 0.55), rgba(24, 10, 15, 0.96));
    border: 2px solid #ef4444; color: #fecaca;
}
.fns-iphone-frame {
    background: #040710; border: 4px solid #1e293b; border-radius: 36px; padding: 13px;
    box-shadow: 0 22px 55px rgba(0,0,0,0.85), inset 0 0 18px rgba(0, 245, 212, 0.16);
    display: flex; flex-direction: column; align-items: center;
}
.fns-iphone-notch { width: 95px; height: 18px; background: #0f172a; border-radius: 99px; margin-bottom: 8px; }
.fns-iphone-screen {
    width: 100%; height: 440px; background: #080e1a; border-radius: 24px;
    overflow: hidden; position: relative; display: flex; align-items: center; justify-content: center;
}
.fns-iphone-overlay {
    position: absolute; bottom: 12px; left: 12px; right: 12px;
    background: rgba(0,0,0,0.7); backdrop-filter: blur(6px);
    padding: 9px 11px; border-radius: 11px; font-size: 0.72rem; color: #fff; pointer-events: none;
}
.fns-track-item {
    background: rgba(20, 32, 56, 0.78); border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px; padding: 10px 12px; cursor: pointer; transition: all 0.2s;
}
.fns-track-item.active {
    border: 2px solid #00f5d4; background: linear-gradient(135deg, rgba(0, 245, 212, 0.18), rgba(15, 23, 42, 0.92));
}
.fns-queue-card {
    background: rgba(16, 26, 46, 0.88); border: 1px solid rgba(56, 189, 248, 0.24);
    border-radius: 13px; padding: 12px 14px; margin-bottom: 10px;
    display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
}

/* MASTER REELS VAULT GRID (TAB 3) */
.fns-vault-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(265px, 1fr)); gap: 18px; margin-top: 14px;
}
.fns-vault-card {
    background: rgba(13, 22, 40, 0.92); border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px; overflow: hidden; display: flex; flex-direction: column;
    box-shadow: 0 10px 28px rgba(0,0,0,0.5);
}
.fns-vault-card.published { border: 2px solid #10b981; }
.fns-vault-card.scheduled { border: 2px solid #a855f7; }

/* FULL-SCREEN CENTER MODAL POPUP FOR VIDEO READY / ERROR / IG POST */
#fns-center-modal-backdrop {
    display: none; position: fixed; inset: 0; background: rgba(2, 6, 18, 0.82);
    backdrop-filter: blur(8px); z-index: 99999; align-items: center; justify-content: center; padding: 20px;
}
.fns-center-modal {
    background: linear-gradient(145deg, #0d1b30, #070e1c);
    border: 2px solid #00f5d4; border-radius: 20px; max-width: 520px; width: 100%;
    padding: 24px; text-align: center; box-shadow: 0 25px 80px rgba(0,0,0,0.9), 0 0 40px rgba(0,245,212,0.3);
}
</style>

<!-- CENTER SCREEN POPUP MODAL (NEVER MISS A VIDEO READY, ERROR, OR IG POST RESULT!) -->
<div id="fns-center-modal-backdrop">
  <div class="fns-center-modal" id="fns-center-modal-box">
    <div id="fns-modal-icon" style="font-size:2.6rem;margin-bottom:8px;">🎉</div>
    <div id="fns-modal-title" style="font-size:1.2rem;font-weight:900;color:#fff;margin-bottom:8px;">Notification</div>
    <div id="fns-modal-body" style="font-size:0.88rem;color:#cbd5e1;line-height:1.55;margin-bottom:18px;word-break:break-word;"></div>
    <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;" id="fns-modal-actions">
      <button class="fns-cta-generate" onclick="fnsCloseModal()">👍 OK, GOT IT</button>
    </div>
  </div>
</div>

<div id="foji-nextgen-studio-shell">
  <!-- TOP NAVIGATION BAR -->
  <div class="fns-topbar">
    <div class="fns-brand">
      <div class="fns-logo-orb">F</div>
      <div>
        <div style="font-size:1.14rem;font-weight:900;color:#fff;">FOJI AI STUDIO</div>
        <div style="font-size:0.7rem;color:#00f5d4;font-weight:700;">ZERO-LAG LIVE RADAR • SMART SCHEDULE QUEUE • MASTER REELS VAULT</div>
      </div>
    </div>

    <div class="fns-tabs">
      <button class="fns-tab-btn active" id="fns-btn-tab1" onclick="fnsSwitchTab(1)">🖥️ 1. Live Pipeline & Preview</button>
      <button class="fns-tab-btn" id="fns-btn-tab2" onclick="fnsSwitchTab(2)">📅 2. Approve & Schedule Queue (<span id="fns-q-badge">0</span>)</button>
      <button class="fns-tab-btn" id="fns-btn-tab3" onclick="fnsSwitchTab(3)">🎞️ 3. All Reels Vault (<span id="fns-vault-badge">0</span>)</button>
      <button class="fns-tab-btn" id="fns-btn-tab4" onclick="fnsSwitchTab(4)">🎬 4. Story Tracks & Characters</button>
    </div>

    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <button class="fns-cta-generate" onclick="fnsStartFullVideoGeneration(1)">🚀 GENERATE 1 REEL</button>
      <button class="fns-cta-schedule" onclick="fnsApproveAndScheduleLatest()">📅 APPROVE & SCHEDULE</button>
      <button class="fns-cta-post" onclick="fnsPublishLatestReel()">📲 POST TO IG NOW</button>
    </div>
  </div>

  <div class="fns-body">
    <!-- LEFT SIDEBAR -->
    <div class="fns-sidebar">
      <div class="fns-side-box">
        <div style="font-size:0.78rem;font-weight:900;color:#00f5d4;margin-bottom:8px;">⏰ AUTO-PILOT ENGINE RULES</div>
        <div style="font-size:0.72rem;color:#cbd5e1;line-height:1.55;">
          🌙 <b>02:30 AM IST:</b> Auto-creates <b>3 Videos</b>.<br/>
          ⚡ <b>T-30 Min Rule:</b> Creates <b>1 Video</b> 30m before every slot.<br/>
          🎞️ <b>Master Vault:</b> Every reel stays saved permanently (Posted & Unposted)!
        </div>
        <div style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.08);font-size:0.72rem;color:#38bdf8;">
          🕒 IST Clock: <b id="fns-server-clock">Syncing...</b>
        </div>
      </div>

      <div class="fns-side-box">
        <div style="font-size:0.78rem;font-weight:800;color:#fff;margin-bottom:8px;">⚡ Quick Studio Actions</div>
        <button class="fns-tab-btn" style="width:100%;margin-bottom:7px;text-align:left;color:#00f5d4;" onclick="fnsStartFullVideoGeneration(1)">🚀 Generate 1 Reel Now</button>
        <button class="fns-tab-btn" style="width:100%;margin-bottom:7px;text-align:left;color:#a855f7;" onclick="fnsStartFullVideoGeneration(3)">🌙 Run 3-Video Batch Now</button>
        <button class="fns-tab-btn" style="width:100%;margin-bottom:7px;text-align:left;color:#f472b6;" onclick="fnsApproveAndScheduleLatest()">📅 Approve & Schedule Next</button>
        <button class="fns-tab-btn" style="width:100%;margin-bottom:7px;text-align:left;color:#34d399;" onclick="fnsPublishLatestReel()">📲 Post Latest to IG Now</button>
        <button class="fns-tab-btn" style="width:100%;text-align:left;color:#38bdf8;" onclick="fnsSwitchTab(3)">🎞️ Open All Reels Vault</button>
      </div>

      <div class="fns-side-box">
        <div style="font-size:0.75rem;font-weight:800;color:#fff;margin-bottom:5px;">📌 Next Open Schedule Slot:</div>
        <div id="fns-next-slot-sidebar" style="font-size:0.78rem;color:#00f5d4;font-weight:800;">Calculating...</div>
      </div>

      <div class="fns-side-box" style="margin-top:auto;">
        <div style="font-size:0.74rem;font-weight:800;color:#00f5d4;margin-bottom:4px;">🛡️ BACKEND LOCK v1.0</div>
        <div style="font-size:0.71rem;color:#94a3b8;line-height:1.45;">
          • Pure Cookie Auth: <b>Locked 🟢</b><br/>
          • 13-Step Gemini Bot: <b>Safe 🟢</b><br/>
          • Total Reels in Vault: <b id="fns-ep-total" style="color:#fff;">0</b>
        </div>
      </div>
    </div>

    <!-- MAIN WORKSPACE -->
    <div class="fns-main-panel">
      <div id="fns-action-toast" style="display:none;margin-bottom:14px;padding:12px 16px;border-radius:12px;background:linear-gradient(90deg,rgba(0,245,212,0.22),rgba(14,165,233,0.22));border:1px solid #00f5d4;color:#fff;font-weight:700;font-size:0.85rem;"></div>

      <!-- ================================================================= -->
      <!-- SCREEN 1: ZERO-LAG CONNECTED PIPELINE + ERROR BANNER + PREVIEW    -->
      <!-- ================================================================= -->
      <div class="fns-screen active" id="fns-screen-1">
        <div class="fns-s1-grid">
          <div class="fns-pipeline-card">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
              <div>
                <div style="font-size:1.08rem;font-weight:900;color:#fff;">13-Step Zero-Lag Connected Pipeline Radar</div>
                <div style="font-size:0.78rem;color:#00f5d4;margin-top:2px;" id="fns-radar-subtitle">Zero-Cache GitHub API Telemetry (Polls every 2 seconds)</div>
              </div>
              <a href="/api/universe/live_screenshot" target="_blank" class="fns-tab-btn" style="text-decoration:none;color:#00f5d4;border-color:#00f5d4;">📸 Live Cloud Screen ↗</a>
            </div>

            <!-- CONNECTED S-CURVE ROAD MAP -->
            <div class="fns-road-wrap">
              <div class="fns-road-row">
                <div class="fns-road-node" id="fns-pnode-1">
                  <div style="font-size:0.65rem;color:#00f5d4;font-weight:800;">STAGE 1</div>
                  <div style="font-size:0.78rem;font-weight:800;color:#fff;">1. AI Episodic Script</div>
                </div>
                <div class="fns-road-connector" id="fns-pconn-1"></div>
                <div class="fns-road-node" id="fns-pnode-2">
                  <div style="font-size:0.65rem;color:#00f5d4;font-weight:800;">STAGE 2</div>
                  <div style="font-size:0.78rem;font-weight:800;color:#fff;">2. Cookie Sign-In</div>
                </div>
                <div class="fns-road-connector" id="fns-pconn-2"></div>
                <div class="fns-road-node" id="fns-pnode-3">
                  <div style="font-size:0.65rem;color:#00f5d4;font-weight:800;">STAGE 3</div>
                  <div style="font-size:0.78rem;font-weight:800;color:#fff;">3. Create Video 9:16</div>
                </div>
                <div class="fns-road-connector" id="fns-pconn-3"></div>
                <div class="fns-road-node" id="fns-pnode-4">
                  <div style="font-size:0.65rem;color:#00f5d4;font-weight:800;">STAGE 4</div>
                  <div style="font-size:0.78rem;font-weight:800;color:#fff;">4. Character Upload</div>
                </div>
              </div>

              <div class="fns-road-turn" id="fns-pturn-1"></div>

              <div class="fns-road-row">
                <div class="fns-road-node" id="fns-pnode-8">
                  <div style="font-size:0.65rem;color:#00f5d4;font-weight:800;">STAGE 8</div>
                  <div style="font-size:0.78rem;font-weight:800;color:#fff;">8. Video Ready in Vault</div>
                </div>
                <div class="fns-road-connector" id="fns-pconn-7"></div>
                <div class="fns-road-node" id="fns-pnode-7">
                  <div style="font-size:0.65rem;color:#00f5d4;font-weight:800;">STAGE 7</div>
                  <div style="font-size:0.78rem;font-weight:800;color:#fff;">7. Hover & MP4 Save</div>
                </div>
                <div class="fns-road-connector" id="fns-pconn-6"></div>
                <div class="fns-road-node" id="fns-pnode-6">
                  <div style="font-size:0.65rem;color:#00f5d4;font-weight:800;">STAGE 6</div>
                  <div style="font-size:0.78rem;font-weight:800;color:#fff;">6. 3D Video Rendering</div>
                </div>
                <div class="fns-road-connector" id="fns-pconn-5"></div>
                <div class="fns-road-node" id="fns-pnode-5">
                  <div style="font-size:0.65rem;color:#00f5d4;font-weight:800;">STAGE 5</div>
                  <div style="font-size:0.78rem;font-weight:800;color:#fff;">5. Prompt Injection</div>
                </div>
              </div>
            </div>

            <!-- LIVE ERROR / FAILURE REASON DIAGNOSTIC BANNER -->
            <div class="fns-error-box" id="fns-error-banner">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;">
                <div style="font-size:0.92rem;font-weight:900;color:#f87171;">🚨 PIPELINE FAILED — EXACT SCREEN REASON:</div>
                <a href="/api/universe/live_screenshot" target="_blank" style="color:#fff;background:#ef4444;padding:5px 12px;border-radius:8px;text-decoration:none;font-size:0.75rem;font-weight:800;">📸 Open Failure Screenshot ↗</a>
              </div>
              <div id="fns-error-reason-text" style="font-size:0.84rem;color:#fee2e2;margin-top:6px;line-height:1.5;"></div>
            </div>

            <!-- 5 Foji Universe Track Selector -->
            <div style="margin-top:16px;padding-top:14px;border-top:1px solid rgba(255,255,255,0.08);">
              <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px;">
                <span style="font-size:0.86rem;font-weight:800;color:#00f5d4;">🎖️ Select Foji Series Track (Pass = Next Part | Fail = Retry Same Part):</span>
                <button class="fns-tab-btn" id="fns-autorotate-btn" onclick="fnsSetAutoRotate()" style="padding:5px 12px;font-size:0.75rem;">🔄 Auto-Rotate All 5 Tracks</button>
              </div>
              <div id="fns-quick-tracks" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:8px;"></div>

              <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;">
                <input type="text" id="fns-custom-twist" placeholder="💡 Optional: Agle Part mein kya twist chahiye? Yahan likho..." style="flex:1;min-width:210px;background:rgba(6,11,22,0.92);border:1px solid rgba(255,255,255,0.16);border-radius:10px;padding:10px 13px;color:#fff;font-size:0.82rem;" />
                <button class="fns-tab-btn active" onclick="fnsLockTwist()">💾 Lock Twist</button>
                <button class="fns-tab-btn" style="background:linear-gradient(90deg,#a855f7,#ec4899);color:#fff;border:none;" onclick="fnsGenerateLiveScriptPreview()">🧠 Test AI Script</button>
              </div>
              <div id="fns-live-script-output" style="display:none;margin-top:12px;background:rgba(4,9,18,0.92);border-left:4px solid #00f5d4;padding:12px;border-radius:10px;font-size:0.81rem;line-height:1.5;"></div>
            </div>

            <!-- Live Activity Logs -->
            <div style="margin-top:16px;padding-top:12px;border-top:1px solid rgba(255,255,255,0.08);">
              <div style="font-size:0.8rem;font-weight:800;color:#94a3b8;margin-bottom:6px;">🔔 Real-Time Pipeline Logs & Alerts</div>
              <div id="fns-notif-feed" style="max-height:135px;overflow-y:auto;display:flex;flex-direction:column;gap:5px;font-size:0.75rem;"></div>
            </div>
          </div>

          <!-- RIGHT: 9:16 iPhone Preview + One-Click Approve & Schedule / Post -->
          <div style="display:flex;flex-direction:column;gap:12px;">
            <div class="fns-iphone-frame">
              <div class="fns-iphone-notch"></div>
              <div style="font-size:0.75rem;font-weight:800;color:#94a3b8;margin-bottom:6px;">📱 Live 9:16 Reel Preview</div>
              <div class="fns-iphone-screen">
                <video id="fns-preview-video" src="/api/universe/latest_video" controls autoplay muted loop playsinline style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display='none';document.getElementById('fns-vid-fallback').style.display='flex';"></video>
                <div id="fns-vid-fallback" style="display:none;flex-direction:column;align-items:center;justify-content:center;padding:16px;text-align:center;">
                  <img src="/api/universe/char_img/foji" style="width:110px;height:110px;object-fit:cover;border-radius:50%;border:2px solid #00f5d4;margin-bottom:10px;" />
                  <div style="font-size:0.82rem;font-weight:800;color:#fff;">Makra & Meera 3D Studio</div>
                  <div style="font-size:0.7rem;color:#94a3b8;margin-top:4px;">Generated 9:16 MP4 streams here</div>
                </div>
                <div class="fns-iphone-overlay">
                  <div style="font-weight:800;color:#00f5d4;" id="fns-phone-ep-title">@ai_foji_lovelife • Verified</div>
                  <div id="fns-phone-ep-diag" style="font-size:0.68rem;color:#e2e8f0;margin-top:2px;">Ready for Approval & Scheduling</div>
                </div>
              </div>
            </div>

            <div class="fns-pipeline-card" style="padding:14px;">
              <button class="fns-cta-schedule" style="width:100%;margin-bottom:8px;padding:12px;font-size:0.84rem;" onclick="fnsApproveAndScheduleLatest()">📅 APPROVE & ADD TO NEXT SCHEDULE SLOT</button>
              <button class="fns-cta-post" style="width:100%;margin-bottom:8px;padding:11px;" id="fns-side-post-btn" onclick="fnsPublishLatestReel()">📲 POST IMMEDIATELY TO INSTAGRAM</button>
              <div style="display:flex;gap:8px;">
                <button class="fns-tab-btn" style="flex:1;font-size:0.75rem;" onclick="fnsStartFullVideoGeneration(1)">🔄 Regenerate</button>
                <a href="/api/universe/latest_video" download="foji_reel.mp4" class="fns-tab-btn" style="flex:1;font-size:0.75rem;text-align:center;text-decoration:none;color:#00f5d4;">📥 Save MP4</a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ================================================================= -->
      <!-- SCREEN 2: APPROVE & SCHEDULED POSTS QUEUE (PERMANENT LOCK!)       -->
      <!-- ================================================================= -->
      <div class="fns-screen" id="fns-screen-2">
        <div style="display:grid;grid-template-columns:1.1fr 1.2fr 0.9fr;gap:18px;">
          <div class="fns-pipeline-card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
              <span style="font-size:0.94rem;font-weight:900;color:#00f5d4;">🎬 1. Ready Videos (Awaiting Approval)</span>
              <span class="fns-badge-live" id="fns-unapproved-cnt">0 Ready</span>
            </div>
            <div id="fns-unapproved-list" style="max-height:460px;overflow-y:auto;"></div>
          </div>

          <div class="fns-pipeline-card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
              <span style="font-size:0.94rem;font-weight:900;color:#a855f7;">📅 2. Active Scheduled Posts Queue (Locked)</span>
              <span class="fns-badge-live" id="fns-scheduled-cnt">0 Scheduled</span>
            </div>
            <div id="fns-scheduled-list" style="max-height:460px;overflow-y:auto;"></div>
          </div>

          <div class="fns-pipeline-card">
            <div style="font-size:0.94rem;font-weight:900;color:#38bdf8;margin-bottom:12px;">⚙️ 3. Automation Timing Rules (IST)</div>
            <div style="margin-bottom:12px;">
              <label style="font-size:0.75rem;color:#cbd5e1;font-weight:700;">🌙 Night Batch Generation Time (3 Videos):</label>
              <input type="time" id="fns-cfg-night-time" value="02:30" style="width:100%;box-sizing:border-box;margin-top:4px;background:#081020;border:1px solid rgba(255,255,255,0.16);color:#00f5d4;padding:9px;border-radius:9px;font-weight:800;" />
            </div>
            <div style="margin-bottom:12px;">
              <label style="font-size:0.75rem;color:#cbd5e1;font-weight:700;">📅 Daily Instagram Publishing Slots (IST):</label>
              <input type="time" id="fns-slot-1" value="07:00" style="width:100%;box-sizing:border-box;margin-top:6px;background:#081020;border:1px solid rgba(255,255,255,0.16);color:#fff;padding:8px;border-radius:8px;" />
              <input type="time" id="fns-slot-2" value="13:30" style="width:100%;box-sizing:border-box;margin-top:6px;background:#081020;border:1px solid rgba(255,255,255,0.16);color:#fff;padding:8px;border-radius:8px;" />
              <input type="time" id="fns-slot-3" value="19:30" style="width:100%;box-sizing:border-box;margin-top:6px;background:#081020;border:1px solid rgba(255,255,255,0.16);color:#fff;padding:8px;border-radius:8px;" />
            </div>
            <button class="fns-cta-generate" style="width:100%;" onclick="fnsSaveScheduleSlots()">💾 SAVE SCHEDULE RULES</button>
          </div>
        </div>
      </div>

      <!-- ================================================================= -->
      <!-- SCREEN 3: PERMANENT MASTER REELS VAULT (POSTED + SCHEDULED + ALL) -->
      <!-- ================================================================= -->
      <div class="fns-screen" id="fns-screen-3">
        <div class="fns-pipeline-card">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
            <div>
              <div style="font-size:1.1rem;font-weight:900;color:#fff;">🎞️ Master Reels Vault — Permanent All-Time Video Archive</div>
              <div style="font-size:0.78rem;color:#94a3b8;margin-top:2px;">
                Aaj tak jitni bhi videos bani hain aur aage banengi, sab yahan hamesha save rahengi! Jo Instagram par post ho chuki hain un par <b style="color:#34d399;">✅ POSTED ON IG</b> dikhega!
              </div>
            </div>
          </div>

          <div class="fns-vault-grid" id="fns-master-vault-grid"></div>
        </div>
      </div>

      <!-- ================================================================= -->
      <!-- SCREEN 4: STORY TRACKS & CHARACTER VAULT                          -->
      <!-- ================================================================= -->
      <div class="fns-screen" id="fns-screen-4">
        <div style="display:grid;grid-template-columns:280px 1fr;gap:18px;">
          <div class="fns-pipeline-card">
            <div style="font-size:0.9rem;font-weight:800;color:#00f5d4;margin-bottom:10px;">👥 3D Character Vault</div>
            <img src="/api/universe/char_img/foji" style="width:100%;height:145px;object-fit:cover;border-radius:10px;margin-bottom:8px;" />
            <div style="font-size:0.8rem;font-weight:800;color:#fff;margin-bottom:10px;">🪖 Makra (Foji Lead) — Active</div>
            <img src="/api/universe/char_img/fojan" style="width:100%;height:145px;object-fit:cover;border-radius:10px;margin-bottom:8px;" />
            <div style="font-size:0.8rem;font-weight:800;color:#fff;">🌸 Meera (Fojan Lead) — Active</div>
          </div>
          <div class="fns-pipeline-card">
            <div style="font-size:0.9rem;font-weight:800;color:#38bdf8;margin-bottom:10px;">📚 5-Track Episodic Storyline Continuity</div>
            <div id="fns-s2-tracks-list"></div>
          </div>
        </div>
      </div>

    </div>
  </div>
</div>

<script>
let _fnsState = { active_mode: 'auto_rotate', selected_track_id: 'love_meera' };
let _fnsTracks = [];
let _fnsKnownVaultFiles = new Set();
let _fnsFirstLoadDone = false;
let _fnsLastErrorKey = '';
let _fnsActivePreviewFile = '';

function fnsPlayAlertBeep(isError=false) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = isError ? 'sawtooth' : 'triangle';
    osc.frequency.setValueAtTime(isError ? 210 : 780, ctx.currentTime);
    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + (isError ? 0.55 : 0.35));
  } catch (e) {}
}

function fnsOpenModal(icon, title, bodyHtml, isError=false) {
  const bd = document.getElementById('fns-center-modal-backdrop');
  const box = document.getElementById('fns-center-modal-box');
  document.getElementById('fns-modal-icon').innerText = icon;
  document.getElementById('fns-modal-title').innerText = title;
  document.getElementById('fns-modal-title').style.color = isError ? '#f87171' : '#00f5d4';
  document.getElementById('fns-modal-body').innerHTML = bodyHtml;
  box.style.borderColor = isError ? '#ef4444' : '#00f5d4';
  bd.style.display = 'flex';
  fnsPlayAlertBeep(isError);
}

function fnsCloseModal() {
  document.getElementById('fns-center-modal-backdrop').style.display = 'none';
}

function fnsShowToast(msg, isError=false) {
  const t = document.getElementById('fns-action-toast');
  if (!t) return;
  t.style.display = 'block';
  t.style.borderColor = isError ? '#ef4444' : '#00f5d4';
  t.innerHTML = msg;
  setTimeout(() => { t.style.display = 'none'; }, 8000);
}

function fnsSwitchTab(num) {
  for (let i = 1; i <= 4; i++) {
    const scr = document.getElementById('fns-screen-' + i);
    const btn = document.getElementById('fns-btn-tab' + i);
    if (scr) scr.classList.toggle('active', i === num);
    if (btn) btn.classList.toggle('active', i === num);
  }
}

function fnsUpdateConnectedPipelineRoad(telemetry, notifications, latestVideoFile) {
  const stepNum = parseInt(telemetry.step_num || 0, 10);
  const rawStatus = (telemetry.status || 'idle').toLowerCase();
  const epoch = parseFloat(telemetry.epoch || 0);
  const ageSeconds = epoch > 0 ? ((Date.now() / 1000) - epoch) : 999999;

  let status = rawStatus;
  if (status === 'active' && ageSeconds > 900) status = 'idle';
  if (stepNum === 0 && status !== 'error') status = 'idle';

  const title = (status === 'idle') ? 'System Idle & Ready' : (telemetry.step_title || 'Ready');
  const detail = (status === 'idle') ? 'Click "🚀 GENERATE 1 REEL" to start live tracking' : (telemetry.sub_detail || '');

  document.getElementById('fns-radar-subtitle').innerText =
    `[${status.toUpperCase()}] ${title} — ${detail} ${telemetry.updated_at ? '(' + telemetry.updated_at + ')' : ''}`;

  for (let i = 1; i <= 8; i++) {
    const nd = document.getElementById('fns-pnode-' + i);
    if (!nd) continue;
    nd.className = 'fns-road-node';

    let badgeEl = nd.querySelector('.fns-stage-state-badge');
    if (!badgeEl) {
      badgeEl = document.createElement('div');
      badgeEl.className = 'fns-stage-state-badge';
      badgeEl.style.cssText = 'font-size:0.65rem;font-weight:900;margin-top:5px;padding:2px 7px;border-radius:6px;display:inline-block;';
      nd.appendChild(badgeEl);
    }

    if (status === 'idle') {
      badgeEl.innerText = '⏸️ STANDBY';
      badgeEl.style.background = 'rgba(255,255,255,0.06)';
      badgeEl.style.color = '#64748b';
    } else if (status === 'active') {
      if (i < stepNum) {
        nd.classList.add('done');
        badgeEl.innerText = '✅ COMPLETED';
        badgeEl.style.background = 'rgba(16,185,129,0.25)';
        badgeEl.style.color = '#34d399';
      } else if (i === stepNum) {
        nd.classList.add('active');
        badgeEl.innerText = '⏳ RUNNING LIVE...';
        badgeEl.style.background = 'rgba(0,245,212,0.28)';
        badgeEl.style.color = '#00f5d4';
      } else {
        badgeEl.innerText = '⏳ WAITING';
        badgeEl.style.background = 'rgba(255,255,255,0.06)';
        badgeEl.style.color = '#64748b';
      }
    } else if (status === 'completed') {
      nd.classList.add('done');
      badgeEl.innerText = '✅ COMPLETED';
      badgeEl.style.background = 'rgba(16,185,129,0.25)';
      badgeEl.style.color = '#34d399';
    } else if (status === 'error') {
      const errStage = stepNum > 0 ? stepNum : 2;
      if (i < errStage) {
        nd.classList.add('done');
        badgeEl.innerText = '✅ COMPLETED';
        badgeEl.style.background = 'rgba(16,185,129,0.25)';
        badgeEl.style.color = '#34d399';
      } else if (i === errStage) {
        nd.classList.add('error');
        badgeEl.innerText = '❌ FAILED HERE';
        badgeEl.style.background = 'rgba(239,68,68,0.3)';
        badgeEl.style.color = '#fca5a5';
      } else {
        badgeEl.innerText = '⏹️ STOPPED';
        badgeEl.style.background = 'rgba(255,255,255,0.05)';
        badgeEl.style.color = '#64748b';
      }
    }
  }

  for (let c = 1; c <= 7; c++) {
    const cn = document.getElementById('fns-pconn-' + c);
    if (!cn) continue;
    cn.className = 'fns-road-connector';
    if (status === 'completed') cn.classList.add('done');
    else if (status === 'active' && c < stepNum) cn.classList.add('done');
    else if (status === 'error' && c === stepNum) cn.classList.add('error');
  }

  const turn = document.getElementById('fns-pturn-1');
  if (turn) {
    turn.className = 'fns-road-turn' + ((status === 'completed' || (status === 'active' && stepNum > 4)) ? ' done' : '');
  }

  // Error Banner + Big Center Modal Popup if Pipeline Fails!
  const errBox = document.getElementById('fns-error-banner');
  const errTxt = document.getElementById('fns-error-reason-text');
  if (status === 'error') {
    errBox.style.display = 'block';
    errTxt.innerHTML = `<b>Failed at ${title}:</b> ${detail}`;
    const errKey = `${title}_${detail}_${telemetry.updated_at}`;
    if (_fnsFirstLoadDone && _fnsLastErrorKey !== errKey) {
      _fnsLastErrorKey = errKey;
      fnsOpenModal(
        '🚨',
        'VIDEO GENERATION FAILED!',
        `<div style="color:#fecaca;font-weight:700;margin-bottom:8px;">Stage: ${title}</div>
         <div style="background:rgba(0,0,0,0.4);padding:10px;border-radius:10px;color:#fff;">${detail}</div>
         <div style="margin-top:12px;"><a href="/api/universe/live_screenshot" target="_blank" style="color:#00f5d4;font-weight:800;">📸 View Cloud Chrome Error Screenshot ↗</a></div>`,
        true
      );
    }
  } else {
    errBox.style.display = 'none';
  }

  // Update 9:16 iPhone Preview Player
  const vidEl = document.getElementById('fns-preview-video');
  const fbEl = document.getElementById('fns-vid-fallback');
  if (status === 'active') {
    if (vidEl) vidEl.style.display = 'none';
    if (fbEl) {
      fbEl.style.display = 'flex';
      fbEl.innerHTML = `
        <div style="width:52px;height:52px;border:4px solid #00f5d4;border-top-color:transparent;border-radius:50%;animation:fnsSpin 0.9s linear infinite;margin-bottom:12px;"></div>
        <style>@keyframes fnsSpin { to { transform: rotate(360deg); } }</style>
        <div style="font-size:0.86rem;font-weight:900;color:#00f5d4;">⏳ ${title}</div>
        <div style="font-size:0.74rem;color:#cbd5e1;margin-top:6px;">${detail}</div>
      `;
    }
  } else if (latestVideoFile && _fnsActivePreviewFile !== latestVideoFile) {
    _fnsActivePreviewFile = latestVideoFile;
    if (fbEl) fbEl.style.display = 'none';
    if (vidEl) {
      vidEl.style.display = 'block';
      vidEl.src = '/api/universe/video_file/' + encodeURIComponent(latestVideoFile) + '?t=' + Date.now();
      vidEl.load();
    }
    document.getElementById('fns-phone-ep-title').innerText = '🎬 Latest: ' + latestVideoFile;
  }
}

function fnsRenderMasterVault(vaultList) {
  document.getElementById('fns-vault-badge').innerText = vaultList.length;
  document.getElementById('fns-ep-total').innerText = vaultList.length;

  // Detect if a brand-new video just arrived in the vault -> Trigger Center Popup Modal!
  for (const item of vaultList) {
    const vf = item.video_file;
    if (vf && !_fnsKnownVaultFiles.has(vf)) {
      _fnsKnownVaultFiles.add(vf);
      if (_fnsFirstLoadDone) {
        fnsOpenModal(
          '🎉',
          'NEW 3D FOJI REEL GENERATED & READY!',
          `<div style="font-weight:800;color:#00f5d4;margin-bottom:6px;">🎬 ${item.title || vf}</div>
           <div style="font-size:0.82rem;color:#e2e8f0;margin-bottom:10px;">"${item.dialogue || ''}"</div>
           <div style="font-size:0.76rem;color:#94a3b8;">Video is loaded in the 9:16 Preview Player and saved permanently in your Master Reels Vault!</div>`,
          false
        );
      }
    }
  }

  const grid = document.getElementById('fns-master-vault-grid');
  if (!grid) return;
  if (!vaultList.length) {
    grid.innerHTML = '<div style="padding:18px;color:#64748b;">No reels in vault yet. Click Generate 1 Reel to create your first video!</div>';
    return;
  }

  grid.innerHTML = vaultList.map(v => {
    const isPub = (v.vault_status === 'published');
    const isSch = (v.vault_status === 'scheduled');
    const badgeBg = isPub ? 'rgba(16,185,129,0.22)' : (isSch ? 'rgba(168,85,247,0.25)' : 'rgba(14,165,233,0.22)');
    const badgeCol = isPub ? '#34d399' : (isSch ? '#e9d5ff' : '#38bdf8');
    return `
      <div class="fns-vault-card ${v.vault_status || ''}">
        <video src="/api/universe/video_file/${encodeURIComponent(v.video_file)}" controls preload="metadata" style="width:100%;height:320px;object-fit:cover;background:#000;"></video>
        <div style="padding:13px;display:flex;flex-direction:column;gap:7px;flex:1;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
            <span style="font-size:0.68rem;font-weight:900;padding:3px 9px;border-radius:99px;background:${badgeBg};color:${badgeCol};">${v.status_badge}</span>
            <span style="font-size:0.68rem;color:#64748b;">${v.video_file}</span>
          </div>
          <div style="font-size:0.84rem;font-weight:800;color:#fff;">${v.title || v.video_file}</div>
          <div style="font-size:0.73rem;color:#cbd5e1;">"${(v.dialogue || '').slice(0, 90)}"</div>
          <div style="display:flex;gap:6px;margin-top:auto;padding-top:8px;flex-wrap:wrap;">
            ${!isPub ? `<button class="fns-cta-schedule" style="flex:1;padding:7px;font-size:0.72rem;" onclick="fnsApproveAndScheduleSpecific('${v.video_file}')">📅 Schedule</button>` : ''}
            <button class="fns-cta-post" style="flex:1;padding:7px;font-size:0.72rem;" onclick="fnsPublishSpecificNow('${v.video_file}')">${isPub ? '📲 Repost IG' : '📲 Post IG Now'}</button>
            <a href="/api/universe/video_file/${encodeURIComponent(v.video_file)}" download="${v.video_file}" class="fns-tab-btn" style="padding:7px 10px;font-size:0.72rem;text-decoration:none;color:#00f5d4;">📥</a>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

async function fnsRefreshHub() {
  try {
    const r = await fetch('/api/universe/status?t=' + Date.now());
    const d = await r.json();
    _fnsState = d.director_state || _fnsState;
    _fnsTracks = d.tracks || [];
    if (d.server_time_ist) document.getElementById('fns-server-clock').innerText = d.server_time_ist;
    if (d.next_open_slot) document.getElementById('fns-next-slot-sidebar').innerText = d.next_open_slot.display_time;

    fnsUpdateConnectedPipelineRoad(d.telemetry || {}, d.notifications || [], d.latest_video_file || '');
    fnsRenderMasterVault(d.master_vault || []);
    fnsRenderTrackSelectors();
    fnsRenderNotifications(d.notifications || []);
    fnsRenderQueueLists(d.queue || {});
    _fnsFirstLoadDone = true;
  } catch (e) {}
}

function fnsRenderQueueLists(q) {
  const unList = q.unapproved_videos || [];
  const scList = q.scheduled_posts || [];

  document.getElementById('fns-unapproved-cnt').innerText = unList.length + ' Ready';
  document.getElementById('fns-scheduled-cnt').innerText = scList.length + ' Scheduled';
  document.getElementById('fns-q-badge').innerText = scList.length;

  const uBox = document.getElementById('fns-unapproved-list');
  if (uBox) {
    if (!unList.length) {
      uBox.innerHTML = '<div style="padding:12px;color:#64748b;font-size:0.78rem;">All generated videos have been scheduled or posted! Check <b>Tab #2 (Scheduled Queue)</b> or <b>Tab #3 (All Reels Vault)</b>!</div>';
    } else {
      uBox.innerHTML = unList.map(v => `
        <div class="fns-queue-card">
          <div style="flex:1;min-width:180px;">
            <div style="font-size:0.83rem;font-weight:800;color:#fff;">🎬 ${v.title}</div>
            <div style="font-size:0.72rem;color:#cbd5e1;margin-top:3px;">"${(v.dialogue || '').slice(0, 85)}"</div>
            <div style="font-size:0.66rem;color:#00f5d4;margin-top:4px;">File: ${v.video_file} • Created: ${v.created_at}</div>
          </div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            <button class="fns-tab-btn" style="padding:6px 10px;font-size:0.72rem;" onclick="fnsPreviewSpecificVideo('${v.video_file}', '${(v.title||'').replace(/'/g, '')}')">▶️ Watch</button>
            <button class="fns-cta-schedule" style="padding:7px 12px;font-size:0.74rem;" onclick="fnsApproveAndScheduleSpecific('${v.video_file}')">📅 Approve & Schedule</button>
            <button class="fns-cta-post" style="padding:7px 12px;font-size:0.74rem;" onclick="fnsPublishSpecificNow('${v.video_file}')">📲 Post Now</button>
          </div>
        </div>
      `).join('');
    }
  }

  const sBox = document.getElementById('fns-scheduled-list');
  if (sBox) {
    if (!scList.length) {
      sBox.innerHTML = '<div style="padding:12px;color:#64748b;font-size:0.78rem;">No posts currently in schedule queue.</div>';
    } else {
      sBox.innerHTML = scList.map((v, idx) => `
        <div class="fns-queue-card" style="border-color:#a855f7;background:rgba(28,18,52,0.75);">
          <div style="flex:1;min-width:180px;">
            <span style="background:#a855f7;color:#fff;font-size:0.66rem;font-weight:900;padding:2px 8px;border-radius:99px;">SLOT #${idx+1}: ${v.scheduled_display}</span>
            <div style="font-size:0.83rem;font-weight:800;color:#fff;margin-top:5px;">🎬 ${v.title}</div>
            <div style="font-size:0.71rem;color:#cbd5e1;margin-top:2px;">File: ${v.video_file}</div>
          </div>
          <div style="display:flex;gap:6px;">
            <button class="fns-cta-post" style="padding:6px 10px;font-size:0.72rem;" onclick="fnsPublishSpecificNow('${v.video_file}')">📲 Post Now</button>
            <button class="fns-tab-btn" style="padding:6px 10px;font-size:0.72rem;color:#f87171;" onclick="fnsRemoveScheduled('${v.id}')">✖ Unschedule</button>
          </div>
        </div>
      `).join('');
    }
  }
}

function fnsPreviewSpecificVideo(vfile, title) {
  fnsSwitchTab(1);
  _fnsActivePreviewFile = vfile;
  const vid = document.getElementById('fns-preview-video');
  const fb = document.getElementById('fns-vid-fallback');
  if (fb) fb.style.display = 'none';
  if (vid) {
    vid.style.display = 'block';
    vid.src = '/api/universe/video_file/' + encodeURIComponent(vfile) + '?t=' + Date.now();
    vid.play();
  }
  document.getElementById('fns-phone-ep-title').innerText = title || vfile;
}

async function fnsApproveAndScheduleLatest() {
  await fnsApproveAndScheduleSpecific('');
}

async function fnsApproveAndScheduleSpecific(vfile) {
  fnsShowToast('📅 Locking video permanently into the next available IST schedule slot...');
  try {
    const r = await fetch('/api/universe/approve_and_schedule', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ video_file: vfile })
    });
    const d = await r.json();
    if (d.ok) {
      fnsOpenModal(
        '📅',
        'VIDEO SCHEDULED SUCCESSFULLY!',
        `<div style="font-weight:800;color:#00f5d4;margin-bottom:8px;">${d.message}</div>
         <div style="font-size:0.82rem;color:#cbd5e1;">This video is now permanently locked in <b>Tab #2 (Scheduled Queue)</b> and synced to GitHub so it will NEVER jump back!</div>`,
        false
      );
      fnsSwitchTab(2);
      fnsRefreshHub();
    } else {
      fnsOpenModal('❌', 'COULD NOT SCHEDULE VIDEO', d.error || 'Failed to schedule', true);
    }
  } catch (e) {
    fnsOpenModal('❌', 'NETWORK ERROR', String(e), true);
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
  fnsOpenModal(
    '⏳',
    'UPLOADING REEL TO INSTAGRAM...',
    `<div style="color:#00f5d4;font-weight:800;margin-bottom:8px;">Uploading ${vfile || 'Latest Reel'} to @ai_foji_lovelife...</div>
     <div style="font-size:0.8rem;color:#cbd5e1;">Generating 9:16 cover thumbnail & publishing via verified Instagram session. Please wait 15–25 seconds...</div>`,
    false
  );
  try {
    const r = await fetch('/api/universe/publish_latest_reel', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ video_file: vfile })
    });
    const d = await r.json();
    if (d.ok) {
      fnsOpenModal(
        '🎉',
        'PUBLISHED ON INSTAGRAM (@ai_foji_lovelife)!',
        `<div style="font-weight:800;color:#34d399;margin-bottom:8px;">${d.message}</div>
         <div style="font-size:0.82rem;color:#cbd5e1;">Status in <b>Tab #3 (All Reels Vault)</b> is now permanently marked as <b>✅ POSTED ON IG</b>!</div>`,
        false
      );
      fnsRefreshHub();
    } else {
      fnsOpenModal('❌', 'INSTAGRAM POST FAILED!', d.error || 'Upload failed', true);
    }
  } catch (e) {
    fnsOpenModal('❌', 'INSTAGRAM UPLOAD ERROR', String(e), true);
  }
}

function fnsRenderTrackSelectors() {
  const qBox = document.getElementById('fns-quick-tracks');
  const s2Box = document.getElementById('fns-s2-tracks-list');
  const autoBtn = document.getElementById('fns-autorotate-btn');

  if (_fnsState.active_mode === 'auto_rotate') {
    autoBtn.innerText = '🔄 Mode: Auto-Rotate All 5 Tracks (ACTIVE)';
    autoBtn.classList.add('active');
  } else {
    autoBtn.innerText = '📌 Mode: Locked to Single Track (Click for Auto-Rotate)';
    autoBtn.classList.remove('active');
  }

  if (qBox) {
    qBox.innerHTML = _fnsTracks.map(t => {
      const isSel = (_fnsState.active_mode === 'locked_track' && _fnsState.selected_track_id === t.id);
      return `<div class="fns-track-item ${isSel ? 'active' : ''}" onclick="fnsSelectTrack('${t.id}')">
        <div style="font-size:0.81rem;font-weight:800;color:#fff;">${t.name}</div>
        <div style="font-size:0.68rem;color:#00f5d4;margin-top:3px;">Next Up: <b>Part #${t.next_part}</b> ${isSel ? '• 📌 LOCKED' : ''}</div>
      </div>`;
    }).join('');
  }

  if (s2Box) {
    s2Box.innerHTML = _fnsTracks.map(t => {
      const isSel = (_fnsState.active_mode === 'locked_track' && _fnsState.selected_track_id === t.id);
      return `<div class="fns-track-item ${isSel ? 'active' : ''}" style="margin-bottom:8px;" onclick="fnsSelectTrack('${t.id}')">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="font-size:0.83rem;font-weight:800;color:#fff;">${t.name}</span>
          <span class="fns-badge-live">Next: Part #${t.next_part}</span>
        </div>
      </div>`;
    }).join('');
  }
}

let _fnsLastSeenNotifId = '';

function fnsRenderNotifications(list) {
  const nBox = document.getElementById('fns-notif-feed');
  if (!nBox) return;
  if (!list.length) {
    nBox.innerHTML = '<div style="color:#64748b;">System ready. No recent alerts.</div>';
    return;
  }

  // Trigger Center Screen Popup Modal for ANY new notification (Video Ready, Scheduled from Telegram/Frontend, Posted, or Error!)
  const newest = list[0];
  if (newest && newest.id) {
    if (_fnsFirstLoadDone && _fnsLastSeenNotifId && _fnsLastSeenNotifId !== newest.id) {
      const isErr = (newest.status === 'error');
      const icon = isErr ? '🚨' : (newest.type === 'schedule' ? '📅' : '🎉');
      fnsOpenModal(
        icon,
        newest.title || 'STUDIO NOTIFICATION',
        `<div style="font-size:0.92rem;color:#fff;font-weight:700;margin-bottom:8px;">${newest.message || ''}</div>
         <div style="font-size:0.75rem;color:#00f5d4;">Time: ${newest.time_str || 'Just Now'}</div>`,
        isErr
      );
    }
    _fnsLastSeenNotifId = newest.id;
  }

  nBox.innerHTML = list.slice(0, 12).map(n => `
    <div style="padding:7px 10px;background:rgba(15,23,42,0.75);border-radius:8px;border-left:3px solid ${n.status==='error'?'#ef4444':(n.status==='success'?'#10b981':'#00f5d4')};display:flex;justify-content:space-between;gap:10px;">
      <span><b>${n.title || 'Event'}:</b> ${n.message || ''}</span>
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
  fnsShowToast('✅ Next Part Twist Locked!');
}

async function fnsStartFullVideoGeneration(cnt=1) {
  const twist = document.getElementById('fns-custom-twist').value;
  fnsUpdateConnectedPipelineRoad({
    step_num: 1,
    step_title: 'Stage 1: AI Episodic Script & Cloud Dispatch',
    sub_detail: 'Starting pipeline now...',
    status: 'active',
    updated_at: 'Just Now',
    epoch: Date.now() / 1000
  }, [], '');

  fnsShowToast('🚀 Pipeline Started! Watch Stage 1 -> Stage 8 light up in real time!');
  try {
    const r = await fetch('/api/universe/trigger_pipeline', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ custom_idea: twist, count: cnt })
    });
    const d = await r.json();
    if (d.ok) fnsShowToast('✅ ' + d.message);
    else fnsOpenModal('❌', 'PIPELINE START ERROR', d.error || 'Failed', true);
  } catch (e) {
    fnsOpenModal('❌', 'REQUEST ERROR', String(e), true);
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
  fnsOpenModal('✅', 'SCHEDULE RULES SAVED!', '02:30 AM Batch (3 Videos) + T-30 Min Auto-Trigger + Daily Slots (' + s1 + ', ' + s2 + ', ' + s3 + ') Locked!', false);
  fnsRefreshHub();
}

async function fnsGenerateLiveScriptPreview() {
  const outBox = document.getElementById('fns-live-script-output');
  outBox.style.display = 'block';
  outBox.innerHTML = '⏳ <b>Calling your .env API key to write a 100% original script for the next Part...</b>';
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
        <div style="color:#00f5d4;font-weight:900;font-size:0.9rem;margin-bottom:4px;">🎬 ${p.emotion_name} (Part #${p.part_number})</div>
        <div style="color:#cbd5e1;margin-bottom:6px;"><b>🎥 3D Visual Scene:</b> ${p.scene_summary}</div>
        <div style="color:#fff;margin-bottom:6px;"><b>🗣️ Spoken Hinglish Dialogue:</b> "${p.dialogue_line_1_hinglish}"</div>
        <div style="color:#fbbf24;white-space:pre-line;"><b>🔥 Hindi Shayari:</b>\n${p.shayari_hindi}</div>
      `;
    } else {
      outBox.innerHTML = '<span style="color:#f87171;">❌ API Error: ' + (d.error || 'Unknown error') + '</span>';
    }
  } catch (e) {
    outBox.innerHTML = '<span style="color:#f87171;">❌ Request Error: ' + e + '</span>';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const shell = document.getElementById('foji-nextgen-studio-shell');
  if (shell && document.body.firstChild) {
    document.body.insertBefore(shell, document.body.firstChild);
  }
  fnsRefreshHub();
  setInterval(fnsRefreshHub, 2200);
});
</script>
"""
                html_text = html_text.replace("</body>", widget_html + "\n</body>", 1)
                response.set_data(html_text)
    except Exception:
        pass
    return response



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7860)), debug=False)