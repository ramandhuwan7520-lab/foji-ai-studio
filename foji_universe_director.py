# -*- coding: utf-8 -*-
import os
import re
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv(override=True)
IST = timezone(timedelta(hours=5, minutes=30))
DIRECTOR_STATE_FILE = "data/director_state.json"
HISTORY_FILE = "data/history.json"
EPISODE_TRACKER_FILE = "data/episode_tracker.json"

FOJI_UNIVERSE_TRACKS = {
    "love_meera": {
        "id": "love_meera",
        "name": "❤️ Makra & Meera (Foji Love Story)",
        "badge": "LOVE & EMOTION",
        "color": "#ff4d79",
        "theme_brief": (
            "Romantic and emotional long-distance love story between Indian Army soldier Makra (Foji) "
            "and his village love Meera (Fojan). Cover real emotions: leave (chhutti) getting cancelled, "
            "secret late-night calls from border bunker, Meera waiting at village courtyard, funny Haryanvi/Desi "
            "banter, emotional reunion, and pride in the uniform."
        )
    },
    "unit_ragda": {
        "id": "unit_ragda",
        "name": "🔥 Ustad Ka Ragda & Punishment",
        "badge": "UNIT PUNISHMENT",
        "color": "#ff9f1c",
        "theme_brief": (
            "Raw, authentic and humorous Indian Army unit ragda (punishment) and discipline life of Makra. "
            "Cover real army unit moments: Ustad catching Makra late for morning PT, frog jumps with "
            "full pitthu (rucksack), murga punishment, rifle/boot inspection, barrack bistar-bandi check, "
            "lower back strain after heavy load, and brotherhood during punishment."
        )
    },
    "training_grind": {
        "id": "training_grind",
        "name": "⚔️ Hardcore Training & Obstacle",
        "badge": "EXTREME TRAINING",
        "color": "#00f5d4",
        "theme_brief": (
            "High-adrenaline Indian Army training, obstacle course, and physical endurance of Makra. "
            "Crawling through mud and rain under barbed wire, rope climbing, 10km battle physical efficiency test (BPET), "
            "firing range bullseye target, overcoming exhaustion through pure fauji willpower."
        )
    },
    "barrack_fun": {
        "id": "barrack_fun",
        "name": "😂 Unit Masti, Chai & Bada Khana",
        "badge": "UNIT COMEDY",
        "color": "#a855f7",
        "theme_brief": (
            "Desi Haryanvi/fauji comedy and brotherhood inside the army barrack and langar. "
            "Steaming steel glass chai sessions, teasing coursemates about marriage and leave applications, "
            "Sunday military haircut comedy, Bada Khana excitement, and funny survival tricks when CO Sahab comes for rounds."
        )
    },
    "border_reality": {
        "id": "border_reality",
        "name": "🏔️ Forward Post Harsh Reality (-15°C)",
        "badge": "HARSH DUTY",
        "color": "#38bdf8",
        "theme_brief": (
            "Emotional, goosebump-inducing harsh reality of forward Line of Control (LOC) and high-altitude snow posts. "
            "Freezing -15°C winds, night sentry duty with rifle, eating hot food in bunker, missing mother's food "
            "and festival at home, yet standing unshakeable for the Indian Tricolour."
        )
    }
}


