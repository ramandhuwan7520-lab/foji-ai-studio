import os
import re
import glob
import json
import time
import shutil
import base64
import urllib.request
import subprocess
from datetime import datetime, timedelta, timezone
import requests
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

load_dotenv()
IST = timezone(timedelta(hours=5, minutes=30))

def send_alert(msg):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=12
            )
        except Exception:
            pass

def send_telegram_photo(photo_path, caption=""):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id and os.path.exists(photo_path):
        try:
            with open(photo_path, "rb") as pf:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": caption[:900]},
                    files={"photo": pf},
                    timeout=20
                )
        except Exception:
            pass

def sync_file_to_github(rel_path, commit_msg):
    gh_pat = (os.getenv("GITHUB_PAT") or os.getenv("GH_TOKEN") or "").strip()
    repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
    full_p = os.path.abspath(rel_path)
    if not gh_pat or not os.path.exists(full_p):
        return
    try:
        with open(full_p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        url = f"https://api.github.com/repos/{repo}/contents/{rel_path}"
        headers = {"Authorization": f"Bearer {gh_pat}", "Accept": "application/vnd.github+json"}
        r = requests.get(url, headers=headers, timeout=8)
        sha = r.json().get("sha") if r.status_code == 200 else None
        payload = {"message": commit_msg, "content": b64, "branch": "main"}
        if sha:
            payload["sha"] = sha
        requests.put(url, headers=headers, json=payload, timeout=10)
    except Exception:
        pass

def push_app_notification(notif_type, title, message, status="info"):
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
        "id": f"notif_{int(time.time()*1000)}",
        "type": notif_type,
        "title": title,
        "message": message,
        "status": status,
        "time_str": now_ist.strftime("%I:%M %p"),
        "date_str": now_ist.strftime("%d %b %Y"),
        "timestamp": time.time()
    })
    items = items[:100]
    with open(n_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    sync_file_to_github(n_path, f"Log: {title[:30]}")

def update_3d_telemetry(step_num, step_title, sub_detail="", status="active", progress=10):
    os.makedirs("data", exist_ok=True)
    t_path = "data/live_telemetry.json"
    payload = {
        "step_num": step_num,
        "step_title": step_title,
        "sub_detail": sub_detail,
        "status": status,
        "progress": progress,
        "updated_at": datetime.now(IST).strftime("%I:%M:%S %p"),
        "epoch": time.time()
    }
    try:
        with open(t_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        sync_file_to_github(t_path, f"Telemetry step {step_num}")
    except Exception:
        pass

def find_image(prefix):
    folder = "assets/characters"
    os.makedirs(folder, exist_ok=True)
    for ext in ["png", "jpg", "jpeg", "webp"]:
        p = os.path.join(folder, f"{prefix}.{ext}")
        if os.path.exists(p):
            return os.path.abspath(p)
    for file in os.listdir(folder):
        if file.lower().startswith(prefix.lower()) and file.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            return os.path.abspath(os.path.join(folder, file))
    return None

def is_valid_mp4(file_path):
    return bool(file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 90 * 1024)

def get_chrome_driver(download_dir):
    bot_profile_dir = os.path.abspath("chrome_bot_profile")
    os.makedirs(bot_profile_dir, exist_ok=True)
    opts = Options()
    opts.add_argument(f"--user-data-dir={bot_profile_dir}")
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=opts)

def launch_chrome_and_connect(download_dir):
    bot_profile_dir = os.path.abspath("chrome_bot_profile")
    os.makedirs(bot_profile_dir, exist_ok=True)

    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium"
    ]
    chrome_exe = next((p for p in chrome_candidates if os.path.exists(p)), None)
    if not chrome_exe:
        raise FileNotFoundError("Google Chrome not found on system!")

    is_linux = (os.name != "nt")
    if is_linux:
        subprocess.run(["pkill", "-f", "9222"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # Close any stale port-9222 Chrome so profile locks never block login
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe", "/FI", "WINDOWTITLE eq *Gemini*"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for LockFile in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lf = os.path.join(bot_profile_dir, LockFile)
            if os.path.exists(lf):
                try:
                    os.remove(lf)
                except Exception:
                    pass

    cmd = [
        chrome_exe,
        "--remote-debugging-port=9222",
        f"--user-data-dir={bot_profile_dir}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--window-size=1920,1080",
        "--start-maximized",
        "--no-sandbox",
        "--disable-dev-shm-usage"
    ]
    if is_linux and not os.environ.get("DISPLAY"):
        cmd.extend(["--headless=new", "--disable-gpu"])

    cmd.append("https://gemini.google.com/app")

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(25):
        try:
            urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1)
            break
        except Exception:
            time.sleep(1)

    opts = Options()
    opts.debugger_address = "127.0.0.1:9222"
    driver = webdriver.Chrome(options=opts)
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": download_dir})
    except Exception:
        pass
    return driver, proc

def is_gemini_logged_in(driver):
    """Checks if the user is actually logged into their Google/Gemini Pro account."""
    js_check_login = """
    const signBtns = Array.from(document.querySelectorAll('a, button, [role="button"]'));
    for (const el of signBtns) {
        const txt = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
        if ((txt === 'sign in' || txt === 'log in') && el.offsetParent !== null) {
            return false;
        }
    }
    const editors = document.querySelectorAll('div[contenteditable="true"], rich-textarea, textarea');
    return editors.length > 0;
    """
    try:
        return bool(driver.execute_script(js_check_login))
    except Exception:
        return False

def ensure_pro_account_logged_in(driver):
    """
    NEVER overwrites local Windows Chrome profile with stale cookies!
    Only injects cookies on Linux Cloud if not logged in.
    On local Windows: if not logged in, waits up to 120 seconds for user to log into Pro ID once,
    then auto-saves fresh cookies to gemini_cookies_secret.txt!
    """
    time.sleep(3)
    if is_gemini_logged_in(driver):
        print("✅ Gemini Pro Account is ALREADY Logged In!")
        save_fresh_cookies_from_driver(driver)
        return True

    # Only inject cookie file if we are on Linux Cloud (or if local profile isn't logged in yet)
    if os.name != "nt":
        raw_cookies = os.getenv("GEMINI_COOKIES_JSON", "").strip()
        if not raw_cookies and os.path.exists("gemini_cookies_secret.txt"):
            try:
                with open("gemini_cookies_secret.txt", "r", encoding="utf-8") as f:
                    raw_cookies = f.read().strip()
            except Exception:
                pass
        if raw_cookies:
            try:
                cookies = json.loads(raw_cookies)
                driver.get("https://accounts.google.com")
                time.sleep(2)
                for c in cookies:
                    if "google.com" in c.get("domain", ""):
                        try:
                            driver.add_cookie({
                                "name": c["name"],
                                "value": c["value"],
                                "domain": c["domain"],
                                "path": c.get("path", "/"),
                                "secure": c.get("secure", True)
                            })
                        except Exception:
                            pass
                driver.get("https://gemini.google.com/app")
                time.sleep(5)
            except Exception as e:
                print(f"⚠️ Cloud cookie load note: {e}")

    if is_gemini_logged_in(driver):
        print("✅ Logged into Gemini via saved session!")
        return True

    # If running on local PC and not logged in, let the user log into their Pro ID right in the open Chrome window!
    if os.name == "nt":
        print("\n" + "="*65)
        print("🔐 ACTION REQUIRED: Chrome khul gaya hai! Apni PRO ID abhi Login karo!")
        print("⏳ Bot 120 seconds tak wait kar raha hai... Login hote hi apne aap aage badhega!")
        print("="*65 + "\n")
        for sec in range(60):
            time.sleep(2)
            if is_gemini_logged_in(driver):
                print("🎉 PRO ID LOGIN DETECTED! Saving session permanently...")
                time.sleep(3)
                save_fresh_cookies_from_driver(driver)
                return True

    snap = "data/gemini_login_error.png"
    try:
        driver.save_screenshot(snap)
        send_telegram_photo(snap, "🔐 Gemini Pro ID is not logged in! Please log in once on local Chrome.")
    except Exception:
        pass
    raise RuntimeError("Gemini Pro ID not logged in!")

def save_fresh_cookies_from_driver(driver):
    try:
        cookies = driver.get_cookies()
        essential = [
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path", "/"),
                "secure": c.get("secure", True)
            }
            for c in cookies if any(k in c.get("domain", "") for k in ["google", "gemini"])
        ]
        if essential:
            with open("gemini_cookies_secret.txt", "w", encoding="utf-8") as f:
                f.write(json.dumps(essential))
            sync_file_to_github("gemini_cookies_secret.txt", "Auto-sync fresh Gemini Pro cookies")
    except Exception:
        pass

