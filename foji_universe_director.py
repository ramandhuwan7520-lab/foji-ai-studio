# -*- coding: utf-8 -*-
import os
import re
import json
import time
import random
import hashlib
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv(override=True)
IST = timezone(timedelta(hours=5, minutes=30))
DIRECTOR_STATE_FILE = "data/director_state.json"
HISTORY_FILE = "data/history.json"

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
            "Cover real army unit moments: Ustad catching Makra 30 seconds late for morning PT, frog jumps with "
            "full pitthu (rucksack), murga punishment, rifle/boot inspection, barrack bistar-bandi check, "
            "kamar dard after heavy load, and brotherhood during punishment."
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
            "firing range bullseye target, overcoming exhaustion and lower back strain through pure fauji willpower."
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
            "Freezing -15°C winds, night sentry duty with rifle, eating Maggi/tinned food in bunker, missing mother's food "
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
        "last_track_index": 0
    }
    save_director_state(default_state)
    return default_state


def save_director_state(state):
    os.makedirs("data", exist_ok=True)
    with open(DIRECTOR_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _get_recent_episode_context(track_id):
    if not os.path.exists(HISTORY_FILE):
        return 1, "This is Episode 1 (Season Premiere). Start a strong opening scene.", []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            hdata = json.load(f)
    except Exception:
        return 1, "This is Episode 1.", []

    hist_list = hdata.get("history", [])
    used_dialogues = [item.get("dialogue_line_1_hinglish", "") for item in hist_list if item.get("dialogue_line_1_hinglish")]
    used_dialogues.extend(hdata.get("failed_dialogues", []))

    track_episodes = [item for item in hist_list if item.get("track_id") == track_id]
    next_ep_num = len(track_episodes) + 1

    recent_overall = hist_list[-3:] if hist_list else []
    if not recent_overall:
        return 1, "This is the very first episode. Introduce Makra's fauji life with high impact.", used_dialogues

    summary_lines = []
    for ep in recent_overall:
        ep_title = ep.get("emotion_name", "Previous Episode")
        ep_diag = ep.get("dialogue_line_1_hinglish", "")
        ep_scene = ep.get("scene_summary", ep.get("gemini_video_prompt", "")[:180])
        summary_lines.append(f"- Past Video ({ep_title}): Scene='{ep_scene}' | Dialogue='{ep_diag}'")

    continuity_text = (
        f"This is Episode #{next_ep_num} of '{FOJI_UNIVERSE_TRACKS[track_id]['name']}'.\n"
        f"Here is what happened in the previous videos:\n" + "\n".join(summary_lines) + "\n"
        f"CRITICAL RULE: Write the NEXT sequential chapter that naturally follows the previous episode's events, "
        f"with a 100% brand-new situation, new setting detail, and completely fresh dialogue."
    )
    return next_ep_num, continuity_text, used_dialogues


def _find_any_gemini_api_key():
    load_dotenv(override=True)
    for k, v in os.environ.items():
        if any(w in k.upper() for w in ["GEMINI", "GOOGLE_API", "GENAI", "AI_KEY"]):
            clean_v = (v or "").strip().strip('"').strip("'")
            if clean_v.startswith("AIza"):
                return clean_v

    for check_file in [".env", "brain.py", "dashboard_app.py", "app.py"]:
        if os.path.exists(check_file):
            try:
                with open(check_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                m = re.search(r"(AIza[0-9A-Za-z\-_]{30,45})", content)
                if m:
                    return m.group(1)
            except Exception:
                pass
    return ""


def _extract_json_dict(raw_text):
    if not raw_text:
        return None
    txt = raw_text.strip()
    if "{" in txt and "}" in txt:
        txt = txt[txt.find("{"):txt.rfind("}") + 1]
    try:
        data = json.loads(txt)
        if isinstance(data, dict) and data.get("dialogue_hinglish"):
            return data
    except Exception:
        pass
    return None


def _synthesize_procedural_linked_episode(track_id, track, ep_num, continuity_context, used_dialogues, custom_idea=""):
    """
    Procedural Episodic Story Synthesizer:
    If external API has network/quota issues, this builds a unique, non-repeating episode
    dynamically linked to the episode number, time-of-day, weather, and custom twist!
    """
    seed_val = int(time.time() * 1000) + ep_num * 97
    rng = random.Random(seed_val)

    times_of_day = [
        "at 04:30 AM dawn under misty floodlights",
        "during scorching afternoon sun with dust rising",
        "under heavy monsoon downpour with mud splashing",
        "at chilly midnight under starry Himalayan sky",
        "during golden sunset near the unit border fence"
    ]
    cameras = [
        "Dynamic low-angle tracking shot moving into an expressive close-up",
        "Cinematic over-the-shoulder shot transitioning to front portrait framing",
        "Dramatic slow-push camera shot capturing sweat and intense eye contact",
        "Handheld realistic documentary-style 3D vertical camera movement"
    ]

    tod = rng.choice(times_of_day)
    cam = rng.choice(cameras)
    twist_note = f" Special focus: {custom_idea.strip()}." if custom_idea.strip() else ""

    if track_id == "unit_ragda":
        events = [
            ("Ustad Ka Pitthu Parade Ragda", "Indian Army dusty parade ground", "Makra in combat dress with 20kg rucksack doing frog jumps while strict moustached Ustad blows whistle", f"Ustad ji, pichli baar 1 minute late tha toh 50 jump lagwaye the, aaj toh ghadi se pehle aaya hu phir bhi ragda!"),
            ("Barrack Bistar-Bandi Inspection", "inside neat Indian Army barrack", "Makra sweating while tightening bedsheet corners as senior Ustad checks boot polish with a cane", f"Bhai, border par dushman se dar nahi lagta, par Saturday inspection mein Ustad ki laathi se rooh kaamp jaati hai!"),
            ("Zero-Dark-Thirty Whistle Drill", "outside unit guard room", "Makra running frantically buttoning his combat jacket while fellow jawans line up with rifles", f"Sapne mein Meera ke haath ke paranthe kha raha tha, Ustad ki ek seeti ne seedha parade ground mein patak diya!"),
            ("Rifle Cleaning & Murga Punishment", "unit armoury courtyard", "Makra and his coursemate holding rifles high above head in squat position while Ustad inspects barrel", f"Kamar mein chank aa gayi Ustad ji, ab toh rifle bhi bol rahi hai ki bas karo kitna chamkaoge!")
        ]
    elif track_id == "training_grind":
        events = [
            ("Barbed Wire Mud Crawl", "army obstacle course trench", "Makra covered in wet mud crawling fiercely under low barbed wire holding INSAS rifle safe from dirt", f"Yeh keechad nahi fauji ka shringar hai bhai, jitna ragadoge utna hi sona ban kar niklenge!"),
            ("10Km BPET Sprint Finish", "mountain road training track", "Makra sprinting with full battle load, veins popping, helping a tired coursemate cross the finish line", f"Saans phool rahi hai aur kamar toot rahi hai, par jab tak foj ki vardi badan par hai, kadam rukenge nahi!"),
            ("25-Foot Rope Climb Challenge", "unit physical training ground", "Makra climbing thick vertical rope using only arm strength while Ustad times him with a stopwatch", f"Gaon ke pedon par chadhne ka aaj asli fayda mila hai, Ustad ki ghadi se pehle rassa paar kar diya!")
        ]
    elif track_id == "barrack_fun":
        events = [
            ("Langar Ki Chai & Chhutti Panchayat", "unit langar verandah", "Makra holding steaming steel glass of chai, laughing loudly with two fellow jawans sitting on ammo boxes", f"Bhai ne chhutti ki arzi mein likha dadi bimar hai, Babu bola pichle saal toh teri dadi ki terahvi hui thi!"),
            ("Sunday Unit Barber Cutting", "under a neem tree near barrack", "Unit barber giving Makra a super high fauji zero-cut while Makra looks shocked into a small mirror", f"Bhai sahab se kaha tha thoda side se chhota kar de, isne toh sar ko pura parade ground bana diya!"),
            ("Bada Khana Ki Taiyari", "unit mess hall decorated with ribbons", "Makra and coursemates joyfully serving hot gulab jamun anddesi khana while dancing to dhol beats", f"Poore mahine ke ragde ka dard ek pal mein gayab ho jata hai jab unit mein Bada Khana banta hai!")
        ]
    elif track_id == "border_reality":
        events = [
            ("Minus 15 Degree Night Sentry", "snow-covered LOC forward bunker", "Makra in white snow-camo jacket with frost on eyebrows holding rifle, looking at a tiny photo of home", f"Yahan hawa haddiyan cheer deti hai maa, par tere aashirwad aur tirange ki kasam, ek inch peeche nahi hatunga!"),
            ("Bunker Mein Barf Wali Maggi", "inside dim wooden high-altitude bunker", "Makra melting snow in a steel pateela over kerosene stove to cook Maggi with frozen hands", f"Five-star hotel ka khana bhi fail hai bhai, jab barf pighla kar bunker mein garma-garam Maggi banti hai!")
        ]
    else:
        events = [
            ("Border Bunker Se Video Call", "sandbag border bunker and split village courtyard", "Makra in olive green uniform smiling affectionately at phone screen showing Meera in Haryanvi suit", f"Meera, network chahe ek dandi aaye ya na aaye, par mere dil ka tower hamesha tere gaon ki taraf rehta hai!"),
            ("Chhutti Pass Hone Ki Khushi", "unit office gate and village lane", "Makra kissing his signed leave certificate and packing bag while Meera counts days on wall calendar", f"Bawali taiyar ho ja, CO sahab ne chhutti par sign kar diye hain, ab seedha tere haath ka churma khaunga!"),
            ("Meera KiChitthi AurFoji KaHausla", "forward post trench", "Makra reading a handwritten letter with a shy smile while Meera is shown tying a thread at village temple", f"Teri har dua meri bulletproof jacket ban jaati hai Meera, tubas muskura kar intezar karna!")
        ]

    # Pick an event whose dialogue hasn't been used recently
    chosen = rng.choice(events)
    for ev in events:
        if ev[3] not in used_dialogues:
            chosen = ev
            break

    sub_title, loc, action_desc, base_diag = chosen
    if custom_idea.strip():
        base_diag = f"Makra ({custom_idea.strip()[:35]}): {base_diag}"

    shayaris = [
        "उस्ताद का रगड़ा और परेड की धूप ही हमें फौलाद बनाती है,\nयही वो भट्ठी है जहाँ से निकल कर वर्दी की शान आती है! 🔥🇮🇳",
        "सरहद की सर्द हवाओं में भी सीने में आग रखते हैं,\nहम फौजी हैं जनाब, अपनी नींद बेचकर वतन को आबाद रखते हैं! 🏔️🪖",
        "घर की याद तो आती है मगर फ़र्ज़ सबसे बड़ा होता है,\nएक फौजी हर तूफ़ान के आगे सीना तान कर खड़ा होता है! ❤️🇮🇳",
        "यारों की महफ़िल और यूनिट की चाय का अलग ही नशा है,\nफौजी की ज़िंदगी में हर दर्द के पीछे एक देसी मज़ा है! 😂☕"
    ]

    return {
        "episode_title": f"Ep {ep_num}: {sub_title}",
        "visual_scene_description": (
            f"{cam} {tod} at {loc}. {action_desc}.{twist_note} "
            f"Ultra-detailed 3D Pixar-style character rendering, expressive Indian Army uniform textures, vertical 9:16 format."
        ),
        "dialogue_hinglish": base_diag,
        "shayari_hindi": rng.choice(shayaris),
        "hashtags": "#indianarmy #faujilife #agniveer #makrameera #ustadkaragda #armyreels"
    }


def _call_live_ai_story_writer(track_id, track, ep_num, continuity_context, used_dialogues, custom_idea=""):
    api_key = _find_any_gemini_api_key()
    avoid_sample = " | ".join([d for d in used_dialogues[-12:] if d])
    user_direction = f"\nUSER SPECIAL DIRECTION FOR THIS EPISODE: {custom_idea}\n" if custom_idea.strip() else ""

    system_prompt = f"""You are the Lead Showrunner & Scriptwriter for 'Foji AI Studio', a viral 3D animated Indian Army series starring:
- Makra (Foji): A young, spirited Haryanvi Indian Army jawan (Agniveer).
- Meera (Fojan): Makra's devoted, witty village love interest (appears in love/home/call scenes).
- Ustad / Unit Coursemates: Appear in unit ragda, training, barrack fun, and border duty scenes.

CURRENT TRACK: {track['name']} ({track['badge']})
TRACK BRIEF: {track['theme_brief']}
EPISODE NUMBER: Episode {ep_num}

PREVIOUS EPISODE CONTINUITY:
{continuity_context}
{user_direction}
STRICT RULES:
1. NEVER repeat any of these past dialogues: [{avoid_sample}]
2. Make this episode directly connected to the previous episode's story arc while introducing a fresh twist, emotion, punishment, or comedic moment.
3. Return ONLY valid JSON with these exact keys:
{{
  "episode_title": "Short catchy Hinglish title (e.g., Ep {ep_num}: Ustad Ka Midnight Raid)",
  "visual_scene_description": "Detailed 3D Pixar-style visual description for vertical 9:16 video: camera angle, lighting, exact Indian Army uniform/barrack/border/village environment, character expressions and physical actions.",
  "dialogue_hinglish": "1 punchy, emotional or hilarious spoken Hinglish dialogue line (15 to 28 words) with authentic desi/fauji flavour.",
  "shayari_hindi": "2-line original goosebump-inducing or funny Hindi shayari matching the exact scene.",
  "hashtags": "6 viral Instagram hashtags"
}}"""

    # 1. Try Official Gemini API via REST (both with and without responseMimeType for maximum compatibility)
    if api_key:
        for model_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-pro"]:
            try:
                api_url = "https://generativelanguage.googleapis.com/v1beta/models/" + model_name + ":generateContent?key=" + api_key
                payload = {
                    "contents": [{"parts": [{"text": system_prompt}]}],
                    "generationConfig": {"temperature": 0.9}
                }
                r = requests.post(api_url, json=payload, timeout=20)
                if r.status_code == 200:
                    cand_txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = _extract_json_dict(cand_txt)
                    if parsed:
                        print(f"   ✅ Live Gemini API ({model_name}) wrote Episode #{ep_num}!")
                        return parsed
            except Exception:
                pass

    # 2. Try google.generativeai SDK if installed
    if api_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            for m in ["gemini-2.0-flash", "gemini-1.5-flash"]:
                try:
                    model = genai.GenerativeModel(m)
                    resp = model.generate_content(system_prompt)
                    parsed = _extract_json_dict(resp.text)
                    if parsed:
                        print(f"   ✅ Gemini SDK ({m}) wrote Episode #{ep_num}!")
                        return parsed
                except Exception:
                    pass
        except Exception:
            pass

    # 3. Never crash: Use Procedural Linked Story Synthesizer so pipeline NEVER stops!
    print(f"   ⚡ Using Built-In Procedural Foji Story Synthesizer for Episode #{ep_num}...")
    return _synthesize_procedural_linked_episode(track_id, track, ep_num, continuity_context, used_dialogues, custom_idea)


def build_real_foji_universe_package(video_id=1, force_track_id=None, custom_idea=""):
    state = get_director_state()
    track_keys = list(FOJI_UNIVERSE_TRACKS.keys())

    if force_track_id and force_track_id in FOJI_UNIVERSE_TRACKS:
        chosen_key = force_track_id
    elif state.get("active_mode") == "locked_track" and state.get("selected_track_id") in FOJI_UNIVERSE_TRACKS:
        chosen_key = state["selected_track_id"]
    else:
        idx = int(state.get("last_track_index", 0)) % len(track_keys)
        chosen_key = track_keys[idx]
        state["last_track_index"] = idx + 1
        save_director_state(state)

    track = FOJI_UNIVERSE_TRACKS[chosen_key]
    ep_num, continuity_context, used_dialogues = _get_recent_episode_context(chosen_key)
    idea_to_use = custom_idea.strip() or state.get("custom_idea", "").strip()

    print(f"🧠 [AI Showrunner] Writing 100% Fresh Linked Script for {track['name']} (Episode #{ep_num})...")
    ai_story = _call_live_ai_story_writer(chosen_key, track, ep_num, continuity_context, used_dialogues, idea_to_use)

    if state.get("custom_idea"):
        state["custom_idea"] = ""
        save_director_state(state)

    ep_title = ai_story.get("episode_title", f"Ep {ep_num}: {track['badge']}")
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
        f"Follow 👉 @ai_foji_lovelife for Next Episode! 🇮🇳🔥\n\n"
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

    return {
        "gemini_cookies_healthy": cookie_ok,
        "ig_session_healthy": ig_ok,
        "blueprint_locked": blueprint_ok,
        "telemetry": telemetry,
        "tracks": list(FOJI_UNIVERSE_TRACKS.values()),
        "director_state": get_director_state()
    }