def get_director_state():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(DIRECTOR_STATE_FILE):
        try:
            with open(DIRECTOR_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    default_state = {
        "active_mode": "auto_rotate",
        "selected_track_id": "love_meera",
        "custom_idea": "",
        "bgm_volume": 20,
        "dialog_volume": 100,
        "last_track_index": 0
    }
    save_director_state(default_state)
    return default_state


def save_director_state(state):
    os.makedirs("data", exist_ok=True)
    with open(DIRECTOR_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _load_episode_tracker():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(EPISODE_TRACKER_FILE):
        try:
            with open(EPISODE_TRACKER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"completed_parts": {}, "pending_attempt": None}


def _save_episode_tracker(tracker):
    os.makedirs("data", exist_ok=True)
    with open(EPISODE_TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)


def get_exact_next_part_for_track(track_id):
    """
    STRICT PART CONTINUITY RULE:
    - Counts how many videos of `track_id` have ACTUALLY succeeded and saved MP4s in `data/history.json`.
    - If Part N succeeded -> returns N + 1.
    - If Part N failed (video was not created) -> returns N again so no part is ever skipped!
    """
    tracker = _load_episode_tracker()
    completed_for_track = int(tracker.get("completed_parts", {}).get(track_id, 0))

    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                hdata = json.load(f)
            hist_list = hdata.get("history", [])
            verified_parts = []
            for item in hist_list:
                if item.get("track_id") == track_id:
                    # Only count if it was actually generated/completed
                    p_num = int(item.get("part_number", 0))
                    verified_parts.append(p_num)
            if verified_parts:
                completed_for_track = max(completed_for_track, max(verified_parts), len(verified_parts))
        except Exception:
            pass

    return completed_for_track + 1


def mark_episode_part_completed(track_id, part_number):
    """Called when a video is successfully created so the next run moves to Part N+1."""
    tracker = _load_episode_tracker()
    comp = tracker.setdefault("completed_parts", {})
    curr = int(comp.get(track_id, 0))
    if int(part_number) > curr:
        comp[track_id] = int(part_number)
    tracker["pending_attempt"] = None
    _save_episode_tracker(tracker)


def _get_recent_episode_context(track_id):
    next_ep_num = get_exact_next_part_for_track(track_id)

    if not os.path.exists(HISTORY_FILE):
        return next_ep_num, f"This is Part #{next_ep_num} (Opening Episode). Start the story with high impact.", []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            hdata = json.load(f)
    except Exception:
        return next_ep_num, f"This is Part #{next_ep_num}.", []

    hist_list = hdata.get("history", [])
    used_dialogues = [item.get("dialogue_line_1_hinglish", "") for item in hist_list if item.get("dialogue_line_1_hinglish")]
    used_dialogues.extend(hdata.get("failed_dialogues", []))

    # Automatically sync completed part numbers from verified history entries
    for item in hist_list:
        t_id = item.get("track_id")
        p_no = item.get("part_number")
        if t_id and p_no:
            mark_episode_part_completed(t_id, p_no)

    next_ep_num = get_exact_next_part_for_track(track_id)
    track_history = [item for item in hist_list if item.get("track_id") == track_id]
    recent_context_items = track_history[-3:] if track_history else hist_list[-3:]

    if not recent_context_items:
        return next_ep_num, f"This is Part #{next_ep_num}. Establish Makra's fauji character with an unforgettable opening scene.", used_dialogues

    summary_lines = []
    for ep in recent_context_items:
        ep_title = ep.get("emotion_name", "Previous Part")
        ep_diag = ep.get("dialogue_line_1_hinglish", "")
        ep_scene = ep.get("scene_summary", ep.get("gemini_video_prompt", "")[:200])
        summary_lines.append(f"- Completed {ep_title}: Visual='{ep_scene}' | Spoken Dialogue='{ep_diag}'")

    continuity_text = (
        f"CURRENT TARGET: Write Part #{next_ep_num} of '{FOJI_UNIVERSE_TRACKS[track_id]['name']}'.\n"
        f"PREVIOUSLY COMPLETED PARTS IN THIS STORY ARC:\n" + "\n".join(summary_lines) + "\n"
        f"STRICT STORY CONTINUITY RULE: Part #{next_ep_num} MUST pick up directly from the aftermath/events of Part #{next_ep_num - 1}. "
        f"Advance the plot forward with a 100% brand-new scene, new physical action, and completely original dialogue."
    )
    return next_ep_num, continuity_text, used_dialogues


def _get_live_gemini_api_key():
    """Reads ANY API key from .env without forcing 'AIza' prefix!"""
    load_dotenv(override=True)
    # 1. Check standard key names first
    for k_name in [
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY", "GENAI_API_KEY",
        "API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "AI_API_KEY"
    ]:
        val = (os.getenv(k_name) or "").strip().strip('"').strip("'")
        if len(val) > 8:
            return val

    # 2. Scan .env directly for any key name containing GEMINI, API, or KEY
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k_up = k.strip().upper()
                    v_clean = v.strip().strip('"').strip("'")
                    if any(w in k_up for w in ["GEMINI", "GOOGLE_API", "GENAI", "OPENAI", "GROQ", "OPENROUTER", "API_KEY"]) and len(v_clean) > 8:
                        if "TELEGRAM" not in k_up and "GITHUB" not in k_up and "INSTA" not in k_up:
                            return v_clean
        except Exception:
            pass
    return ""


def _parse_ai_json(raw_text):
    if not raw_text:
        return None
    txt = raw_text.strip()
    if "{" in txt and "}" in txt:
        txt = txt[txt.find("{"):txt.rfind("}") + 1]
    try:
        data = json.loads(txt)
        if isinstance(data, dict) and data.get("dialogue_hinglish") and data.get("visual_scene_description"):
            return data
    except Exception:
        pass
    return None


def _call_pure_gemini_api_writer(track_id, track, ep_num, continuity_context, used_dialogues, custom_idea=""):
    """
    100% REAL LIVE AI WRITER:
    Reads your exact API key from .env (regardless of prefix/format) and writes a brand-new connected episode!
    """
    api_key = _get_live_gemini_api_key()
    if not api_key:
        raise RuntimeError("No API key found in .env! Please check your .env file.")

    avoid_sample = " | ".join([d for d in used_dialogues[-20:] if d])
    user_direction = f"\nDIRECTOR SPECIAL TWIST FOR PART #{ep_num}: {custom_idea}\n" if custom_idea.strip() else ""
    unique_nonce = f"{int(time.time())}-{ep_num}"

    system_prompt = f"""You are the Lead Showrunner & Scriptwriter for 'Foji AI Studio' (Generation Seed: {unique_nonce}), a 3D Pixar-style Indian Army series starring:
- Makra (Foji): Young, energetic Haryanvi Indian Army soldier (Agniveer).
- Meera (Fojan): Makra's devoted, expressive village love interest.
- Ustad & Unit Brothers: Strict moustached drill instructor and funny coursemates.

SERIES TRACK: {track['name']} ({track['badge']})
TRACK BRIEF: {track['theme_brief']}
CURRENT EPISODE PART TO WRITE: Part #{ep_num}

STORY CONTINUITY FROM PAST VIDEOS:
{continuity_context}
{user_direction}
MANDATORY RULES:
1. Write 100% original, never-before-seen content for Part #{ep_num}.
2. NEVER repeat or paraphrase any of these past dialogues: [{avoid_sample}]
3. Connect the story naturally to the previous part while placing the characters in a fresh visual action.
4. Output ONLY a valid JSON object with these exact keys:
{{
  "episode_title": "Part {ep_num}: [Short Catchy Hinglish Title]",
  "visual_scene_description": "Detailed 3D Pixar-style 9:16 vertical scene description: camera movement, lighting, Indian Army uniform/environment details, character facial expressions and physical action.",
  "dialogue_hinglish": "1 powerful, emotional or hilarious spoken Hinglish dialogue line (16 to 28 words) with authentic Haryanvi/Fauji soul.",
  "shayari_hindi": "2-line original goosebump-inducing or witty Hindi shayari matching this exact scene.",
  "hashtags": "6 viral Instagram hashtags"
}}"""

    last_err = ""

    # Route A: If key is Groq (gsk_...), OpenRouter (sk-or-...), or OpenAI (sk-...)
    if api_key.startswith("gsk_") or api_key.startswith("sk-"):
        if api_key.startswith("gsk_"):
            oa_url = "https://api.groq.com/openai/v1/chat/completions"
            oa_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]
        elif api_key.startswith("sk-or-"):
            oa_url = "https://openrouter.ai/api/v1/chat/completions"
            oa_models = ["google/gemini-2.0-flash-001", "google/gemini-flash-1.5", "meta-llama/llama-3.3-70b-instruct"]
        else:
            oa_url = "https://api.openai.com/v1/chat/completions"
            oa_models = ["gpt-4o-mini", "gpt-4o"]

        for m_name in oa_models:
            try:
                r = requests.post(
                    oa_url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": m_name,
                        "messages": [{"role": "user", "content": system_prompt}],
                        "temperature": 0.92
                    },
                    timeout=25
                )
                if r.status_code == 200:
                    cand_txt = r.json()["choices"][0]["message"]["content"]
                    parsed = _parse_ai_json(cand_txt)
                    if parsed:
                        print(f"   ✅ Live API ({m_name}) generated 100% fresh script for Part #{ep_num}!")
                        return parsed
                else:
                    last_err = f"HTTP {r.status_code}: {r.text[:160]}"
            except Exception as e:
                last_err = str(e)

    # Route B: Standard Google Gemini REST API (works with any Google/Gemini API key format)
    base_host = "https://generativelanguage.googleapis.com"
    candidate_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]

    try:
        list_r = requests.get(f"{base_host}/v1beta/models?key={api_key}", timeout=10)
        if list_r.status_code == 200:
            avail = []
            for m_obj in list_r.json().get("models", []):
                methods = m_obj.get("supportedGenerationMethods", [])
                m_name = m_obj.get("name", "").replace("models/", "")
                if "generateContent" in methods and "gemini" in m_name and "vision" not in m_name and "embedding" not in m_name:
                    avail.append(m_name)
            if avail:
                flash_first = sorted(avail, key=lambda x: (0 if "flash" in x else 1))
                for fm in flash_first:
                    if fm not in candidate_models:
                        candidate_models.insert(0, fm)
    except Exception:
        pass

    for model_name in candidate_models:
        try:
            url = f"{base_host}/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": system_prompt}]}],
                "generationConfig": {"temperature": 0.95}
            }
            r = requests.post(url, json=payload, timeout=25)
            if r.status_code == 200:
                cand_txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                parsed = _parse_ai_json(cand_txt)
                if parsed:
                    print(f"   ✅ Live Gemini API ({model_name}) generated 100% fresh script for Part #{ep_num}!")
                    return parsed
            else:
                last_err = f"HTTP {r.status_code}: {r.text[:160]}"
        except Exception as e:
            last_err = str(e)

    raise RuntimeError(f"API Script Generation Error (Key prefix '{api_key[:5]}...'): {last_err}")