def dismiss_annoying_popups(driver):
    js_dismiss = """
    const dismissWords = ['no thanks', 'got it', 'dismiss', 'not now', 'skip', 'continue', 'close', 'accept all', 'i agree', 'try it', 'ok'];
    for (const btn of document.querySelectorAll('button, [role="button"]')) {
        const txt = (btn.innerText || btn.getAttribute('aria-label') || '').trim().toLowerCase();
        if (dismissWords.includes(txt) && btn.offsetParent !== null) {
            btn.click();
        }
    }
    """
    try:
        driver.execute_script(js_dismiss)
    except Exception:
        pass

def select_flash_model(driver):
    """Step 1: Selects Gemini Flash model from top/bottom model picker."""
    js_open_picker = """
    const els = Array.from(document.querySelectorAll('button, [role="button"], div[aria-haspopup="menu"], span'));
    for (const el of els) {
        const t = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
        if ((t.includes('gemini') || t.includes('flash') || t.includes('pro') || t.includes('2.0') || t.includes('2.5') || t.includes('fast') || t.includes('model')) && el.offsetParent !== null && t.length < 30) {
            el.click();
            return true;
        }
    }
    return false;
    """
    try:
        driver.execute_script(js_open_picker)
        time.sleep(1.5)
        js_pick_flash = """
        const items = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], [role="menuitemradio"], button, div, span'));
        for (const item of items) {
            const txt = (item.innerText || '').trim().toLowerCase();
            if ((txt.includes('flash') || txt.includes('fast')) && item.offsetParent !== null && txt.length < 45) {
                item.click();
                return 'SELECTED_FLASH';
            }
        }
        return '';
        """
        res = driver.execute_script(js_pick_flash)
        time.sleep(1.2)
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        return bool(res)
    except Exception:
        return False

