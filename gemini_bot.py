import os
import re
import json
import time
import glob
import shutil
import socket
import subprocess
import requests
import urllib3.util.connection as urllib3_cn
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

load_dotenv()

def allowed_gai_family():
    return socket.AF_INET

urllib3_cn.allowed_gai_family = allowed_gai_family

def cleanup_locks_and_old_ports():
    wdm_dir = os.path.expanduser(r"~\.wdm")
    if os.path.exists(wdm_dir):
        for root, _, files in os.walk(wdm_dir):
            for f in files:
                if "lock" in f.lower():
                    try:
                        os.remove(os.path.join(root, f))
                    except Exception:
                        pass

def connect_selenium_to_chrome(options):
    try:
        return webdriver.Chrome(options=options)
    except Exception:
        wdm_exe_pattern = os.path.expanduser(r"~\.wdm\drivers\chromedriver\**\chromedriver.exe")
        found_drivers = glob.glob(wdm_exe_pattern, recursive=True)
        if found_drivers:
            from selenium.webdriver.chrome.service import Service
            latest_driver = sorted(found_drivers, key=os.path.getmtime, reverse=True)[0]
            return webdriver.Chrome(service=Service(latest_driver), options=options)
        raise

def send_alert(message):
    print(f"\n🔔 [GEMINI BOT ALERT]:\n{message}\n")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id and "baad_mein" not in token:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": f"🤖 Gemini Bot Update:\n\n{message}"},
                timeout=10
            )
        except Exception:
            pass

def is_valid_mp4(file_path):
    if not os.path.exists(file_path) or os.path.getsize(file_path) < 300 * 1024:
        return False
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
            return b"ftyp" in header
    except Exception:
        return False

def find_real_chrome():
    """Works on both your Windows Laptop AND 24/7 Free Linux Cloud Servers!"""
    paths = [
        # Linux Cloud Server paths
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        # Windows Laptop paths
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("❌ Chrome binary nahi mili!")

def find_image(keyword):
    folder = os.path.abspath("assets/characters")
    for f in os.listdir(folder):
        if keyword.lower() in f.lower() and f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            return os.path.join(folder, f)
    return None

def js_click(driver, element):
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)

def dismiss_annoying_popups(driver):
    """
    Scans the entire screen for any unexpected Google/Gemini popups, cookie banners,
    feature tours, or dialog boxes and closes them automatically without touching the chat!
    """
    popup_xpaths = [
        "//button[normalize-space(.)='Got it' or normalize-space(.)='Dismiss' or normalize-space(.)='No thanks' or normalize-space(.)='Not now' or normalize-space(.)='OK' or normalize-space(.)='Accept all' or normalize-space(.)='Continue' or normalize-space(.)='Stay signed out']",
        "//div[@role='dialog' or @role='alertdialog' or contains(@class, 'mat-mdc-dialog') or contains(@class, 'popup') or contains(@class, 'promo')]//button[contains(@aria-label, 'Close') or contains(@aria-label, 'close') or contains(@aria-label, 'Dismiss') or .//mat-icon[text()='close']]",
        "//mat-snack-bar-container//button"
    ]
    for xp in popup_xpaths:
        try:
            btns = [b for b in driver.find_elements(By.XPATH, xp) if b.is_displayed()]
            for b in btns:
                js_click(driver, b)
                time.sleep(0.3)
        except Exception:
            pass

def is_video_currently_generating(driver):
    """
    DEEP FULL-SCREEN DETECTOR:
    Detects if Gemini is still thinking, loading over a slow network, streaming a response,
    or rendering a video anywhere on the page!
    """
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        body_text = ""

    latest_text = get_latest_response_text(driver).lower()
    combined_text = latest_text + "\n" + body_text[-1500:]

    generating_phrases = [
        "generating video",
        "creating video",
        "creating your video",
        "generating your video",
        "this may take a few minutes",
        "working on it",
        "hang tight",
        "just a sec",
        "thinking",
        "generating...",
        "loading"
    ]
    if any(p in combined_text for p in generating_phrases):
        return True

    # Check all possible loading bars, spinners, skeletons, and streaming indicators
    spinners = driver.find_elements(
        By.CSS_SELECTOR,
        "mat-progress-bar, mat-spinner, .loading-spinner, [role='progressbar'], "
        ".video-loading, .generating-indicator, [aria-busy='true'], .skeleton-loader, "
        "lottie-player, .thinking-indicator"
    )
    for sp in spinners:
        try:
            if sp.is_displayed():
                return True
        except Exception:
            pass

    # If the 'Stop generating' / 'Stop response' button is visible, Gemini is 100% still working!
    stop_btns = driver.find_elements(
        By.XPATH,
        "//button[contains(@aria-label, 'Stop') or contains(@aria-label, 'stop') or contains(@mattooltip, 'Stop') or .//mat-icon[contains(text(), 'stop')]]"
    )
    for sb in stop_btns:
        try:
            if sb.is_displayed():
                return True
        except Exception:
            pass

    return False