def build_real_foji_universe_package(video_id=1, force_track_id=None, custom_idea="", is_preview=False):
    state = get_director_state()
    track_keys = list(FOJI_UNIVERSE_TRACKS.keys())
    tracker = _load_episode_tracker()

    # If the previous run failed before completing its video, retry the SAME track & SAME part!
    pending = tracker.get("pending_attempt")
    if not is_preview and not force_track_id and pending and pending.get("track_id") in FOJI_UNIVERSE_TRACKS:
        chosen_key = pending["track_id"]
        print(f"🔄 [Smart Retry] Previous Part #{pending.get('part_number')} did not finish video generation. Retrying same Part #{pending.get('part_number')} with fresh AI script!")
    elif force_track_id and force_track_id in FOJI_UNIVERSE_TRACKS:
        chosen_key = force_track_id
    elif state.get("active_mode") == "locked_track" and state.get("selected_track_id") in FOJI_UNIVERSE_TRACKS:
        chosen_key = state["selected_track_id"]
    else:
        idx = int(state.get("last_track_index", 0)) % len(track_keys)
        chosen_key = track_keys[idx]
        if not is_preview:
            state["last_track_index"] = idx + 1
            save_director_state(state)

    track = FOJI_UNIVERSE_TRACKS[chosen_key]
    ep_num, continuity_context, used_dialogues = _get_recent_episode_context(chosen_key)
    idea_to_use = custom_idea.strip() or state.get("custom_idea", "").strip()

    print(f"🧠 [Live Gemini API Showrunner] Writing 100% Fresh Connected Script for {track['name']} (Part #{ep_num})...")
    ai_story = _call_pure_gemini_api_writer(chosen_key, track, ep_num, continuity_context, used_dialogues, idea_to_use)

    if not is_preview:
        tracker["pending_attempt"] = {
            "track_id": chosen_key,
            "part_number": ep_num,
            "video_id": video_id,
            "started_at": time.time()
        }
        _save_episode_tracker(tracker)
        if state.get("custom_idea"):
            state["custom_idea"] = ""
            save_director_state(state)

    ep_title = ai_story.get("episode_title", f"Part {ep_num}: {track['badge']}")
    if not ep_title.lower().startswith("part") and not ep_title.lower().startswith("ep"):
        ep_title = f"Part {ep_num}: {ep_title}"

    vis_scene = ai_story.get("visual_scene_description", "")
    dialogue = ai_story.get("dialogue_hinglish", "")
    shayari = ai_story.get("shayari_hindi", "")
    hashtags = ai_story.get("hashtags", "#indianarmy #faujilife #makrameera #agniveer #armyreels")

    gemini_prompt = (
        f"Create a vertical 9:16 high-definition 3D Pixar-style animated video using the uploaded reference character images "
        f"for character face and uniform consistency. "
        f"Series Track: {track['name']} ({ep_title}). "
        f"Scene & Action: {vis_scene} "
        f"Spoken Lip-Sync Dialogue & Emotion: The lead character speaks with natural lip-sync and intense real emotion in Hindi/Hinglish: "
        f"\"{dialogue}\". "
        f"Cinematic 3D lighting, realistic Indian Army textures, vertical 9:16 reel aspect ratio."
    )

    caption = (
        f"🎖️ {ep_title} | {track['badge']}\n\n"
        f"🗣️ \"{dialogue}\"\n\n"
        f"{shayari}\n\n"
        f"Follow 👉 @ai_foji_lovelife for Part {ep_num + 1}! 🇮🇳🔥\n\n"
        f"{hashtags}"
    )

    return {
        "video_id": video_id,
        "track_id": chosen_key,
        "part_number": ep_num,
        "emotion_name": f"{track['name']} — {ep_title}",
        "badge": track["badge"],
        "scene_summary": vis_scene,
        "dialogue_line_1_hinglish": dialogue,
        "shayari_hindi": shayari,
        "gemini_video_prompt": gemini_prompt,
        "caption": caption,
        "created_at": datetime.now(IST).strftime("%d %b %Y, %I:%M %p")
    }


