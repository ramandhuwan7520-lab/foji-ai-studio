# 🛡️ IPV4 SSL HANDSHAKE FIX FOR PYTHON 3.14
try:
    import socket as _sock
    import urllib3.util.connection as _ucn
    _ucn.allowed_gai_family = lambda: _sock.AF_INET
except Exception:
    pass
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

FOJI_UNIVERSE_TRACKS = {'training_ustad': {'id': 'training_ustad', 'name': 'Academy Training & Morning Drill', 'badge': 'Training & Drill Series', 'characters': ['Young Haryanvi Soldier Makra', 'Strict Moustached Haryanvi Drill Instructor (Ustad)', 'Batchmates'], 'theme_brief': 'Raw, energetic Indian Army academy training life: 4 AM whistle sprint on dusty parade ground, rope climb, obstacle wall, heavy backpack endurance jog, pushups in golden sunrise dust, sharp Haryanvi Ustad coaching & brotherhood grit. STRICT BAN: Zero snow, zero snow mountains, zero glaciers.'}, 'unit_ragda': {'id': 'unit_ragda', 'name': 'Ustad Ka Ragda & Punishment', 'badge': 'Viral Ragda & Punishment', 'characters': ['Young Soldier Makra', 'Strict Haryanvi Ustad', 'Funny Batchmate'], 'theme_brief': "Hilarious yet hardcore Army training punishments ('Ragda'): 4 AM murga walk, frog jumps with pithu bag, sandy ground front-roll race, caught sneaking late by Ustad, pushup penalty with savage Haryanvi one-liners & unstoppable desi attitude. STRICT BAN: Zero snow mountains."}, 'funny_fauji': {'id': 'funny_fauji', 'name': 'Fauji Masti, Bakwas & Comedy', 'badge': 'Barracks Comedy & Masti', 'characters': ['Young Soldier Makra', '2 Hilarious Barracks Buddies', 'Strict Havildar'], 'theme_brief': 'Laugh-out-loud Fauji barracks masti & desi bakwas: sneaking extra gulab jamun in mess hall, hiding phone under blanket during night inspection, snoring roommate prank, fighting for warm bucket water, hilarious Haryanvi banter. STRICT BAN: Zero snow mountains.'}, 'duty_fatigue': {'id': 'duty_fatigue', 'name': 'Duty, Fatigue & Working Reality', 'badge': 'Real Unit Work & Fatigue', 'characters': ['Young Soldier Makra', 'Unit Team & Senior Havildar'], 'theme_brief': "Authentic behind-the-scenes Army unit working reality ('Fatigue' & Duty): unloading ration trucks, sweeping barracks courtyard before CO inspection, midnight sentry guard duty with torch & hot cutting chai, polishing boots, sweaty tired smile and silent pride. STRICT BAN: Zero snow mountains."}, 'agniveer_reality': {'id': 'agniveer_reality', 'name': 'Agniveer Reality & Pride', 'badge': 'Agniveer Real Journey', 'characters': ['Young Agniveer Soldier Makra', 'Batchmates & Parents on Call'], 'theme_brief': 'Real emotional & proud Agniveer life reality: 4-year dedication, sending first salary home to mother, missing village Holi/Diwali while standing on duty, blistered feet after 10km run, proud late-night video call to parents. STRICT BAN: Zero snow mountains.'}, 'love_meera': {'id': 'love_meera', 'name': 'Foji & Fojan Desi Nok-Jhok', 'badge': 'Relatable Desi Romance', 'characters': ['Young Soldier Makra in Plain Olive Uniform', 'His Partner Meera'], 'theme_brief': 'Sweet, grounded, relatable desi nok-jhok between Makra and Meera in real Indian settings: bustling railway platform farewell, evening video call from barracks veranda, surprise home courtyard visit, playful Haryanvi teasing. STRICT BAN: Zero snow mountains, zero snowy/alpine hills, zero paper letters.'}}

TRACK_ORDER = ['training_ustad', 'unit_ragda', 'funny_fauji', 'duty_fatigue', 'agniveer_reality', 'love_meera']

DAILY_VIRAL_HASHTAGS = {
    0: "#mondaymotivation #agniveerbharti #indianarmy #haryanvishayari #faujilife #armyreels #desifauji #viralreels",
    1: "#ustadkaragda #faujattitude #indianarmy #armylover #haryanvistatus #agniveer #faujistatus #trendingreels",
    2: "#fojifojan #faujilove #kuchupuchu #indianarmy #longdistancelove #faujiwife #romanticreels #explorepage",
    3: "#locborder #siachenheroes #indianarmy #maakapyar #faujiduty #tiranga #armybrotherhood #goosebumps",
    4: "#haryanvishayar #fojishayari #desifauji #indianarmy #attitudestatus #faujireality #reelsindia #viralshorts",
    5: "#faujimasti #barracklife #armycomedy #indianarmy #faujiyaari #desicomedy #agniveerlife #funnymoments",
    6: "#faujihomecoming #surprisevisit #indianarmy #fojifojan #emotionalreunion #armylife #proudindian #viralvideos"
}


_GH_PUSH_LOCK = threading.Lock() if "threading" in globals() else __import__("threading").Lock()

def push_json_to_github_instantly(rel_path, commit_msg, blocking=False):
    """
    BULLETPROOF 5X-RETRY GITHUB JSON SYNC WITH `[skip render] [skip ci]`:
    When `blocking=True` (used for Schedule / Delete / Queue updates), waits until GitHub
    confirms 200/201 so Render polls NEVER revert a scheduled video back to Pending!
    """
    import threading as _th
    safe_msg = str(commit_msg or "Sync studio state").strip()
    if "[skip render]" not in safe_msg.lower():
        safe_msg = f"{safe_msg} [skip render] [skip ci]"

    def _do_push():
        gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
        repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
        rel_clean = rel_path.replace("\\", "/").lstrip("./")
        full_p = os.path.abspath(rel_path)
        if not gh_pat or not os.path.exists(full_p):
            return False
        with _GH_PUSH_LOCK:
            for attempt in range(1, 6):
                try:
                    with open(full_p, "rb") as f:
                        b64_content = _b64.b64encode(f.read()).decode("utf-8")
                    url = f"https://api.github.com/repos/{repo}/contents/{rel_clean}"
                    headers = {"Authorization": f"Bearer {gh_pat}", "Accept": "application/vnd.github+json"}
                    r = requests.get(f"{url}?ref=main&t={int(time.time()*1000)}", headers=headers, timeout=12)
                    sha = r.json().get("sha") if r.status_code == 200 else None
                    payload = {"message": safe_msg, "content": b64_content, "branch": "main"}
                    if sha:
                        payload["sha"] = sha
                    rp = requests.put(url, headers=headers, json=payload, timeout=18)
                    if rp.status_code in (200, 201):
                        return True
                    if rp.status_code in (409, 422, 500, 502, 503):
                        time.sleep(0.8 * attempt)
                        continue
                    print(f"⚠️ [GH Push] {rel_clean} HTTP {rp.status_code}: {rp.text[:120]}")
                    return False
                except Exception as _pe:
                    print(f"🔁 [GH Push Retry {attempt}/5] {rel_clean}: {_pe}")
                    time.sleep(0.9 * attempt)
        return False

    if blocking:
        return _do_push()
    _th.Thread(target=_do_push, daemon=True).start()
    return True





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
    state['updated_epoch'] = time.time()
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