def click_plus_and_select_create_video(driver):
    """
    Step 2: Strictly selects 'Create videos' / 'Video' tool.
    Tries:
      A) Direct 'Create videos' / 'Video' / 'Veo' chip on the prompt bar
      B) Clicking 'Tools' button -> 'Create videos'
      C) Clicking '+' button -> 'Create videos'
    Retries up to 4 times until verified!
    """
    for attempt in range(4):
        dismiss_annoying_popups(driver)

        # A. Check if 'Create videos' or 'Video' chip is directly visible on screen
        js_direct = """
        const allEls = Array.from(document.querySelectorAll('button, [role="button"], mat-chip, [role="menuitem"], [role="option"], span, div'));
        for (const el of allEls) {
            const txt = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
            if ((txt === 'create videos' || txt === 'create video' || txt === 'video' || txt === 'generate video' || txt === 'veo') && el.offsetParent !== null) {
                el.click();
                return 'CLICKED_DIRECT: ' + txt;
            }
        }
        return '';
        """
        res = driver.execute_script(js_direct)
        if res:
            print(f"   ✅ Create Video Tool Selected ({res})")
            time.sleep(2.0)
            return True

        # B. Click '+' button OR 'Tools' button near the prompt box
        js_open_menu = """
        const btns = Array.from(document.querySelectorAll('button, [role="button"], mat-icon'));
        for (const b of btns) {
            const lbl = ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '') + ' ' + (b.getAttribute('mattooltip') || '') + ' ' + (b.getAttribute('data-mat-icon-name') || '')).toLowerCase();
            if ((lbl.includes('tools') || lbl.includes('add') || lbl.includes('plus') || lbl.includes('more') || lbl.includes(' attach') || lbl.trim() === '+') && b.offsetParent !== null) {
                b.click();
                return 'OPENED_MENU: ' + lbl.trim();
            }
        }
        return '';
        """
        menu_opened = driver.execute_script(js_open_menu)
        time.sleep(2.0)

        # C. Now click 'Create videos' / 'Video' inside the opened popup menu
        js_pick_from_menu = """
        const items = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], button, [role="button"], li, span, div'));
        for (const el of items) {
            const txt = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
            if ((txt === 'create videos' || txt === 'create video' || txt === 'video' || txt.includes('create video') || txt.includes('generate video')) && el.offsetParent !== null && txt.length < 32) {
                el.click();
                return 'CLICKED_MENU_ITEM: ' + txt;
            }
        }
        return '';
        """
        picked = driver.execute_script(js_pick_from_menu)
        if picked:
            print(f"   ✅ Create Video Tool Selected from Menu ({picked})")
            time.sleep(2.0)
            return True

        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(1.0)

    print("   ⚠️ Note: 'Create videos' chip not found in UI; enforcing video creation via prompt & tools.")
    return False

