import os
import sys
import shutil
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import os
import shutil
import os
import re
import json
import time
import base64 as _b64
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(override=True)

IST = timezone(timedelta(hours=5, minutes=30))

DIRECTOR_STATE_FILE = "data/director_state.json"
EPISODE_TRACKER_FILE = "data/episode_tracker.json"
HISTORY_FILE = "data/history.json"
TELEMETRY_FILE = "data/live_telemetry.json"
QUEUE_FILE = "data/scheduled_queue.json"
SCHEDULE_CFG_FILE = "data/schedule_config.json"

_LAST_CLOUD_PULL_TS = 0.0
_LOCAL_QUEUE_MODIFIED_TS = 0.0

FOJI_UNIVERSE_TRACKS = {
    "love_meera": {
        "id": "love_meera",
        "name": "❤️ Foji Makra & Fojan Meera Love Story",
        "badge": "Romantic & Emotional Series",
        "characters": ["Foji Makra (Young Haryanvi Agniveer Soldier)", "Fojan Meera (Devoted Village Love Interest)"],
        "theme_brief": (
            "Heart-touching long-distance romance and emotional separation between Indian Army Agniveer soldier Makra "
            "and his beloved Meera. Include authentic fauji chutti moments, border letters, video call glitches, "
            "railway station farewells, village waiting scenes, and deep love for both uniform (Tiranga) and soulmate."
        )
    },
    "training_ustad": {
        "id": "training_ustad",
        "name": "⚔️ Agniveer Training Center & Drill",
        "badge": "High-Energy Academy Series",
        "characters": ["Foji Makra (Recruit)", "Strict Moustached Drill Ustad", "Unit Coursemates"],
        "theme_brief": (
            "Intense yet relatable Indian Army training academy life: 4 AM whistle parade, obstacle course, "
            "firing range accuracy, chest-high mud crawl, rifle drill inspection, and the transformation of a "
            "raw village boy into a steel-hearted soldier."
        )
    },
    "unit_ragda": {
        "id": "unit_ragda",
        "name": "🔥 Ustad Ka Ragda & Punishment",
        "badge": "Viral Fauji Ragda Series",
        "characters": ["Foji Makra", "Strict Drill Ustad", "Funny Unit Buddy"],
        "theme_brief": (
            "Authentic Indian Army 'Ragda' (tough disciplinary physical punishment with brotherhood and humor): "
            "frog jumps with full 20kg pithu bag, front-rolls in parade ground dust, pushups in rain because of "
            "one unpolished boot or late fall-in, and Ustad's iconic Haryanvi/Hindi dialogues."
        )
    },
    "fauji_masti": {
        "id": "fauji_masti",
        "name": "😂 Barrack Masti, Mess & Brotherhood",
        "badge": "Desi Fauji Comedy Series",
        "characters": ["Foji Makra", "Bihari & Punjabi Unit Brothers", "Mess Havildar"],
        "theme_brief": (
            "Hilarious and heartwarming barrack life: stealing extra gulab jamun from the army mess, "
            "bada khana dance, funny haircut day, hiding phone during night roll-call, trunk inspection panic, "
            "and unbreakable brotherhood among soldiers."
        )
    },
    "border_duty": {
        "id": "border_duty",
        "name": "🏔️ LOC Border Patrol & Maa KaPyar",
        "badge": "Goosebumps Patriotic Series",
        "characters": ["Foji Makra (Snow/Border Post)", "Post Commander", "Meera / Maa in Village"],
        "theme_brief": (
            "High-altitude snowy Siachen/Jammu LOC bunker duty at -25°C, night ambush patrol, drinking गरम chai "
            "in a freezing bunker, protecting the Tricolor flag during a blizzard, and emotional memories of home."
        )
    }
}

TRACK_ORDER = ["love_meera", "unit_ragda", "training_ustad", "fauji_masti", "border_duty"]


def push_json_to_github_instantly(rel_path, commit_msg):
    """Pushes JSON state files to GitHub main branch with automatic retry on SHA conflict."""
    gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
    rel_clean = rel_path.replace("\\", "/")
    full_p = os.path.abspath(rel_path)
    if not gh_pat or not os.path.exists(full_p):
        return False
    for _attempt in range(3):
        try:
            with open(full_p, "rb") as f:
                b64_content = _b64.b64encode(f.read()).decode("utf-8")
            url = f"https://api.github.com/repos/{repo}/contents/{rel_clean}"
            headers = {"Authorization": f"Bearer {gh_pat}", "Accept": "application/vnd.github+json"}
            r = requests.get(f"{url}?ref=main&t={int(time.time()*1000)}", headers=headers, timeout=10)
            sha = r.json().get("sha") if r.status_code == 200 else None
            payload = {"message": commit_msg, "content": b64_content, "branch": "main"}
            if sha:
                payload["sha"] = sha
            put_r = requests.put(url, headers=headers, json=payload, timeout=20)
            if put_r.status_code in (200, 201):
                return True
            time.sleep(1.2)
        except Exception:
            time.sleep(1.0)
    return False


def _fetch_github_json_zero_cache(rel_path):
    """Zero-cache GitHub Contents API reader so Render and Cloud Workers always share real-time state."""
    repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
    gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    rel_clean = rel_path.replace("\\", "/")
    headers = {"Accept": "application/vnd.github+json", "Cache-Control": "no-cache"}
    if gh_pat:
        headers["Authorization"] = f"Bearer {gh_pat}"
    try:
        url = f"https://api.github.com/repos/{repo}/contents/{rel_clean}?ref=main&t={int(time.time()*1000)}"
        r = requests.get(url, headers=headers, timeout=7)
        if r.status_code == 200:
            content_b64 = r.json().get("content", "")
            if content_b64:
                raw_bytes = _b64.b64decode(content_b64)
                return json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        pass
    return None


