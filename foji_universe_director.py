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

FOJI_UNIVERSE_TRACKS = {
    "love_meera": {
        "id": "love_meera",
        "name": "❤️ Foji & Fojan Emotional Love & Nok-Jhok",
        "badge": "Romantic & Desi Nok-Jhok Series",
        "characters": ["Young Haryanvi Agniveer Soldier", "His Devoted Fojan (Jaan / Kuchu Puchu / Laado)"],
        "theme_brief": (
            "Heart-touching and cute relatable romance, teasing nok-jhok, emotional separation, and surprise homecoming "
            "between a young Indian Army soldier and his beloved Fojan. Include authentic fauji chutti surprises, "
            "late-night bunker video calls with cute nicknames ('Jaan', 'Kuchu Puchu', 'Bawli', 'Laado', 'Gulgule', 'Fauji Sahab'), "
            "railway station platform hugs, karwa chauth/diwali waiting, and pride in the uniform. (STRICT BAN: NEVER include paper letters/chitthi!)."
        )
    },
    "training_ustad": {
        "id": "training_ustad",
        "name": "⚔️ Agniveer Training Center & Drill Reality",
        "badge": "High-Energy Academy Series",
        "characters": ["Young Recruit", "Strict Moustached Haryanvi Drill Ustad", "Unit Coursemates"],
        "theme_brief": (
            "Hard-hitting reality of Indian Army training academy life: 4 AM whistle sprint, obstacle course wall jump, "
            "firing range bullseye, chest-high mud crawl under barbed wire, rifle drill inspection, and raw goosebump dialogues "
            "that turn a village boy into a steel-hearted commando."
        )
    },
    "unit_ragda": {
        "id": "unit_ragda",
        "name": "🔥 Ustad Ka Ragda & Fauji Attitude",
        "badge": "Viral Fauji Ragda Series",
        "characters": ["Young Soldier", "Strict Drill Ustad", "Funny Unit Brother"],
        "theme_brief": (
            "Authentic Indian Army 'Ragda' (tough disciplinary physical punishment with Haryanvi swagger and brotherhood): "
            "frog jumps with full 25kg pithu bag, elbows bleeding in parade ground gravel, pushups in pouring rain, "
            "and Ustad's thunderous Haryanvi/Desi reality dialogues about Fauj discipline."
        )
    },
    "fauji_masti": {
        "id": "fauji_masti",
        "name": "😂 Barrack Masti, Mess & Fauji Yaari",
        "badge": "Desi Fauji Comedy Series",
        "characters": ["Young Soldier", "Desi Unit Brothers", "Strict Mess Havildar"],
        "theme_brief": (
            "Hilarious and viral barrack comedy: stealing hot gulab jamun from the army mess, zero-trim fauji haircut prank, "
            "bada khana bhangra/haryanvi dance, hiding smartphone under pillow during Ustad's surprise night raid, "
            "and unbreakable brotherhood."
        )
    },
    "border_duty": {
        "id": "border_duty",
        "name": "🏔️ LOC Border Reality, Maa Ka Pyar & Tiranga",
        "badge": "Goosebumps Patriotic Series",
        "characters": ["Soldier at Snowy LOC Bunker", "Unit Buddy / Commander", "Maa on Call"],
        "theme_brief": (
            "Goosebump-inducing reality of -25°C Siachen/Jammu LOC border duty: frozen eyelashes in blizzard, "
            "warming hands over steel mug of garam chai with rifle strapped to chest, emotional call with Maa back in village, "
            "and fearless Haryanvi/Fauji shayari protecting the Tiranga."
        )
    },
    "viral_trend": {
        "id": "viral_trend",
        "name": "🚀 Trending Viral Fauji & Desi Reality Specials",
        "badge": "Standalone Viral Trend Engine",
        "characters": ["Indian Army Soldier", "Dynamic Co-Star (Ustad / Unit Buddy / Fojan / Villager)"],
        "theme_brief": (
            "Standalone, ultra-viral high-retention reels engineered around current Instagram/YouTube Shorts trends! "
            "Not bound to slow story buildup — instant 2-second hook! Themes rotate across: Civilian vs Fauji Reality contrast, "
            "Haryanvi Attitude & Shayari in Uniform, Cute 'Kuchu Puchu / Jaan' Video Call Comedy, Sudden Uniform Surprise in Village Market, "
            "4 AM Ground Runner Motivation, and Spine-Chilling Border Warning to Enemies."
        )
    }
}