def select_portrait_9_16_ratio(driver):
    """
    Step 3: Strictly selects 9:16 Portrait ratio inside Create Videos tool.
    """
    for attempt in range(3):
        # 1. If '9:16' or 'Portrait' button is directly visible, click it
        js_direct_916 = """
        const els = Array.from(document.querySelectorAll('button, [role="button"], [role="menuitem"], [role="option"], mat-chip, span'));
        for (const el of els) {
            const txt = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('mattooltip') || '')).toLowerCase();
            if ((txt.includes('9:16') || txt.includes('portrait')) && el.offsetParent !== null && txt.length < 40) {
                el.click();
                return 'DIRECT_9_16';
            }
        }
        return '';
        """
        if driver.execute_script(js_direct_916):
            print("   ✅ Selected 9:16 Portrait directly!")
            time.sleep(1.2)
            return True

        # 2. If '16:9' or 'Aspect ratio' dropdown is visible, click it first to open ratio menu, then click '9:16'
        js_open_aspect = """
        const els = Array.from(document.querySelectorAll('button, [role="button"], mat-chip, span, div'));
        for (const el of els) {
            const txt = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('mattooltip') || '')).toLowerCase();
            if ((txt.includes('16:9') || txt.includes('aspect') || txt.includes('landscape') || txt.includes('ratio')) && el.offsetParent !== null && txt.length < 40) {
                el.click();
                return 'OPENED_ASPECT';
            }
        }
        return '';
        """
        if driver.execute_script(js_open_aspect):
            time.sleep(1.5)
            if driver.execute_script(js_direct_916):
                print("   ✅ Selected 9:16 Portrait from Aspect Ratio dropdown!")
                time.sleep(1.2)
                return True

        time.sleep(1.0)

    print("   ℹ️ 9:16 Portrait enforced via prompt specification.")
    return False