def wait_for_complete_gemini_reply(driver, previous_bubble_count, max_wait_sec=300):
    """
    Waits patiently (up to 5 full minutes on slow networks!) until Gemini ACTUALLY finishes
    loading/thinking and produces either a complete text reply, a quota message, or a video!
    NEVER exits early while network/Gemini is still loading!
    """
    start_time = time.time()
    last_text = ""
    stable_ticks = 0

    while time.time() - start_time < max_wait_sec:
        time.sleep(3)
        dismiss_annoying_popups(driver)

        # 1. If a <video> tag appeared on screen, return immediately!
        if driver.find_elements(By.TAG_NAME, "video"):
            return "VIDEO_ELEMENT_DETECTED"

        # 2. Check if a quota banner appeared anywhere on screen
        reopen_t, banner_txt = scan_entire_chat_for_quota_banner(driver)
        if reopen_t and banner_txt:
            return banner_txt

        # 3. Check response bubbles
        bubbles = get_response_bubbles(driver)
        if len(bubbles) > previous_bubble_count:
            current_text = bubbles[-1].text.strip()
            if current_text:
                # Make sure Gemini isn't still actively streaming/typing or showing a spinner
                if current_text == last_text and len(current_text) > 8 and not is_video_currently_generating(driver):
                    stable_ticks += 1
                    if stable_ticks >= 2:
                        return current_text
                else:
                    last_text = current_text
                    stable_ticks = 0
                    continue

        # 4. If no text has appeared yet (or bubble is still empty), keep waiting patiently!
        if is_video_currently_generating(driver):
            print("⏳ Gemini abhi loading/thinking mode mein hai (Slow Network Wait Active)...")
            continue

    return get_latest_response_text(driver)

def check_screen_error_or_limit(driver):
    if is_video_currently_generating(driver):
        return None

    latest_text = get_latest_response_text(driver)
    if not latest_text:
        return None

    low = latest_text.lower()
    error_or_limit_phrases = [
        "limit resets",
        "reached your",
        "video generation limit",
        "you've reached your limit",
        "can't generate",
        "cannot generate",
        "create more videos",
        "try again",
        "quota",
        "something went wrong",
        "unable to generate",
        "unable to create",
        "i can't create",
        "i cannot create",
        "sorry"
    ]
    if any(p in low for p in error_or_limit_phrases):
        return latest_text
    return None

def select_flash_lite_model(driver):
    """
    STRICTLY selects 'Flash Lite' (3.5 Flash Lite / Flash-Lite) for ultra-fast video generation!
    Falls back to Flash if Lite is not in dropdown.
    """
    print("⚙️ Locking 'Flash Lite' Model in Gemini Chat for Ultra-Fast Rendering...")
    dismiss_annoying_popups(driver)
    try:
        dropdown_xpath = (
            "//button[contains(@aria-label, 'model') or contains(@aria-label, 'Model') or "
            "contains(., 'Flash') or contains(., 'Pro') or contains(., 'Argon') or contains(., 'Lite') or contains(., '3.')]"
        )
        btns = [b for b in driver.find_elements(By.XPATH, dropdown_xpath) if b.is_displayed()]
        if btns:
            js_click(driver, btns[0])
            time.sleep(1.5)

            # Priority 1: Flash Lite / Lite
            lite_options = driver.find_elements(
                By.XPATH,
                "//*[@role='menuitem' or @role='option' or self::button or self::div or self::span]"
                "[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'lite')]"
            )
            for opt in lite_options:
                if opt.is_displayed():
                    js_click(driver, opt)
                    print("✅ Model Strictly Locked to: 'Flash Lite'!")
                    time.sleep(1.5)
                    return True

            # Priority 2: Standard Flash (if Lite label is merged)
            flash_options = driver.find_elements(
                By.XPATH,
                "//*[@role='menuitem' or @role='option' or self::button or self::div or self::span]"
                "[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'flash')]"
            )
            for opt in flash_options:
                if opt.is_displayed():
                    js_click(driver, opt)
                    print("✅ Model Locked to: 'Flash'!")
                    time.sleep(1.5)
                    return True

            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    except Exception as e:
        print(f"⚠️ Model selector note: {e}")
    return False

