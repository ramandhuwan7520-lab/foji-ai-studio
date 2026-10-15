import os
import json
import socket
import random
from datetime import datetime
from dotenv import load_dotenv
import requests
import urllib3.util.connection as urllib3_cn

load_dotenv()

def allowed_gai_family():
    return socket.AF_INET

urllib3_cn.allowed_gai_family = allowed_gai_family

HISTORY_FILE = "data/history.json"

SERIES_TRACKS = [
    {
        "id": "romantic",
        "series_title": "Foji & Fojan: Pyar aur Nok-Jhok",
        "theme_desc": "Romantic Nok-Jhok, secret surprises on army leave, and deep chemistry",
        "bgm": "romantic",
        "music_style": "romantic Bollywood flute and soft acoustic guitar melody"
    },
    {
        "id": "fighting",
        "series_title": "Foji & Fojan: Shaq aur Haq",
        "theme_desc": "Cute jealousy, possessive attitude, unknown phone calls, and fierce love",
        "bgm": "fighting",
        "music_style": "dramatic playful tension beat with desi dholak rhythm"
    },
    {
        "id": "naughty_double_meaning",
        "series_title": "Foji & Fojan: Shararati Raatein",
        "theme_desc": "Naughty double-meaning teasing, late-night bedroom/car banter, and playful romance",
        "bgm": "naughty_double_meaning",
        "music_style": "trendy groovy Bollywood lounge beat"
    },
    {
        "id": "glamorous_bold",
        "series_title": "Foji & Fojan: Royal Swag & Attitude",
        "theme_desc": "Glamorous partywear, high-chemistry bold attitude, and killer looks",
        "bgm": "glamorous_bold",
        "music_style": "stylish high-energy modern Bollywood trap instrumental"
    },
    {
        "id": "emotional",
        "series_title": "Foji & Fojan: Chhutti Khatam aur Farz",
        "theme_desc": "Emotional army call back to border, packing the rucksack, tears and pride",
        "bgm": "emotional",
        "music_style": "heart-touching patriotic Indian flute and emotional violin instrumental"
    },
    {
        "id": "funny",
        "series_title": "Foji & Fojan: Fauji Discipline vs Biwi ke Nakhre",
        "theme_desc": "Funny desi comedy, morning PT exercise vs household chores, hilarious couple nok-jhok",
        "bgm": "funny",
        "music_style": "quirky upbeat comical desi instrumental tune"
    },
    {
        "id": "sad",
        "series_title": "Foji & Fojan: Intezaar aur Judaai",
        "theme_desc": "Longing at the railway station, rainy window memories, and emotional waiting",
        "bgm": "sad",
        "music_style": "melancholic slow Bollywood piano and violin lofi instrumental"
    },
    {
        "id": "love_feelings",
        "series_title": "Foji & Fojan: Izhaar-e-Mohabbat",
        "theme_desc": "Deep soulful love confession under starry skies or snowy mountains",
        "bgm": "love_feelings",
        "music_style": "soulful dreamy Bollywood romantic strings and flute instrumental"
    }
]

def is_real_video_file(file_path):
    return file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 200 * 1024

def load_and_clean_history():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(HISTORY_FILE):
        return {"generated_count": 0, "recent_tracks": [], "history": []}

    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    valid_history = []
    valid_recent_tracks = []

    for idx, item in enumerate(data.get("history", []), start=1):
        vid_num = item.get("video_id", idx)
        raw_path = os.path.abspath(f"output/raw_videos/raw_video_{vid_num}.mp4")
        final_path = os.path.abspath(f"output/final_reels/final_reel_{vid_num}.mp4")

        if item.get("video_completed") is True or is_real_video_file(raw_path) or is_real_video_file(final_path):
            item["video_completed"] = True
            valid_history.append(item)
            t_id = item.get("track_id") or item.get("emotion_id") or item.get("bgm_folder")
            if t_id:
                valid_recent_tracks.append(t_id)

    return {
        "generated_count": max([i.get("video_id", 0) for i in valid_history], default=0),
        "recent_tracks": valid_recent_tracks,
        "history": valid_history
    }