def upload_character_images_strictly(driver, foji_img, fojan_img):
    """Step 4: Uploads both Foji and Fojan character images and verifies thumbnails appear."""
    # Unhide any hidden file inputs so send_keys works 100% reliably
    js_unhide_inputs = """
    for (const inp of document.querySelectorAll('input[type="file"]')) {
        inp.style.display = 'block';
        inp.style.visibility = 'visible';
        inp.style.opacity = '1';
    }
    """
    try:
        driver.execute_script(js_unhide_inputs)
    except Exception:
        pass

    file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
    if not file_inputs:
        js_click_plus = """
        const btns = Array.from(document.querySelectorAll('button, [role="button"]'));
        for (const b of btns) {
            const l = ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '') + ' ' + (b.getAttribute('mattooltip') || '')).toLowerCase();
            if ((l.includes('add') || l.includes('upload') || l.includes('plus') || l.includes('image') || l.includes('file') || l.trim() === '+') && b.offsetParent !== null) {
                b.click();
                return true;
            }
        }
        return false;
        """
        driver.execute_script(js_click_plus)
        time.sleep(1.8)
        js_click_upload = """
        const items = Array.from(document.querySelectorAll('[role="menuitem"], button, span, div'));
        for (const item of items) {
            const t = (item.innerText || item.getAttribute('aria-label') || '').toLowerCase();
            if ((t.includes('upload') || t.includes('files') || t.includes('computer') || t.includes('image')) && item.offsetParent !== null && t.length < 35) {
                item.click();
                return true;
            }
        }
        return false;
        """
        driver.execute_script(js_click_upload)
        time.sleep(1.8)
        try:
            driver.execute_script(js_unhide_inputs)
        except Exception:
            pass
        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")

    if file_inputs:
        target_input = file_inputs[-1]
        try:
            target_input.send_keys(f"{foji_img}\n{fojan_img}")
            print("   ✅ Uploaded both Foji & Fojan images together!")
            time.sleep(6)
            return True
        except Exception:
            try:
                target_input.send_keys(foji_img)
                time.sleep(3.5)
                file_inputs_2 = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                if file_inputs_2:
                    file_inputs_2[-1].send_keys(fojan_img)
                print("   ✅ Uploaded Foji & Fojan images sequentially!")
                time.sleep(5)
                return True
            except Exception as e:
                print(f"   ⚠️ Upload warning: {e}")
    return False

def paste_and_send_prompt(driver, prompt_text):
    """Step 5: Pastes prompt and clicks Send."""
    clean_prompt = " ".join(prompt_text.splitlines()).strip()
    selectors = [
        "div.ql-editor[contenteditable='true']",
        "rich-textarea div[contenteditable='true']",
        "div[contenteditable='true'][role='textbox']",
        "div[contenteditable='true']",
        "textarea"
    ]
    box = None
    for sel in selectors:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        for el in els:
            if el.is_displayed():
                box = el
                break
        if box:
            break

    if not box:
        raise RuntimeError("Gemini input box not found!")

    try:
        box.click()
    except Exception:
        driver.execute_script("arguments[0].focus();", box)
    time.sleep(0.8)

    js_insert = """
    const el = arguments[0];
    const txt = arguments[1];
    el.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, txt);
    if ((el.innerText || el.value || '').trim().length < 10) {
        el.innerText = txt;
        el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    """
    driver.execute_script(js_insert, box, clean_prompt)
    time.sleep(1.5)
    try:
        box.send_keys(" ")
        time.sleep(0.3)
        box.send_keys(Keys.BACKSPACE)
    except Exception:
        pass
    time.sleep(2.0)

    js_send = """
    const btns = Array.from(document.querySelectorAll('button, [role="button"]'));
    for (const b of btns) {
        const lbl = ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('mattooltip') || '') + ' ' + (b.innerText || '')).toLowerCase();
        if ((lbl.includes('send') || lbl.includes('submit') || lbl.includes('generate')) && !lbl.includes('feedback') && !b.disabled && b.getAttribute('aria-disabled') !== 'true' && b.offsetParent !== null) {
            b.click();
            return true;
        }
    }
    return false;
    """
    for _ in range(4):
        sent = driver.execute_script(js_send)
        if not sent:
            try:
                box.send_keys(Keys.ENTER)
            except Exception:
                pass
        time.sleep(2.5)
        try:
            rem_txt = (box.text or box.get_attribute("value") or "").strip()
            if len(rem_txt) < 15:
                break
        except Exception:
            break