TRACK_ORDER = ["viral_trend", "love_meera", "unit_ragda", "training_ustad", "fauji_masti", "border_duty"]

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
    """Non-blocking background GitHub state sync with `[skip render] [skip ci]` so Render NEVER burns build minutes!"""
    import threading as _th
    safe_msg = str(commit_msg or "Sync studio state").strip()
    if "[skip render]" not in safe_msg.lower():
        safe_msg = f"{safe_msg} [skip render] [skip ci]"
    def _bg_push():
        gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN") or "").strip()
        repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
        rel_clean = rel_path.replace("\\", "/")
        full_p = os.path.abspath(rel_path)
        if not gh_pat or not os.path.exists(full_p):
            return False
        with _GH_PUSH_LOCK:
            for _attempt in range(2):
                try:
                    with open(full_p, "rb") as f:
                        b64_content = _b64.b64encode(f.read()).decode("utf-8")
                    url = f"https://api.github.com/repos/{repo}/contents/{rel_clean}"
                    headers = {"Authorization": f"Bearer {gh_pat}", "Accept": "application/vnd.github+json"}
                    r = requests.get(f"{url}?ref=main&t={int(time.time()*1000)}", headers=headers, timeout=8)
                    sha = r.json().get("sha") if r.status_code == 200 else None
                    payload = {"message": safe_msg, "content": b64_content, "branch": "main"}
                    if sha:
                        payload["sha"] = sha
                    put_r = requests.put(url, headers=headers, json=payload, timeout=12)
                    if put_r.status_code in (200, 201):
                        return True
                    time.sleep(0.5)
                except Exception:
                    time.sleep(0.5)
        return False

    if blocking:
        return _bg_push()
    _th.Thread(target=_bg_push, daemon=True).start()
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