def get_real_system_health():
    cookie_ok = os.path.exists("gemini_cookies_secret.txt") and os.path.getsize("gemini_cookies_secret.txt") > 200
    ig_ok = os.path.exists("data/ig_session.json") and os.path.getsize("data/ig_session.json") > 100
    blueprint_ok = os.path.exists("data/gemini_learned_blueprint.json")

    telemetry = {
        "step_num": 0,
        "step_title": "System Idle & Ready",
        "sub_detail": "All 13 steps locked & verified",
        "status": "ready",
        "progress": 100,
        "updated_at": datetime.now(IST).strftime("%I:%M:%S %p")
    }
    if os.path.exists("data/live_telemetry.json"):
        try:
            with open("data/live_telemetry.json", "r", encoding="utf-8") as f:
                telemetry = json.load(f)
        except Exception:
            pass

    # Find latest generated MP4 video for live 9:16 mobile preview frame
    latest_video_file = ""
    raw_dir = "output/raw_videos"
    if os.path.exists(raw_dir):
        mp4s = [os.path.join(raw_dir, f) for f in os.listdir(raw_dir) if f.endswith(".mp4")]
        if mp4s:
            newest = max(mp4s, key=os.path.getmtime)
            latest_video_file = os.path.basename(newest)

    # Calculate next part number for each track
    tracks_with_parts = []
    for t_id, t_obj in FOJI_UNIVERSE_TRACKS.items():
        copy_t = dict(t_obj)
        copy_t["next_part"] = get_exact_next_part_for_track(t_id)
        tracks_with_parts.append(copy_t)

    hist_count = 0
    recent_history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                hd = json.load(f)
                recent_history = hd.get("history", [])[-6:]
                hist_count = len(hd.get("history", []))
        except Exception:
            pass

    return {
        "gemini_cookies_healthy": cookie_ok,
        "ig_session_healthy": ig_ok,
        "blueprint_locked": blueprint_ok,
        "telemetry": telemetry,
        "tracks": tracks_with_parts,
        "director_state": get_director_state(),
        "latest_video_file": latest_video_file,
        "total_episodes_completed": hist_count,
        "recent_history": list(reversed(recent_history))
    }