def find_strict_plus_button(driver):
    strict_plus_xpaths = [
        "//button[.//mat-icon[normalize-space(text())='add' or normalize-space(@fonticon)='add'] and not(contains(@aria-label, 'More'))]",
        "//button[(contains(@aria-label, 'Upload') or contains(@aria-label, 'Add files') or contains(@aria-label, 'Insert') or normalize-space(text())='+') and not(contains(@aria-label, 'More'))]",
        "//rich-textarea/ancestor::div[contains(@class, 'input') or contains(@class, 'prompt')]//button[.//mat-icon[contains(text(), 'add')]]"
    ]
    for xp in strict_plus_xpaths:
        btns = [b for b in driver.find_elements(By.XPATH, xp) if b.is_displayed()]
        if btns:
            return btns[0]
    return None

def click_plus_and_select_create_video(driver):
    print("➕ Step 1: Clicking strictly on the '+' Icon in the chat box...")
    dismiss_annoying_popups(driver)
    plus_btn = find_strict_plus_button(driver)
    if not plus_btn:
        return False

    js_click(driver, plus_btn)
    time.sleep(2)

    print("🎬 Step 2: Selecting 'Create video' from the '+' Menu...")
    create_video_xpaths = [
        "//*[@role='menuitem' or @role='option' or self::button or self::li or self::div]"
        "[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'create video') or "
        "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'create a video')]"
    ]

    target_item = None
    for xp in create_video_xpaths:
        items = [el for el in driver.find_elements(By.XPATH, xp) if el.is_displayed()]
        if items:
            target_item = items[-1]
            break

    if not target_item:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(1)
        return False

    parent_btn = target_item
    try:
        anc = target_item.find_elements(By.XPATH, "./ancestor-or-self::*[@role='menuitem' or self::button][1]")
        if anc:
            parent_btn = anc[0]
    except Exception:
        pass

    is_disabled = (
        parent_btn.get_attribute("disabled") is not None or
        parent_btn.get_attribute("aria-disabled") == "true" or
        "disabled" in (parent_btn.get_attribute("class") or "").lower()
    )
    if is_disabled:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(1)
        return False

    js_click(driver, parent_btn)
    time.sleep(2)
    print("✅ 'Create video' successfully selected!")
    return True

def select_portrait_9_16_ratio(driver):
    print("📐 Step 3: Selecting 'Portrait (9:16)' Video Size...")
    dismiss_annoying_popups(driver)
    try:
        direct_portrait = [
            el for el in driver.find_elements(
                By.XPATH,
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'portrait') or contains(., '9:16')]"
            ) if el.is_displayed()
        ]
        if direct_portrait:
            js_click(driver, direct_portrait[-1])
            time.sleep(1.5)
            return True

        ratio_trigger_xpaths = [
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'landscape') or contains(., '16:9') or contains(@aria-label, 'Aspect') or contains(@aria-label, 'aspect') or contains(@aria-label, 'Size')]",
            "//*[@role='button' and (contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'landscape') or contains(., '16:9'))]"
        ]
        for xp in ratio_trigger_xpaths:
            btns = [b for b in driver.find_elements(By.XPATH, xp) if b.is_displayed()]
            if btns:
                js_click(driver, btns[0])
                time.sleep(1.5)
                break

        portrait_xpaths = [
            "//*[@role='menuitem' or @role='option' or self::button or self::span or self::div]"
            "[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'portrait') or contains(text(), '9:16') or contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'vertical')]"
        ]
        for pxp in portrait_xpaths:
            p_opts = [p for p in driver.find_elements(By.XPATH, pxp) if p.is_displayed()]
            if p_opts:
                js_click(driver, p_opts[-1])
                time.sleep(1.5)
                return True
    except Exception:
        pass
    return False