def save_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_completed_parts_for_track(history_data, track_id, before_part=None):
    past_episodes = []
    for item in history_data.get("history", []):
        item_track = item.get("track_id") or item.get("emotion_id") or item.get("bgm_folder")
        if item_track == track_id and item.get("video_completed") is True:
            if before_part is None or int(item.get("part_number", 1)) < int(before_part):
                past_episodes.append(item)
    return past_episodes

def build_episodic_director_prompt(track, next_part_num, past_episodes, is_regenerate=False, old_rejected_line=None):
    track_id = track["id"]
    series_title = track["series_title"]
    theme_desc = track["theme_desc"]
    bgm_cat = track["bgm"]
    music_style = track.get("music_style", "Bollywood romantic instrumental")

    regen_instruction = ""
    if is_regenerate:
        regen_instruction = f"""
        🔄 REGENERATION MODE ACTIVE FOR PART {next_part_num}:
        The user rejected the previous version of Part {next_part_num} (Old dialogue was: "{old_rejected_line}").
        You MUST keep this as **PART {next_part_num}**, but invent a 100% DIFFERENT camera angle, DIFFERENT setting, DIFFERENT outfits, and a MUCH MORE VIRAL, fresh dialogue exchange!
        """

    if next_part_num == 1 or not past_episodes:
        continuity_block = f"""
        EPISODE STATUS: THIS IS **PART 1** (OPENING EPISODE) of '{series_title}'.
        - Set up an irresistible opening scene for Foji Makra and Fojan Meera based on: {theme_desc}.
        - End the 2nd dialogue on a cliffhanger so viewers eagerly wait for Part 2!
        {regen_instruction}
        """
    else:
        prev_summary_lines = []
        for idx, ep in enumerate(past_episodes[-3:], start=max(1, len(past_episodes) - 2)):
            prev_summary_lines.append(
                f"  * Part {ep.get('part_number', idx)}:\n"
                f"    - Location: {ep.get('new_location')}\n"
                f"    - Plot Summary: {ep.get('story_summary', 'N/A')}\n"
                f"    - {ep.get('dialogue_speaker_1')}: \"{ep.get('dialogue_line_1_hinglish')}\"\n"
                f"    - {ep.get('dialogue_speaker_2')}: \"{ep.get('dialogue_line_2_hinglish')}\"\n"
                f"    - Cliffhanger: {ep.get('next_part_hook', 'Story continues')}"
            )
        prev_context_str = "\n".join(prev_summary_lines)

        continuity_block = f"""
        EPISODE STATUS: THIS IS **PART {next_part_num}** (DIRECT SEQUEL TO PART {next_part_num - 1}) of '{series_title}'.
        PREVIOUS COMPLETED PART(S):
        {prev_context_str}
        Directly continue the story from where Part {next_part_num - 1} ended!
        {regen_instruction}
        """

    return f"""
    You are India's #1 Viral Instagram Reels Web-Series Creator & Screenwriter for a 3D Pixar-style animated channel.

    FIXED LEAD CHARACTERS (From Reference Images):
    1. FOJI MAKRA: Handsome young Indian Army SOLDIER / JAWAN (fit muscular build, sharp jawline, expressive eyes, desi swag).
       - CRITICAL UNIFORM RULE: Foji Makra is an enlisted Soldier (Sepoy/Jawan), NOT an Officer! Whenever he wears an Indian Army uniform, his shoulder straps/epaulettes MUST BE 100% PLAIN WITHOUT ANY STARS! Never put officer stars on his shoulders.
    2. FOJAN MEERA: Stunning young Indian woman (expressive eyes, sharp-witted, romantic, full of attitude and deep love for Makra).

    SERIES TRACK: {series_title} ({theme_desc})
    CURRENT EPISODE TO WRITE: **PART {next_part_num}**

    {continuity_block}

    CRITICAL 8-SECOND DIALOGUE LENGTH RULE (SO DIALOGUES NEVER CUT OFF MID-SENTENCE):
    - The generated video is strictly 8 to 10 seconds long in total!
    - Dialogue 1 MUST BE VERY SHORT & PUNCHY: **Strictly 5 to 7 words maximum** (takes max 3.2 seconds to speak).
    - Dialogue 2 MUST BE VERY SHORT & PUNCHY: **Strictly 5 to 7 words maximum** (takes max 3.2 seconds to speak).
    - Total words across BOTH dialogues combined must NOT exceed 14 words!

    HYPER-DETAILED `gemini_video_prompt` RULES (INCLUDING NATIVE BACKGROUND MUSIC):
    - Start with: "Create a 9:16 Portrait 3D Pixar Disney style 8k cinematic animated video using the uploaded character reference images."
    - State clearly: "Image 1 is Foji Makra (Indian Army Jawan/Soldier — strictly NO stars on his shoulders, plain soldier shoulder straps only). Image 2 is Fojan Meera. Strictly maintain their exact 3D Pixar facial features."
    - Describe their exact new outfits (`foji_new_dress` and `fojan_new_dress`) and setting (`new_location`).
    - Explicitly write the SHORT spoken dialogues WITH CHARACTER NAMES and fast pacing so both finish speaking before 7.5 seconds:
      * [0.0s - 3.8s]: <Foji Makra or Fojan Meera> <action/expression> and speaks clearly in Hindi at a natural brisk pace: "<Short 6-word Line 1>".
      * [3.8s - 7.5s]: <Fojan Meera or Foji Makra> <reaction/gesture> and replies clearly in Hindi before the video ends: "<Short 6-word Line 2>".
      * [7.5s - 10.0s]: Both hold an expressive cinematic reaction/smile so the audio never cuts off abruptly.
    - MANDATORY BUILT-IN MUSIC INSTRUCTION: End the `gemini_video_prompt` with: "IMPORTANT AUDIO INSTRUCTION: Generate a rich, emotional {music_style} background music track playing softly throughout the entire video at 20% volume underneath the crystal-clear 100% volume Hindi spoken dialogues."

    Return ONLY valid JSON in this exact structure:
    {{
        "track_id": "{track_id}",
        "emotion_id": "{bgm_cat}",
        "emotion_name": "{series_title} - Part {next_part_num}",
        "part_number": {next_part_num},
        "bgm_folder": "{bgm_cat}",
        "viral_score": 96,
        "story_summary": "1-sentence summary of Part {next_part_num}",
        "next_part_hook": "Cliffhanger left for Part {next_part_num + 1}",
        "new_location": "Detailed 3D Pixar setting description",
        "foji_new_dress": "Detailed outfit for Foji Makra (plain soldier shoulder straps with NO stars)",
        "fojan_new_dress": "Detailed outfit description for Fojan Meera",
        "dialogue_speaker_1": "Foji Makra or Fojan Meera",
        "dialogue_line_1_hinglish": "Short 5-7 word viral hook dialogue in Hinglish",
        "dialogue_line_1_hindi": "Short 5-7 word dialogue in Hindi",
        "dialogue_speaker_2": "Fojan Meera or Foji Makra",
        "dialogue_line_2_hinglish": "Short 5-7 word killer reply in Hinglish",
        "dialogue_line_2_hindi": "Short 5-7 word reply in Hindi",
        "gemini_video_prompt": "Complete master-level 9:16 Portrait 3D Pixar video prompt enforcing plain soldier shoulders (NO stars on Foji Makra), new outfits, short 6-word dialogues in [0.0s-3.8s] and [3.8s-7.5s], and built-in {music_style} background music.",
        "insta_title": "{series_title} ❤️ (Part {next_part_num})",
        "insta_caption": "Engaging desi caption for Part {next_part_num} + 'Part {next_part_num + 1} ke liye Follow kar lo! 👇'",
        "insta_hashtags": "#foji #indianarmy #faujilove #reelsindia #trendingreels #pixaranimation #desilove #faujidil #viralreels #part{next_part_num}"
    }}
    """