def _sanitize_veo_safe_prompt(text):
    """
    Strips trademarked studio names ('Pixar', 'Disney') and Veo safety-trigger military/weapon/violence words
    so Google Veo NEVER rejects the video with 'I seem to be encountering an error'!
    """
    if not text:
        return ""
    replacements = [
        (r"\b3d\s+pixar[- ]style\b", "stylized 3D animated"),
        (r"\bpixar[- ]style\b", "stylized 3D animated"),
        (r"\b3d\s+pixar\s+cgi\b", "high-detail 3D stylized CGI"),
        (r"\bpixar\b", "stylized 3D animated"),
        (r"\bdisney\b", "feature-film 3D"),
        (r"\bindian\s+army\s+soldier\b", "young uniformed cadet"),
        (r"\barmy\s+soldier\b", "young uniformed cadet"),
        (r"\bindian\s+army\b", "uniformed academy"),
        (r"\bcombat\s+uniform\b", "olive-green field uniform"),
        (r"\bcombat\b", "outdoor training"),
        (r"\brifle\s+bolt\b", "jacket zipper"),
        (r"\brifle\b", "steel tea mug"),
        (r"\bgun\b", "whistle"),
        (r"\bweapon\b", "backpack"),
        (r"\bbleeding\b", "sweating"),
        (r"\bblood\b", "sweat"),
        (r"\bkhoon\b", "junoon"),
        (r"\bbarood\b", "josh"),
        (r"\bmaut\b", "mushkil"),
        (r"\bdushman\b", "mushkil"),
        (r"\benemies\b", "challenges"),
        (r"\benemy\b", "challenge"),
        (r"\bbarbed\s+wire\b", "training hurdles"),
        (r"\bfiring\s+range\b", "athletic track"),
        (r"\bshooting\b", "sprinting"),
        (r"\bloc\s+bunker\b", "snowy mountain watchtower"),
        (r"\bbunker\b", "mountain cabin"),
        (r"\bloc\b", "high mountain"),
        (r"\bwar\b", "marathon"),
        (r"\bpunishment\b", "fitness drill"),
        (r"\bexplosion\b", "sunburst"),
        (r"\bblast\b", "cheer"),
    ]
    cleaned = str(text)
    for pat, rep in replacements:
        cleaned = re.sub(pat, rep, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _call_pure_gemini_api_writer(track_id, track, ep_num, continuity_context, used_dialogues, custom_idea=""):
    all_keys = _get_all_live_gemini_api_keys()
    if not all_keys:
        raise RuntimeError("No API key found in .env! Please check your .env file.")

    avoid_sample = " | ".join([d for d in used_dialogues[-22:] if d])
    user_direction = f"\nDIRECTOR SPECIAL VIRAL CONCEPT: {custom_idea}\n" if custom_idea.strip() else ""
    unique_nonce = f"{int(time.time()*1000)}-p{ep_num}"

    dress_idx = (ep_num + len(used_dialogues)) % len(MEERA_WARDROBE_CATALOG)
    assigned_meera_dress = MEERA_WARDROBE_CATALOG[dress_idx]

    solo_army_tracks = {"training_ustad", "unit_ragda", "funny_fauji", "fauji_masti", "duty_fatigue", "agniveer_reality", "border_duty", "border_night_reality", "fauji_dosti_barracks", "civil_vs_fauji", "festival_on_duty", "fauji_safar_train", "chhutti_ghar_wapsi"}
    if track_id == "viral_trend":
        default_needs_meera = (ep_num % 2 == 0)
    else:
        default_needs_meera = (track_id in {"love_meera", "video_call_network"})

    weekday_idx = datetime.now(IST).weekday()
    daily_tags = globals().get("DAILY_VIRAL_HASHTAGS", {}).get(
        weekday_idx,
        "#indianarmy #faujilife #haryanvishayari #agniveer #fojifojan #armyreels #viralreels"
    )

    viral_angles = [
        "MORNING FITNESS MOTIVATION & HARYANVI SWAG: Sharp, funny or inspiring contrast between sleepy civilian morning and energetic 4 AM cadet life.",
        "CUTE 'KUCHU PUCHU / JAAN / BAWLI' NOK-JHOK: Playful, ultra-relatable teasing or warm smile on a video call or surprise visit.",
        "HIGH-ENERGY COACH USTAD DRILL & BROTHERHOOD: Energetic pushups or sprint on a sunny ground with a witty Haryanvi comeback.",
        "DINING MESS COMEDY PUNCH: Fast visual comedy with hot gulab jamun / laddu / chai in the hostel mess and a funny reaction.",
        "EMOTIONAL SNOWY MOUNTAIN CHAI & MAA CALL: Warm steaming chai mug in snowfall with soulful pride and love for home."
    ]
    chosen_viral_angle = viral_angles[(ep_num + int(time.time() // 300)) % len(viral_angles)]

    system_prompt = f"""You are India's #1 Viral 8-Second 3D Animated Reel Writer & Haryanvi Shayar (Seed: {unique_nonce}).

TRACK: {track['name']} ({track['badge']})
TRACK BRIEF: {track['theme_brief']}
VIRAL ANGLE: {chosen_viral_angle}
EPISODE / REEL NUMBER: {"Standalone Viral Special #" + str(ep_num) if track_id == "viral_trend" else "Part #" + str(ep_num)}
INCLUDE FEMALE PARTNER IN SCENE: {"YES (Young Cadet + His Partner)" if default_needs_meera else "NO (Young Cadet + Coach Ustad / Hostel Friends)"}
IF FEMALE PARTNER APPEARS, HER OUTFIT: "{assigned_meera_dress}"

PAST CONTEXT (Do NOT repeat):
{continuity_context}
{user_direction}
CRITICAL VEO VIDEO SAFETY & 8-SECOND TIMING RULES (MUST FOLLOW 100%):
1. ZERO TRADEMARKS OR VIOLENCE: NEVER use words like 'Pixar', 'Disney', 'gun', 'rifle', 'weapon', 'blood', 'bleeding', 'combat', 'war', 'enemies', 'LOC', 'bunker', 'firing', 'punishment', or 'death'. Describe safe, lively, family-friendly 3D cartoon scenes (fitness drills, hostel mess comedy, snowy mountain chai, cute video calls, village homecoming).
2. SHORT 8-SECOND DIALOGUE (10 TO 17 WORDS MAX!): Because the video clip is 8 seconds long, `dialogue_hinglish` MUST be punchy, expressive, and strictly 10 to 17 words so the character finishes speaking cleanly!
3. CRISP VISUAL SCENE (35 TO 50 WORDS MAX!): Describe one clear location, bright expressive faces, and lively physical motion. No paper letters/chitthi, no on-screen text.
4. NATURAL PET-NAMES: Never spam 'Makra'/'Meera'. Use natural words like 'Jaan', 'Kuchu Puchu', 'Laado', 'Bawli', 'Fauji Sahab', 'Ustad Ji', 'Sher', 'Laadle'.
5. NEVER repeat past dialogues: [{avoid_sample}]
6. Output ONLY a valid JSON object (no markdown fences):
{{
  "episode_title": "{"🔥 Viral Special: " if track_id == "viral_trend" else f"Part {ep_num}: "}[Catchy Hinglish Title]",
  "include_meera": {"true" if default_needs_meera else "false"},
  "meera_outfit": "{assigned_meera_dress}",
  "opening_hook_3s": "Short 10-word visual action hook.",
  "visual_scene_description": "Crisp 35-50 word family-friendly 3D animated 9:16 vertical scene description with vivid lighting and facial expression.",
  "dialogue_hinglish": "Punchy 10-17 word spoken Hinglish/Haryanvi dialogue that fits cleanly inside 8 seconds.",
  "shayari_hindi": "2-line heart-touching Haryanvi / Fauji shayari for Instagram caption.",
  "song_lyrics_cue": "1 soulful background mood cue for caption.",
  "bgm_mood_direction": "Exact BGM mood (funny / emotional / ragda / patriotic).",
  "hashtags": "{daily_tags}"
}}"""

    base_host = "https://generativelanguage.googleapis.com"
    default_chain = [
        "gemini-3-flash-preview", "gemini-flash-lite-latest", "gemma-4-26b-a4b-it",
        "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest", "gemini-1.5-flash"
    ]
    cached_best = []
    if os.path.exists("data/working_model_cache.json"):
        try:
            cached_best = json.load(open("data/working_model_cache.json", "r", encoding="utf-8")).get("verified_models", [])
        except Exception:
            pass
    ordered_models = cached_best + [m for m in default_chain if m not in cached_best]

    for api_key in all_keys:
        if api_key.startswith("gsk_") or api_key.startswith("sk-"):
            oa_url = "https://api.groq.com/openai/v1/chat/completions" if api_key.startswith("gsk_") else (
                "https://openrouter.ai/api/v1/chat/completions" if api_key.startswith("sk-or-") else "https://api.openai.com/v1/chat/completions"
            )
            oa_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"] if api_key.startswith("gsk_") else ["google/gemini-2.5-flash", "gpt-4o-mini"]
            for m_name in oa_models:
                try:
                    r = requests.post(
                        oa_url,
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={"model": m_name, "messages": [{"role": "user", "content": system_prompt}], "temperature": 0.92},
                        timeout=16
                    )
                    if r.status_code == 200:
                        parsed = _parse_ai_json(r.json()["choices"][0]["message"]["content"])
                        if parsed:
                            parsed.setdefault("include_meera", default_needs_meera)
                            parsed.setdefault("meera_outfit", assigned_meera_dress)
                            parsed.setdefault("hashtags", daily_tags)
                            return parsed
                except Exception:
                    pass
            continue

        for model_name in ordered_models:
            try:
                url = f"{base_host}/v1beta/models/{model_name}:generateContent?key={api_key}"
                gen_cfg = {"temperature": 0.92}
                if "gemini" in model_name.lower():
                    gen_cfg["responseMimeType"] = "application/json"
                payload = {"contents": [{"parts": [{"text": system_prompt}]}], "generationConfig": gen_cfg}
                r = requests.post(url, json=payload, timeout=18)
                if r.status_code == 200:
                    parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    cand_txt = "".join([p.get("text", "") for p in parts if "text" in p])
                    parsed = _parse_ai_json(cand_txt)
                    if parsed:
                        print(f"✅ [Viral AI Showrunner] Veo-Safe Script composed using model: {model_name}")
                        parsed.setdefault("include_meera", default_needs_meera)
                        parsed.setdefault("meera_outfit", assigned_meera_dress)
                        parsed.setdefault("hashtags", daily_tags)
                        return parsed
            except Exception:
                pass

    return {
        "episode_title": f"Part {ep_num}: Subah Ki Chai Aur Fauji Swag",
        "include_meera": default_needs_meera,
        "meera_outfit": assigned_meera_dress,
        "opening_hook_3s": "Close-up of the smiling cadet lifting a steaming steel cup of masala chai in golden sunrise light.",
        "visual_scene_description": "Stylized 3D animated vertical scene on a sunny mountain courtyard. The cheerful young man in an olive-green uniform laughs warmly with expressive eyes while holding a steaming steel mug of tea.",
        "dialogue_hinglish": (
            "Oye meri kuchu puchu, tu bas muskurati reh jaan, tere fauji ki har subah tere naam hai!"
            if default_needs_meera else
            "Ustad ji, subah char baje ki daud aur garam chai, asli maza toh isi zindagi mein hai!"
        ),
        "shayari_hindi": "Vardi ka junoon aur dil mein apno ka pyaar, isi se banta hai har fauji ka sansaar!",
        "song_lyrics_cue": "Warm acoustic morning folk melody",
        "bgm_mood_direction": "emotional" if default_needs_meera else "patriotic",
        "hashtags": daily_tags
    }






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
        min_completed = min(int(tracker.get(t_key, {}).get("completed_part", 0)) for t_key in TRACK_ORDER)
        lagging_tracks = [
            t_key for t_key in TRACK_ORDER
            if int(tracker.get(t_key, {}).get("completed_part", 0)) == min_completed
        ]
        chosen_key = lagging_tracks[0]
        if not is_preview:
            state["selected_track_id"] = chosen_key
            save_director_state(state)

    track = FOJI_UNIVERSE_TRACKS[chosen_key]
    past_eps, used_dialogues = _load_past_episodes_for_track(chosen_key)
    ep_num = int(tracker.get(chosen_key, {}).get("next_part", 1))

    if past_eps and chosen_key != "viral_trend":
        recent_summaries = []
        for idx, pe in enumerate(past_eps[-4:], start=max(1, len(past_eps) - 3)):
            p_num = pe.get("part_number", idx)
            recent_summaries.append(
                f"- Part #{p_num} ({pe.get('emotion_name', '')}): Scene='{pe.get('scene_summary', '')[:120]}' | "
                f"Spoken Dialogue='{pe.get('dialogue_line_1_hinglish', '')}'"
            )
        continuity_context = "PREVIOUSLY COMPLETED EPISODES IN THIS TRACK:\n" + "\n".join(recent_summaries)
    else:
        continuity_context = "Standalone High-Retention Viral Reel — hook the audience in the first 2 seconds with maximum emotional or comedic impact!"

    idea_to_use = custom_idea.strip() or state.get("custom_idea", "").strip()
    print(f"🧠 [Live AI Showrunner] Composing Viral Script, Haryanvi Shayari & BGM for {track['name']} (#{ep_num})...")
    ai_story = _call_pure_gemini_api_writer(chosen_key, track, ep_num, continuity_context, used_dialogues, idea_to_use)

    if not is_preview and state.get("custom_idea"):
        state["custom_idea"] = ""
        save_director_state(state)

    ep_title = ai_story.get("episode_title", f"Part {ep_num}: {track['name']}").strip()
    if chosen_key != "viral_trend" and f"Part {ep_num}" not in ep_title and f"Part #{ep_num}" not in ep_title:
        ep_title = f"Part {ep_num}: {ep_title}"

    opening_hook = ai_story.get("opening_hook_3s", "Fast cinematic zoom on soldier's intense eyes with dramatic bass drop.").strip()
    visual_scene = ai_story.get("visual_scene_description", "").strip()
    dialogue_line = ai_story.get("dialogue_hinglish", "").strip()
    shayari = ai_story.get("shayari_hindi", "").strip()
    song_cue = ai_story.get("song_lyrics_cue", "Soulful Haryanvi / Patriotic acoustic background melody").strip()
    bgm_cue = ai_story.get("bgm_mood_direction", "Cinematic bass, dhol beat & emotional flute").strip()

    weekday_idx = datetime.now(IST).weekday()
    default_daily_tags = globals().get("DAILY_VIRAL_HASHTAGS", {}).get(
        weekday_idx,
        "#indianarmy #faujilife #haryanvishayari #agniveer #fojifojan #armyreels #viralreels"
    )
    hashtags = (ai_story.get("hashtags") or default_daily_tags).strip()
    if "#indianarmy" not in hashtags.lower():
        hashtags = f"{hashtags} {default_daily_tags}".strip()

    solo_army_tracks = {"training_ustad", "unit_ragda", "funny_fauji", "fauji_masti", "duty_fatigue", "agniveer_reality", "border_duty", "border_night_reality", "fauji_dosti_barracks", "civil_vs_fauji", "festival_on_duty", "fauji_safar_train", "chhutti_ghar_wapsi"}
    raw_inc = ai_story.get("include_meera", chosen_key not in solo_army_tracks)
    if isinstance(raw_inc, str):
        include_meera = raw_inc.strip().lower() in ("true", "yes", "1")
    else:
        include_meera = bool(raw_inc)

    combined_low = (visual_scene + " " + dialogue_line).lower()
    if chosen_key in solo_army_tracks:
        explicit_couple_in_idea = any(w in (idea_to_use or "").lower() for w in ["meera", "fojan", "girlfriend", "wife", "couple", "love story"])
        explicit_meera_in_scene = any(w in combined_low for w in ["meera", "fojan", "kuchu puchu", "girlfriend", "wife"])
        if not (explicit_couple_in_idea or explicit_meera_in_scene):
            include_meera = False
    if False:
        include_meera = False

    dress_idx = (ep_num + len(used_dialogues)) % len(MEERA_WARDROBE_CATALOG)
    meera_outfit = ai_story.get("meera_outfit") or MEERA_WARDROBE_CATALOG[dress_idx]

    q_now = get_scheduled_queue()
    existing_cnt = len(q_now.get("published_posts", [])) + len(q_now.get("scheduled_posts", [])) + len(q_now.get("unapproved_videos", [])) + 1
    clean_track_slug = "".join(w.capitalize() for w in chosen_key.split("_"))
    ts_slug = datetime.now(IST).strftime("%m%d_%H%M%S")
    unique_vid_id = f"Video_{existing_cnt + 20:03d}_{clean_track_slug}_Part_{ep_num:02d}_{ts_slug}"
    unique_mp4_name = f"{unique_vid_id}.mp4"

    safe_hook = _sanitize_veo_safe_prompt(opening_hook)
    safe_scene = _sanitize_veo_safe_prompt(visual_scene)
    safe_diag = _sanitize_veo_safe_prompt(dialogue_line)
    # Keep dialogue crisp so it fits comfortably inside an 8-second Veo clip
    diag_words = safe_diag.split()
    if len(diag_words) > 22:
        safe_diag = " ".join(diag_words[:22]).rstrip(",;:") + "!"

    if include_meera:
        char_instruction = (
            f"Generate a 9:16 vertical stylized 3D animated video featuring the two characters from the uploaded reference images "
            f"(the young man in plain olive-green uniform without shoulder stars, and the young woman wearing {meera_outfit}). "
        )
    else:
        char_instruction = (
            f"Generate a 9:16 vertical stylized 3D animated video featuring the cheerful young man in plain olive-green uniform "
            f"from the uploaded reference image alongside his friendly coach or hostel friends. "
        )

    gemini_video_prompt = _sanitize_veo_safe_prompt(
        f"{char_instruction}"
        f"Scene: {safe_hook} {safe_scene} "
        f"Spoken Hindi dialogue with natural lip-sync and warm Indian accent: \"{safe_diag}\" "
        f"Style: High-detail 3D animated feature film lighting, smooth expressive acting, clean 9:16 portrait framing, no on-screen text."
    )

    follow_line = (
        "🇮🇳 Follow @ai_foji_lovelife for Daily Viral Fauji Reels!"
        if chosen_key == "viral_trend"
        else f"🇮🇳 Follow @ai_foji_lovelife for Part #{ep_num + 1}!"
    )

    caption = (
        f"🎖️ {ep_title} | {track['name']}\n\n"
        f"🗣️ \"{dialogue_line}\"\n\n"
        f"🔥 {shayari}\n\n"
        f"🎵 Vibe: {song_cue}\n\n"
        f"{follow_line}\n\n"
        f"{hashtags}"
    )

    return {
        "video_id": unique_vid_id,
        "video_file": unique_mp4_name,
        "track_id": chosen_key,
        "track_name": track["name"],
        "part_number": ep_num,
        "include_meera": include_meera,
        "meera_outfit": meera_outfit if include_meera else "N/A (Solo Army Reality Scene)",
        "emotion_name": f"{track['name']} — {ep_title}",
        "opening_hook_3s": opening_hook,
        "scene_summary": visual_scene,
        "dialogue_line_1_hinglish": dialogue_line,
        "shayari_hindi": shayari,
        "song_lyrics_cue": song_cue,
        "bgm_mood_direction": bgm_cue,
        "gemini_video_prompt": gemini_video_prompt,
        "caption": caption,
        "created_at": datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
    }




def get_schedule_config():
    os.makedirs("data", exist_ok=True)
    default_cfg = {
        "night_batch_time": "01:00, 01:30, 02:00",
        "night_batch_count": 3,
        "pre_slot_minutes": 30,
        "daily_slots": ["06:30", "12:30", "18:30"],
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



def _parse_item_slot_epoch(item):
    """Reliably extracts the scheduled epoch timestamp from a queue item."""
    IST_TZ = timezone(timedelta(hours=5, minutes=30))
    for k in ("scheduled_epoch", "target_epoch"):
        val = item.get(k)
        if isinstance(val, (int, float)) and val > 1700000000:
            return float(val)
    sf = str(item.get("scheduled_for") or "").strip()
    if sf:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(sf, fmt).replace(tzinfo=IST_TZ)
                return dt.timestamp()
            except Exception:
                pass
    sk = str(item.get("scheduled_slot_key") or "").strip()
    if sk:
        try:
            dt = datetime.strptime(sk, "%Y-%m-%d_%H:%M").replace(tzinfo=IST_TZ)
            return dt.timestamp()
        except Exception:
            pass
    return 0.0


def _get_configured_daily_slots():
    try:
        cfg = get_schedule_config()
        raw = cfg.get("daily_slots") or cfg.get("times") or ["06:30", "12:30", "18:30"]
        cleaned = sorted(list({str(x).strip() for x in raw if ":" in str(x)}))
        if cleaned:
            return cleaned
    except Exception:
        pass
    return ["06:30", "12:30", "18:30"]


def _get_next_valid_slot_after(ref_epoch):
    """
    Given any timestamp `ref_epoch`, returns the exact next slot (`06:30`, `12:30`, or `18:30` IST)
    that is strictly AFTER `ref_epoch` (by at least 2 minutes).
    """
    IST_TZ = timezone(timedelta(hours=5, minutes=30))
    base_dt = datetime.fromtimestamp(ref_epoch, tz=IST_TZ)
    slots = _get_configured_daily_slots()
    for day_offset in range(0, 365):
        cand_date = (base_dt + timedelta(days=day_offset)).date()
        for hm in slots:
            hh, mm = map(int, hm.split(":")[:2])
            slot_dt = datetime(cand_date.year, cand_date.month, cand_date.day, hh, mm, 0, tzinfo=IST_TZ)
            if slot_dt.timestamp() > (ref_epoch + 120):
                return slot_dt
    return base_dt + timedelta(hours=6)


def _stamp_slot_fields_on_item(item, slot_dt):
    """Writes ALL exact keys used by `calculate_next_available_slot_ist` & `approve_and_schedule_video_item`."""
    item["status"] = "scheduled"
    item["scheduled_slot_key"] = slot_dt.strftime("%Y-%m-%d_%H:%M")
    item["scheduled_iso"] = slot_dt.isoformat()
    item["scheduled_epoch"] = slot_dt.timestamp()
    item["scheduled_for"] = slot_dt.strftime("%Y-%m-%d %H:%M:%S")
    item["date_label"] = slot_dt.strftime("%d %b %Y")
    item["time_label"] = slot_dt.strftime("%I:%M %p")
    item["scheduled_display"] = slot_dt.strftime("%d %b %Y at %I:%M %p IST")
    item["scheduled_full_badge"] = f"{item['date_label']} • {item['time_label']} IST"
    return item


def enforce_smart_cascade_schedule(q_data, force_shift_video_file=None):
    """
    SMART DOMINO CASCADE SCHEDULER (WITH 2-HOUR ACTIVE DUE WINDOW FOR AUTO-POSTER!):
    1) Keeps any video that is currently DUE (`now - 2 hours <= scheduled_epoch <= now`) at its
       exact due timestamp so `_background_master_scheduler_daemon` can publish it to Instagram!
    2) If a video MISSED its slot by more than 2 hours (`scheduled_epoch < now - 7200`),
       OR if `force_shift_video_file` is passed (when an upload attempt fails at slot time),
       OR if two videos have the same duplicate slot,
       it automatically shifts that video to the NEXT upcoming future slot and domino-cascades
       all subsequent scheduled videos forward 1-by-1 (`06:30 -> 12:30 -> 18:30 -> next day 06:30`)!
    """
    IST_TZ = timezone(timedelta(hours=5, minutes=30))
    now_ep = datetime.now(IST_TZ).timestamp()

    ledger_p = "data/posted_ledger.json"
    led_map = {}
    if os.path.exists(ledger_p):
        try:
            led_map = json.load(open(ledger_p, "r", encoding="utf-8"))
        except Exception:
            pass
    for p_item in q_data.get("published_posts", []):
        vf = p_item.get("video_file")
        if vf:
            led_map[vf] = p_item
    try:
        os.makedirs("data", exist_ok=True)
        with open(ledger_p, "w", encoding="utf-8") as lf:
            json.dump(led_map, lf, indent=2, ensure_ascii=False)
    except Exception:
        pass

    pub_files = set(led_map.keys())
    q_data["published_posts"] = list(led_map.values())
    q_data["published_history"] = list(led_map.values())
    sched_list = [s for s in q_data.get("scheduled_posts", []) if s.get("video_file") and s.get("video_file") not in pub_files]
    q_data["unapproved_videos"] = [u for u in q_data.get("unapproved_videos", []) if u.get("video_file") and u.get("video_file") not in pub_files]

    seen_vf = set()
    unique_sched = []
    for s in sched_list:
        vf = s.get("video_file")
        if vf not in seen_vf:
            seen_vf.add(vf)
            unique_sched.append(s)

    with_ts = []
    without_ts = []
    for s in unique_sched:
        ep = _parse_item_slot_epoch(s)
        if ep > 0:
            s["_parsed_ep"] = ep
            with_ts.append(s)
        else:
            without_ts.append(s)

    with_ts.sort(key=lambda x: x["_parsed_ep"])
    ordered_sched = with_ts + without_ts

    # Allow a 2-hour active due window (`now_ep - 7200`) so a post due right now stays due for the Auto-Poster,
    # UNLESS `force_shift_video_file` explicitly requests shifting a failed due post to the next future slot!
    cursor_epoch = now_ep - 7200
    valid_slots = set(_get_configured_daily_slots())

    for item in ordered_sched:
        vf = item.get("video_file")
        item_ep = item.pop("_parsed_ep", 0.0) or _parse_item_slot_epoch(item)

        if force_shift_video_file and vf == force_shift_video_file:
            # This post failed at its due time -> shift it to the next future slot after `now_ep`
            # which automatically pushes cursor_epoch forward and cascades all following videos!
            slot_dt = _get_next_valid_slot_after(max(cursor_epoch, now_ep))
        elif item_ep > cursor_epoch:
            slot_dt = datetime.fromtimestamp(item_ep, tz=IST_TZ)
            hm_str = slot_dt.strftime("%H:%M")
            if hm_str not in valid_slots:
                slot_dt = _get_next_valid_slot_after(max(cursor_epoch, now_ep))
        else:
            # Missed slot (>2 hours old) or duplicate collision with previous video -> cascade to next future slot!
            slot_dt = _get_next_valid_slot_after(max(cursor_epoch, now_ep))

        _stamp_slot_fields_on_item(item, slot_dt)
        cursor_epoch = slot_dt.timestamp()

    q_data["scheduled_posts"] = ordered_sched
    return q_data


def save_scheduled_queue(q_data, sync_cloud=True, allow_unschedule=False):
    """
    RACE-PROOF PERMANENT QUEUE SAVE (v14):
    - Before saving/pushing, merges latest remote GitHub `scheduled_posts` & `published_posts`
      so GitHub Actions video generation runs NEVER revert a Render-scheduled video back to Pending!
    - Only removes a video from `scheduled_posts` when `allow_unschedule=True` (explicit Remove/Delete)
      or when the video has been published!
    """
    global _LOCAL_QUEUE_MODIFIED_TS
    try:
        if sync_cloud and not allow_unschedule and "_fetch_github_json_zero_cache" in globals():
            rem_q = _fetch_github_json_zero_cache(QUEUE_FILE)
            if isinstance(rem_q, dict):
                del_set = set()
                if os.path.exists("data/deleted_ids.json"):
                    try:
                        del_set.update(os.path.basename(str(x)) for x in json.load(open("data/deleted_ids.json", "r", encoding="utf-8")))
                    except Exception:
                        pass

                pub_map = {x.get("video_file"): x for x in (rem_q.get("published_posts") or []) if x.get("video_file")}
                for x in (q_data.get("published_posts") or []):
                    if x.get("video_file"):
                        pub_map[x["video_file"]] = x
                pub_keys = set(pub_map.keys()) | load_posted_ledger()

                # UNION merge of scheduled_posts so scheduled videos NEVER revert to Pending
                sched_map = {}
                for x in (rem_q.get("scheduled_posts") or []):
                    vf = x.get("video_file")
                    if vf and vf not in pub_keys and os.path.basename(vf) not in del_set:
                        sched_map[vf] = x
                for x in (q_data.get("scheduled_posts") or []):
                    vf = x.get("video_file")
                    if vf and vf not in pub_keys and os.path.basename(vf) not in del_set:
                        sched_map[vf] = x
                sched_keys = set(sched_map.keys())

                unapp_map = {}
                for x in (q_data.get("unapproved_videos") or []) + (rem_q.get("unapproved_videos") or []):
                    vf = x.get("video_file")
                    if vf and vf not in pub_keys and vf not in sched_keys and os.path.basename(vf) not in del_set and vf not in unapp_map:
                        unapp_map[vf] = x

                q_data["published_posts"] = list(pub_map.values())[:150]
                q_data["scheduled_posts"] = sorted(sched_map.values(), key=lambda x: float(x.get("scheduled_epoch", 0)))
                q_data["unapproved_videos"] = list(unapp_map.values())
    except Exception as _me:
        print(f"Queue pre-save merge note: {_me}")

    try:
        enforce_smart_cascade_schedule(q_data)
    except Exception as e:
        print(f"Schedule cascade note: {e}")

    q_data["updated_epoch"] = time.time()
    _LOCAL_QUEUE_MODIFIED_TS = q_data["updated_epoch"]
    os.makedirs("data", exist_ok=True)
    tmp_p = QUEUE_FILE + ".tmp"
    with open(tmp_p, "w", encoding="utf-8") as f:
        json.dump(q_data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_p, QUEUE_FILE)
    if sync_cloud and "push_json_to_github_instantly" in globals():
        try:
            push_json_to_github_instantly(QUEUE_FILE, "Sync permanently locked scheduled queue", blocking=True)
        except Exception:
            pass





def _infer_track_and_part_from_filename(fname, meta=None):
    meta = meta or {}
    tid = meta.get("track_id") or ""
    pnum = meta.get("part_number") or 0
    low = str(fname).lower()
    if not tid:
        if "ragda" in low:
            tid = "unit_ragda"
        elif "train" in low or "ustad" in low:
            tid = "training_ustad"
        elif "masti" in low or "comedy" in low:
            tid = "fauji_masti"
        elif "border" in low or "loc" in low:
            tid = "border_duty"
        else:
            tid = "love_meera"
    if not pnum:
        m_p = re.search(r"(?:_p|part_)(\d+)", low)
        if m_p:
            pnum = int(m_p.group(1))
        else:
            pnum = 1
    t_obj = FOJI_UNIVERSE_TRACKS.get(tid, FOJI_UNIVERSE_TRACKS["love_meera"])
    title = meta.get("emotion_name") or f"{t_obj['name']} • Part {pnum}"
    return tid, int(pnum), title


def sync_raw_videos_into_unapproved_queue():
    """
    CLOUD & RENDER SAFE VAULT SYNC:
    - Never wipes `unapproved_videos` when running on Render (where `output/raw_videos` is empty on local disk)!
    - Combines local `output/raw_videos/*.mp4`, `data/cloud_mp4_index.json`, and `data/history.json`
      so EVERY generated video immediately appears in the Frontend Ready Queue & Master Vault!
    """
    q = get_scheduled_queue()
    scheduled_files = {item.get("video_file") for item in q.get("scheduled_posts", []) if item.get("video_file")}
    published_files = {item.get("video_file") for item in q.get("published_posts", []) if item.get("video_file")} | load_posted_ledger() | set(q.get("upload_claimed_files") or [])
    if any(it.get("video_file") in published_files for it in q.get("scheduled_posts", [])):
        q["scheduled_posts"] = [it for it in q.get("scheduled_posts", []) if it.get("video_file") not in published_files]
        save_scheduled_queue(q, sync_cloud=False)

    del_set = set()
    if os.path.exists("data/deleted_ids.json"):
        try:
            del_set.update(str(x) for x in json.load(open("data/deleted_ids.json", "r", encoding="utf-8")))
        except Exception:
            pass

    raw_dir = "output/raw_videos"
    os.makedirs(raw_dir, exist_ok=True)
    valid_mp4s = {
        f for f in os.listdir(raw_dir)
        if f.endswith(".mp4") and os.path.getsize(os.path.join(raw_dir, f)) > 50 * 1024
    }
    if os.path.exists("data/cloud_mp4_index.json"):
        try:
            with open("data/cloud_mp4_index.json", "r", encoding="utf-8") as cf:
                valid_mp4s.update(x for x in json.load(cf) if str(x).endswith(".mp4"))
        except Exception:
            pass

    hist_map = {}
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                hd = json.load(f)
            for h in hd.get("history", []):
                vid_id = h.get("video_id")
                vfile = h.get("video_file") or (f"raw_video_{vid_id}.mp4" if vid_id else "")
                if vfile and vfile.endswith(".mp4"):
                    hist_map[vfile] = h
                    valid_mp4s.add(vfile)
        except Exception:
            pass

    # Also keep all existing unapproved_videos that aren't scheduled/published/deleted
    for item in q.get("unapproved_videos", []):
        vf = item.get("video_file")
        if vf and vf.endswith(".mp4"):
            valid_mp4s.add(vf)

    valid_mp4s = {f for f in valid_mp4s if f not in del_set}

    clean_unapproved = []
    seen_unapproved = set()
    changed = False
    for item in q.get("unapproved_videos", []):
        vf = item.get("video_file")
        if not vf or vf in del_set or vf in scheduled_files or vf in published_files or vf in seen_unapproved:
            changed = True
            continue
        seen_unapproved.add(vf)
        clean_unapproved.append(item)
    q["unapproved_videos"] = clean_unapproved

    def _vid_sort_ts(fname):
        fp = os.path.join(raw_dir, fname)
        if os.path.exists(fp):
            return os.path.getmtime(fp)
        m_dt = re.search(r"_(\d{4})_(\d{6})", fname)
        if m_dt:
            try:
                dt = datetime.strptime(f"2026{m_dt.group(1)}{m_dt.group(2)}", "%Y%m%d%H%M%S").replace(tzinfo=IST)
                return dt.timestamp()
            except Exception:
                pass
        return 0.0

    all_candidate_files = sorted(list(valid_mp4s), key=_vid_sort_ts, reverse=True)

    for fname in all_candidate_files:
        if fname not in scheduled_files and fname not in published_files and fname not in seen_unapproved:
            meta = hist_map.get(fname, {})
            full_p = os.path.join(raw_dir, fname)
            mtime_str = (
                datetime.fromtimestamp(os.path.getmtime(full_p), IST).strftime("%d %b %Y, %I:%M %p")
                if os.path.exists(full_p)
                else (meta.get("completed_at") or meta.get("created_at") or "Ready in Studio")
            )
            inf_tid, inf_pnum, inf_title = _infer_track_and_part_from_filename(fname, meta)
            q["unapproved_videos"].append({
                "id": f"vid_{fname}",
                "video_file": fname,
                "title": inf_title,
                "track_id": inf_tid,
                "part_number": inf_pnum,
                "dialogue": meta.get("dialogue_line_1_hinglish", "Fresh 3D Foji Episode Ready"),
                "shayari": meta.get("shayari_hindi", ""),
                "caption": meta.get("caption", "🎖️ Foji Life 3D Story | Follow @ai_foji_lovelife 🇮🇳🔥 #indianarmy #faujilife"),
                "created_at": meta.get("completed_at") or meta.get("created_at") or mtime_str,
                "status": "awaiting_approval"
            })
            seen_unapproved.add(fname)
            changed = True

    if changed:
        os.makedirs("data", exist_ok=True)
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            json.dump(q, f, indent=2, ensure_ascii=False)
    return q



def format_clean_video_label(fname, track_id="love_meera", part_num=1, idx_num=1):
    """Converts ugly raw_video_1109_023053_p1.mp4 into clean 'Video_09_LoveMeera_Part_01'"""
    s = str(fname or "").replace(".mp4", "")
    if s.startswith("Video_"):
        return s
    slug_map = {
        "love_meera": "LoveMeera",
        "unit_ragda": "UstadRagda",
        "training_ustad": "TrainingDrill",
        "fauji_masti": "BarrackMasti",
        "border_duty": "BorderDuty"
    }
    t_slug = slug_map.get(track_id, "FojiStory")
    m_num = re.search(r"raw_video_(\d+)", s)
    v_num = int(m_num.group(1)) if (m_num and len(m_num.group(1)) <= 3) else idx_num
    return f"Video_{v_num:02d}_{t_slug}_Part_{int(part_num or 1):02d}"


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

    sorted_list = sorted(vault_map.values(), key=_sort_key, reverse=True)
    total_len = len(sorted_list)
    for i, item in enumerate(sorted_list):
        vf = item.get("video_file", "")
        inf_tid, inf_pnum, inf_title = _infer_track_and_part_from_filename(vf, item)
        item["track_id"] = inf_tid
        item["part_number"] = inf_pnum
        v_num = total_len - i
        item["video_number"] = v_num
        item["clean_video_code"] = format_clean_video_label(vf, inf_tid, inf_pnum, v_num)
        # Clean any 'raw_video_...' from title
        raw_t = str(item.get("title") or "")
        if "raw_video" in raw_t.lower() or not raw_t.strip():
            item["title"] = f"{inf_title}"
        # Ensure scheduled items ALWAYS have full Date + Time
        if item.get("vault_status") == "scheduled":
            d_lbl = item.get("date_label") or ""
            t_lbl = item.get("time_label") or ""
            if not d_lbl and item.get("scheduled_epoch"):
                try:
                    dt_s = datetime.fromtimestamp(float(item["scheduled_epoch"]), IST)
                    d_lbl = dt_s.strftime("%d %b %Y")
                    t_lbl = dt_s.strftime("%I:%M %p")
                    item["date_label"] = d_lbl
                    item["time_label"] = t_lbl
                except Exception:
                    pass
            if d_lbl and t_lbl:
                item["scheduled_full_badge"] = f"{d_lbl} • {t_lbl} IST"
            else:
                item["scheduled_full_badge"] = item.get("scheduled_display") or "Scheduled"
    return sorted_list


def calculate_next_available_slot_ist():
    """
    SMART SEQUENTIAL & ALWAYS-AFTER-LAST SLOT CALCULATOR:
    1) Runs `enforce_smart_cascade_schedule(q)` first so any missed slots are cascaded forward.
    2) Finds the LAST scheduled video's timestamp (`max_scheduled_epoch`) in `scheduled_posts`.
    3) Assigns the newly scheduled video to the exact next slot (`06:30`, `12:30`, or `18:30` IST)
       strictly AFTER that last scheduled video!
    """
    q = get_scheduled_queue()
    enforce_smart_cascade_schedule(q)

    now_ep = datetime.now(IST).timestamp()
    max_ep = now_ep
    for item in q.get("scheduled_posts", []):
        if item.get("status") == "scheduled":
            ep = _parse_item_slot_epoch(item)
            if ep > max_ep:
                max_ep = ep

    slot_dt = _get_next_valid_slot_after(max_ep)
    return {
        "slot_key": slot_dt.strftime("%Y-%m-%d_%H:%M"),
        "scheduled_iso": slot_dt.isoformat(),
        "scheduled_epoch": slot_dt.timestamp(),
        "display_time": slot_dt.strftime("%d %b %Y at %I:%M %p IST"),
        "date_label": slot_dt.strftime("%d %b %Y"),
        "time_label": slot_dt.strftime("%I:%M %p")
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

    _sched_vf = target_item.get("video_file", "reel.mp4")
    # Ensure a newly scheduled reel is NOT stuck inside upload_claimed_files
    q["upload_claimed_files"] = [
        x for x in (q.get("upload_claimed_files") or [])
        if os.path.basename(str(x)) != os.path.basename(str(_sched_vf))
    ]
    save_scheduled_queue(q, sync_cloud=False)
    push_json_to_github_instantly(
        SCHEDULED_QUEUE_FILE,
        f"Scheduled {_sched_vf} -> {slot_info['display_time']} [skip render] [skip ci]",
        blocking=True
    )

    # Non-blocking notification
    def _bg_sched_notif():
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
    __import__("threading").Thread(target=_bg_sched_notif, daemon=True).start()

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
    """
    RACE-FREE RENDER <-> GITHUB STATE SYNC (v12):
    - Respects 25-second `_LOCAL_QUEUE_MODIFIED_TS` lock so local Schedule/Delete actions
      NEVER get overwritten by a slightly delayed GitHub CDN read!
    - Always absorbs brand-new cloud videos into Pending Review without ever pulling
      already-scheduled or deleted videos back into Pending!
    """
    global _LAST_CLOUD_PULL_TS
    if (time.time() - _LAST_CLOUD_PULL_TS) < 3.0:
        return
    _LAST_CLOUD_PULL_TS = time.time()

    sync_files = [
        "data/live_telemetry.json",
        "data/cloud_mp4_index.json",
        "data/scheduled_queue.json",
        "data/posted_ledger.json",
        "data/notifications.json",
        "data/history.json",
        "data/episode_tracker.json",
    ]
    local_q_age = time.time() - float(globals().get("_LOCAL_QUEUE_MODIFIED_TS", 0) or 0)

    del_set = set()
    if os.path.exists("data/deleted_ids.json"):
        try:
            del_set.update(os.path.basename(str(x)) for x in json.load(open("data/deleted_ids.json", "r", encoding="utf-8")))
        except Exception:
            pass

    for rel_json in sync_files:
        if rel_json == "data/scheduled_queue.json" and local_q_age < 25:
            continue
        remote_data = _fetch_github_json_zero_cache(rel_json)
        if remote_data is None:
            continue
        local_p = os.path.abspath(rel_json)
        os.makedirs(os.path.dirname(local_p), exist_ok=True)
        should_write = True

        if rel_json == "data/live_telemetry.json" and os.path.exists(local_p):
            try:
                loc_t = json.load(open(local_p, "r", encoding="utf-8"))
                loc_ep = float(loc_t.get("epoch", 0))
                rem_ep = float(remote_data.get("epoch", 0))
                rem_st = str(remote_data.get("status", "")).lower()
                if rem_ep < loc_ep and rem_st not in ("completed", "error"):
                    should_write = False
            except Exception:
                pass

        elif rel_json == "data/cloud_mp4_index.json" and isinstance(remote_data, list):
            try:
                loc_l = json.load(open(local_p, "r", encoding="utf-8")) if os.path.exists(local_p) else []
                if isinstance(loc_l, list):
                    merged_l = list(loc_l)
                    for fn in remote_data:
                        if fn and fn not in merged_l and os.path.basename(str(fn)) not in del_set:
                            merged_l.append(fn)
                    remote_data = merged_l[-200:]
            except Exception:
                pass

        elif rel_json == "data/posted_ledger.json" and isinstance(remote_data, dict):
            try:
                loc_d = json.load(open(local_p, "r", encoding="utf-8")) if os.path.exists(local_p) else {}
                if isinstance(loc_d, dict):
                    merged_d = dict(loc_d)
                    merged_d.update(remote_data)
                    remote_data = merged_d
            except Exception:
                pass

        elif rel_json == "data/scheduled_queue.json" and isinstance(remote_data, dict):
            try:
                if os.path.exists(local_p):
                    loc_q = json.load(open(local_p, "r", encoding="utf-8"))
                    loc_ep = float(loc_q.get("updated_epoch", 0) or 0)
                    rem_ep = float(remote_data.get("updated_epoch", 0) or 0)

                    loc_pub = {x.get("video_file"): x for x in (loc_q.get("published_posts") or []) if x.get("video_file")}
                    rem_pub = {x.get("video_file"): x for x in (remote_data.get("published_posts") or []) if x.get("video_file")}
                    merged_pub = dict(loc_pub)
                    merged_pub.update(rem_pub)
                    pub_keys = set(merged_pub.keys()) | load_posted_ledger()

                    # Scheduled items ALWAYS win over unapproved_videos (a scheduled video NEVER reverts to pending!)
                    loc_sched = {x.get("video_file"): x for x in (loc_q.get("scheduled_posts") or []) if x.get("video_file")}
                    rem_sched = {x.get("video_file"): x for x in (remote_data.get("scheduled_posts") or []) if x.get("video_file")}
                    if loc_ep >= rem_ep:
                        merged_sched = dict(rem_sched)
                        merged_sched.update(loc_sched)
                    else:
                        merged_sched = dict(loc_sched)
                        merged_sched.update(rem_sched)
                    merged_sched = {k: v for k, v in merged_sched.items() if k not in pub_keys and os.path.basename(k) not in del_set}
                    sched_keys = set(merged_sched.keys())

                    merged_unapp = {}
                    for it in (remote_data.get("unapproved_videos") or []) + (loc_q.get("unapproved_videos") or []):
                        vf = it.get("video_file")
                        if vf and vf not in pub_keys and vf not in sched_keys and os.path.basename(vf) not in del_set and vf not in merged_unapp:
                            merged_unapp[vf] = it

                    remote_data["published_posts"] = list(merged_pub.values())[:150]
                    remote_data["scheduled_posts"] = sorted(
                        merged_sched.values(),
                        key=lambda x: float(x.get("scheduled_epoch", 0))
                    )
                    remote_data["unapproved_videos"] = list(merged_unapp.values())
                    remote_data["updated_epoch"] = max(loc_ep, rem_ep)
            except Exception:
                pass

        if should_write:
            try:
                tmp_p = local_p + ".tmp"
                with open(tmp_p, "w", encoding="utf-8") as wf:
                    json.dump(remote_data, wf, indent=2, ensure_ascii=False)
                os.replace(tmp_p, local_p)
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

    vault_items = build_master_all_reels_vault()
    if not raw_videos and vault_items:
        raw_videos = [v.get("video_file") for v in vault_items if v.get("video_file")]

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
    1. On Laptop: Copies MP4 to `D:\foji_ai_automation/Posted_YouTube_Archive/`
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



POSTED_LEDGER_FILE = "data/posted_ledger.json"

def load_posted_ledger():
    if os.path.exists(POSTED_LEDGER_FILE):
        try:
            data = json.load(open(POSTED_LEDGER_FILE, "r", encoding="utf-8"))
            if isinstance(data, dict):
                return set(os.path.basename(str(k)) for k in data.keys() if k)
            if isinstance(data, list):
                return set(os.path.basename(str(x)) for x in data if x)
        except Exception:
            pass
    return set()


def record_video_permanently_posted(video_file, caption="", permalink="", media_pk=""):
    vf = os.path.basename(str(video_file or "").strip())
    if not vf:
        return False

    os.makedirs("data", exist_ok=True)
    ledger_dict = {}
    if os.path.exists(POSTED_LEDGER_FILE):
        try:
            raw_d = json.load(open(POSTED_LEDGER_FILE, "r", encoding="utf-8"))
            if isinstance(raw_d, dict):
                ledger_dict = raw_d
            elif isinstance(raw_d, list):
                ledger_dict = {
                    os.path.basename(str(x)): {"video_file": os.path.basename(str(x)), "status": "published"}
                    for x in raw_d if x
                }
        except Exception:
            ledger_dict = {}

    ledger_dict[vf] = {
        "video_file": vf,
        "status": "published",
        "published_at": datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"),
        "permalink": permalink or "",
        "media_pk": str(media_pk or "")
    }
    with open(POSTED_LEDGER_FILE, "w", encoding="utf-8") as lf:
        json.dump(ledger_dict, lf, indent=2)

    q = get_scheduled_queue()
    removed_item = None
    new_sched = []
    for it in q.get("scheduled_posts", []):
        if os.path.basename(str(it.get("video_file") or "")) == vf:
            removed_item = it
        else:
            new_sched.append(it)
    q["scheduled_posts"] = new_sched

    new_unapp = []
    for it in q.get("unapproved_videos", []):
        if os.path.basename(str(it.get("video_file") or "")) == vf:
            removed_item = removed_item or it
        else:
            new_unapp.append(it)
    q["unapproved_videos"] = new_unapp

    claimed = list(q.get("upload_claimed_files") or [])
    if vf not in claimed:
        claimed.append(vf)
    q["upload_claimed_files"] = claimed

    pub_list = q.get("published_posts", [])
    if not any(os.path.basename(str(p.get("video_file") or "")) == vf for p in pub_list):
        pub_entry = dict(removed_item or {})
        pub_entry.update({
            "video_file": vf,
            "caption": caption or (removed_item.get("caption", "") if removed_item else ""),
            "status": "published",
            "published_at": datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"),
            "permalink": permalink or pub_entry.get("permalink", ""),
            "media_pk": str(media_pk or pub_entry.get("media_pk", ""))
        })
        pub_list.insert(0, pub_entry)
        q["published_posts"] = pub_list[:150]

    save_scheduled_queue(q, sync_cloud=False)

    if os.environ.get("RENDER") != "true" and os.environ.get("GITHUB_ACTIONS") != "true":
        for src_dir in ("output/raw_videos", "output/final_reels"):
            src_p = os.path.join(src_dir, vf)
            if os.path.exists(src_p):
                try:
                    os.makedirs("archive_posted_reels", exist_ok=True)
                    dst_p = os.path.join("archive_posted_reels", vf)
                    if not os.path.exists(dst_p):
                        shutil.copy2(src_p, dst_p)
                except Exception:
                    pass

    try:
        push_json_to_github_instantly(POSTED_LEDGER_FILE, f"Lock posted ledger {vf} [skip render] [skip ci]", blocking=True)
        push_json_to_github_instantly("data/scheduled_queue.json", f"Lock posted queue {vf} [skip render] [skip ci]", blocking=True)
    except Exception:
        try:
            import gemini_bot as _gb
            _gb.sync_file_to_github(POSTED_LEDGER_FILE, f"Lock posted ledger {vf} [skip render] [skip ci]")
            _gb.sync_file_to_github("data/scheduled_queue.json", f"Lock posted queue {vf} [skip render] [skip ci]")
        except Exception:
            pass
    return True





def prune_old_posted_mp4s_keep_repo_light(max_age_days=7):
    """
    LIFETIME STORAGE GUARD:
    Deletes raw MP4s from `output/raw_videos/` ONLY if they are ALREADY locked in
    `posted_ledger.json` AND older than `max_age_days` (keeping laptop `archive_posted_reels/` untouched).
    """
    try:
        ledger = load_posted_ledger()
        if not ledger:
            return 0
        raw_dir = "output/raw_videos"
        if not os.path.isdir(raw_dir):
            return 0
        cutoff = time.time() - (max_age_days * 86400)
        removed = 0
        for fn in os.listdir(raw_dir):
            if fn.endswith(".mp4") and fn in ledger:
                fp = os.path.join(raw_dir, fn)
                if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                    if os.environ.get("RENDER") != "true" and os.environ.get("GITHUB_ACTIONS") != "true":
                        os.makedirs("archive_posted_reels", exist_ok=True)
                        dst = os.path.join("archive_posted_reels", fn)
                        if not os.path.exists(dst):
                            shutil.copy2(fp, dst)
                    os.remove(fp)
                    removed += 1
        return removed
    except Exception:
        return 0



# =========================================================================
# v12 EXPANDED REAL-LIFE FAUJI CATEGORIES + DAILY LIVE VIRAL TREND RADAR
# =========================================================================
_EXTRA_REAL_LIFE_TRACKS = {
    "chhutti_ghar_wapsi": {
        "id": "chhutti_ghar_wapsi",
        "name": "Chhutti, Maa-Baap & Ghar Ki Yaadein",
        "badge": "Real Family & Leave Emotion",
        "characters": ["Young Soldier Makra", "Mother (Maa)", "Father (Bapu)", "Fojan Meera"],
        "theme_brief": "Deeply real, goosebumps Indian Army leave reality: stepping off village bus at dawn with heavy iron trunk, touching mother's feet in courtyard, father's silent proud misty eyes, homemade bajra roti & ghee, packing bag again with heavy heart when leave ends. Authentic village courtyard & rustic morning light. STRICT BAN: Zero snow mountains."
    },
    "fauji_dosti_barracks": {
        "id": "fauji_dosti_barracks",
        "name": "Fauji Dosti & Barracks Ki Asli Zindagi",
        "badge": "True Soldier Brotherhood",
        "characters": ["Young Soldier Makra", "Best Fauji Buddy (Raju/Sonu)", "Barracks Roommates"],
        "theme_brief": "Raw, authentic Indian Army barracks brotherhood: sharing last hot chai & paratha after exhausting night guard, helping an injured buddy polish boots before inspection, late-night quiet heart-to-heart on iron bunk beds, unbreakable dosti across Haryana/UP/Punjab/Rajasthan jawans. Warm tungsten barracks realism. STRICT BAN: Zero snow mountains."
    },
    "border_night_reality": {
        "id": "border_night_reality",
        "name": "LOC Border Raat Ki Asli Pehredari",
        "badge": "Real Border Night Grit",
        "characters": ["Young Soldier Makra", "Senior Post Commander", "Sentry Partner"],
        "theme_brief": "Gritty true-to-life border outpost reality: silent 2 AM watchtower duty in rain/mist, crackling wireless walkie-talkie check, clutching rifle with steady eyes while the whole nation sleeps peacefully, holding family photo for 2 seconds inside pocket then saluting duty. Realistic cinematic night lighting."
    },
    "civil_vs_fauji": {
        "id": "civil_vs_fauji",
        "name": "Civil Duniya vs Fauji Asli Hakikat",
        "badge": "Real Hakikat Contrast",
        "characters": ["Young Soldier Makra", "Civilian Friend / Crowd", "Unit Jawans"],
        "theme_brief": "Hard-hitting, super-viral realistic contrast: civilian friends complaining about Wi-Fi or traffic vs Makra smiling through 45C desert dust storm, muddy monsoon trench, or 3 AM sudden alarm fall-in. Honest raw hakikat dialogues that hit straight to the heart and spark massive shares. STRICT BAN: Zero snow mountains."
    },
    "video_call_network": {
        "id": "video_call_network",
        "name": "1-Bar Network & Fauji Video Call",
        "badge": "Real Signal Struggle & Love",
        "characters": ["Young Soldier Makra", "Fojan Meera on Video Call"],
        "theme_brief": "Ultra-relatable real Fauji life: climbing a rocky mound or tin shed roof in evening wind searching for 1 bar of mobile network just to see Meera's face for 20 seconds, pixelating screen, hilarious yet melting Haryanvi love banter before 'Reconnecting...' cuts the call. Authentic dusk sky realism. STRICT BAN: Zero snow mountains."
    },
    "festival_on_duty": {
        "id": "festival_on_duty",
        "name": "Tyohar Duty Par (Diwali, Holi & Rakhi)",
        "badge": "Festivals Away From Home",
        "characters": ["Young Soldier Makra", "Unit Brothers", "Family on Phone"],
        "theme_brief": "Heart-touching real Army festival life: lighting two small clay diyas on sandbags at the unit gate on Diwali night, applying gulal on dusty uniform with batchmates on Holi, tying sister's posted Rakhi on wrist while on sentry duty, smiling through tears with proud desi spirit. STRICT BAN: Zero snow mountains."
    },
    "fauji_safar_train": {
        "id": "fauji_safar_train",
        "name": "Fauji Safar: Train, Trunk & Posting",
        "badge": "Real Railway Journey & Respect",
        "characters": ["Young Soldier Makra", "Fojan Meera / Fellow Train Passengers"],
        "theme_brief": "Authentic Indian Railway sleeper-coach journey of a soldier returning to posting: blue painted Fauji iron trunk under seat, kulhad chai at golden-hour station halt, elderly passenger/kid saluting Makra with pure respect, train whistle goodbye as village fields fly past window. Realistic Indian railway atmosphere. STRICT BAN: Zero snow mountains."
    }
}

try:
    _sample_tr = next(iter(FOJI_UNIVERSE_TRACKS.values()))
    for _tk_new, _tv_new in _EXTRA_REAL_LIFE_TRACKS.items():
        if _tk_new not in FOJI_UNIVERSE_TRACKS:
            _m_tr = dict(_sample_tr)
            _m_tr.update(_tv_new)
            FOJI_UNIVERSE_TRACKS[_tk_new] = _m_tr
        if _tk_new not in TRACK_ORDER:
            TRACK_ORDER.append(_tk_new)
except Exception as _tr_err:
    print(f"⚠️ Extra real tracks init note: {_tr_err}")

_ORIG_GET_EP_TRACKER = get_episode_tracker


def get_episode_tracker():
    tr = _ORIG_GET_EP_TRACKER()
    changed = False
    for tk in FOJI_UNIVERSE_TRACKS:
        if tk not in tr:
            tr[tk] = {"completed_part": 0, "next_part": 1}
            changed = True
    if changed:
        try:
            with open(EPISODE_TRACKER_FILE, "w", encoding="utf-8") as wf:
                json.dump(tr, wf, indent=2, ensure_ascii=False)
        except Exception:
            pass
    return tr


USED_STORY_HOOKS_FILE = "data/used_story_hooks.json"
DAILY_VIRAL_TRENDS_FILE = "data/daily_viral_trends.json"

_REALISTIC_VISUAL_ANGLES = [
    "Handheld documentary-style close-up with natural golden sunrise dust motes and real sweat texture",
    "Over-the-shoulder candid shot inside an authentic dimly lit Indian Army barracks room",
    "Rain-soaked railway station platform at dusk with warm sodium-lamp reflections and steam",
    "Harsh midday 45C dusty ground shimmer with crisp shadows and gritty documentary realism",
    "Warm kerosene-lamp / village courtyard evening glow with realistic earthen walls and brass utensils",
    "Silent 2 AM outpost watchtower with flashlight beam cutting through real monsoon mist",
    "Bustling army mess hall clinking steel plates, rising steam from dal-roti, candid comic framing",
    "Windy hilltop sunset silhouette holding phone high for 1-bar mobile signal",
    "Crowded Indian sleeper train doorway looking out at green mustard fields rushing past",
    "Quiet dawn verandah of a Haryana village home with charpai, steaming steel glass chai, and sparrows",
    "Muddy obstacle-course ground level low-angle tracking shot showing raw boots & grit",
    "Sandbag bunker corner lit by two glowing clay diyas under a deep starry night sky"
]

_VIRAL_STORY_TWISTS = [
    "A sudden unexpected phone call changes the entire mood in the last 3 seconds",
    "Starts like comedy/banter, flips into a raw goosebumps truth that makes viewers hit Share",
    "Silent unspoken sacrifice that nobody notices except one close buddy or mother",
    "A funny white lie Makra tells his family on call so they never worry about his tough duty",
    "Savage Haryanvi witty comeback that shuts down a strict Havildar/civilian brag",
    "Hidden handwritten note or small gift discovered inside the iron Fauji trunk",
    "Unexpected respect from a stranger child or elder that melts away all exhaustion",
    "A 3-second shocking opening visual hook followed by a deeply relatable real-life punchline",
    "Friendly barracks bet that goes hilariously wrong right when the Senior Ustad walks in",
    "Comparing a luxury civilian moment with raw Fauji pride without ever complaining",
    "Caught sneaking extra chai/food or hiding a phone, saved by a clever last-second excuse",
    "Counting down days to chhutti when sudden emergency duty cancels the train ticket"
]


def _fetch_daily_viral_army_trends():
    """
    LIVE DAILY VIRAL TREND RADAR (FREE & FAST):
    Scans today's fresh Indian Army / Fauji / Agniveer / Viral Reels pulse once every 6 hours
    so every daily script pitches fresh, relevant, high-retention viral hooks!
    """
    try:
        if os.path.exists(DAILY_VIRAL_TRENDS_FILE):
            cached = json.load(open(DAILY_VIRAL_TRENDS_FILE, "r", encoding="utf-8"))
            if (time.time() - float(cached.get("ts", 0))) < 6 * 3600 and cached.get("trends"):
                return cached["trends"]
    except Exception:
        pass

    trends = []
    rss_urls = [
        "https://news.google.com/rss/search?q=Indian+Army+viral+video+OR+fauji+reels+OR+agniveer+story&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=Indian+Army+soldier+emotional+OR+training+viral&hl=en-IN&gl=IN&ceid=IN:en",
    ]
    for u in rss_urls:
        try:
            r = requests.get(u, timeout=4.0, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and "<title>" in r.text:
                titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", r.text)
                for t1, t2 in titles[1:6]:
                    clean_t = re.sub(r"\s+-\s+[^-]+$", "", (t1 or t2 or "").strip())
                    if len(clean_t) > 15 and clean_t not in trends:
                        trends.append(clean_t[:110])
        except Exception:
            pass
        if len(trends) >= 5:
            break

    if not trends:
        trends = [
            "Real Fauji life behind the uniform — raw 4 AM grit vs silent smile",
            "Agniveer & young soldier emotional salary/homecoming truth",
            "Hilarious barracks banter & strict Ustad comedy with Haryanvi punch",
            "Fauji long-distance love & 1-bar signal video call struggle"
        ]

    try:
        os.makedirs("data", exist_ok=True)
        with open(DAILY_VIRAL_TRENDS_FILE, "w", encoding="utf-8") as wf:
            json.dump({"ts": time.time(), "date": datetime.now(IST).strftime("%Y-%m-%d"), "trends": trends[:6]}, wf, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return trends[:6]


def _load_used_story_hooks():
    try:
        rem = _fetch_github_json_zero_cache(USED_STORY_HOOKS_FILE)
        if isinstance(rem, list):
            os.makedirs("data", exist_ok=True)
            with open(USED_STORY_HOOKS_FILE, "w", encoding="utf-8") as wf:
                json.dump(rem[-100:], wf, indent=2, ensure_ascii=False)
            return rem[-100:]
    except Exception:
        pass
    if os.path.exists(USED_STORY_HOOKS_FILE):
        try:
            d = json.load(open(USED_STORY_HOOKS_FILE, "r", encoding="utf-8"))
            if isinstance(d, list):
                return d[-100:]
        except Exception:
            pass
    return []


def _record_used_story_hook(pkg):
    try:
        hooks = _load_used_story_hooks()
        entry = {
            "ts": datetime.now(IST).strftime("%Y-%m-%d %H:%M"),
            "track": pkg.get("track_id", ""),
            "title": str(pkg.get("emotion_name") or "")[:90],
            "loc": str(pkg.get("new_location") or "")[:90],
            "d1": str(pkg.get("dialogue_line_1_hinglish") or "")[:120],
            "d2": str(pkg.get("dialogue_line_2_hinglish") or "")[:120],
        }
        hooks.append(entry)
        os.makedirs("data", exist_ok=True)
        with open(USED_STORY_HOOKS_FILE, "w", encoding="utf-8") as wf:
            json.dump(hooks[-100:], wf, indent=2, ensure_ascii=False)
        try:
            import gemini_bot as _gb_h
            _gb_h.sync_file_to_github(USED_STORY_HOOKS_FILE, "Record fresh story hook anti-repeat [skip render] [skip ci]")
        except Exception:
            pass
    except Exception:
        pass


_ORIG_BUILD_REAL_FOJI_PKG = build_real_foji_universe_package


def build_real_foji_universe_package(video_id=1, force_track_id=None, custom_idea="", is_preview=False):
    import random as _rnd_s
    enhanced_idea = (custom_idea or "").strip()
    if not is_preview:
        used_hooks = _load_used_story_hooks()
        recent_bans = [
            f"[{h.get('track','')}] {h.get('title','')} | {h.get('loc','')} | \"{h.get('d1','')}\""
            for h in used_hooks[-20:]
            if h.get("d1") or h.get("title")
        ]
        trends = _fetch_daily_viral_army_trends()
        chosen_trend = _rnd_s.choice(trends) if trends else "Authentic Indian Army real-life emotion"
        chosen_angle = _rnd_s.choice(_REALISTIC_VISUAL_ANGLES)
        chosen_twist = _rnd_s.choice(_VIRAL_STORY_TWISTS)
        uniq_nonce = datetime.now(IST).strftime("%d%b-%H%M%S")

        fresh_directive = (
            f"REAL-LIFE VIRAL STORY MANDATE ({uniq_nonce}): "
            f"Today's Viral Pulse to pitch & outperform: '{chosen_trend}'. "
            f"Visual Realism & Camera Style: {chosen_angle}. "
            f"Story Twist: {chosen_twist}. "
            f"MAKE IT 100% REALISTIC HAKIKAT (authentic everyday Indian Army/village truth, real body language, natural lighting, "
            f"sharp memorable Hindi/Haryanvi dialogues — NEVER generic cartoon tropes, NEVER repeat past scenes or dialogues!)."
        )
        if recent_bans:
            fresh_directive += " STRICTLY BANNED PAST STORIES (DO NOT REUSE): " + " ; ".join(recent_bans[-10:])
        enhanced_idea = f"{enhanced_idea} | {fresh_directive}" if enhanced_idea else fresh_directive

    pkg = _ORIG_BUILD_REAL_FOJI_PKG(
        video_id=video_id,
        force_track_id=force_track_id,
        custom_idea=enhanced_idea,
        is_preview=is_preview
    )
    if not is_preview and isinstance(pkg, dict):
        _record_used_story_hook(pkg)
    return pkg


# === v14 GUARANTEED SOLO MALE SOLDIER CAST GUARD ===
_V14_SOLO_CAST_ENFORCED = True
_V14_COUPLE_TRACKS = {"love_meera", "video_call_network"}
_V14_PREV_BUILD_PKG = build_real_foji_universe_package


def build_real_foji_universe_package(video_id=1, force_track_id=None, custom_idea="", is_preview=False):
    pkg = _V14_PREV_BUILD_PKG(
        video_id=video_id,
        force_track_id=force_track_id,
        custom_idea=custom_idea,
        is_preview=is_preview
    )
    if isinstance(pkg, dict):
        tk = str(pkg.get("track_id") or "").strip().lower()
        idea_low = str(custom_idea or "").lower()
        scene_low = (
            str(pkg.get("gemini_video_prompt") or "") + " " +
            str(pkg.get("dialogue_line_1_hinglish") or "") + " " +
            str(pkg.get("dialogue_line_2_hinglish") or "")
        ).lower()
        explicit_couple = (
            tk in _V14_COUPLE_TRACKS
            or any(w in idea_low for w in ("meera", "fojan", "girlfriend", "wife", "couple", "love story", "gulgule", "jalebi"))
        )
        if not explicit_couple:
            if not any(w in scene_low for w in ("fojan meera", "wife meera", "girlfriend meera", "meera smiles", "meera holds")):
                pkg["include_meera"] = False
    return pkg