def upload_character_images_strictly(driver, foji_img, fojan_img):
    print("📸 Step 4: Uploading Character Images (Foji Makra & Fojan Meera)...")
    dismiss_annoying_popups(driver)
    try:
        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        if not file_inputs:
            plus_btn = find_strict_plus_button(driver)
            if plus_btn:
                js_click(driver, plus_btn)
                time.sleep(1.5)
                file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")

        if file_inputs:
            try:
                driver.execute_script("arguments[0].setAttribute('multiple', 'multiple');", file_inputs[0])
                file_inputs[0].send_keys(f"{foji_img}\n{fojan_img}")
            except Exception:
                file_inputs[0].send_keys(foji_img)
                time.sleep(2)
                file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                if file_inputs:
                    file_inputs[0].send_keys(fojan_img)

            time.sleep(5)
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(1)
            return True
    except Exception:
        pass
    return False

def paste_and_send_prompt(driver, prompt_text):
    print("✍️ Step 5: Submitting Prompt in Background Chrome...")
    dismiss_annoying_popups(driver)
    chat_selectors = [
        "rich-textarea div[contenteditable='true']",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
        "textarea"
    ]
    chat_box = None
    for sel in chat_selectors:
        boxes = [b for b in driver.find_elements(By.CSS_SELECTOR, sel) if b.is_displayed()]
        if boxes:
            chat_box = boxes[0]
            break

    if not chat_box:
        raise RuntimeError("❌ Gemini chat input box nahi mila!")

    js_click(driver, chat_box)
    time.sleep(0.5)
    driver.execute_script(
        "arguments[0].focus();"
        "arguments[0].innerText = arguments[1];"
        "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
        "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
        chat_box,
        prompt_text
    )
    time.sleep(1)
    chat_box.send_keys(" ")
    time.sleep(1)

    send_btns = driver.find_elements(
        By.XPATH,
        "//button[contains(@aria-label, 'Send') or contains(@aria-label, 'Submit') or .//mat-icon[normalize-space(text())='send']]"
    )
    clicked_send = False
    for sb in send_btns:
        if sb.is_displayed() and sb.is_enabled():
            js_click(driver, sb)
            clicked_send = True
            break

    if not clicked_send:
        chat_box.send_keys(Keys.ENTER)

def generate_live_script_in_chrome_if_needed(driver, latest_pkg, history_data):
    if not latest_pkg.get("needs_browser_brain"):
        return latest_pkg["gemini_video_prompt"]

    part_num = latest_pkg.get("part_number", 1)
    track_id = latest_pkg.get("track_id", "romantic")
    ep_title = latest_pkg.get("emotion_name", f"Part {part_num}")

    prev_count = len(get_response_bubbles(driver))
    brain_prompt = latest_pkg["browser_brain_prompt"] + "\n\nIMPORTANT: Return ONLY raw JSON object, no markdown explanation."
    paste_and_send_prompt(driver, brain_prompt)

    resp_text = wait_for_complete_gemini_reply(driver, prev_count, max_wait_sec=40)
    if "{" in resp_text and "}" in resp_text and "gemini_video_prompt" in resp_text:
        try:
            start_idx = resp_text.find("{")
            end_idx = resp_text.rfind("}") + 1
            parsed = json.loads(resp_text[start_idx:end_idx])

            parsed["track_id"] = track_id
            parsed["part_number"] = part_num
            parsed["needs_browser_brain"] = False
            parsed["video_completed"] = False
            latest_pkg.update(parsed)

            with open("data/history.json", "w", encoding="utf-8") as f:
                json.dump(history_data, f, indent=4, ensure_ascii=False)

            driver.get("https://gemini.google.com/app")
            time.sleep(4)
            select_flash_lite_model(driver)
            return latest_pkg["gemini_video_prompt"]
        except Exception:
            pass

    driver.get("https://gemini.google.com/app")
    time.sleep(4)
    select_flash_lite_model(driver)
    return (
        f"Create a 9:16 Portrait 3D Pixar Disney style 8k cinematic animated video using the two uploaded character images. "
        f"Image 1 is Foji Makra (handsome Indian Army Soldier/Jawan — strictly NO stars on his shoulders, plain soldier shoulder straps only). "
        f"Image 2 is Fojan Meera (stunning young Indian woman). Keep their exact facial features. Episode: {ep_title}. "
        f"Give both Foji Makra and Fojan Meera brand-new stylish outfits fitting Part {part_num}. "
        f"Keep spoken dialogues VERY SHORT (max 6 words each) so both finish completely within 8 seconds: "
        f"From 0 to 4 seconds, Foji Makra speaks a short 6-word Hindi hook with clear lip-sync. "
        f"From 4 to 8 seconds, Fojan Meera replies with a short 6-word punchy Hindi line. "
        f"Add soft Bollywood {latest_pkg['bgm_folder']} instrumental background music."
    )

