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
DEFAULT_SLOTS = ["08:00", "14:00", "20:00"]

IG_SESSION_FILE = "data/ig_session.json"
NOTIF_FILE = "data/notifications.json"
DELETED_IDS_FILE = "data/deleted_ids.json"

UPLOAD_PROGRESS_MAP = {}
GLOBAL_DELETED_IDS = set()
FILE_LOCK = threading.Lock()
TG_LAST_UPDATE_ID = 0

SERIES_TRACKS = [
    {"id": "romantic", "name": "Foji & Fojan Love Saga", "bgm": "romantic", "loc": "Snowy Kashmir Valley & Army Cantt"},
    {"id": "border_action", "name": "LOC Vigil & Braveheart", "bgm": "patriotic", "loc": "High Altitude Border Outpost"},
    {"id": "emotional", "name": "Chithi & Homecoming", "bgm": "emotional", "loc": "Village Courtyard & Railway Station"},
    {"id": "comedy", "name": "Foji Nok-Jhok & Chai", "bgm": "upbeat", "loc": "Army Canteen & Festive Market"},
    {"id": "patriotic", "name": "Tiranga Shaan & Duty", "bgm": "patriotic", "loc": "Regiment Parade Ground"}
]

# ==============================================================================
# 🛡️ MEMORY GUARD & DATA FILES INITIALIZER
# ==============================================================================
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

    if not os.path.exists(NOTIF_FILE):
        with open(NOTIF_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, indent=2)

