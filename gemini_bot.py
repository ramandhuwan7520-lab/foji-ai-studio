import os
import re
import json
import time
import glob
import shutil
import random
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

LIVE_LOGS_BUFFER = []

from datetime import datetime, timedelta, timezone
IST = timezone(timedelta(hours=5, minutes=30))

def push_app_notification(notif_type, title, message, status="info"):
    """Bug #6: Saves every micro & macro event into data/notifications.json and syncs to Cloud immediately."""
    os.makedirs("data", exist_ok=True)
    n_path = "data/notifications.json"
    items = []
    if os.path.exists(n_path):
        try:
            with open(n_path, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            items = []
    now_ist = datetime.now(IST)
    items.insert(0, {
        "id": f"notif_{int(time.time() * 1000)}_{random.randint(100,999)}",
        "type": notif_type,
        "title": title,
        "message": message,
        "status": status,
        "time_str": now_ist.strftime("%I:%M:%S %p IST"),
        "date_str": now_ist.strftime("%d %b %Y"),
        "timestamp": time.time()
    })
    items = items[:120]
    try:
        with open(n_path, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            subprocess.run(["git", "config", "user.name", "FojiCloudEngine"], check=False)
            subprocess.run(["git", "config", "user.email", "foji@studio.ai"], check=False)
            subprocess.run(["git", "add", "data/notifications.json", "data/live_telemetry.json"], check=False)
            subprocess.run(["git", "commit", "-m", f"Notif: {title[:40]}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "push", "origin", "HEAD:main", "--force"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def update_3d_telemetry(step_num, step_title, sub_detail, status="active", progress=10, driver=None):
    """Bug #4 Fix: Immediately pushes error/completion state to GitHub so Frontend never stays stuck on steps 1-6!"""
    os.makedirs("data", exist_ok=True)
    now_ist = datetime.now(IST)
    # If status is error or completed, set step_num to 0 so pipeline box hides immediately on refresh!
    effective_step = 0 if status in ("error", "completed", "idle") else step_num
    payload = {
        "step_num": effective_step,
        "raw_step": step_num,
        "step_title": step_title,
        "sub_detail": sub_detail,
        "status": status,
        "progress": progress,
        "timestamp": now_ist.strftime("%I:%M:%S %p IST"),
        "epoch": time.time()
    }
    try:
        with open("data/live_telemetry.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        if os.environ.get("GITHUB_ACTIONS") == "true" and (status in ("error", "completed") or step_num in (1, 2, 4, 5, 6)):
            subprocess.run(["git", "config", "user.name", "FojiCloudEngine"], check=False)
            subprocess.run(["git", "config", "user.email", "foji@studio.ai"], check=False)
            subprocess.run(["git", "add", "data/live_telemetry.json", "data/notifications.json"], check=False)
            subprocess.run(["git", "commit", "-m", f"Telemetry: {status} {step_title[:30]}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "push", "origin", "HEAD:main", "--force"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    print(f"🌐 [STEP {step_num}/6 | {status.upper()}] {step_title} -> {sub_detail} ({progress}%)")

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
    """Works on both Windows Laptop AND Ubuntu 24.04 Cloud Server without version mismatch!"""
    for attempt in range(4):
        try:
            return webdriver.Chrome(options=options)
        except Exception as e:
            if attempt == 3:
                wdm_exe_pattern = os.path.expanduser(r"~\.wdm\drivers\chromedriver\**\chromedriver*")
                found_drivers = glob.glob(wdm_exe_pattern, recursive=True)
                if found_drivers:
                    from selenium.webdriver.chrome.service import Service
                    latest_driver = sorted(found_drivers, key=os.path.getmtime, reverse=True)[0]
                    return webdriver.Chrome(service=Service(latest_driver), options=options)
                raise RuntimeError(f"Chrome connect failed after 4 tries: {e}")
            time.sleep(2)

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

def extract_and_verify_gemini_mp4(driver, raw_dir, existing_mp4s, output_video_path):
    """
    PERMANENT BUG #1 FIX:
    Guarantees the rendered <video> in Gemini is actually saved as a valid .mp4 file on disk!
    Method 1: Clicks Gemini Download button & waits up to 45s for Chrome download to finish (.crdownload -> .mp4).
    Method 2: Directly extracts the <video src> stream inside Chrome via JS fetch / session cookies!
    """
    # Method 1: Trigger official Download button
    dl_btns = driver.find_elements(
        By.XPATH,
        "//button[contains(@aria-label, 'Download') or contains(@mattooltip, 'Download') or .//mat-icon[contains(text(), 'download')]]"
    )
    if dl_btns:
        js_click(driver, dl_btns[-1])

    # Poll up to 45 seconds for Chrome to finish writing the .mp4
    for _ in range(15):
        time.sleep(3)
        current_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
        new_files = list(current_mp4s - existing_mp4s) or list(current_mp4s)
        for fpath in sorted(new_files, key=os.path.getmtime, reverse=True):
            if is_valid_mp4(fpath):
                if os.path.abspath(fpath) != os.path.abspath(output_video_path):
                    shutil.copy2(fpath, output_video_path)
                if is_valid_mp4(output_video_path):
                    return True

    # Method 2: Direct JS Blob / Video SRC extraction inside Chrome if Download button was blocked!
    try:
        videos = driver.find_elements(By.TAG_NAME, "video")
        if videos:
            vid_el = videos[-1]
            vid_src = vid_el.get_attribute("src") or ""
            if not vid_src:
                sources = vid_el.find_elements(By.TAG_NAME, "source")
                if sources:
                    vid_src = sources[0].get_attribute("src") or ""

            if vid_src:
                print(f"📥 Extracting video directly from stream URL: {vid_src[:60]}...")
                b64_data = driver.execute_async_script("""
                    const url = arguments[0];
                    const callback = arguments[arguments.length - 1];
                    fetch(url, {credentials: 'include'})
                      .then(r => r.blob())
                      .then(b => {
                          const reader = new FileReader();
                          reader.onloadend = () => callback(reader.result.split(',')[1]);
                          reader.readAsDataURL(b);
                      })
                      .catch(() => callback(null));
                """, vid_src)
                if b64_data:
                    import base64
                    with open(output_video_path, "wb") as bf:
                        bf.write(base64.b64decode(b64_data))
                    if is_valid_mp4(output_video_path):
                        return True

                # Method 3: Python requests with Chrome cookies
                sess = requests.Session()
                for ck in driver.get_cookies():
                    sess.cookies.set(ck["name"], ck["value"])
                r = sess.get(vid_src, headers={"User-Agent": driver.execute_script("return navigator.userAgent;")}, timeout=30)
                if r.status_code == 200 and len(r.content) > 300 * 1024:
                    with open(output_video_path, "wb") as rf:
                        rf.write(r.content)
                    if is_valid_mp4(output_video_path):
                        return True
    except Exception as e:
        print(f"⚠️ Direct stream extraction note: {e}")

    return is_valid_mp4(output_video_path)    

def find_real_chrome():
    """Works on both your Windows Laptop AND 24/7 Free Linux Cloud Servers!"""
    paths = [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("❌ Chrome binary nahi mili!")

def launch_chrome_and_connect(raw_dir, headless=True):
    """Launches 100% Invisible Chrome on both Linux Cloud (7GB RAM) & Windows Laptop."""
    cleanup_locks_and_old_ports()
    os.makedirs(raw_dir, exist_ok=True)
    chrome_exe = find_real_chrome()
    profile_path = os.path.abspath("chrome_profile")
    os.makedirs(profile_path, exist_ok=True)

    # Remove stale SingletonLock left by any previous crash on Linux/Windows
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lp = os.path.join(profile_path, lock_file)
        if os.path.exists(lp) or os.path.islink(lp):
            try:
                os.unlink(lp)
            except Exception:
                pass

    cmd = [
        chrome_exe,
        f"--user-data-dir={profile_path}",
        "--remote-debugging-port=9222",
        "--remote-allow-origins=*",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--window-size=1920,1080",
        "--mute-audio",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-blink-features=AutomationControlled",
        "https://gemini.google.com/app"
    ]
    if headless:
        cmd.insert(4, "--headless=new")

    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    chrome_proc = subprocess.Popen(
        cmd,
        creationflags=creation_flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(6)

    options = webdriver.ChromeOptions()
    options.debugger_address = "127.0.0.1:9222"
    driver = connect_selenium_to_chrome(options)
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": raw_dir})
    except Exception:
        pass
    driver._chrome_proc = chrome_proc
    return driver, chrome_proc

def get_chrome_driver(raw_dir=None):
    """Helper used by cloud_worker.py to export Google Login Cookies from local Chrome."""
    if not raw_dir:
        raw_dir = os.path.abspath("output/raw_videos")
    driver, _ = launch_chrome_and_connect(raw_dir, headless=False)
    return driver

def inject_cloud_cookies_if_present(driver):
    """Injects GEMINI_COOKIES_JSON into Cloud Chrome so Google never asks for OTP/Password!"""
    cookies_env = os.environ.get("GEMINI_COOKIES_JSON", "").strip()
    if not cookies_env:
        return
    try:
        driver.get("https://gemini.google.com")
        time.sleep(2)
        for ck in json.loads(cookies_env):
            try:
                driver.add_cookie(ck)
            except Exception:
                pass
        print("🔐 Cloud Google Login Cookies injected successfully!")
        driver.get("https://gemini.google.com/app")
        time.sleep(4)
    except Exception as e:
        print(f"⚠️ Cookie injection notice: {e}")

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

def get_response_bubbles(driver):
    """Returns all Gemini response message containers on the screen."""
    selectors = [
        "model-response",
        "message-content",
        ".model-response-text",
        "[data-message-author-role='model']",
        ".response-container-content"
    ]
    for sel in selectors:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems:
                return elems
        except Exception:
            pass
    return []

def get_latest_response_text(driver):
    """Safely extracts the text of the latest Gemini reply bubble."""
    bubbles = get_response_bubbles(driver)
    if bubbles:
        try:
            return bubbles[-1].text.strip()
        except Exception:
            pass
    return ""

def extract_reopen_time_and_details(text):
    """Extracts quota reset time or error details from Gemini's message."""
    if not text:
        return "Unknown Time", "Screen par abhi koi reply nahi aaya."
    clean = " ".join(text.split())
    m = re.search(
        r"(try again (?:after|at|in)\s+[^.!?\n]+|available (?:again )?(?:after|at|in)\s+[^.!?\n]+|\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)\b|\b\d+\s*(?:hours?|minutes?|mins?|days?)\b)",
        clean,
        re.IGNORECASE
    )
    reopen_time = m.group(1).strip() if m else "Check Gemini Quota / Try Later"
    return reopen_time, clean[:300]

def scan_entire_chat_for_quota_banner(driver):
    """
    FIXED: Scans ONLY the active latest response bubble or active toast popup (NEVER the sidebar history!),
    preventing false-positive Quota Limit alerts when your limit is already open!
    """
    latest_txt = get_latest_response_text(driver)
    snackbars = driver.find_elements(By.CSS_SELECTOR, "mat-snack-bar-container, [role='alert']")
    snack_txt = " ".join([s.text for s in snackbars if s.is_displayed()])
    combined = f"{latest_txt}\n{snack_txt}".strip()
    if not combined:
        return None, None

    lower_comb = combined.lower()
    strict_quota_keywords = [
        "you've reached your video generation limit",
        "reached your limit for generating videos",
        "can't generate more videos right now",
        "video generation limit resets"
    ]
    for kw in strict_quota_keywords:
        if kw in lower_comb:
            reopen_t, _ = extract_reopen_time_and_details(combined)
            return reopen_t, combined[:260]
    return None, None

def dismiss_annoying_popups(driver):
    popup_xpaths = [
        "//button[normalize-space(.)='Got it' or normalize-space(.)='Dismiss' or normalize-space(.)='No thanks' or normalize-space(.)='Not now' or normalize-space(.)='OK' or normalize-space(.)='Accept all' or normalize-space(.)='Continue']",
        "//div[@role='dialog' or @role='alertdialog']//button[contains(@aria-label, 'Close') or contains(@aria-label, 'close') or .//mat-icon[text()='close']]"
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
    latest_text = get_latest_response_text(driver).lower()
    generating_phrases = [
        "generating video", "creating video", "creating your video",
        "generating your video", "this may take a few minutes",
        "working on it", "hang tight", "just a sec"
    ]
    if any(p in latest_text for p in generating_phrases):
        return True

    spinners = driver.find_elements(
        By.CSS_SELECTOR,
        "mat-progress-bar, mat-spinner, .loading-spinner, [role='progressbar'], "
        ".video-loading, .generating-indicator, [aria-busy='true'], lottie-player"
    )
    for sp in spinners:
        try:
            if sp.is_displayed():
                return True
        except Exception:
            pass

    stop_btns = driver.find_elements(
        By.XPATH,
        "//button[contains(@aria-label, 'Stop') or contains(@aria-label, 'stop') or .//mat-icon[contains(text(), 'stop')]]"
    )
    for sb in stop_btns:
        try:
            if sb.is_displayed():
                return True
        except Exception:
            pass
    return False

def wait_for_complete_gemini_reply(driver, previous_bubble_count, max_wait_sec=300):
    start_time = time.time()
    last_text = ""
    stable_ticks = 0

    while time.time() - start_time < max_wait_sec:
        time.sleep(3)
        dismiss_annoying_popups(driver)

        if driver.find_elements(By.TAG_NAME, "video"):
            return "VIDEO_ELEMENT_DETECTED"

        reopen_t, banner_txt = scan_entire_chat_for_quota_banner(driver)
        if reopen_t and banner_txt:
            return banner_txt

        bubbles = get_response_bubbles(driver)
        if len(bubbles) > previous_bubble_count:
            current_text = bubbles[-1].text.strip()
            if current_text:
                if current_text == last_text and len(current_text) > 8 and not is_video_currently_generating(driver):
                    stable_ticks += 1
                    if stable_ticks >= 2:
                        return current_text
                else:
                    last_text = current_text
                    stable_ticks = 0
                    continue
    return get_latest_response_text(driver)

def check_screen_error_or_limit(driver):
    """FIXED: Checks ONLY strict quota/error phrases in the latest reply bubble."""
    if is_video_currently_generating(driver):
        return None
    latest_text = get_latest_response_text(driver)
    if not latest_text:
        return None
    low = latest_text.lower()
    strict_phrases = [
        "you've reached your video generation limit",
        "reached your limit for generating videos",
        "can't generate more videos right now",
        "video generation limit resets",
        "something went wrong"
    ]
    if any(p in low for p in strict_phrases):
        return latest_text
    return None

def select_flash_lite_model(driver):
    """
    Takes a live screenshot of Hidden Chrome, checks Google login status,
    and selects 'Flash' (or Fast/Default video-capable model) without false-failing!
    """
    dismiss_annoying_popups(driver)
    time.sleep(2)
    update_3d_telemetry(1, "CHECKING GEMINI & FLASH MODEL", "Capturing live Chrome screen & checking model dropdown...", "active", 18, driver=driver)

    # 1. Check if Google Cookies expired / Signed out
    sign_in_btns = [
        b for b in driver.find_elements(By.XPATH, "//a[contains(., 'Sign in')] | //button[contains(., 'Sign in')]")
        if b.is_displayed()
    ]
    if sign_in_btns and not find_strict_plus_button(driver):
        err = "❌ Hidden Chrome mein Google Account Signed-Out dikh raha hai! (Live Window mein screenshot dekhein — Cookies refresh karein)"
        update_3d_telemetry(1, "GOOGLE SIGN-IN REQUIRED", err, "error", 0, driver=driver)
        send_alert(err)
        raise RuntimeError(err)

    # 2. Try opening Model Switcher Dropdown to pick 'Flash' (excluding 'Lite')
    try:
        dropdown_xpath = (
            "//button[contains(@aria-label, 'model') or contains(@aria-label, 'Model') or "
            "contains(@data-test-id, 'model') or contains(., 'Flash') or contains(., 'Pro') or contains(., 'Gemini')]"
        )
        btns = [b for b in driver.find_elements(By.XPATH, dropdown_xpath) if b.is_displayed()]
        if btns:
            js_click(driver, btns[0])
            time.sleep(2)
            update_3d_telemetry(1, "MODEL MENU OPENED", "Selecting 'Flash' from dropdown...", "active", 22, driver=driver)

            menu_items = driver.find_elements(
                By.XPATH,
                "//*[@role='menuitem' or @role='option' or self::button or self::div or self::span]"
                "[(contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'flash') or "
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'fast')) and "
                "not(contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'lite'))]"
            )
            clicked = False
            for item in menu_items:
                if item.is_displayed():
                    js_click(driver, item)
                    clicked = True
                    time.sleep(1.5)
                    break

            if not clicked:
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                time.sleep(1)
    except Exception as e:
        print(f"⚠️ Model switcher note: {e}")

    update_3d_telemetry(1, "FLASH ENGINE READY", "Gemini Flash model locked! Proceeding to '+' menu...", "active", 25, driver=driver)
    return True

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
    update_3d_telemetry(2, "CLICKING '+' & CREATE VIDEO", "Triggering Veo 3D Video Tool in Chat Box", "active", 34)
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
    update_3d_telemetry(3, "LOCKING 9:16 PORTRAIT RATIO", "Setting Vertical Reel Dimension (1080x1920)", "active", 50)
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
    update_3d_telemetry(4, "INJECTING 3D CHARACTERS", "Uploading Foji Makra & Fojan Meera Reference DNA", "active", 66)
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
    update_3d_telemetry(5, "TRANSMITTING CINEMATIC PROMPT", "Sending 8-Sec Lip-Sync Script & Audio Cues", "active", 82)
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

    resp_text = wait_for_complete_gemini_reply(driver, prev_count, max_wait_sec=60)
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
    Checks if the video was ALREADY rendered in a previous Gemini chat and downloads it!
    """
    print("🕵️ Checking if video was ALREADY rendered in a previous Gemini chat...")
    try:
        saved_url = latest_pkg.get("gemini_chat_url")
        if saved_url and "gemini.google.com/app/" in saved_url and saved_url != "https://gemini.google.com/app":
            print(f"🔗 Opening exact saved chat URL: {saved_url}")
            driver.get(saved_url)
            time.sleep(6)
        else:
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

        driver.get("https://gemini.google.com/app")
        time.sleep(4)
    except Exception as e:
        print(f"⚠️ Past chat recovery check note: {e}")
    return False

def generate_video_in_gemini(pending_pkg=None):
    with open("data/history.json", "r", encoding="utf-8") as f:
        history_data = json.load(f)

    latest_pkg = pending_pkg or (history_data["history"][-1] if history_data.get("history") else {})
    video_num = latest_pkg.get("video_id", int(history_data.get("generated_count", 0)) + 1)

    foji_img = find_image("foji")
    fojan_img = find_image("fojan")
    if not foji_img or not fojan_img:
        err = "❌ 'assets/characters/' folder mein 'foji' aur 'fojan' ki photos nahi mili!"
        update_3d_telemetry(1, "CHARACTER PHOTO MISSING", err, "error", 0)
        push_app_notification("error", "Character Photos Missing", err, "error")
        send_alert(err)
        raise FileNotFoundError(err)

    raw_dir = os.path.abspath("output/raw_videos")
    os.makedirs(raw_dir, exist_ok=True)
    output_video_path = os.path.join(raw_dir, f"raw_video_{video_num}.mp4")

    update_3d_telemetry(1, "LAUNCHING HIDDEN CHROME", "Opening Gemini Workspace & clearing popups...", "active", 12)
    driver, chrome_proc = launch_chrome_and_connect(raw_dir, headless=True)

    try:
        time.sleep(3)
        inject_cloud_cookies_if_present(driver)
        dismiss_annoying_popups(driver)

        select_flash_lite_model(driver)

        base_video_prompt = latest_pkg.get("gemini_video_prompt", "")
        if "music" not in base_video_prompt.lower():
            base_video_prompt += " Include cinematic Indian instrumental background music matching the emotion."

        existing_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
        initial_videos = len(driver.find_elements(By.TAG_NAME, "video"))
        prev_bubbles = len(get_response_bubbles(driver))

        update_3d_telemetry(2, "SELECTING CREATE VIDEO", "Clicking '+' Icon & selecting Create Video...", "active", 32)
        create_video_selected = click_plus_and_select_create_video(driver)
        if not create_video_selected:
            err_msg = "❌ Gemini '+' Menu mein 'Create video' select nahi hua! (Video Quota/Limit Exhausted)"
            update_3d_telemetry(2, "CREATE VIDEO UNAVAILABLE", err_msg, "error", 0)
            push_app_notification("error", "Gemini Video Limit Reached", err_msg, "error")
            send_alert(err_msg)
            raise RuntimeError(err_msg)

        update_3d_telemetry(3, "SETTING 9:16 PORTRAIT", "Locking vertical 9:16 reel ratio...", "active", 48)
        select_portrait_9_16_ratio(driver)

        update_3d_telemetry(4, "UPLOADING CHARACTERS", "Uploading Foji & Fojan reference photos...", "active", 64)
        upload_character_images_strictly(driver, foji_img, fojan_img)

        update_3d_telemetry(5, "SUBMITTING 3D SCRIPT", "Pasting fresh dialogue & music prompt...", "active", 80)
        paste_and_send_prompt(driver, base_video_prompt)

        time.sleep(5)
        update_3d_telemetry(5, "RENDERING 3D VIDEO IN GEMINI", "Waiting patiently for Gemini video output...", "active", 88)
        video_saved = False

        for tick in range(300):
            time.sleep(5)
            dismiss_annoying_popups(driver)

            videos = driver.find_elements(By.TAG_NAME, "video")
            if len(videos) > initial_videos:
                update_3d_telemetry(6, "DOWNLOADING RENDERED MP4", "Video generated! Extracting & verifying MP4...", "active", 95)
                if extract_and_verify_gemini_mp4(driver, raw_dir, existing_mp4s, output_video_path):
                    video_saved = True
                    break

            if is_video_currently_generating(driver):
                continue

            current_bubbles = len(get_response_bubbles(driver))
            if current_bubbles > prev_bubbles and not is_video_currently_generating(driver):
                time.sleep(4)
                if len(driver.find_elements(By.TAG_NAME, "video")) > initial_videos:
                    continue
                reply_txt = get_latest_response_text(driver).strip()
                if reply_txt:
                    update_3d_telemetry(5, "GEMINI MESSAGE / ERROR", reply_txt[:240], "error", 0)
                    push_app_notification("error", "Gemini Generation Stopped", reply_txt[:200], "error")
                    send_alert(f"⚠️ *GEMINI RESPONSE / ERROR:*\n\n{reply_txt}")
                    raise RuntimeError(reply_txt)

        if video_saved and is_valid_mp4(output_video_path):
            update_3d_telemetry(6, "REEL SENT FOR APPROVAL", "3D Video Verified & Sent for Approval!", "completed", 100)
            return output_video_path

        timeout_err = "❌ Video render ya MP4 verification પૂरा nahi ho paya."
        update_3d_telemetry(5, "RENDER / MP4 ERROR", timeout_err, "error", 0)
        push_app_notification("error", "Video Render Incomplete", timeout_err, "error")
        send_alert(timeout_err)
        raise RuntimeError(timeout_err)

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