def mark_episode_completed_in_history(history_data, latest_pkg, post_video_limit_note=None):
    latest_pkg["video_completed"] = True
    if post_video_limit_note:
        latest_pkg["quota_reopen_note"] = post_video_limit_note
    track_id = latest_pkg.get("track_id") or latest_pkg.get("emotion_id")
    if "recent_tracks" not in history_data:
        history_data["recent_tracks"] = []
    if track_id:
        history_data["recent_tracks"].append(track_id)
    with open("data/history.json", "w", encoding="utf-8") as f:
        json.dump(history_data, f, indent=4, ensure_ascii=False)

def recover_rendered_video_from_past_chats(driver, latest_pkg, raw_dir, output_video_path):
    """
    SMART CHAT HUNTER:
    1. First checks if the exact `gemini_chat_url` was saved in history.json for this video.
    2. If not, scans the Left Sidebar recent chats to find the conversation matching our prompt/characters!
    3. If the <video> is already rendered inside that chat, downloads it immediately without re-generating!
    """
    print("🕵️ Checking if video was ALREADY rendered in a previous Gemini chat...")
    try:
        saved_url = latest_pkg.get("gemini_chat_url")
        if saved_url and "gemini.google.com/app/" in saved_url and saved_url != "https://gemini.google.com/app":
            print(f"🔗 Opening exact saved chat URL: {saved_url}")
            driver.get(saved_url)
            time.sleep(6)
        else:
            # Scan sidebar chat history items for keywords from our prompt/theme
            search_keywords = [
                latest_pkg.get("dialogue_line_1_hinglish", "")[:18].lower(),
                latest_pkg.get("emotion_name", "")[:15].lower(),
                "foji makra",
                "9:16 portrait",
                "pixar"
            ]
            sidebar_links = driver.find_elements(
                By.XPATH,
                "//a[contains(@href, '/app/')] | //div[@role='listitem' or contains(@class, 'conversation')]"
            )
            for link in sidebar_links[:12]:
                txt = (link.text or "").lower()
                if any(k and k in txt for k in search_keywords):
                    print(f"📂 Found matching chat in sidebar: '{link.text.strip()[:40]}' -> Opening...")
                    js_click(driver, link)
                    time.sleep(6)
                    break

        # Check if a rendered <video> exists in this opened chat!
        videos = driver.find_elements(By.TAG_NAME, "video")
        if videos:
            print("🎉 Found ALREADY RENDERED Video in Chat History! Downloading MP4 now...")
            existing_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
            dl_btns = driver.find_elements(
                By.XPATH,
                "//button[contains(@aria-label, 'Download') or contains(@mattooltip, 'Download') or .//mat-icon[contains(text(), 'download')]]"
            )
            if dl_btns:
                js_click(driver, dl_btns[-1])
                time.sleep(8)

            current_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
            new_files = list(current_mp4s - existing_mp4s) or list(current_mp4s)
            for fpath in sorted(new_files, key=os.path.getmtime, reverse=True):
                if is_valid_mp4(fpath):
                    if os.path.abspath(fpath) != os.path.abspath(output_video_path):
                        shutil.move(fpath, output_video_path)
                    return True

        # Reset back to main app screen if no finished video found
        driver.get("https://gemini.google.com/app")
        time.sleep(4)
    except Exception as e:
        print(f"⚠️ Past chat recovery check note: {e}")
    return False