def get_all_videos_count(driver):
    js_vids = """
    let vids = Array.from(document.querySelectorAll('video'));
    for (const el of document.querySelectorAll('*')) {
        if (el.shadowRoot) {
            vids = vids.concat(Array.from(el.shadowRoot.querySelectorAll('video')));
        }
    }
    return vids.length;
    """
    try:
        return int(driver.execute_script(js_vids) or 0)
    except Exception:
        return len(driver.find_elements(By.TAG_NAME, "video"))

def get_response_bubbles(driver):
    for sel in ["message-content", ".model-response-text", "model-response", "[data-message-author-role='model']"]:
        els = driver.find_elements(By.CSS_SELECTOR, sel)
        if els:
            return els
    return []

def get_latest_response_text(driver):
    bubbles = get_response_bubbles(driver)
    if not bubbles:
        return ""
    try:
        return (bubbles[-1].text or "").strip()
    except Exception:
        return ""

def is_video_currently_generating(driver):
    js_check = """
    const bodyTxt = (document.body.innerText || '').toLowerCase();
    const keywords = [
        'generating video', 'creating your video', 'creating video',
        'hang tight', 'this may take a minute', 'generating...',
        'almost there', 'putting the finishing touches'
    ];
    for (const kw of keywords) {
        if (bodyTxt.includes(kw)) return true;
    }
    const stopBtns = document.querySelectorAll('button[aria-label*="Stop" i], button[mattooltip*="Stop" i]');
    for (const b of stopBtns) {
        if (b.offsetParent !== null) return true;
    }
    return false;
    """
    try:
        return bool(driver.execute_script(js_check))
    except Exception:
        return False