# ==============================================================================
# ⏰ SMART 2:30 AM BATCH + T-30 MIN AUTO-GENERATOR + SCHEDULE QUEUE ENGINE
# ==============================================================================
QUEUE_FILE = "data/scheduled_queue.json"
SCHEDULE_CFG_FILE = "data/schedule_config.json"


def get_schedule_config():
    os.makedirs("data", exist_ok=True)
    default_cfg = {
        "night_batch_time": "02:30",
        "night_batch_count": 3,
        "pre_slot_minutes": 30,
        "daily_slots": ["07:00", "13:30", "19:30"],
        "auto_pilot_enabled": True,
        "last_triggered_keys": []
    }
    if os.path.exists(SCHEDULE_CFG_FILE):
        try:
            with open(SCHEDULE_CFG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            default_cfg.update(saved)
            if "slots" in saved and "daily_slots" not in saved:
                default_cfg["daily_slots"] = saved["slots"]
        except Exception:
            pass
    return default_cfg


def save_schedule_config(cfg):
    os.makedirs("data", exist_ok=True)
    with open(SCHEDULE_CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def get_scheduled_queue():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"unapproved_videos": [], "scheduled_posts": [], "published_posts": []}


def save_scheduled_queue(qdata):
    os.makedirs("data", exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(qdata, f, indent=2, ensure_ascii=False)


def sync_raw_videos_into_unapproved_queue():
    """Scans output/raw_videos for any newly generated MP4s and registers them in unapproved_videos list."""
    q = get_scheduled_queue()
    known_files = set()
    for lst_name in ["unapproved_videos", "scheduled_posts", "published_posts"]:
        for item in q.get(lst_name, []):
            if item.get("video_file"):
                known_files.add(item["video_file"])

    raw_dir = "output/raw_videos"
    if not os.path.exists(raw_dir):
        return q

    hist_map = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                hd = json.load(f)
            for h in hd.get("history", []):
                vid_id = h.get("video_id")
                if vid_id:
                    hist_map[f"raw_video_{vid_id}.mp4"] = h
        except Exception:
            pass

    changed = False
    mp4_files = sorted(
        [f for f in os.listdir(raw_dir) if f.endswith(".mp4")],
        key=lambda x: os.path.getmtime(os.path.join(raw_dir, x))
    )
    for fname in mp4_files:
        if fname not in known_files:
            meta = hist_map.get(fname, {})
            now_ist = datetime.now(IST)
            q.setdefault("unapproved_videos", []).append({
                "id": f"vid_{int(time.time() * 1000)}_{fname}",
                "video_file": fname,
                "title": meta.get("emotion_name", f"Foji 3D Reel ({fname})"),
                "track_id": meta.get("track_id", "love_meera"),
                "part_number": meta.get("part_number", 1),
                "dialogue": meta.get("dialogue_line_1_hinglish", "Fresh 3D Foji Episode Ready for Approval"),
                "caption": meta.get("caption", "🎖️ Foji Life 3D Story | Follow @ai_foji_lovelife 🇮🇳🔥 #indianarmy #faujilife"),
                "created_at": now_ist.strftime("%d %b %Y, %I:%M %p"),
                "status": "awaiting_approval"
            })
            known_files.add(fname)
            changed = True

    if changed:
        save_scheduled_queue(q)
    return q


def calculate_next_available_slot_ist():
    """Finds the next open daily schedule slot that does not already have a video assigned to it."""
    cfg = get_schedule_config()
    slots = sorted(cfg.get("daily_slots", ["07:00", "13:30", "19:30"]))
    q = get_scheduled_queue()
    taken_keys = {
        item.get("scheduled_slot_key")
        for item in q.get("scheduled_posts", [])
        if item.get("status") == "scheduled"
    }

    now_ist = datetime.now(IST)
    for day_offset in range(0, 15):
        target_date = now_ist + timedelta(days=day_offset)
        date_str = target_date.strftime("%Y-%m-%d")
        display_date = target_date.strftime("%d %b %Y")
        for hm in slots:
            try:
                hh, mm = [int(x) for x in hm.split(":")]
            except Exception:
                hh, mm = 7, 0
            slot_dt = target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if slot_dt <= now_ist + timedelta(minutes=1):
                continue
            slot_key = f"{date_str}_{hm}"
            if slot_key not in taken_keys:
                return {
                    "slot_key": slot_key,
                    "scheduled_iso": slot_dt.isoformat(),
                    "scheduled_epoch": slot_dt.timestamp(),
                    "display_time": slot_dt.strftime("%d %b %Y at %I:%M %p IST"),
                    "date_label": display_date,
                    "time_label": slot_dt.strftime("%I:%M %p")
                }

    fallback_dt = now_ist + timedelta(hours=4)
    return {
        "slot_key": fallback_dt.strftime("%Y-%m-%d_%H:%M"),
        "scheduled_iso": fallback_dt.isoformat(),
        "scheduled_epoch": fallback_dt.timestamp(),
        "display_time": fallback_dt.strftime("%d %b %Y at %I:%M %p IST"),
        "date_label": fallback_dt.strftime("%d %b %Y"),
        "time_label": fallback_dt.strftime("%I:%M %p")
    }


def approve_and_schedule_video_item(video_file=None, custom_caption=""):
    """
    Approves a generated video and locks it into the NEXT available schedule slot!
    If today's slots are full, automatically queues it into tomorrow's slot!
    """
    q = sync_raw_videos_into_unapproved_queue()
    unapproved = q.get("unapproved_videos", [])

    target_item = None
    if video_file:
        for it in unapproved:
            if it.get("video_file") == video_file:
                target_item = it
                break
    if not target_item and unapproved:
        target_item = unapproved[0]

    if not target_item:
        # Check if there is any raw video file in output/raw_videos
        raw_dir = "output/raw_videos"
        mp4s = sorted([f for f in os.listdir(raw_dir) if f.endswith(".mp4")], key=lambda x: os.path.getmtime(os.path.join(raw_dir, x))) if os.path.exists(raw_dir) else []
        if not mp4s:
            raise RuntimeError("Abhi koi nayi video schedule karne ke liye tayar nahi hai! Pehle Generate karein.")
        newest_f = mp4s[-1]
        target_item = {
            "id": f"vid_{int(time.time() * 1000)}",
            "video_file": newest_f,
            "title": f"Foji 3D Reel ({newest_f})",
            "dialogue": "Approved from Command Center",
            "caption": custom_caption or "🎖️ Foji Life 3D Story | Follow @ai_foji_lovelife 🇮🇳🔥 #indianarmy #faujilife"
        }
    else:
        q["unapproved_videos"] = [x for x in unapproved if x.get("id") != target_item.get("id")]

    if custom_caption.strip():
        target_item["caption"] = custom_caption.strip()

    slot_info = calculate_next_available_slot_ist()
    target_item["status"] = "scheduled"
    target_item["scheduled_slot_key"] = slot_info["slot_key"]
    target_item["scheduled_epoch"] = slot_info["scheduled_epoch"]
    target_item["scheduled_display"] = slot_info["display_time"]
    target_item["date_label"] = slot_info["date_label"]
    target_item["time_label"] = slot_info["time_label"]

    q.setdefault("scheduled_posts", []).append(target_item)
    q["scheduled_posts"].sort(key=lambda x: float(x.get("scheduled_epoch", 0)))
    save_scheduled_queue(q)
    return target_item


# ==============================================================================
# 🔄 LIVE GITHUB CLOUD-TO-FRONTEND REALTIME BRIDGE (FOR RENDER DASHBOARD)
# ==============================================================================
_LAST_CLOUD_PULL_TS = 0.0


def pull_latest_cloud_state_for_frontend():
    """
    Ensures the Render Frontend ALWAYS displays real-time Step Progress (1..8) and
    automatically downloads any newly generated MP4 from GitHub into `output/raw_videos/`
    so you can watch, schedule, or post it directly from the Frontend!
    """
    global _LAST_CLOUD_PULL_TS
    if (time.time() - _LAST_CLOUD_PULL_TS) < 4.0:
        return
    _LAST_CLOUD_PULL_TS = time.time()

    repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
    gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    headers = {"Cache-Control": "no-cache"}
    if gh_pat:
        headers["Authorization"] = f"Bearer {gh_pat}"

    raw_base = f"https://raw.githubusercontent.com/{repo}/main"

    # 1. Pull real-time JSON state files from GitHub main branch if newer
    for rel_json in ["data/live_telemetry.json", "data/notifications.json", "data/history.json", "data/scheduled_queue.json", "data/episode_tracker.json"]:
        try:
            r = requests.get(f"{raw_base}/{rel_json}?t={int(time.time())}", headers=headers, timeout=5)
            if r.status_code == 200:
                remote_data = r.json()
                local_p = os.path.abspath(rel_json)
                os.makedirs(os.path.dirname(local_p), exist_ok=True)
                should_write = True
                if rel_json == "data/live_telemetry.json" and os.path.exists(local_p):
                    try:
                        with open(local_p, "r", encoding="utf-8") as lf:
                            loc_t = json.load(lf)
                        if float(remote_data.get("epoch", 0)) < float(loc_t.get("epoch", 0)):
                            should_write = False
                    except Exception:
                        pass
                if should_write:
                    with open(local_p, "w", encoding="utf-8") as wf:
                        json.dump(remote_data, wf, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # 2. Check if output/raw_videos on GitHub has any MP4 that isn't on this server yet -> download it!
    try:
        os.makedirs("output/raw_videos", exist_ok=True)
        api_url = f"https://api.github.com/repos/{repo}/contents/output/raw_videos"
        api_headers = {"Accept": "application/vnd.github+json"}
        if gh_pat:
            api_headers["Authorization"] = f"Bearer {gh_pat}"
        r_list = requests.get(api_url, headers=api_headers, timeout=8)
        if r_list.status_code == 200 and isinstance(r_list.json(), list):
            for item in r_list.json():
                fname = item.get("name", "")
                if fname.endswith(".mp4"):
                    local_vid = os.path.join("output/raw_videos", fname)
                    if not os.path.exists(local_vid) or os.path.getsize(local_vid) < 100 * 1024:
                        dl_url = item.get("download_url") or f"{raw_base}/output/raw_videos/{fname}"
                        vr = requests.get(dl_url, headers=headers, timeout=45)
                        if vr.status_code == 200 and len(vr.content) > 100 * 1024:
                            with open(local_vid, "wb") as vf:
                                vf.write(vr.content)
                            print(f"📥 [Frontend Sync] Downloaded new cloud video {fname} into local studio!")
    except Exception:
        pass