def generate_video_in_gemini(recover_only=False):
    cleanup_locks_and_old_ports()

    with open("data/history.json", "r", encoding="utf-8") as f:
        history_data = json.load(f)

    latest_pkg = history_data["history"][-1]
    video_num = latest_pkg.get("video_id", history_data["generated_count"])

    foji_img = find_image("foji")
    fojan_img = find_image("fojan")
    if not foji_img or not fojan_img:
        raise FileNotFoundError("❌ 'assets/characters/' folder mein 'foji' aur 'fojan' naam ki photos rakho!")

    raw_dir = os.path.abspath("output/raw_videos")
    os.makedirs(raw_dir, exist_ok=True)
    output_video_path = os.path.join(raw_dir, f"raw_video_{video_num}.mp4")

    if os.path.exists(output_video_path) and is_valid_mp4(output_video_path):
        print(f"✅ Raw video already exists on disk: {output_video_path}")
        mark_episode_completed_in_history(history_data, latest_pkg)
        return output_video_path

    chrome_exe = find_real_chrome()
    profile_path = os.path.abspath("chrome_profile")

    print("🕵️ Launching Invisible Background Chrome Engine...")
    cmd = [
        chrome_exe,
        f"--user-data-dir={profile_path}",
        "--remote-debugging-port=9222",
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080",
        "--window-position=-32000,-32000",
        "--mute-audio",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        "https://gemini.google.com/app"
    ]
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    chrome_proc = subprocess.Popen(cmd, creationflags=creation_flags)
    time.sleep(5)

    options = webdriver.ChromeOptions()
    options.debugger_address = "127.0.0.1:9222"
    driver = connect_selenium_to_chrome(options)
    driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": raw_dir})

    try:
        time.sleep(4)
        dismiss_annoying_popups(driver)

        # STEP 0: First check if the video ALREADY finished rendering in an earlier chat!
        if recover_rendered_video_from_past_chats(driver, latest_pkg, raw_dir, output_video_path):
            mark_episode_completed_in_history(history_data, latest_pkg)
            print(f"🎉 Recovered Already-Finished Video from Gemini Chat History: {output_video_path}")
            return output_video_path

        if recover_only:
            raise RuntimeError("Pichli chat mein koi bani hui video nahi mili. Normal generation start karein.")

        # Auto-Retry Loop (Up to 2 attempts: if attempt 1 fails NOT due to quota limit, modifies prompt & retries!)
        base_video_prompt = generate_live_script_in_chrome_if_needed(driver, latest_pkg, history_data)

        for attempt_idx in range(1, 3):
            if attempt_idx == 1:
                active_prompt = base_video_prompt
            else:
                print("🔄 Attempt 1 had a non-limit glitch -> Auto-Simplifying & Sanitizing Prompt for Attempt 2...")
                driver.get("https://gemini.google.com/app")
                time.sleep(4)
                active_prompt = (
                    f"Create a 9:16 Portrait 3D Pixar animated video using the two uploaded character images. "
                    f"Image 1 is Foji Makra (Indian Army Soldier with plain shoulder straps, no stars) and Image 2 is Fojan Meera. "
                    f"Scene: {latest_pkg.get('new_location', 'Cinematic Indian setting')}. "
                    f"From 0 to 4 seconds, {latest_pkg.get('dialogue_speaker_1', 'Foji Makra')} says in Hindi: \"{latest_pkg.get('dialogue_line_1_hinglish', 'Kaisi ho Meera?')}\". "
                    f"From 4 to 8 seconds, {latest_pkg.get('dialogue_speaker_2', 'Fojan Meera')} replies in Hindi: \"{latest_pkg.get('dialogue_line_2_hinglish', 'Bas aapka intezar tha!')}\". "
                    f"Include soft Bollywood instrumental background music."
                )

            select_flash_lite_model(driver)
            create_video_selected = click_plus_and_select_create_video(driver)

            if not create_video_selected:
                print("⚠️ '+' menu slow tha ya Create Video direct open nahi hua -> Direct Prompt bhej kar wait kar rahe hain...")
                prev_bubbles = len(get_response_bubbles(driver))
                initial_vids = len(driver.find_elements(By.TAG_NAME, "video"))
                upload_character_images_strictly(driver, foji_img, fojan_img)
                paste_and_send_prompt(driver, f"Generate a 9:16 portrait video using these character images: {active_prompt}")

                # Wait up to 5 minutes for slow network!
                full_reply = wait_for_complete_gemini_reply(driver, prev_bubbles, max_wait_sec=300)

                # Agar Gemini ne video bana di hai, toh error mat do — seedha main download loop mein aage badho!
                if full_reply == "VIDEO_ELEMENT_DETECTED" or len(driver.find_elements(By.TAG_NAME, "video")) > initial_vids or is_video_currently_generating(driver):
                    print("✅ Gemini ne video generation start/complete kar di hai! Continuing pipeline...")
                else:
                    reopen_time, clean_reply = extract_reopen_time_and_details(full_reply)
                    send_alert(f"⛔ *GEMINI VIDEO LIMIT / STATUS:*\n⏰ *Reopen:* `{reopen_time}`\n💬 {clean_reply}")
                    raise RuntimeError(f"⛔ GEMINI LIMIT -> {clean_reply}")

            # Save the exact chat URL into history.json as soon as Gemini assigns a conversation ID!
            time.sleep(6)
            if "/app/" in driver.current_url:
                latest_pkg["gemini_chat_url"] = driver.current_url
                with open("data/history.json", "w", encoding="utf-8") as f:
                    json.dump(history_data, f, indent=4, ensure_ascii=False)

            print(f"⏳ [Attempt {attempt_idx}] Waiting Patiently for Slow Network / Gemini Render...")
            video_saved = False
            response_appeared = False

            # Wait up to 15 minutes (180 ticks * 5s) so slow network NEVER causes premature exit!
            for tick in range(180):
                time.sleep(5)
                dismiss_annoying_popups(driver)

                if "/app/" in driver.current_url and latest_pkg.get("gemini_chat_url") != driver.current_url:
                    latest_pkg["gemini_chat_url"] = driver.current_url
                    with open("data/history.json", "w", encoding="utf-8") as f:
                        json.dump(history_data, f, indent=4, ensure_ascii=False)

                # Check if <video> appeared
                videos = driver.find_elements(By.TAG_NAME, "video")
                if len(videos) > initial_videos:
                    print("\n🎬 Video Rendered! Downloading MP4...")
                    time.sleep(4)
                    dl_btns = driver.find_elements(
                        By.XPATH,
                        "//button[contains(@aria-label, 'Download') or contains(@mattooltip, 'Download') or .//mat-icon[contains(text(), 'download')]]"
                    )
                    if dl_btns:
                        js_click(driver, dl_btns[-1])
                        time.sleep(8)

                    current_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
                    new_files = list(current_mp4s - existing_mp4s) or list(current_mp4s)
                    for fpath in sorted(new_files, key=os.path.getmtime, reverse=True):
                        if is_valid_mp4(fpath):
                            if os.path.abspath(fpath) != os.path.abspath(output_video_path):
                                shutil.move(fpath, output_video_path)
                            video_saved = True
                            break
                    if video_saved:
                        break

                # Wait patiently as long as NO final reply/video/limit has appeared yet!
                current_bubbles = len(get_response_bubbles(driver))
                latest_bubble_txt = get_latest_response_text(driver).strip()
                if (current_bubbles <= prev_bubbles or not latest_bubble_txt) and not is_video_currently_generating(driver):
                    reopen_chk, banner_chk = scan_entire_chat_for_quota_banner(driver)
                    if reopen_chk:
                        send_alert(f"⛔ *QUOTA LIMIT:* `{reopen_chk}`\n\n{banner_chk}")
                        raise RuntimeError(f"⛔ QUOTA LIMIT: {banner_chk}")
                    print(f"⏳ [Tick {tick}/180] Waiting for slow network / Gemini response to appear on screen...")
                    continue

                if is_video_currently_generating(driver):
                    response_appeared = True
                    continue

                if current_bubbles > prev_bubbles:
                    response_appeared = True
                    screen_error = check_screen_error_or_limit(driver)
                    if screen_error:
                        time.sleep(3)
                        screen_error = get_latest_response_text(driver)
                        low_err = screen_error.lower()
                        # If it's a strict Quota Limit, stop immediately and report time
                        if any(k in low_err for k in ["limit", "resets", "quota", "tomorrow", "more videos"]):
                            reopen_time, clean_err = extract_reopen_time_and_details(screen_error)
                            send_alert(f"⛔ *QUOTA LIMIT:* `{reopen_time}`\n\n{clean_err}")
                            raise RuntimeError(f"⛔ QUOTA LIMIT: {clean_err}")
                        else:
                            # It's a prompt/generation glitch -> break inner loop to trigger Attempt 2 with modified prompt!
                            print(f"⚠️ Non-limit error detected: {screen_error[:120]} -> Retrying with modified prompt...")
                            break

            if video_saved and is_valid_mp4(output_video_path):
                time.sleep(2)
                reopen_time, _ = scan_entire_chat_for_quota_banner(driver)
                post_limit_note = f"⏰ Next Limit Reopen: {reopen_time}" if reopen_time else None
                mark_episode_completed_in_history(history_data, latest_pkg, post_limit_note)
                return output_video_path

        raise RuntimeError("❌ Both attempts finished without a rendered video.")

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        try:
            chrome_proc.terminate()
        except Exception:
            pass

if __name__ == "__main__":
    generate_video_in_gemini()