# ==============================================================================
# ☁️ GITHUB REST API SYNC
# ==============================================================================
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
            "id": f"notif_{int(time.time() * 1000)}_{random.randint(100,999)}",
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
            data = {"generated_count": 0, "track_parts": {}, "recent_tracks": [], "deleted_ids": [], "history": []}

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
# 🧠 AI SCRIPT ENGINE & GEMINI VIDEO PACKAGE GENERATOR
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
                    "generationConfig": {"temperature": 0.85}
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
    recent_dialogues = list(recent_dialogues or [])[-8:]
    now_ist = datetime.now(IST)

    sys_instruction = (
        "You are an Indian 3D Pixar-style Cinema Director creating a viral Instagram Reel episode "
        "starring 'Foji Makra' (Indian Army Soldier/Jawan with plain shoulder straps, NO stars) "
        "and 'Fojan Meera' (his witty, loving Indian wife). "
        "Create a fresh micro-story, natural Hinglish dialogues (5-7 words per character), "
        "a vivid location, and a background music instruction."
    )
    user_req = (
        f"Episode: {track['name']} - Part {part_num}.\n"
        f"Do NOT repeat these dialogues: {json.dumps(recent_dialogues, ensure_ascii=False)}\n"
        "Return ONLY valid JSON with keys: new_location, dialogue_line_1_hinglish, dialogue_line_2_hinglish, music_direction, caption"
    )

    d1 = "Meera, sarhad ki har subah tumhari yaad se shuru hoti hai!"
    d2 = "Aur meri har shaam aapke laut aane ki dua se, Foji sahab!"
    scene_setting = track["loc"]
    music_cue = f"Add soulful Bollywood {track['bgm']} instrumental background music."
    caption = ""

    try:
        ai_raw = call_live_gemini_ai_brain(sys_instruction, user_req)
        s_idx, e_idx = ai_raw.find("{"), ai_raw.rfind("}") + 1
        if s_idx != -1 and e_idx > s_idx:
            parsed = json.loads(ai_raw[s_idx:e_idx])
            d1 = parsed.get("dialogue_line_1_hinglish") or d1
            d2 = parsed.get("dialogue_line_2_hinglish") or d2
            scene_setting = parsed.get("new_location") or scene_setting
            music_cue = parsed.get("music_direction") or music_cue
            caption = parsed.get("caption") or ""
    except Exception:
        pass

    if not caption:
        caption = (
            f"❤️ {track['name']} • Part {part_num} 🇮🇳✨\n"
            f"🪖 \"{d1}\"\n"
            f"💖 \"{d2}\"\n.\n"
            f"#FojiFojan #IndianArmy #3DAnimation #FojiLoveStory #ReelsIndia"
        )

    prompt = (
        f"Create a 9:16 Portrait 3D Pixar Disney style 8K cinematic animated video using the two uploaded character images. "
        f"Image 1 is Foji Makra (handsome Indian Army Soldier/Jawan with plain soldier shoulder straps, strictly NO stars). "
        f"Image 2 is Fojan Meera (young Indian woman). Keep their exact facial identity. "
        f"Series: {track['name']} (Part {part_num}). Location: {scene_setting}. "
        f"From 0 to 4 seconds, Foji Makra speaks in Hindi with exact lip-sync: \"{d1}\". "
        f"From 4 to 8 seconds, Fojan Meera replies in Hindi with lip-sync: \"{d2}\". "
        f"MANDATORY MUSIC & AUDIO: {music_cue}"
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
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
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
                {"text": "✅ Approve & Post", "callback_data": f"approve_post:{vid_id}"},
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

    tid = candidate_pkg.get("track_id")
    if tid:
        hist.setdefault("recent_tracks", []).append(tid)

    save_history(hist, sync_cloud=True, msg=f"Add verified reel #{candidate_pkg['video_id']}", blocking=True)
    log_notification("generated", "New Reel Ready", f"{candidate_pkg['emotion_name']} is ready for approval.", "success")
    if send_for_approval:
        send_telegram_approval_card(candidate_pkg, mp4_path=out_path)
    trim_system_memory()
    return candidate_pkg

# ==============================================================================
# 🚀 DIRECT INSTAGRAM REEL PUBLISHER (ONLY UPLOAD, ZERO SCRAPING!)
# ==============================================================================
def get_authenticated_ig_client():
    from instagrapi import Client
    ig_user = os.getenv("INSTAGRAM_USERNAME", "").strip().lstrip("@")
    ig_pass = os.getenv("INSTAGRAM_PASSWORD", "").strip()
    ig_sess_id = os.getenv("INSTAGRAM_SESSIONID", "").strip()

    cl = Client()
    cl.delay_range = [1, 2]
    cl.set_device({
        "app_version": "358.0.0.42.96",
        "android_version": 34,
        "android_release": "14.0",
        "dpi": "480dpi",
        "resolution": "1080x2400",
        "manufacturer": "Samsung",
        "device": "dm3q",
        "model": "SM-S918B",
        "cpu": "qcom",
        "version_code": "658492103"
    })

    if ig_sess_id:
        try:
            cl.login_by_sessionid(urllib.parse.unquote(ig_sess_id))
            return cl
        except Exception:
            pass

    if os.path.exists(IG_SESSION_FILE):
        try:
            try:
                cl.load_settings(IG_SESSION_FILE, override_app_version=True)
            except TypeError:
                cl.load_settings(IG_SESSION_FILE)
            cl.login(ig_user, ig_pass)
            cl.dump_settings(IG_SESSION_FILE)
            return cl
        except Exception:
            try:
                os.remove(IG_SESSION_FILE)
            except Exception:
                pass

    if ig_user and ig_pass:
        cl.login(ig_user, ig_pass)
        try:
            cl.dump_settings(IG_SESSION_FILE)
        except Exception:
            pass
        return cl
    raise RuntimeError("Instagram credentials not configured in .env / Secrets.")

def publish_reel_item_to_instagram(video_id):
    vid_key = str(video_id)
    UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 15, "stage": "Verifying MP4 file...", "status": "uploading", "error": ""}

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
        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 45, "stage": "Authenticating Instagram...", "status": "uploading", "error": ""}
        cl = get_authenticated_ig_client()

        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 78, "stage": "Uploading Reel & Caption...", "status": "uploading", "error": ""}
        media = cl.clip_upload(raw_mp4, caption=target.get("caption", ""))

        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 96, "stage": "Finalizing post...", "status": "uploading", "error": ""}
        target["ig_media_id"] = str(media.id)
        target["code"] = str(media.code)
        target["permalink"] = f"https://www.instagram.com/reel/{media.code}/"
        target["status"] = "posted"
        target["scheduled_slot"] = None
        target["posted_at"] = datetime.now(IST).strftime("%d %b %Y, %I:%M %p")
        save_history(hist, sync_cloud=True, msg=f"Published Reel #{video_id}", blocking=True)

        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 100, "stage": "Published!", "status": "done", "error": ""}
        log_notification("posted", "Published to Instagram", f"{target.get('emotion_name')} is now live.", "success")
        trim_system_memory()
        return True, "POSTED DONE"

    except Exception as e:
        err_msg = str(e)[:140]
        UPLOAD_PROGRESS_MAP[vid_key] = {"pct": 0, "stage": "Failed", "status": "error", "error": err_msg}
        log_notification("error", "Upload Failed", err_msg, "error")
        trim_system_memory()
        return False, err_msg