def generate_video_package(force_track_id=None, force_part_number=None, is_regenerate=False, old_rejected_line=None, reuse_video_id=None):
    """
    Generates a fresh episodic concept.
    If `is_regenerate=True` (or `force_track_id` & `force_part_number` are passed), it regenerates THAT EXACT PART NUMBER in a brand-new creative style!
    """
    api_key = os.getenv("GEMINI_API_KEY")
    history_data = load_and_clean_history()

    chosen_track = None
    if force_track_id:
        for t in SERIES_TRACKS:
            if t["id"] == force_track_id:
                chosen_track = t
                break

    if not chosen_track:
        recent_tracks = history_data.get("recent_tracks", [])[-4:]
        available_tracks = [t for t in SERIES_TRACKS if t["id"] not in recent_tracks] or SERIES_TRACKS
        chosen_track = random.choice(available_tracks)

    track_id = chosen_track["id"]
    series_title = chosen_track["series_title"]
    bgm_cat = chosen_track["bgm"]
    music_style = chosen_track.get("music_style", "Bollywood romantic instrumental")

    if force_part_number is not None:
        next_part_num = int(force_part_number)
        past_episodes = get_completed_parts_for_track(history_data, track_id, before_part=next_part_num)
    else:
        past_episodes = get_completed_parts_for_track(history_data, track_id)
        next_part_num = len(past_episodes) + 1

    next_video_id = reuse_video_id if reuse_video_id else (history_data["generated_count"] + 1)

    print(f"\n🎬 Series Track: '{series_title}' -> Preparing **PART {next_part_num}** (Regenerate Mode: {is_regenerate})")

    master_prompt = build_episodic_director_prompt(
        chosen_track, next_part_num, past_episodes,
        is_regenerate=is_regenerate, old_rejected_line=old_rejected_line
    )
    payload = {
        "contents": [{"parts": [{"text": master_prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0}
    }

    session = requests.Session()
    fast_models = ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-2.0-flash"]

    for model_name in fast_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            res = session.post(url, json=payload, timeout=(4, 18))
            if res.status_code == 200:
                raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                package = json.loads(raw_text)
                package["video_id"] = next_video_id
                package["track_id"] = track_id
                package["part_number"] = next_part_num
                package["emotion_name"] = f"{series_title} (Part {next_part_num})"
                package["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                package["needs_browser_brain"] = False
                package["video_completed"] = False

                # Remove old entry if reusing video_id
                history_data["history"] = [h for h in history_data["history"] if h.get("video_id") != next_video_id]
                history_data["generated_count"] = max(history_data["generated_count"], next_video_id)
                history_data["history"].append(package)
                save_history(history_data)

                print(f"✅ {series_title} - PART {next_part_num} Script Created via [{model_name}]!")
                return package
        except Exception:
            pass

    print(f"⚡ Handing over '{series_title} (Part {next_part_num})' script creation to Gemini Flash-Lite in Chrome!")
    package = {
        "video_id": next_video_id,
        "track_id": track_id,
        "emotion_id": bgm_cat,
        "emotion_name": f"{series_title} (Part {next_part_num})",
        "part_number": next_part_num,
        "bgm_folder": bgm_cat,
        "music_style": music_style,
        "viral_score": random.randint(92, 99),
        "needs_browser_brain": True,
        "video_completed": False,
        "browser_brain_prompt": master_prompt,
        "story_summary": f"Part {next_part_num} of {series_title}",
        "next_part_hook": f"To be continued in Part {next_part_num + 1}",
        "new_location": f"3D Pixar Cinematic Setting (Part {next_part_num})",
        "foji_new_dress": "Indian Army Soldier uniform with plain shoulder straps (NO stars)",
        "fojan_new_dress": "Designer ethnic attire",
        "dialogue_speaker_1": "Foji Makra",
        "dialogue_line_1_hinglish": "Generating in Chrome Flash-Lite...",
        "dialogue_line_1_hindi": "Generating...",
        "dialogue_speaker_2": "Fojan Meera",
        "dialogue_line_2_hinglish": "Generating in Chrome Flash-Lite...",
        "dialogue_line_2_hindi": "Generating...",
        "gemini_video_prompt": "",
        "insta_title": f"{series_title} ❤️ | Part {next_part_num}",
        "insta_caption": f"{series_title} (Part {next_part_num}) ❤️🔥 Agle Part {next_part_num + 1} mein kya hoga? Comment mein batao aur page Follow kar lo! 👇",
        "insta_hashtags": f"#foji #indianarmy #faujilove #reelsindia #trendingreels #pixaranimation #desilove #faujidil #viralreels #part{next_part_num}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    history_data["history"] = [h for h in history_data["history"] if h.get("video_id") != next_video_id]
    history_data["generated_count"] = max(history_data["generated_count"], next_video_id)
    history_data["history"].append(package)
    save_history(history_data)
    return package

if __name__ == "__main__":
    pkg = generate_video_package()
    print(f"🎉 Prepared: {pkg['emotion_name']} (Part {pkg['part_number']})")