def _call_pure_gemini_api_writer(track_id, track, ep_num, continuity_context, used_dialogues, custom_idea=""):
    all_keys = _get_all_live_gemini_api_keys()
    if not all_keys:
        raise RuntimeError("No API key found in .env! Please check your .env file.")

    avoid_sample = " | ".join([d for d in used_dialogues[-22:] if d])
    user_direction = f"\nDIRECTOR SPECIAL VIRAL CONCEPT: {custom_idea}\n" if custom_idea.strip() else ""
    unique_nonce = f"{int(time.time()*1000)}-p{ep_num}"

    dress_idx = (ep_num + len(used_dialogues)) % len(MEERA_WARDROBE_CATALOG)
    assigned_meera_dress = MEERA_WARDROBE_CATALOG[dress_idx]

    solo_army_tracks = {"training_ustad", "unit_ragda", "fauji_masti", "border_duty"}
    if track_id == "viral_trend":
        # Viral trend alternates dynamically between solo reality army trends & cute couple trends!
        default_needs_meera = (ep_num % 2 == 0)
    else:
        default_needs_meera = (track_id not in solo_army_tracks)

    weekday_idx = datetime.now(IST).weekday()
    daily_tags = globals().get("DAILY_VIRAL_HASHTAGS", {}).get(
        weekday_idx,
        "#indianarmy #faujilife #haryanvishayari #agniveer #fojifojan #armyreels #viralreels"
    )

    # Rotate fresh viral angles so the AI never repeats boring templates
    viral_angles = [
        "RAW REALITY OF FAUJ + GOOSEBUMP HARYANVI SHAYARI: Hard-hitting contrast between comfortable civilian life and a soldier's extreme sacrifice, ending with a thunderous Haryanvi shayari punchline.",
        "CUTE 'KUCHU PUCHU / JAAN / BAWLI' NOK-JHOK & ROMANCE: Playful, ultra-relatable teasing or emotional reassurance on a bunker video call or sudden homecoming without ever sounding robotic.",
        "HIGH-ADRENALINE USTAD RAGDA & DESI ATTITUDE: Mud, rain, heavy pithu sprint, and a legendary desi dialogue that gives every army aspirant goosebumps.",
        "BROTHERHOOD & BARRACK COMEDY PUNCH: Fast-paced visual slapstick in the mess/barrack with a savage witty Haryanvi comeback.",
        "EMOTIONAL MAA / HOME CALL AT FREEZING BORDER: Raw emotion in -25°C blizzard with soulful background folk song and patriotic pride."
    ]
    chosen_viral_angle = viral_angles[(ep_num + int(time.time() // 300)) % len(viral_angles)]

    system_prompt = f"""You are India's #1 Viral Reels Showrunner, Haryanvi Shayar & 3D Cinema Director for 'Foji AI Studio' (Seed: {unique_nonce}).

TRACK: {track['name']} ({track['badge']})
TRACK BRIEF: {track['theme_brief']}
VIRAL ANGLE FOR THIS REEL: {chosen_viral_angle}
EPISODE / REEL NUMBER: {"Standalone Viral Trend Special #" + str(ep_num) if track_id == "viral_trend" else "Part #" + str(ep_num)}
INCLUDE FOJAN (LOVE INTEREST) IN SCENE: {"YES (Soldier + His Fojan)" if default_needs_meera else "NO (Pure Army Scene: Soldier + Ustad / Unit Brothers)"}
IF FOJAN APPEARS, HER MANDATORY NEW OUTFIT: "{assigned_meera_dress}"

PAST CONTEXT (Do NOT repeat):
{continuity_context}
{user_direction}
STRICT VIRAL & QUALITY RULES (FOLLOW 100%):
1. ZERO FORCED CHARACTER NAMES IN DIALOGUE: Do NOT keep saying 'Makra' or 'Meera' in dialogues!
   - When talking to his beloved Fojan (or when she talks to him), use natural, viral affectionate pet-names like: "Jaan", "Meri Kuchu Puchu", "Bawli", "Laado", "Meri Fojan", "Gulgule", "Fauji Sahab", "Chhore".
   - In pure Army/Border/Ragda scenes, use raw, authentic Fauji addressing: "Ustad Ji", "Sher", "Fauji", "Jawan", "Laadle".
2. STRICT BAN ON LETTERS / CHITTHI: NEVER create scenes with paper letters (chitthi/patra), reading paper, or floating text! Use real physical action, facial expressions, live video calls, or face-to-face confrontation.
3. HARYANVI SHAYARI + SONG + SCENE-MATCHED BGM:
   - `dialogue_hinglish`: Must feel 100% real, punchy, emotional or hilarious (can be short & sharp 12 words or a powerful 28-word delivery with integrated Haryanvi shayari rhythm — NO filler or robotic words!).
   - `shayari_hindi`: A badass, heart-touching 2-line Haryanvi / Desi Fauji Shayari (in clean Hinglish/Hindi script).
   - `song_lyrics_cue`: 1 matching soulful Hindi/Punjabi/Haryanvi song line or vocal melody that plays in the background.
   - `bgm_mood_direction`: Exact background music & sound effects cue matching the scene (e.g., 'Deep Haryanvi dhol & bass drop with roaring wind', 'Emotional pahadi flute & acoustic guitar crescendo', 'Cinematic military snare drums & brass').
4. NEVER repeat any past dialogue from: [{avoid_sample}]
5. Output ONLY a valid JSON object (no markdown fences) with these exact keys:
{{
  "episode_title": "{"🔥 Viral Special: " if track_id == "viral_trend" else f"Part {ep_num}: "}[Catchy Viral Hinglish Hook Title]",
  "include_meera": {"true" if default_needs_meera else "false"},
  "meera_outfit": "{assigned_meera_dress}",
  "opening_hook_3s": "Explosive first 2-second visual and sound hook that stops the user from scrolling immediately.",
  "visual_scene_description": "Ultra-detailed 3D Pixar-style 9:16 vertical scene: dynamic camera movement, cinematic lighting, authentic Indian Army uniform/gear (no officer stars on recruit/soldier shoulders), exact expressions and dramatic action.",
  "dialogue_hinglish": "Spoken Hinglish/Haryanvi dialogue (powerful reality Fauji punch or cute Jaan/Kuchu Puchu banter + shayari delivery).",
  "shayari_hindi": "2-line damdar Haryanvi / Fauji reality shayari.",
  "song_lyrics_cue": "1 soulful matching background song verse / vocal melody.",
  "bgm_mood_direction": "Exact background music instrument, beat, and ambient SFX matching the video mood.",
  "hashtags": "{daily_tags}"
}}"""

    base_host = "https://generativelanguage.googleapis.com"
    default_chain = [
        "gemini-2.5-flash", "gemini-2.0-flash", "gemini-3-flash-preview",
        "gemini-flash-latest", "gemini-2.5-flash-lite", "gemini-1.5-flash", "gemini-2.5-pro"
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
                        timeout=12
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
                r = requests.post(url, json=payload, timeout=12)
                if r.status_code == 200:
                    parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    cand_txt = "".join([p.get("text", "") for p in parts if "text" in p])
                    parsed = _parse_ai_json(cand_txt)
                    if parsed:
                        print(f"✅ [Viral AI Showrunner] Script & BGM composed using model: {model_name}")
                        try:
                            new_v = [model_name] + [x for x in ordered_models if x != model_name]
                            with open("data/working_model_cache.json", "w", encoding="utf-8") as wf:
                                json.dump({"verified_models": new_v[:4], "full_chain": new_v, "updated_at": time.time()}, wf)
                        except Exception:
                            pass
                        parsed.setdefault("include_meera", default_needs_meera)
                        parsed.setdefault("meera_outfit", assigned_meera_dress)
                        parsed.setdefault("hashtags", daily_tags)
                        return parsed
            except Exception:
                pass

    try:
        r_pol = requests.post(
            "https://text.pollinations.ai/openai",
            headers={"Content-Type": "application/json"},
            json={"model": "openai", "messages": [{"role": "user", "content": system_prompt}]},
            timeout=12
        )
        if r_pol.status_code == 200:
            parsed = _parse_ai_json(r_pol.json()["choices"][0]["message"]["content"])
            if parsed:
                parsed.setdefault("include_meera", default_needs_meera)
                parsed.setdefault("meera_outfit", assigned_meera_dress)
                parsed.setdefault("hashtags", daily_tags)
                return parsed
    except Exception:
        pass

    return {
        "episode_title": f"Part {ep_num}: Fauji Jigra Aur Jaan Ki Yaad",
        "include_meera": default_needs_meera,
        "meera_outfit": assigned_meera_dress,
        "opening_hook_3s": "Sudden thunder flash over a snowy bunker as the young soldier locks his rifle bolt with intense eyes.",
        "visual_scene_description": f"3D Pixar-style 9:16 vertical cinematic scene for {track['name']}. Authentic Indian Army combat uniform, dramatic lighting, emotional intensity.",
        "dialogue_hinglish": (
            "Oye meri kuchu puchu, tu fikar na kar jaan... jab tak tere fauji ke seene mein saans hai, na sarhad jhukegi aur na tera bharosa tootega!"
            if default_needs_meera else
            "Sun le laadle, Haryane ka khoon aur fauj ki vardi jab ek sath garm hove hain na, toh toofan bhi rasta badal leve hai!"
        ),
        "shayari_hindi": "Boli mein Haryanvi thaat aur seene mein Tirange ki aag rakhte hain, hum fauji hain sahab, maut ko bhijeb mein rakh kar ghoomte hain!",
        "song_lyrics_cue": "Sandese aate hain, humein tadpate hain... soulful acoustic hum with Haryanvi folk flute",
        "bgm_mood_direction": "Deep cinematic bass drop with emotional pahadi flute, marching boots rhythm, and winter wind SFX",
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

    solo_army_tracks = {"training_ustad", "unit_ragda", "fauji_masti", "border_duty"}
    raw_inc = ai_story.get("include_meera", chosen_key not in solo_army_tracks)
    if isinstance(raw_inc, str):
        include_meera = raw_inc.strip().lower() in ("true", "yes", "1")
    else:
        include_meera = bool(raw_inc)

    combined_low = (visual_scene + " " + dialogue_line).lower()
    if chosen_key in solo_army_tracks and not any(w in combined_low for w in ["meera", "fojan", "kuchu puchu", "laado", "girlfriend", "wife"]):
        include_meera = False

    dress_idx = (ep_num + len(used_dialogues)) % len(MEERA_WARDROBE_CATALOG)
    meera_outfit = ai_story.get("meera_outfit") or MEERA_WARDROBE_CATALOG[dress_idx]

    q_now = get_scheduled_queue()
    existing_cnt = len(q_now.get("published_posts", [])) + len(q_now.get("scheduled_posts", [])) + len(q_now.get("unapproved_videos", [])) + 1
    clean_track_slug = "".join(w.capitalize() for w in chosen_key.split("_"))
    ts_slug = datetime.now(IST).strftime("%m%d_%H%M%S")
    unique_vid_id = f"Video_{existing_cnt + 20:03d}_{clean_track_slug}_Part_{ep_num:02d}_{ts_slug}"
    unique_mp4_name = f"{unique_vid_id}.mp4"

    if include_meera:
        char_instruction = (
            f"Create a high-definition 9:16 vertical 3D Pixar-style animated video using the two uploaded character reference images "
            f"(Image 1: Young Indian Army soldier in military uniform without officer stars; Image 2: His Fojan love interest). "
            f"IMPORTANT WARDROBE FOR FOJAN: Keep her exact facial identity from Image 2, wearing a fresh outfit: {meera_outfit}. "
        )
    else:
        char_instruction = (
            f"Create a high-definition 9:16 vertical 3D Pixar-style animated video using the uploaded character reference image "
            f"(Young Indian Army soldier in combat/training uniform without officer stars). Focus on the soldier and his Army unit/Ustad. "
        )

    gemini_video_prompt = (
        f"{char_instruction}"
        f"OPENING 2-SECOND HOOK: {opening_hook} "
        f"SCENE & PHYSICAL ACTION: {visual_scene} (No floating text or paper letters!). "
        f"LIP-SYNC SPOKEN HINDI/HARYANVI DIALOGUE (Authentic native Indian accent, powerful emotion & rhythm): \"{dialogue_line}\" "
        f"BACKGROUND MUSIC & SONG DIRECTION: {bgm_cue}. Include subtle background musical vibe of: '{song_cue}'. "
        f"CINEMATOGRAPHY: Ultra-detailed 3D Pixar CGI, expressive micro-expressions, rich dramatic lighting, vertical 9:16 portrait format."
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


def save_scheduled_queue(q_data, sync_cloud=True):
    """Runs Smart Domino Cascade Scheduler before every save and pushes via `push_json_to_github_instantly`."""
    global _LOCAL_QUEUE_MODIFIED_TS
    try:
        enforce_smart_cascade_schedule(q_data)
    except Exception as e:
        print(f"Schedule cascade note: {e}")
    q_data["updated_epoch"] = time.time()
    _LOCAL_QUEUE_MODIFIED_TS = q_data["updated_epoch"]
    os.makedirs("data", exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(q_data, f, indent=2, ensure_ascii=False)
    if sync_cloud and "push_json_to_github_instantly" in globals():
        try:
            push_json_to_github_instantly(QUEUE_FILE, "Sync smart-cascaded scheduled queue")
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
    published_files = {item.get("video_file") for item in q.get("published_posts", []) if item.get("video_file")}

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

    save_scheduled_queue(q, sync_cloud=True)

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
            if rel_json == "data/director_state.json" and os.path.exists(local_p):
                try:
                    loc_d = json.load(open(local_p, "r", encoding="utf-8"))
                    if float(remote_data.get("updated_epoch", 0)) < float(loc_d.get("updated_epoch", 0)):
                        should_write = False
                except Exception:
                    pass
            if rel_json == "data/live_telemetry.json" and os.path.exists(local_p):
                try:
                    with open(local_p, "r", encoding="utf-8") as lf:
                        loc_t = json.load(lf)
                    loc_ep = float(loc_t.get("epoch", 0))
                    rem_ep = float(remote_data.get("epoch", 0))
                    # Never let stale remote 'idle' overwrite an active local pipeline!
                    if rem_ep < loc_ep:
                        should_write = False
                    elif loc_t.get("status") == "active" and remote_data.get("status") == "idle" and (time.time() - loc_ep) < 120:
                        should_write = False
                    elif loc_t.get("status") == "active" and remote_data.get("status") == "active" and int(remote_data.get("step_num", 0)) < int(loc_t.get("step_num", 0)) and (time.time() - loc_ep) < 90:
                        should_write = False
                except Exception:
                    pass
            if should_write:
                with open(local_p, "w", encoding="utf-8") as wf:
                    json.dump(remote_data, wf, indent=2, ensure_ascii=False)

    if (time.time() - _LOCAL_QUEUE_MODIFIED_TS) > 5.0:
        remote_q = _fetch_github_json_zero_cache(QUEUE_FILE)
        if isinstance(remote_q, dict):
            loc_q = get_scheduled_queue()
            if float(remote_q.get("updated_epoch", 0)) >= float(loc_q.get("updated_epoch", 0)):
                with open(QUEUE_FILE, "w", encoding="utf-8") as wf:
                    json.dump(remote_q, wf, indent=2, ensure_ascii=False)
            else:
                # Merge any newly generated unapproved video from remote_q so it never gets missed!
                loc_known = {
                    x.get("video_file")
                    for k in ("unapproved_videos", "scheduled_posts", "published_posts")
                    for x in loc_q.get(k, [])
                }
                added_new = False
                for ru in remote_q.get("unapproved_videos", []):
                    rvf = ru.get("video_file")
                    if rvf and rvf not in loc_known:
                        loc_q.setdefault("unapproved_videos", []).insert(0, ru)
                        loc_known.add(rvf)
                        added_new = True
                if added_new:
                    with open(QUEUE_FILE, "w", encoding="utf-8") as wf:
                        json.dump(loc_q, wf, indent=2, ensure_ascii=False)

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