def get_director_state():
    os.makedirs("data", exist_ok=True)
    default_state = {
        "active_mode": "auto_rotate",
        "selected_track_id": "love_meera",
        "last_rotated_index": -1,
        "custom_idea": "",
        "bgm_volume": 20,
        "dialog_volume": 100
    }
    if os.path.exists(DIRECTOR_STATE_FILE):
        try:
            with open(DIRECTOR_STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                default_state.update(saved)
        except Exception:
            pass
    return default_state


def save_director_state(state):
    os.makedirs("data", exist_ok=True)
    with open(DIRECTOR_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    push_json_to_github_instantly(DIRECTOR_STATE_FILE, "Sync director state")


def get_episode_tracker():
    """
    100% STRICT PART CONTINUITY ENGINE:
    Reconciles local `episode_tracker.json`, remote GitHub `episode_tracker.json`,
    AND `data/history.json` so that once Part N is generated, it ALWAYS advances to Part N+1
    and NEVER repeats Part 1!
    """
    os.makedirs("data", exist_ok=True)
    default_tracker = {
        tid: {"completed_part": 0, "next_part": 1}
        for tid in FOJI_UNIVERSE_TRACKS.keys()
    }

    # 1. Load local tracker
    if os.path.exists(EPISODE_TRACKER_FILE):
        try:
            with open(EPISODE_TRACKER_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if k in default_tracker and isinstance(v, dict):
                    cp = int(v.get("completed_part", 0))
                    np = int(v.get("next_part", cp + 1))
                    default_tracker[k]["completed_part"] = max(default_tracker[k]["completed_part"], cp)
                    default_tracker[k]["next_part"] = max(default_tracker[k]["next_part"], np, cp + 1)
        except Exception:
            pass

    # 2. Reconcile with data/history.json so even if episode_tracker.json wasn't synced, history advances the part!
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                hd = json.load(f)
            for item in hd.get("history", []):
                tid = item.get("track_id")
                pnum = int(item.get("part_number", 0))
                # Only count if it has a video_file or completed_at OR exists in raw_videos
                vfile = item.get("video_file", "")
                vid_id = item.get("video_id")
                has_mp4 = False
                if vfile and os.path.exists(os.path.join("output/raw_videos", vfile)):
                    has_mp4 = True
                elif vid_id and os.path.exists(os.path.join("output/raw_videos", f"raw_video_{vid_id}.mp4")):
                    has_mp4 = True
                elif item.get("completed_at"):
                    has_mp4 = True

                if tid in default_tracker and pnum > 0 and has_mp4:
                    if pnum > default_tracker[tid]["completed_part"]:
                        default_tracker[tid]["completed_part"] = pnum
                        default_tracker[tid]["next_part"] = pnum + 1
        except Exception:
            pass

    return default_tracker


def save_episode_tracker(tracker):
    os.makedirs("data", exist_ok=True)
    with open(EPISODE_TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, ensure_ascii=False)
    push_json_to_github_instantly(EPISODE_TRACKER_FILE, "Advance episode part tracker")


def mark_episode_part_completed(track_id, completed_part_num):
    """Advances the track to Part N+1 and syncs immediately to GitHub!"""
    tracker = get_episode_tracker()
    if track_id not in tracker:
        tracker[track_id] = {"completed_part": 0, "next_part": 1}
    c_num = max(int(completed_part_num), int(tracker[track_id].get("completed_part", 0)))
    tracker[track_id]["completed_part"] = c_num
    tracker[track_id]["next_part"] = c_num + 1
    save_episode_tracker(tracker)
    print(f"📈 [Part Tracker Locked] Track '{track_id}' Part #{c_num} DONE -> Next run will build Part #{c_num + 1}!")


def _load_past_episodes_for_track(track_id):
    if not os.path.exists(HISTORY_FILE):
        return [], []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get("history", [])
        all_used_dialogues = [x.get("dialogue_line_1_hinglish", "") for x in items if x.get("dialogue_line_1_hinglish")]
        all_used_dialogues.extend(data.get("failed_dialogues", []))
        track_eps = [x for x in items if x.get("track_id") == track_id]
        return track_eps, all_used_dialogues
    except Exception:
        return [], []


def _get_all_live_gemini_api_keys():
    load_dotenv(override=True)
    keys = []
    for k_name in [
        "GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY", "GENAI_API_KEY",
        "API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "AI_API_KEY"
    ]:
        val = (os.getenv(k_name) or "").strip().strip('"').strip("'")
        if len(val) > 8 and val not in keys:
            keys.append(val)

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
                            if v_clean not in keys:
                                keys.append(v_clean)
        except Exception:
            pass
    if not keys and os.path.exists("data/studio_key_vault.json"):
        try:
            with open("data/studio_key_vault.json", "r", encoding="utf-8") as vf:
                for b64k in json.load(vf).get("vault", []):
                    dec = _b64.b64decode(b64k.encode("utf-8")).decode("utf-8").strip()
                    if len(dec) > 8 and dec not in keys:
                        keys.append(dec)
        except Exception:
            pass
    return keys


def _get_live_gemini_api_key():
    keys = _get_all_live_gemini_api_keys()
    return keys[0] if keys else ""


def _parse_ai_json(raw_text):
    if not raw_text:
        return None
    txt = raw_text.strip()
    txt = re.sub(r"^```(?:json)?\s*", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s*```$", "", txt)
    if "{" in txt and "}" in txt:
        txt = txt[txt.find("{"):txt.rfind("}") + 1]
    for candidate in [txt, re.sub(r",[\s\n]*}", "}", txt)]:
        try:
            data = json.loads(candidate, strict=False)
            if isinstance(data, dict) and (data.get("dialogue_hinglish") or data.get("visual_scene_description")):
                return data
        except Exception:
            pass
    # Regex fallback if model returned unescaped quotes inside JSON strings
    ep_m = re.search(r'"episode_title"\s*:\s*"([^"]+)"', txt)
    vs_m = re.search(r'"visual_scene_description"\s*:\s*"([^"]+)"', txt)
    dl_m = re.search(r'"dialogue_hinglish"\s*:\s*"([^"]+)"', txt)
    sh_m = re.search(r'"shayari_hindi"\s*:\s*"([^"]+)"', txt)
    ht_m = re.search(r'"hashtags"\s*:\s*"([^"]+)"', txt)
    if dl_m and vs_m:
        return {
            "episode_title": ep_m.group(1) if ep_m else "New Foji Episode",
            "visual_scene_description": vs_m.group(1),
            "dialogue_hinglish": dl_m.group(1),
            "shayari_hindi": sh_m.group(1) if sh_m else "???? ?? ????? ??? ?????? ?? ??? ??, ???? ?? ??? ?? ?????????? ?? ??? ???",
            "hashtags": ht_m.group(1) if ht_m else "#indianarmy #faujilife #agniveer #fojifojan #armyreels #desifauji"
        }
    return None


MEERA_WARDROBE_CATALOG = [
    "Royal Crimson Red Punjabi Salwar Kameez with golden Phulkari dupatta and jhumkas",
    "Mustard Yellow Rajasthani Bandhani Kurti with mirror-work lehenga skirt and braided hair",
    "Emerald Green Velvet Haryanvi Daman-Kurti with silver oxidized jewelry and sheer chunni",
    "Pastel Peach & Mint Chikankari Anarkali Suit with pearl earrings and flowing scarf",
    "Deep Royal Blue Silk Patiala Suit with heavy Zari border dupatta and glass bangles",
    "Magenta Pink Floral Printed Georgette Suit with golden gota-patti work and parandi",
    "Ivory White & Gold Festive Sharara Suit with colorful Leheriya dupatta",
    "Maroon & Teal Embroidered Festive Lehenga Choli with traditional matha-patti",
    "Lavender Purple Contemporary Kurti with white palazzo and silver jhumkas",
    "Turquoise Cyan Cotton Village Suit with bright orange phulkari chunni",
    "Sunset Orange & Red Bridal-Style Heavy Suit with golden kaleere and nose ring (nath)",
    "Wine Berry Silk Kurti with cream Banarasi dupatta and traditional kundan earrings"
]


def _call_pure_gemini_api_writer(track_id, track, ep_num, continuity_context, used_dialogues, custom_idea=""):
    all_keys = _get_all_live_gemini_api_keys()
    if not all_keys:
        raise RuntimeError("No API key found in .env! Please check your .env file.")

    avoid_sample = " | ".join([d for d in used_dialogues[-20:] if d])
    user_direction = f"\nDIRECTOR SPECIAL TWIST FOR PART #{ep_num}: {custom_idea}\n" if custom_idea.strip() else ""
    unique_nonce = f"{int(time.time()*1000)}-part{ep_num}"

    # Pick a guaranteed different outfit for Meera based on episode number + history count
    dress_idx = (ep_num + len(used_dialogues)) % len(MEERA_WARDROBE_CATALOG)
    assigned_meera_dress = MEERA_WARDROBE_CATALOG[dress_idx]

    # Decide default character requirement by track
    solo_army_tracks = {"training_ustad", "unit_ragda", "fauji_masti"}
    default_needs_meera = (track_id not in solo_army_tracks)

    system_prompt = f"""You are the Lead Showrunner & Scriptwriter for 'Foji AI Studio' (Seed: {unique_nonce}), a 3D Pixar-style Indian Army series starring:
- Makra (Foji): Young, energetic Haryanvi Indian Army soldier (Agniveer).
- Meera (Fojan): Makra's devoted village love interest (ONLY include Meera when the scene genuinely involves romance, home leave, railway farewell, letter/video call, or village memory. Do NOT force Meera into pure Army parade/ragda/barrack scenes!).
- Ustad & Unit Brothers: Strict moustached drill instructor and funny coursemates.

SERIES TRACK: {track['name']} ({track['badge']})
TRACK BRIEF: {track['theme_brief']}
CURRENT EPISODE PART TO WRITE: Part #{ep_num} (Continue the story forward from Part #{max(1, ep_num - 1)}!)
DEFAULT INCLUDE MEERA IN THIS TRACK: {"YES (Both Makra & Meera)" if default_needs_meera else "NO (Only Foji Makra & Army Ustad/Brothers unless custom twist mentions Meera)"}
IF MEERA APPEARS, HER MANDATORY NEW OUTFIT FOR THIS VIDEO: "{assigned_meera_dress}" (NEVER use her old dress!)

STORY CONTINUITY FROM PAST VIDEOS:
{continuity_context}
{user_direction}
MANDATORY RULES:
1. Write 100% original, never-before-seen content for Part #{ep_num}. Move the plot forward to a new incident/location!
2. NEVER repeat or paraphrase any of these past dialogues: [{avoid_sample}]
3. If Meera is in the scene, explicitly describe her wearing "{assigned_meera_dress}" in `visual_scene_description`. If the scene is pure Army training/ragda/barrack comedy without Meera, set `"include_meera": false` and focus 100% on Foji Makra!
4. Output ONLY a valid JSON object (no markdown fences) with these exact keys:
{{
  "episode_title": "Part {ep_num}: [Short Catchy Hinglish Title]",
  "include_meera": {"true" if default_needs_meera else "false"},
  "meera_outfit": "{assigned_meera_dress}",
  "visual_scene_description": "Detailed 3D Pixar-style 9:16 vertical scene description: camera movement, lighting, Indian Army uniform/environment details, exact outfits, character facial expressions and physical action.",
  "dialogue_hinglish": "1 powerful, emotional or hilarious spoken Hinglish dialogue line (16 to 28 words) with authentic Haryanvi/Fauji soul.",
  "shayari_hindi": "2-line original goosebump-inducing or witty Hindi shayari matching this exact scene.",
  "hashtags": "6 viral Instagram hashtags"
}}"""

    base_host = "https://generativelanguage.googleapis.com"
    error_log = []

    for api_key in all_keys:
        if api_key.startswith("gsk_") or api_key.startswith("sk-"):
            if api_key.startswith("gsk_"):
                oa_url = "https://api.groq.com/openai/v1/chat/completions"
                oa_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
            elif api_key.startswith("sk-or-"):
                oa_url = "https://openrouter.ai/api/v1/chat/completions"
                oa_models = ["google/gemini-2.5-flash", "meta-llama/llama-3.3-70b-instruct"]
            else:
                oa_url = "https://api.openai.com/v1/chat/completions"
                oa_models = ["gpt-4o-mini", "gpt-4o"]

            for m_name in oa_models:
                try:
                    r = requests.post(
                        oa_url,
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={"model": m_name, "messages": [{"role": "user", "content": system_prompt}], "temperature": 0.9},
                        timeout=25
                    )
                    if r.status_code == 200:
                        cand_txt = r.json()["choices"][0]["message"]["content"]
                        parsed = _parse_ai_json(cand_txt)
                        if parsed:
                            parsed.setdefault("include_meera", default_needs_meera)
                            parsed.setdefault("meera_outfit", assigned_meera_dress)
                            return parsed
                    else:
                        error_log.append(f"{m_name}: HTTP {r.status_code}")
                except Exception as e:
                    error_log.append(f"{m_name}: {e}")
            continue

        discovered = []
        try:
            m_resp = requests.get(f"{base_host}/v1beta/models?key={api_key}", timeout=10)
            if m_resp.status_code == 200:
                for m_obj in m_resp.json().get("models", []):
                    m_id = m_obj.get("name", "").replace("models/", "")
                    methods = m_obj.get("supportedGenerationMethods", [])
                    if "generateContent" in methods and ("gemini" in m_id.lower() or "gemma" in m_id.lower()):
                        if not any(skip in m_id.lower() for skip in [
                            "vision", "embedding", "imagen", "veo", "aqa", "tts",
                            "audio", "robotics", "computer-use", "image", "learnlm"
                        ]):
                            discovered.append(m_id)
        except Exception as e:
            error_log.append(f"ListModels error: {e}")

        preferred_order = [
            "gemini-3-flash-preview",
            "gemini-2.5-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemma-4-31b-it",
            "gemma-4-26b-a4b-it",
            "gemini-2.5-pro",
            "gemini-pro-latest"
        ]

        ordered_models = []
        for pm in preferred_order:
            if not discovered or pm in discovered:
                ordered_models.append(pm)
        for dm in discovered:
            if dm not in ordered_models:
                ordered_models.append(dm)

        print(f"🔎 [Trying Verified Active Models]: {', '.join(ordered_models[:8])}")

        for model_name in ordered_models:
            try:
                url = f"{base_host}/v1beta/models/{model_name}:generateContent?key={api_key}"
                gen_cfg = {"temperature": 0.9}
                if "gemini" in model_name.lower():
                    gen_cfg["responseMimeType"] = "application/json"
                payload = {"contents": [{"parts": [{"text": system_prompt}]}], "generationConfig": gen_cfg}
                r = requests.post(url, json=payload, timeout=25)
                if r.status_code == 200:
                    parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    cand_txt = "".join([p.get("text", "") for p in parts if "text" in p])
                    parsed = _parse_ai_json(cand_txt)
                    if parsed:
                        print(f"✅ [AI Scriptwriter] Script generated using live model: {model_name}")
                        parsed.setdefault("include_meera", default_needs_meera)
                        parsed.setdefault("meera_outfit", assigned_meera_dress)
                        return parsed
                    else:
                        error_log.append(f"{model_name}: JSON parse failed")
                else:
                    short_msg = r.text[:140].replace("\n", " ")
                    print(f"⚠️ [{model_name}] HTTP {r.status_code} -> trying next active model...")
                    error_log.append(f"{model_name}: HTTP {r.status_code} ({short_msg})")
            except Exception as e:
                error_log.append(f"{model_name}: {e}")

    raise RuntimeError("API Script Generation Error: " + " | ".join(error_log[-3:]))


def build_real_foji_universe_package(video_id=1, force_track_id=None, custom_idea="", is_preview=False):
    if not is_preview:
        try:
            rem_tr = _fetch_github_json_zero_cache(EPISODE_TRACKER_FILE)
            if isinstance(rem_tr, dict):
                loc_tr = get_episode_tracker()
                for tk, tv in rem_tr.items():
                    if tk in loc_tr and isinstance(tv, dict):
                        loc_tr[tk]["completed_part"] = max(int(loc_tr[tk]["completed_part"]), int(tv.get("completed_part", 0)))
                        loc_tr[tk]["next_part"] = max(int(loc_tr[tk]["next_part"]), int(tv.get("next_part", 1)), loc_tr[tk]["completed_part"] + 1)
                with open(EPISODE_TRACKER_FILE, "w", encoding="utf-8") as wf:
                    json.dump(loc_tr, wf, indent=2, ensure_ascii=False)
        except Exception:
            pass

    state = get_director_state()
    tracker = get_episode_tracker()

    if force_track_id and force_track_id in FOJI_UNIVERSE_TRACKS:
        chosen_key = force_track_id
    elif state.get("active_mode") == "locked_track" and state.get("selected_track_id") in FOJI_UNIVERSE_TRACKS:
        chosen_key = state["selected_track_id"]
    else:
        next_idx = (int(state.get("last_rotated_index", -1)) + 1) % len(TRACK_ORDER)
        chosen_key = TRACK_ORDER[next_idx]
        if not is_preview:
            state["last_rotated_index"] = next_idx
            state["selected_track_id"] = chosen_key
            save_director_state(state)

    track = FOJI_UNIVERSE_TRACKS[chosen_key]
    past_eps, used_dialogues = _load_past_episodes_for_track(chosen_key)
    ep_num = int(tracker.get(chosen_key, {}).get("next_part", 1))

    if past_eps:
        recent_summaries = []
        for idx, pe in enumerate(past_eps[-4:], start=max(1, len(past_eps) - 3)):
            p_num = pe.get("part_number", idx)
            recent_summaries.append(
                f"- Part #{p_num} ({pe.get('emotion_name', '')}): Scene='{pe.get('scene_summary', '')[:120]}' | "
                f"Spoken Dialogue='{pe.get('dialogue_line_1_hinglish', '')}'"
            )
        continuity_context = "PREVIOUSLY COMPLETED EPISODES IN THIS TRACK:\n" + "\n".join(recent_summaries)
    else:
        continuity_context = "This is Part #1 (Series Premiere of this track). Establish an unforgettable opening hook!"

    idea_to_use = custom_idea.strip() or state.get("custom_idea", "").strip()
    print(f"🧠 [Live AI Showrunner] Writing Connected Script for {track['name']} (Part #{ep_num})...")
    ai_story = _call_pure_gemini_api_writer(chosen_key, track, ep_num, continuity_context, used_dialogues, idea_to_use)

    if not is_preview and state.get("custom_idea"):
        state["custom_idea"] = ""
        save_director_state(state)

    ep_title = ai_story.get("episode_title", f"Part {ep_num}: {track['name']}").strip()
    if f"Part {ep_num}" not in ep_title and f"Part #{ep_num}" not in ep_title:
        ep_title = f"Part {ep_num}: {ep_title}"

    visual_scene = ai_story.get("visual_scene_description", "").strip()
    dialogue_line = ai_story.get("dialogue_hinglish", "").strip()
    shayari = ai_story.get("shayari_hindi", "").strip()
    hashtags = ai_story.get("hashtags", "#indianarmy #faujilife #agniveer #fojifojan #armyreels #desifauji").strip()

    # Smart Character Cast Decision: Should Meera be uploaded in this video or ONLY Foji Makra?
    solo_army_tracks = {"training_ustad", "unit_ragda", "fauji_masti"}
    raw_inc = ai_story.get("include_meera", chosen_key not in solo_army_tracks)
    if isinstance(raw_inc, str):
        include_meera = raw_inc.strip().lower() in ("true", "yes", "1")
    else:
        include_meera = bool(raw_inc)
    # If Meera's name is explicitly in the dialogue/scene, include her; if it's a pure solo track without her name, keep solo Makra!
    if chosen_key in solo_army_tracks and "meera" not in (visual_scene + " " + dialogue_line).lower():
        include_meera = False

    dress_idx = (ep_num + len(used_dialogues)) % len(MEERA_WARDROBE_CATALOG)
    meera_outfit = ai_story.get("meera_outfit") or MEERA_WARDROBE_CATALOG[dress_idx]

    # SMART YOUTUBE-READY NAMING: Video_023_LoveMeera_Part_06_1111_1930.mp4
    existing_cnt = len(get_scheduled_queue().get("published_posts", [])) + len(get_scheduled_queue().get("unapproved_videos", [])) + 1
    clean_track_slug = "".join(w.capitalize() for w in chosen_key.split("_"))
    ts_slug = datetime.now(IST).strftime("%m%d_%H%M%S")
    unique_vid_id = f"Video_{existing_cnt + 20:03d}_{clean_track_slug}_Part_{ep_num:02d}_{ts_slug}"
    unique_mp4_name = f"{unique_vid_id}.mp4"

    if include_meera:
        char_instruction = (
            f"Create a high-definition 9:16 vertical 3D Pixar-style animated video using the two uploaded character reference images "
            f"(Image 1: Indian Army soldier Makra; Image 2: Fojan Meera). "
            f"IMPORTANT WARDROBE CHANGE FOR MEERA: Keep Meera's exact facial features from Image 2, but DO NOT use the dress from the reference image! "
            f"In this episode, Meera MUST wear a brand-new outfit: {meera_outfit}. "
        )
    else:
        char_instruction = (
            f"Create a high-definition 9:16 vertical 3D Pixar-style animated video using the uploaded character reference image "
            f"(Indian Army soldier Makra in military uniform/training gear). Focus on Foji Makra and his Army unit/ustad (Meera is NOT in this scene). "
        )

    gemini_video_prompt = (
        f"{char_instruction}"
        f"EPISODE: {track['name']} - {ep_title}. "
        f"SCENE & ACTION: {visual_scene} "
        f"LIP-SYNC SPOKEN HINDI/HINGLISH DIALOGUE (Clear native Indian accent with deep emotion): \"{dialogue_line}\" "
        f"CINEMATOGRAPHY: Ultra-detailed 3D Pixar CGI, expressive facial animation, rich cinematic lighting, vertical 9:16 portrait format."
    )

    caption = (
        f"🎖️ {ep_title} | {track['name']}\n\n"
        f"🗣️ \"{dialogue_line}\"\n\n"
        f"🔥 {shayari}\n\n"
        f"🇮🇳 Follow @ai_foji_lovelife for Part #{ep_num + 1}!\n\n"
        f"{hashtags}"
    )

    return {
        "video_id": unique_vid_id,
        "video_file": unique_mp4_name,
        "track_id": chosen_key,
        "track_name": track["name"],
        "part_number": ep_num,
        "include_meera": include_meera,
        "meera_outfit": meera_outfit if include_meera else "N/A (Makra Solo Army Scene)",
        "emotion_name": f"{track['name']} — {ep_title}",
        "scene_summary": visual_scene,
        "dialogue_line_1_hinglish": dialogue_line,
        "shayari_hindi": shayari,
        "gemini_video_prompt": gemini_video_prompt,
        "caption": caption,
        "created_at": datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    }


def get_schedule_config():
    os.makedirs("data", exist_ok=True)
    default_cfg = {
        "night_batch_time": "02:30",
        "night_batch_count": 3,
        "pre_slot_minutes": 30,
        "daily_slots": ["06:30", "12:30", "19:30"],
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
    push_json_to_github_instantly(SCHEDULE_CFG_FILE, "Sync schedule config")


def get_scheduled_queue():
    os.makedirs("data", exist_ok=True)
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("unapproved_videos", [])
                data.setdefault("scheduled_posts", [])
                pub = data.get("published_posts") or data.get("published_history") or []
                # Deduplicate by video_file
                seen_v = set()
                clean_pub = []
                for item in pub:
                    vf = item.get("video_file")
                    if vf and vf not in seen_v:
                        seen_v.add(vf)
                        clean_pub.append(item)
                data["published_posts"] = clean_pub
                data["published_history"] = clean_pub
                return data
        except Exception:
            pass
    return {"unapproved_videos": [], "scheduled_posts": [], "published_posts": [], "published_history": [], "updated_epoch": 0}


def save_scheduled_queue(qdata, sync_cloud=True):
    global _LOCAL_QUEUE_MODIFIED_TS
    _LOCAL_QUEUE_MODIFIED_TS = time.time()
    qdata["updated_epoch"] = _LOCAL_QUEUE_MODIFIED_TS
    os.makedirs("data", exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(qdata, f, indent=2, ensure_ascii=False)
    if sync_cloud:
        push_json_to_github_instantly(QUEUE_FILE, "Update scheduled & published queue state")


def sync_raw_videos_into_unapproved_queue():
    """
    Scans BOTH `output/raw_videos/*.mp4` AND `data/history.json` so EVERY video ever generated
    (including all 3 night-batch videos at 2:30 AM and 6:00 AM) is visible in the Frontend!
    """
    q = get_scheduled_queue()
    scheduled_files = {item.get("video_file") for item in q.get("scheduled_posts", []) if item.get("video_file")}
    published_files = {item.get("video_file") for item in q.get("published_posts", []) if item.get("video_file")}

    raw_dir = "output/raw_videos"
    os.makedirs(raw_dir, exist_ok=True)
    valid_disk_mp4s = {f for f in os.listdir(raw_dir) if f.endswith(".mp4") and os.path.getsize(os.path.join(raw_dir, f)) > 100 * 1024}
    if os.path.exists("data/cloud_mp4_index.json"):
        try:
            with open("data/cloud_mp4_index.json", "r", encoding="utf-8") as cf:
                valid_disk_mp4s.update(json.load(cf))
        except Exception:
            pass
    clean_unapproved = []
    seen_unapproved = set()
    changed = False
    for item in q.get("unapproved_videos", []):
        vf = item.get("video_file")
        if not vf or vf not in valid_disk_mp4s or vf in scheduled_files or vf in published_files or vf in seen_unapproved:
            changed = True
            continue
        seen_unapproved.add(vf)
        clean_unapproved.append(item)
    q["unapproved_videos"] = clean_unapproved

    hist_map = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                hd = json.load(f)
            for h in hd.get("history", []):
                vid_id = h.get("video_id")
                vfile = h.get("video_file") or (f"raw_video_{vid_id}.mp4" if vid_id else "")
                if vfile:
                    hist_map[vfile] = h
        except Exception:
            pass

    raw_dir = "output/raw_videos"
    os.makedirs(raw_dir, exist_ok=True)
    mp4_files = sorted(
        [f for f in os.listdir(raw_dir) if f.endswith(".mp4")],
        key=lambda x: os.path.getmtime(os.path.join(raw_dir, x)),
        reverse=True
    )

    # ONLY include real MP4 files (>100KB) that actually exist on disk (no failed/ghost entries!)
    all_candidate_files = sorted(list(valid_disk_mp4s), reverse=True)

    for fname in all_candidate_files:
        if fname not in scheduled_files and fname not in published_files and fname not in seen_unapproved:
            meta = hist_map.get(fname, {})
            if meta.get("posted") or meta.get("status") == "published":
                q["published_posts"].append({
                    "id": f"pub_{fname}",
                    "video_file": fname,
                    "title": meta.get("emotion_name", f"Foji 3D Reel ({fname})"),
                    "track_id": meta.get("track_id", "love_meera"),
                    "part_number": meta.get("part_number", 1),
                    "dialogue": meta.get("dialogue_line_1_hinglish", ""),
                    "caption": meta.get("caption", ""),
                    "published_at": meta.get("posted_at") or meta.get("completed_at") or "Posted on IG",
                    "status": "published"
                })
                published_files.add(fname)
                changed = True
                continue

            full_p = os.path.join(raw_dir, fname)
            mtime_str = (
                datetime.fromtimestamp(os.path.getmtime(full_p), IST).strftime("%d %b %Y, %I:%M %p")
                if os.path.exists(full_p)
                else (meta.get("created_at") or "Today")
            )
            q["unapproved_videos"].append({
                "id": f"vid_{fname}",
                "video_file": fname,
                "title": meta.get("emotion_name", f"Foji 3D Reel ({fname})"),
                "track_id": meta.get("track_id", "love_meera"),
                "part_number": meta.get("part_number", 1),
                "dialogue": meta.get("dialogue_line_1_hinglish", "Fresh 3D Foji Episode Ready"),
                "shayari": meta.get("shayari_hindi", ""),
                "caption": meta.get("caption", "🎖️ Foji Life 3D Story | Follow @ai_foji_lovelife 🇮🇳🔥 #indianarmy #faujilife"),
                "created_at": meta.get("completed_at") or meta.get("created_at") or mtime_str,
                "status": "awaiting_approval"
            })
            seen_unapproved.add(fname)
            changed = True

    if changed:
        save_scheduled_queue(q, sync_cloud=False)
    return q


def build_master_all_reels_vault():
    q = sync_raw_videos_into_unapproved_queue()
    vault_map = {}

    for item in q.get("published_posts", []):
        vf = item.get("video_file")
        if vf:
            copy_it = dict(item)
            copy_it["vault_status"] = "published"
            copy_it["status_badge"] = f"✅ POSTED ON IG ({item.get('published_at', 'Live')})"
            vault_map[vf] = copy_it

    for item in q.get("scheduled_posts", []):
        vf = item.get("video_file")
        if vf and vf not in vault_map:
            copy_it = dict(item)
            copy_it["vault_status"] = "scheduled"
            copy_it["status_badge"] = f"📅 SCHEDULED ({item.get('scheduled_display', '')})"
            vault_map[vf] = copy_it

    for item in q.get("unapproved_videos", []):
        vf = item.get("video_file")
        if vf and vf not in vault_map:
            copy_it = dict(item)
            copy_it["vault_status"] = "awaiting_approval"
            copy_it["status_badge"] = "🔵 READY (AWAITING SCHEDULE / POST)"
            vault_map[vf] = copy_it

    raw_dir = "output/raw_videos"
    def _sort_key(obj):
        vf = obj.get("video_file", "")
        fp = os.path.join(raw_dir, vf)
        if os.path.exists(fp):
            return os.path.getmtime(fp)
        return float(obj.get("scheduled_epoch", 0))

    return sorted(vault_map.values(), key=_sort_key, reverse=True)


def calculate_next_available_slot_ist():
    """
    STRICT SEQUENTIAL SLOT CALCULATOR:
    Assigns videos in exact chronological sequence across daily_slots (e.g. 06:30, 12:30, 19:30).
    If 06:30 and 12:30 are taken, the 3rd video ALWAYS gets 19:30 today (or 06:30 tomorrow)!
    """
    cfg = get_schedule_config()
    raw_slots = cfg.get("daily_slots", ["06:30", "12:30", "19:30"])
    clean_slots = []
    for s in raw_slots:
        s_str = str(s).strip()
        if ":" in s_str:
            clean_slots.append(s_str)
    if not clean_slots:
        clean_slots = ["06:30", "12:30", "19:30"]

    def _slot_minutes(hm_str):
        try:
            h, m = [int(x) for x in hm_str.split(":")[:2]]
            return h * 60 + m
        except Exception:
            return 390

    slots = sorted(list(set(clean_slots)), key=_slot_minutes)
    q = get_scheduled_queue()
    taken_keys = {
        item.get("scheduled_slot_key")
        for item in q.get("scheduled_posts", [])
        if item.get("status") == "scheduled"
    }

    now_ist = datetime.now(IST)
    for day_offset in range(0, 30):
        target_date = now_ist + timedelta(days=day_offset)
        date_str = target_date.strftime("%Y-%m-%d")
        display_date = target_date.strftime("%d %b %Y")
        for hm in slots:
            try:
                hh, mm = [int(x) for x in hm.split(":")[:2]]
            except Exception:
                hh, mm = 6, 30
            slot_dt = target_date.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if slot_dt <= now_ist + timedelta(minutes=1):
                continue
            slot_key = f"{date_str}_{hh:02d}:{mm:02d}"
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


def approve_and_schedule_video_item(video_file=None, custom_caption="", source_label="Frontend"):
    """
    UNIFIED SCHEDULER FOR BOTH TELEGRAM & FRONTEND:
    Locks the video into the next sequential slot, updates `scheduled_queue.json`,
    pushes to GitHub, AND creates a popup notification so Frontend & Telegram both show the exact time!
    """
    q = sync_raw_videos_into_unapproved_queue()
    unapproved = q.get("unapproved_videos", [])

    target_item = None
    if video_file:
        vbase = os.path.basename(str(video_file))
        for it in unapproved:
            if it.get("video_file") == vbase:
                target_item = it
                break
        if not target_item:
            for it in build_master_all_reels_vault():
                if it.get("video_file") == vbase:
                    target_item = dict(it)
                    break

    if not target_item and unapproved:
        # Pick oldest unapproved video first so Part 1 -> Part 2 -> Part 3 schedule in exact order!
        target_item = unapproved[-1]

    if not target_item:
        raise RuntimeError("Sabhi videos pehle se Schedule ya Post ho chuki hain! Nayi video generate karein.")

    q["unapproved_videos"] = [
        x for x in unapproved
        if x.get("video_file") != target_item.get("video_file")
    ]

    if custom_caption.strip():
        target_item["caption"] = custom_caption.strip()

    slot_info = calculate_next_available_slot_ist()
    target_item["status"] = "scheduled"
    target_item["scheduled_by"] = source_label
    target_item["scheduled_slot_key"] = slot_info["slot_key"]
    target_item["scheduled_epoch"] = slot_info["scheduled_epoch"]
    target_item["scheduled_display"] = slot_info["display_time"]
    target_item["date_label"] = slot_info["date_label"]
    target_item["time_label"] = slot_info["time_label"]

    q["scheduled_posts"] = [
        x for x in q.get("scheduled_posts", [])
        if x.get("video_file") != target_item.get("video_file")
    ]
    q["scheduled_posts"].append(target_item)
    q["scheduled_posts"].sort(key=lambda x: float(x.get("scheduled_epoch", 0)))

    save_scheduled_queue(q, sync_cloud=True)

    # Push live notification so Frontend immediately pops up a Center Modal even if scheduled from Telegram!
    try:
        import gemini_bot
        gemini_bot.push_app_notification(
            "schedule",
            f"📅 Video Scheduled ({source_label})!",
            f"{target_item.get('title', target_item['video_file'])} locked for {slot_info['display_time']}!",
            "success"
        )
    except Exception:
        pass

    return target_item


def mark_video_as_published_in_vault(video_file, caption="", media_pk=""):
    q = sync_raw_videos_into_unapproved_queue()
    vname = os.path.basename(str(video_file))
    now_str = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")

    found_item = None
    for lst_key in ["scheduled_posts", "unapproved_videos"]:
        rem = []
        for it in q.get(lst_key, []):
            if it.get("video_file") == vname:
                found_item = it
            else:
                rem.append(it)
        q[lst_key] = rem

    if not found_item:
        found_item = {
            "id": f"pub_{int(time.time()*1000)}",
            "video_file": vname,
            "title": f"Foji 3D Reel ({vname})",
            "dialogue": "Published to Instagram (@ai_foji_lovelife)",
            "caption": caption
        }

    if caption:
        found_item["caption"] = caption
    found_item["status"] = "published"
    found_item["published_at"] = now_str
    found_item["published_epoch"] = time.time()
    found_item["ig_media_pk"] = str(media_pk or "LIVE")

    q["published_posts"] = [
        x for x in q.get("published_posts", [])
        if x.get("video_file") != vname
    ]
    q["published_posts"].insert(0, found_item)
    save_scheduled_queue(q, sync_cloud=True)

    # Also mark posted in history.json
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                hd = json.load(f)
            for h in hd.get("history", []):
                if h.get("video_file") == vname or f"raw_video_{h.get('video_id')}.mp4" == vname:
                    h["posted"] = True
                    h["posted_at"] = now_str
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(hd, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return found_item


def pull_latest_cloud_state_for_frontend():
    global _LAST_CLOUD_PULL_TS
    if (time.time() - _LAST_CLOUD_PULL_TS) < 2.5:
        return
    _LAST_CLOUD_PULL_TS = time.time()

    for rel_json in ["data/live_telemetry.json", "data/notifications.json", "data/history.json", "data/episode_tracker.json"]:
        remote_data = _fetch_github_json_zero_cache(rel_json)
        if remote_data is not None:
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

    if (time.time() - _LOCAL_QUEUE_MODIFIED_TS) > 12.0:
        remote_q = _fetch_github_json_zero_cache(QUEUE_FILE)
        if isinstance(remote_q, dict):
            loc_q = get_scheduled_queue()
            if float(remote_q.get("updated_epoch", 0)) > float(loc_q.get("updated_epoch", 0)):
                with open(QUEUE_FILE, "w", encoding="utf-8") as wf:
                    json.dump(remote_q, wf, indent=2, ensure_ascii=False)

    # ZERO-RAM CLOUD INDEX: On Render/Linux, DO NOT download 25+ MP4s into 512MB RAM!
    # Only record their filenames in data/cloud_mp4_index.json so the Vault knows about every video with 0 MB RAM!
    repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
    gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    api_headers = {"Accept": "application/vnd.github+json", "Cache-Control": "no-cache"}
    if gh_pat:
        api_headers["Authorization"] = f"Bearer {gh_pat}"
    try:
        os.makedirs("output/raw_videos", exist_ok=True)
        api_url = f"https://api.github.com/repos/{repo}/contents/output/raw_videos?ref=main&t={int(time.time())}"
        r_list = requests.get(api_url, headers=api_headers, timeout=8)
        if r_list.status_code == 200 and isinstance(r_list.json(), list):
            cloud_mp4s = []
            for item in r_list.json():
                fname = item.get("name", "")
                if fname.endswith(".mp4") and int(item.get("size", 0)) > 100 * 1024:
                    cloud_mp4s.append(fname)
                    # Only download full MP4 on Windows Laptop (never on 512MB Render Cloud!)
                    if os.name == "nt" and not os.environ.get("RENDER"):
                        local_vid = os.path.join("output/raw_videos", fname)
                        if not os.path.exists(local_vid) or os.path.getsize(local_vid) < 100 * 1024:
                            dl_url = item.get("download_url")
                            if dl_url:
                                vr = requests.get(dl_url, headers=api_headers, timeout=45)
                                if vr.status_code == 200 and len(vr.content) > 100 * 1024:
                                    with open(local_vid, "wb") as vf:
                                        vf.write(vr.content)
            with open("data/cloud_mp4_index.json", "w", encoding="utf-8") as cf:
                json.dump(cloud_mp4s, cf)
    except Exception:
        pass


def get_real_system_health():
    state = get_director_state()
    tracker = get_episode_tracker()

    telemetry = {
        "step_num": 0,
        "step_title": "System Idle & Ready",
        "sub_detail": "Waiting for next generation",
        "status": "idle",
        "progress": 0,
        "updated_at": ""
    }
    if os.path.exists(TELEMETRY_FILE):
        try:
            with open(TELEMETRY_FILE, "r", encoding="utf-8") as f:
                telemetry.update(json.load(f))
        except Exception:
            pass

    recent_history = []
    total_generated = 0
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                hd = json.load(f)
                hist_list = hd.get("history", [])
                total_generated = len(hist_list)
                recent_history = list(reversed(hist_list[-12:]))
        except Exception:
            pass

    raw_videos = []
    if os.path.exists("output/raw_videos"):
        mp4s = [
            os.path.join("output/raw_videos", f)
            for f in os.listdir("output/raw_videos")
            if f.endswith(".mp4") and os.path.getsize(os.path.join("output/raw_videos", f)) > 100 * 1024
        ]
        mp4s.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        raw_videos = [os.path.basename(p) for p in mp4s]

    tracks_summary = []
    for tid in TRACK_ORDER:
        t_info = FOJI_UNIVERSE_TRACKS[tid]
        t_prog = tracker.get(tid, {"completed_part": 0, "next_part": 1})
        tracks_summary.append({
            "id": tid,
            "name": t_info["name"],
            "badge": t_info["badge"],
            "completed_part": t_prog.get("completed_part", 0),
            "next_part": t_prog.get("next_part", 1),
            "theme_brief": t_info["theme_brief"]
        })

    return {
        "director_state": state,
        "tracks": tracks_summary,
        "telemetry": telemetry,
        "total_episodes_completed": max(total_generated, len(raw_videos)),
        "recent_history": recent_history,
        "latest_video_file": raw_videos[0] if raw_videos else None,
        "all_raw_videos": raw_videos,
        "gemini_cookie_ready": os.path.exists("gemini_cookies_secret.txt") or bool(os.getenv("GEMINI_COOKIES_JSON")),
        "ig_session_ready": os.path.exists("data/ig_session.json") or bool(os.getenv("IG_SESSION_JSON"))
    }

def delete_file_from_github_repo(rel_path, commit_msg="Clean up video from cloud storage"):
    """Deletes a file (.mp4 or .jpg) from GitHub repository via REST API so repo & Render never bloat."""
    gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
    repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
    rel_clean = rel_path.replace("\\", "/")
    if not gh_pat:
        return False
    try:
        url = f"https://api.github.com/repos/{repo}/contents/{rel_clean}"
        headers = {"Authorization": f"Bearer {gh_pat}", "Accept": "application/vnd.github+json"}
        r = requests.get(f"{url}?ref=main&t={int(time.time()*1000)}", headers=headers, timeout=10)
        if r.status_code == 200:
            sha = r.json().get("sha")
            if sha:
                del_r = requests.delete(url, headers=headers, json={"message": commit_msg, "sha": sha, "branch": "main"}, timeout=15)
                return del_r.status_code in (200, 204)
    except Exception:
        pass
    return False


def archive_video_to_laptop_folder(vname, meta=None):
    """Saves a permanent copy of the video & metadata into D:\foji_ai_automation/Posted_YouTube_Archive on Laptop."""
    if os.environ.get("RENDER") or os.name != "nt":
        return
    try:
        archive_dir = os.path.abspath("Posted_YouTube_Archive")
        os.makedirs(archive_dir, exist_ok=True)
        src_mp4 = os.path.abspath(os.path.join("output/raw_videos", vname))
        if os.path.exists(src_mp4) and os.path.getsize(src_mp4) > 50 * 1024:
            dst_mp4 = os.path.join(archive_dir, vname)
            if not os.path.exists(dst_mp4):
                shutil.copy2(src_mp4, dst_mp4)
            if isinstance(meta, dict):
                with open(dst_mp4 + ".json", "w", encoding="utf-8") as mf:
                    json.dump(meta, mf, indent=2, ensure_ascii=False)
    except Exception:
        pass


def delete_video_everywhere_manual(video_file_or_id):
    """
    Manual Delete from Web UI or Telegram:
    1. Archives a safe backup in Posted_YouTube_Archive on Laptop (just in case)
    2. Removes from unapproved_videos, scheduled_posts, and published_posts
    3. Deletes from output/raw_videos (Render/Local) AND deletes from GitHub Repo!
    """
    raw_str = os.path.basename(str(video_file_or_id).strip())
    vname = raw_str if raw_str.endswith(".mp4") else f"raw_video_{raw_str}.mp4"
    if not os.path.exists(os.path.join("output/raw_videos", vname)) and os.path.exists(os.path.join("output/raw_videos", raw_str)):
        vname = raw_str

    q = get_scheduled_queue()
    for k in ["unapproved_videos", "scheduled_posts", "published_posts", "published_history"]:
        q[k] = [x for x in q.get(k, []) if x.get("video_file") != vname and str(x.get("id")) != raw_str]

    # Record in deleted_ids.json so sync never resurrects it
    del_file = "data/deleted_ids.json"
    del_set = set()
    if os.path.exists(del_file):
        try:
            with open(del_file, "r", encoding="utf-8") as df:
                del_set.update(str(x) for x in json.load(df))
        except Exception:
            pass
    del_set.add(vname)
    del_set.add(vname.replace("raw_video_", "").replace(".mp4", ""))
    with open(del_file, "w", encoding="utf-8") as df:
        json.dump(list(del_set), df)

    if os.path.exists("data/cloud_mp4_index.json"):
        try:
            with open("data/cloud_mp4_index.json", "r", encoding="utf-8") as cf:
                c_list = [x for x in json.load(cf) if x != vname]
            with open("data/cloud_mp4_index.json", "w", encoding="utf-8") as cf:
                json.dump(c_list, cf)
        except Exception:
            pass

    save_scheduled_queue(q, sync_cloud=True)
    push_json_to_github_instantly(del_file, f"Record deleted reel {vname}")

    # Delete local output/raw_videos file & thumbnail
    for p in [os.path.join("output/raw_videos", vname), os.path.join("output/raw_videos", vname + ".jpg")]:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    # Delete from GitHub Repository asynchronously
    delete_file_from_github_repo(f"output/raw_videos/{vname}", f"Delete {vname}")
    delete_file_from_github_repo(f"output/raw_videos/{vname}.jpg", f"Delete {vname}.jpg")
    return vname


def auto_purge_posted_videos_older_than_1_hour():
    """
    Runs automatically in background:
    Any reel in `published_posts` that was posted more than 1 hour (3600s) ago:
    1. On Laptop: Copies MP4 to `D:\foji_ai_automation/Posted_YouTube_Archive\`
    2. Deletes the heavy MP4 from `output/raw_videos/` on Render AND GitHub repo!
    3. Marks `cloud_purged = True` in `published_posts` so the Posted section still shows its title & Instagram link!
    """
    q = get_scheduled_queue()
    now_t = time.time()
    changed = False

    for item in q.get("published_posts", []):
        vname = item.get("video_file", "")
        if not vname or item.get("cloud_purged"):
            continue
        pub_ep = float(item.get("published_epoch", 0))
        if pub_ep <= 0:
            # If old item had no epoch, set it to now so it gets 1 hour before purge
            item["published_epoch"] = now_t
            changed = True
            continue

        if (now_t - pub_ep) >= 3600:
            # 1. Save to Laptop Archive if running on Windows
            archive_video_to_laptop_folder(vname, item)

            # 2. Delete heavy MP4 from GitHub Repo so GitHub/Render never run out of memory/storage
            delete_file_from_github_repo(f"output/raw_videos/{vname}", f"Auto-purge {vname} 1hr after IG post")

            # 3. Delete from output/raw_videos/ (it remains safely in Posted_YouTube_Archive on Laptop!)
            raw_p = os.path.join("output/raw_videos", vname)
            if os.path.exists(raw_p):
                archive_video_to_laptop_folder(vname, item)
                try:
                    os.remove(raw_p)
                except Exception:
                    pass

            item["cloud_purged"] = True
            changed = True
            print(f"🧹 [1-Hour Auto-Purge] {vname} archived to Laptop & deleted from GitHub/Render Cloud!")

    if changed:
        q["published_history"] = q.get("published_posts", [])
        save_scheduled_queue(q, sync_cloud=True)