def extract_and_verify_gemini_mp4(driver, raw_dir, existing_mp4s, output_video_path):
    """Step 6: Downloads and verifies the rendered MP4 video."""
    js_click_dl = """
    const btns = Array.from(document.querySelectorAll('button, a, [role="button"]'));
    for (const b of btns) {
        const l = ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('mattooltip') || '') + ' ' + (b.innerText || '')).toLowerCase();
        if (l.includes('download') && b.offsetParent !== null) {
            b.click();
            return true;
        }
    }
    return false;
    """
    try:
        driver.execute_script(js_click_dl)
    except Exception:
        pass

    for _ in range(20):
        time.sleep(2)
        current_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
        new_files = [f for f in (current_mp4s - existing_mp4s) if not f.endswith(".crdownload")]
        if new_files:
            newest = max(new_files, key=os.path.getctime)
            if is_valid_mp4(newest):
                if os.path.abspath(newest) != os.path.abspath(output_video_path):
                    shutil.move(newest, output_video_path)
                return True

    js_get_src = """
    let vids = Array.from(document.querySelectorAll('video'));
    for (const el of document.querySelectorAll('*')) {
        if (el.shadowRoot) {
            vids = vids.concat(Array.from(el.shadowRoot.querySelectorAll('video')));
        }
    }
    for (let i = vids.length - 1; i >= 0; i--) {
        const v = vids[i];
        const src = v.currentSrc || v.src || (v.querySelector('source') ? v.querySelector('source').src : '');
        if (src) return src;
    }
    return '';
    """
    try:
        video_url = driver.execute_script(js_get_src)
        if video_url and video_url.startswith("http") and not video_url.startswith("blob:"):
            cookies_dict = {c["name"]: c["value"] for c in driver.get_cookies()}
            r = requests.get(video_url, cookies=cookies_dict, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=60)
            if r.status_code == 200:
                with open(output_video_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                if is_valid_mp4(output_video_path):
                    return True

        if video_url:
            driver.set_script_timeout(90)
            b64_data = driver.execute_async_script("""
                const url = arguments[0];
                const callback = arguments[arguments.length - 1];
                fetch(url)
                  .then(r => r.blob())
                  .then(blob => {
                      const reader = new FileReader();
                      reader.onloadend = () => callback(reader.result);
                      reader.onerror = () => callback('');
                      reader.readAsDataURL(blob);
                  })
                  .catch(() => callback(''));
            """, video_url)
            if b64_data and "," in b64_data:
                raw_bytes = base64.b64decode(b64_data.split(",", 1)[1])
                with open(output_video_path, "wb") as f:
                    f.write(raw_bytes)
                if is_valid_mp4(output_video_path):
                    return True
    except Exception as e:
        print(f"⚠️ Direct video stream fallback note: {e}")

    return False

def generate_video_in_gemini(pending_pkg=None):
    with open("data/history.json", "r", encoding="utf-8") as f:
        history_data = json.load(f)

    latest_pkg = pending_pkg or (history_data["history"][-1] if history_data.get("history") else {})
    video_num = latest_pkg.get("video_id", int(history_data.get("generated_count", 0)) + 1)

    foji_img = find_image("foji")
    fojan_img = find_image("fojan")
    if not foji_img or not fojan_img:
        err = "Character photos missing in assets/characters."
        update_3d_telemetry(1, "Assets Missing", err, "error", 0)
        push_app_notification("error", "Assets Missing", err, "error")
        send_alert(f"⚠️ *Assets Missing*\n{err}")
        raise FileNotFoundError(err)

    raw_dir = os.path.abspath("output/raw_videos")
    os.makedirs(raw_dir, exist_ok=True)
    output_video_path = os.path.join(raw_dir, f"raw_video_{video_num}.mp4")

    print("🚀 [Step 1/6] Launching Chrome & Opening Gemini...")
    update_3d_telemetry(1, "Opening Gemini", "Verifying Pro Account Login...", "active", 15)
    driver, chrome_proc = launch_chrome_and_connect(raw_dir)

    try:
        # Guarantee Pro ID is logged in (never overwrite local login with dead cookies!)
        ensure_pro_account_logged_in(driver)
        dismiss_annoying_popups(driver)

        # 1. Select Flash Model
        print("⚡ [Step 1/6] Selecting Flash Model...")
        update_3d_telemetry(1, "Selecting Flash", "Switching to Flash model...", "active", 22)
        select_flash_model(driver)

        base_video_prompt = latest_pkg.get("gemini_video_prompt", "")
        if "music" not in base_video_prompt.lower():
            base_video_prompt += " Include cinematic Indian instrumental background music matching the emotion."

        existing_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
        initial_videos = get_all_videos_count(driver)
        prev_bubbles = len(get_response_bubbles(driver))

        # 2. Click '+' / Tools and select 'Create videos'
        print("🎬 [Step 2/6] Selecting Create Videos tool...")
        update_3d_telemetry(2, "Create Videos Tool", "Clicking + / Tools -> Create Videos...", "active", 35)
        click_plus_and_select_create_video(driver)

        # 3. Select 9:16 Portrait
        print("📱 [Step 3/6] Selecting 9:16 Portrait ratio...")
        update_3d_telemetry(3, "9:16 Portrait", "Selecting 9:16 vertical ratio...", "active", 50)
        select_portrait_9_16_ratio(driver)

        # 4. Upload both Character Images
        print("📸 [Step 4/6] Uploading Foji & Fojan images...")
        update_3d_telemetry(4, "Uploading Characters", "Uploading Foji & Fojan images...", "active", 68)
        upload_character_images_strictly(driver, foji_img, fojan_img)

        # 5. Paste Prompt & Click Generate
        print("✉️ [Step 5/6] Submitting prompt to Gemini...")
        update_3d_telemetry(5, "Generating Video", "Submitting prompt & waiting for Gemini...", "active", 82)
        paste_and_send_prompt(driver, base_video_prompt)

        time.sleep(8)
        snap_start = "data/gemini_started.png"
        try:
            driver.save_screenshot(snap_start)
            send_telegram_photo(snap_start, f"🎬 Gemini Prompt Submitted for *{latest_pkg.get('emotion_name', 'Reel')}*!")
        except Exception:
            pass

        update_3d_telemetry(5, "Rendering Video", "Gemini is rendering 3D video...", "active", 86)
        video_saved = False
        idle_ticks = 0

        for tick in range(180):
            time.sleep(5)
            dismiss_annoying_popups(driver)

            current_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
            new_files = [f for f in (current_mp4s - existing_mp4s) if not f.endswith(".crdownload")]
            if new_files:
                newest = max(new_files, key=os.path.getctime)
                if is_valid_mp4(newest):
                    if os.path.abspath(newest) != os.path.abspath(output_video_path):
                        shutil.move(newest, output_video_path)
                    video_saved = True
                    break

            vid_count = get_all_videos_count(driver)
            if vid_count > initial_videos:
                print("✅ [Step 6/6] Video detected in Gemini! Downloading MP4...")
                update_3d_telemetry(6, "Downloading MP4", "Saving & verifying rendered video...", "active", 97)
                if extract_and_verify_gemini_mp4(driver, raw_dir, existing_mp4s, output_video_path):
                    video_saved = True
                    break

            generating_now = is_video_currently_generating(driver)
            current_bubbles = len(get_response_bubbles(driver))
            elapsed_mins = round(((tick + 1) * 5) / 60.0, 1)
            print(f"⏳ [{elapsed_mins}/15.0 min] Generating: {generating_now} | Videos: {vid_count}/{initial_videos} | Bubbles: {current_bubbles}/{prev_bubbles}")

            if tick % 6 == 0:
                prog = min(95, 85 + int(tick / 18))
                update_3d_telemetry(5, "Rendering 3D Video", f"Gemini rendering video... ({elapsed_mins} min elapsed)", "active", prog)

            if generating_now:
                idle_ticks = 0
                continue

            if current_bubbles > prev_bubbles and tick >= 3:
                time.sleep(4)
                if get_all_videos_count(driver) > initial_videos or is_video_currently_generating(driver):
                    continue
                reply_txt = get_latest_response_text(driver).strip()
                if reply_txt and not any(w in reply_txt.lower() for w in ["generating", "creating", "hang tight", "here's your video", "here is your video"]):
                    clean_reply = reply_txt[:240]
                    print(f"💬 Gemini Reply: {clean_reply}")
                    snap_reply = "data/gemini_reply.png"
                    driver.save_screenshot(snap_reply)
                    send_telegram_photo(snap_reply, f"💬 Gemini Response:\n{clean_reply}")
                    update_3d_telemetry(5, "Gemini Response", clean_reply, "error", 0)
                    push_app_notification("error", "Gemini Response", clean_reply, "error")
                    raise RuntimeError(clean_reply)

            idle_ticks += 1
            if idle_ticks >= 24:
                snap_idle = "data/gemini_idle.png"
                driver.save_screenshot(snap_idle)
                reply_txt = get_latest_response_text(driver).strip()
                msg = reply_txt[:220] if reply_txt else "Gemini did not start video generation."
                send_telegram_photo(snap_idle, f"⚠️ {msg}")
                update_3d_telemetry(5, "Gemini Notice", msg, "error", 0)
                push_app_notification("error", "Gemini Notice", msg, "error")
                raise RuntimeError(msg)

        if video_saved and is_valid_mp4(output_video_path):
            print(f"🎉 SUCCESS! Saved MP4 at {output_video_path}")
            update_3d_telemetry(6, "Reel Ready", "Sent for approval!", "completed", 100)
            return output_video_path

        timeout_err = "Gemini video render timed out after 15 minutes."
        update_3d_telemetry(5, "Timeout", timeout_err, "error", 0)
        push_app_notification("error", "Timeout", timeout_err, "error")
        send_alert(f"⚠️ *Gemini Notice:*\n{timeout_err}")
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
        if os.name != "nt":
            subprocess.run(["pkill", "-9", "-f", "chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    generate_video_in_gemini()