# ==============================================================================
# 📲 SHARED REEL ACTIONS & TELEGRAM BUTTON LISTENER
# ==============================================================================
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

    dt_obj = datetime.strptime(assigned_slot, "%H:%M")
    slot_label = dt_obj.strftime("%I:%M %p")
    target_title = f"Reel #{vid_str}"
    for item in hist.get("history", []):
        if str(item.get("video_id", "")) == vid_str:
            item["status"] = "scheduled"
            item["scheduled_slot"] = assigned_slot
            item["scheduled_label"] = slot_label
            item["schedule_click_order"] = int(time.time())
            target_title = item.get("emotion_name", target_title)
            break
    save_history(hist, sync_cloud=True, msg=f"Schedule Reel #{vid_str}", blocking=True)
    log_notification("scheduled", f"Scheduled • {slot_label}", f"{target_title} queued for auto-post.", "info")
    return slot_label

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
    gemini_bot.update_3d_telemetry(1, "Regenerating", "Opening Gemini Flash...", "active", 15)
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
                            requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery", json={"callback_query_id": cb_id, "text": "🚀 Uploading to Instagram..."}, timeout=10)
                            def _post_notify(v=vid_id, cid=chat_id):
                                ok, msg = publish_reel_item_to_instagram(v)
                                txt = f"✅ *Reel #{v} Published to Instagram!*" if ok else f"❌ *Upload Failed:* {msg}"
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
        first_s = slots[0] if slots else "08:00"
        next_dt = datetime.strptime(f"{tomorrow_str} {first_s}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
        next_slot_label = f"Tomorrow {next_dt.strftime('%I:%M %p IST')}"

    rem_sec = max(0, int((next_dt - now_ist).total_seconds()))
    return {
        "next_slot_label": next_slot_label,
        "remaining_seconds": rem_sec,
        "queued_count": len(scheduled_reels),
        "status_banner": "SCHEDULED REEL ARMED" if scheduled_reels else "AUTO-PILOT ACTIVE (02:30 AM & T-30M)"
    }

# ==============================================================================
# 🌐 CLEAN FLASK ENDPOINTS
# ==============================================================================
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
    gemini_bot.update_3d_telemetry(1, "Opening Gemini", "Selecting Flash model...", "active", 15)
    log_notification("generated", "Generation Started", "Creating new 3D episode in Gemini.", "info")

    def _bg():
        if os.name != "nt" and not os.path.exists("/usr/bin/google-chrome"):
            if not trigger_github_7gb_worker(action_type="generate_only"):
                err = "GITHUB_PAT missing in Render Environment! Add GITHUB_PAT or run locally."
                log_notification("error", "Cloud Trigger Failed", err, "error")
                gemini_bot.update_3d_telemetry(0, "Trigger Failed", err, "error", 0)
            return
        try:
            generate_single_reel_package(send_for_approval=True)
        except Exception as e:
            err = str(e)[:180]
            log_notification("error", "Gemini Notice", err, "error")
            gemini_bot.update_3d_telemetry(0, "Paused", err, "error", 0)

    threading.Thread(target=_bg, daemon=True).start()
    return jsonify({"ok": True})

@app.route("/api/reel_action", methods=["POST"])
def api_reel_action():
    body = request.json or {}
    action = body.get("action")
    vid_id = str(body.get("video_id", ""))

    if action == "approve_post":
        UPLOAD_PROGRESS_MAP[vid_id] = {"pct": 10, "stage": "Starting upload...", "status": "uploading", "error": ""}
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

# ==============================================================================
# ⚡ ULTRA-SIMPLE, ZERO-IG, SUPER-FAST FRONTEND (GENERATE + APPROVE + SCHEDULE)
# ==============================================================================
CLEAN_FAST_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AutoReels 3D AI — Generate • Approve • Schedule</title>
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
  body {
    font-family: 'Plus Jakarta Sans', sans-serif;
    background: #040711;
    color: #f8fafc;
    min-height: 100vh;
  }
  .lux-navbar {
    max-width: 1120px; margin: 16px auto; padding: 14px 22px;
    background: var(--glass); border: 1px solid var(--border); border-radius: 20px;
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;
  }
  .brand-title {
    font-family: 'Space Grotesk', sans-serif; font-size: 1.35rem; font-weight: 800;
    color: #fde68a;
  }
  .nav-tabs { display: flex; gap: 10px; }
  .nav-tab {
    padding: 10px 18px; border-radius: 12px; font-weight: 700; font-size: 0.9rem;
    color: #94a3b8; background: rgba(255,255,255,0.05); border: 1px solid transparent; cursor: pointer;
  }
  .nav-tab.active {
    color: #fff; background: rgba(16, 185, 129, 0.2); border-color: var(--emerald);
  }
  .ist-clock {
    font-family: 'Space Grotesk', monospace; font-size: 0.95rem; font-weight: 800;
    color: #fde68a; background: rgba(0,0,0,0.45); padding: 8px 14px; border-radius: 12px;
    border: 1px solid rgba(245, 158, 11, 0.4);
  }
  .container { max-width: 1120px; margin: 0 auto 60px; padding: 0 18px; }
  .page-section { display: none; }
  .page-section.active { display: block; }

  .lux-card {
    background: var(--glass); border: 1px solid var(--border);
    border-radius: 20px; padding: 22px; margin-bottom: 20px;
  }
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
    <div class="brand-title">🎬 AutoReels 3D AI</div>
    <div style="font-size:0.75rem;color:#94a3b8;">Generate • Approve & Post • Schedule</div>
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
        <strong style="color:#34d399;font-size:0.92rem;" id="cd-status-banner">AUTO-PILOT ACTIVE (02:30 AM & T-30M)</strong>
        <div style="font-size:0.82rem;color:#cbd5e1;margin-top:2px;" id="cd-next-slot-txt">Next Slot: 08:00 AM IST</div>
      </div>
      <div style="font-family:'Space Grotesk',monospace;font-size:1.1rem;font-weight:800;color:#fde68a;" id="cd-reverse-timer">00h : 00m : 00s</div>
    </div>

    <div id="pipeline-box">
      <div style="display:flex;justify-content:space-between;font-weight:800;">
        <span id="pipe-title" style="color:#fde68a;">STEP 1: Opening Gemini Flash...</span>
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
        ⚡ Generate New 3D Reel
      </button>
    </div>

    <h3 style="margin-bottom:14px;font-size:1.15rem;">🎬 Approval & Scheduled Queue (<span id="badge-daily-cnt">0</span>)</h3>
    <div id="vault-daily-view"></div>

    <h3 style="margin:26px 0 14px;font-size:1.1rem;color:#94a3b8;">✅ Recently Posted Archive (<span id="badge-posted-cnt">0</span>)</h3>
    <div id="vault-posted-view"></div>

  </section>

  <section id="page-schedule" class="page-section">
    <div class="lux-card">
      <h2 style="font-size:1.3rem;font-weight:800;margin-bottom:6px;">⏰ Daily Auto-Post Schedule (IST)</h2>
      <p style="color:#94a3b8;font-size:0.84rem;margin-bottom:16px;">
        System tries once at <strong>02:30 AM IST</strong> to build all 3 videos, and tries once <strong>30 minutes before</strong> each slot if needed.
      </p>
      <div class="kpi-grid">
        <div style="background:rgba(0,0,0,0.4);padding:16px;border-radius:14px;border:1px solid var(--border);">
          <label style="color:#fde68a;font-weight:700;font-size:0.8rem;">🌅 SLOT 1</label>
          <input type="time" id="slot-1" value="08:00" oninput="onScheduleTimeInputChanged()"
                 style="width:100%;margin-top:8px;padding:10px;border-radius:10px;background:#0f172a;color:#fff;border:1px solid #334155;font-size:1.05rem;font-weight:700;">
        </div>
        <div style="background:rgba(0,0,0,0.4);padding:16px;border-radius:14px;border:1px solid var(--border);">
          <label style="color:#fde68a;font-weight:700;font-size:0.8rem;">☀️ SLOT 2</label>
          <input type="time" id="slot-2" value="14:00" oninput="onScheduleTimeInputChanged()"
                 style="width:100%;margin-top:8px;padding:10px;border-radius:10px;background:#0f172a;color:#fff;border:1px solid #334155;font-size:1.05rem;font-weight:700;">
        </div>
        <div style="background:rgba(0,0,0,0.4);padding:16px;border-radius:14px;border:1px solid var(--border);">
          <label style="color:#fde68a;font-weight:700;font-size:0.8rem;">🌙 SLOT 3</label>
          <input type="time" id="slot-3" value="20:00" oninput="onScheduleTimeInputChanged()"
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
  let savedScheduleTimes = ["08:00", "14:00", "20:00"];
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
      showModal("🚀 Gemini Video Pipeline Started", "Opening Gemini Flash -> + Create Videos -> 9:16 -> Uploading Characters & Prompt.");
      pollTelemetryLoop();
    });
  }

  function handleApproveAndPost(videoId) {
    showModal("🚀 Publishing...", "Uploading Reel to Instagram...", []);
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
            showModal("✅ Published!", "Reel is now live on Instagram!");
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
      showModal("⏰ Scheduled", `Reel will auto-post at ${res.slot_time || 'Next Slot'} IST.`);
    });
  }

  function handleRegenerateReel(videoId) {
    fetch('/api/reel_action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ action: 'regenerate', video_id: videoId })
    }).then(() => {
      showModal("🔄 Regenerating...", "Creating fresh video in Gemini Flash.");
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
    const t1 = document.getElementById('slot-1').value || "08:00";
    const t2 = document.getElementById('slot-2').value || "14:00";
    const t3 = document.getElementById('slot-3').value || "20:00";
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
              <button class="btn-3d" onclick="handleApproveAndPost('${item.video_id}')">✅ Approve & Post</button>
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
            <span style="color:#34d399;font-weight:800;font-size:0.84rem;margin-left:10px;">✅ Posted • ${item.posted_at || ''}</span>
            <p style="margin-top:12px;background:rgba(0,0,0,0.45);padding:14px;border-radius:12px;font-size:0.88rem;color:#e2e8f0;white-space:pre-line;">${item.caption || ''}</p>
          </div>
        </div>
      `).join('') || `<div class="lux-card" style="color:#94a3b8;text-align:center;">No posted reels yet.</div>`;

      if (!scheduleInputsDirty && appState.schedule_config && appState.schedule_config.times) {
        savedScheduleTimes = appState.schedule_config.times;
        document.getElementById('slot-1').value = savedScheduleTimes[0] || "08:00";
        document.getElementById('slot-2').value = savedScheduleTimes[1] || "14:00";
        document.getElementById('slot-3').value = savedScheduleTimes[2] || "20:00";
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
            <button class="btn-3d" onclick="handleApproveAndPost('${item.video_id}')">🚀 Post Now</button>
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
          showModal("🎬 3D Reel Ready!", "Video downloaded & added to Approval Queue!");
        } else if (t.status === 'error' && t.sub_detail && tEpoch > lastHandledTelemetryEpoch) {
          lastHandledTelemetryEpoch = tEpoch;
          fetch('/api/reset_telemetry', { method: 'POST' });
          fetchAppState();
          showModal("💬 Gemini Notice", t.sub_detail);
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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7860)), debug=False)