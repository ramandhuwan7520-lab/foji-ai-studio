import os
import glob
import json
import time
import shutil
import base64
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
COOKIE_FILE = "gemini_cookies_secret.txt"


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
    items = items[:80]
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


def create_direct_chrome_driver(download_dir):
    os.makedirs(download_dir, exist_ok=True)
    bot_profile_dir = os.path.abspath("chrome_bot_profile")
    os.makedirs(bot_profile_dir, exist_ok=True)

    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        lp = os.path.join(bot_profile_dir, lock_name)
        if os.path.exists(lp):
            try:
                os.remove(lp)
            except Exception:
                pass

    opts = Options()
    if os.name == "nt":
        opts.add_argument(f"--user-data-dir={bot_profile_dir}")
        opts.add_argument("--profile-directory=Default")
        opts.add_argument("--start-maximized")
    else:
        opts.add_argument("--window-size=1920,1080")
        if not os.environ.get("DISPLAY"):
            opts.add_argument("--headless=new")

    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--mute-audio")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    opts.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(60)
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": download_dir})
    except Exception:
        pass
    return driver


def real_human_click(driver, element):
    if not element:
        return False
    try:
        ActionChains(driver).move_to_element(element).pause(0.15).click(element).perform()
        return True
    except Exception:
        try:
            driver.execute_script("""
                const el = arguments[0];
                const rect = el.getBoundingClientRect();
                const x = rect.left + rect.width / 2;
                const y = rect.top + rect.height / 2;
                ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evtType => {
                    el.dispatchEvent(new MouseEvent(evtType, {
                        view: window, bubbles: true, cancelable: true, clientX: x, clientY: y
                    }));
                });
            """, element)
            return True
        except Exception:
            return False


def is_gemini_logged_in(driver):
    js_check = """
    const btns = Array.from(document.querySelectorAll('a, button, [role="button"]'));
    for (const el of btns) {
        const txt = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
        if ((txt === 'sign in' || txt === 'log in') && el.offsetParent !== null) {
            return false;
        }
    }
    const editors = document.querySelectorAll('div[contenteditable="true"], rich-textarea, textarea');
    return editors.length > 0;
    """
    try:
        return bool(driver.execute_script(js_check))
    except Exception:
        return False


def save_cookies_from_driver(driver):
    try:
        cookies = driver.get_cookies()
        essential = [
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ".google.com"),
                "path": c.get("path", "/"),
                "secure": c.get("secure", True)
            }
            for c in cookies if any(k in c.get("domain", "") for k in ["google", "gemini"])
        ]
        if essential:
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                f.write(json.dumps(essential, indent=2))
            sync_file_to_github(COOKIE_FILE, "Update fresh Gemini Pro cookies")
    except Exception:
        pass


def open_fresh_new_chat(driver):
    """Ensures we are in a brand new chat and NOT inside old sidebar history."""
    driver.get("https://gemini.google.com/app")
    time.sleep(5)
    js_new_chat = """
    const btns = Array.from(document.querySelectorAll('a, button, [role="button"]'));
    for (const b of btns) {
        if (b.offsetParent === null) continue;
        const txt = (b.innerText || '').trim().toLowerCase();
        const aria = ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('mattooltip') || '')).toLowerCase();
        if (txt === 'new chat' || aria.includes('new chat')) {
            return b;
        }
    }
    return null;
    """
    try:
        nc_btn = driver.execute_script(js_new_chat)
        if nc_btn and "/app/" in driver.current_url:
            real_human_click(driver, nc_btn)
            time.sleep(2.5)
    except Exception:
        pass


def load_and_ensure_login(driver):
    open_fresh_new_chat(driver)

    if is_gemini_logged_in(driver):
        print("✅ Gemini Pro Account is Logged In!")
        save_cookies_from_driver(driver)
        return True

    raw_cookies = os.getenv("GEMINI_COOKIES_JSON", "").strip()
    if not raw_cookies and os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                raw_cookies = f.read().strip()
        except Exception:
            pass

    if raw_cookies:
        print("🔐 Injecting saved Google/Gemini cookies...")
        try:
            cookies = json.loads(raw_cookies)
            driver.get("https://www.google.com")
            time.sleep(2)
            for c in cookies:
                try:
                    driver.add_cookie({
                        "name": c["name"],
                        "value": c["value"],
                        "domain": ".google.com",
                        "path": c.get("path", "/"),
                        "secure": True
                    })
                except Exception:
                    pass
            driver.get("https://gemini.google.com")
            time.sleep(2)
            for c in cookies:
                try:
                    driver.add_cookie({
                        "name": c["name"],
                        "value": c["value"],
                        "path": c.get("path", "/"),
                        "secure": True
                    })
                except Exception:
                    pass
            open_fresh_new_chat(driver)
        except Exception as e:
            print(f"⚠️ Cookie injection error: {e}")

    if is_gemini_logged_in(driver):
        print("✅ Gemini Login Verified via Cookies!")
        return True

    if os.name == "nt":
        print("\n" + "="*68)
        print("🔐 PRO LOGIN NEEDED: Khule hue Chrome mein apni Gemini PRO ID login karo!")
        print("⏳ Bot 3 minute tak wait kar raha hai... Login hote hi khud aage badhega!")
        print("="*68 + "\n")
        for _ in range(90):
            time.sleep(2)
            if is_gemini_logged_in(driver):
                print("🎉 PRO ID LOGIN DETECTED! Saving cookies permanently...")
                time.sleep(3)
                save_cookies_from_driver(driver)
                return True

    raise RuntimeError("Gemini Pro ID not logged in!")


def dismiss_popups(driver):
    js = """
    const words = ['no thanks', 'got it', 'dismiss', 'not now', 'skip', 'continue', 'close', 'accept all', 'i agree', 'try it', 'ok'];
    for (const b of document.querySelectorAll('button, [role="button"]')) {
        if (b.closest('mat-sidenav, nav, aside')) continue;
        const t = (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase();
        if (words.includes(t) && b.offsetParent !== null) b.click();
    }
    """
    try:
        driver.execute_script(js)
    except Exception:
        pass


# ==============================================================================
# 🎯 STRICT CHAT-BOX & MODEL PICKER FUNCTIONS (NEVER TOUCHES LEFT SIDEBAR!)
# ==============================================================================
def select_flash_model_strictly(driver):
    """
    Step 1: Strictly ignores the left chat history sidebar!
    Finds the Model Switcher either:
      1) Inside the bottom chat input box bar (right/left of the prompt box), OR
      2) In the top main header bar (above the chat area, x > 260, y < 90).
    Then clicks 'Flash' from the opened menu overlay.
    """
    dismiss_popups(driver)
    js_find_model_picker = """
    const box = document.querySelector('div[contenteditable="true"], rich-textarea, textarea');
    const boxRect = box ? box.getBoundingClientRect() : {left: 350, top: window.innerHeight - 200};

    const candidates = Array.from(document.querySelectorAll(
        'bard-mode-switcher button, [data-test-id*="model" i], [data-test-id*="mode" i], button, [role="button"]'
    ));

    for (const el of candidates) {
        if (el.offsetParent === null) continue;
        // STRICT RULE: Never click anything inside left sidebar / chat history!
        if (el.closest('mat-sidenav, side-navigation, nav, aside, [role="navigation"], .conversations-container, .chat-history')) continue;

        const r = el.getBoundingClientRect();
        // Must be either in the top header (y < 90, x > 240) OR inside the bottom chat bar (near boxRect)
        const inTopHeader = (r.top >= 0 && r.top < 95 && r.left > 240);
        const inBottomChatBar = (r.left >= boxRect.left - 80 && Math.abs(r.top - boxRect.top) < 160);
        if (!inTopHeader && !inBottomChatBar) continue;

        const txt = (el.innerText || '').trim().toLowerCase();
        const aria = ((el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('mattooltip') || '')).toLowerCase();

        if (
            txt === 'flash' || txt === 'pro' || txt === 'fast' ||
            txt.includes('2.5 flash') || txt.includes('2.0 flash') ||
            txt.includes('2.5 pro') || txt.includes('2.0 pro') ||
            txt.includes('gemini 2.') || txt.includes('thinking') ||
            aria.includes('model') || aria.includes('switch mode') || aria.includes('mode switcher')
        ) {
            if (txt.length < 28) return el;
        }
    }
    return null;
    """
    try:
        picker_btn = driver.execute_script(js_find_model_picker)
        if picker_btn:
            cur_label = (picker_btn.text or "").strip()
            print(f"   🔍 Found Model Switcher in Chat Area: '{cur_label}'")
            real_human_click(driver, picker_btn)
            time.sleep(1.8)

            # Click 'Flash' inside the popup overlay container (.cdk-overlay-container)
            js_pick_flash_from_overlay = """
            const overlay = document.querySelector('.cdk-overlay-container') || document.body;
            const items = Array.from(overlay.querySelectorAll('[role="menuitem"], [role="option"], [role="menuitemradio"], .mat-mdc-menu-item, button, li'));
            for (const item of items) {
                if (item.offsetParent === null) continue;
                if (item.closest('mat-sidenav, side-navigation, nav, aside')) continue;
                const t = (item.innerText || '').trim().toLowerCase();
                if ((t.includes('flash') || t.includes('fast')) && !t.includes('pro ') && t.length < 90) {
                    return item;
                }
            }
            return null;
            """
            flash_item = driver.execute_script(js_pick_flash_from_overlay)
            if flash_item:
                real_human_click(driver, flash_item)
                print("   ✅ Selected 'Flash' model from Model menu!")
                time.sleep(1.5)
                return True

            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.8)
    except Exception as e:
        print(f"   ⚠️ Model switcher note: {e}")
    return False


def click_chatbox_plus_and_select_create_video(driver):
    """
    Step 2: Strictly finds the '+' (Add / Tools) button INSIDE the bottom Chat Input Box container,
    clicks it, and selects 'Create video' / 'Create videos' from the popup menu!
    Never clicks anything in the left sidebar!
    """
    for attempt in range(3):
        dismiss_popups(driver)

        # 1. Check if 'Create videos' / 'Create video' chip is already visible inside the chat area or popup overlay
        js_find_create_video_option = """
        const box = document.querySelector('div[contenteditable="true"], rich-textarea, textarea');
        const boxRect = box ? box.getBoundingClientRect() : {left: 320, top: window.innerHeight - 220};

        const els = Array.from(document.querySelectorAll(
            '.cdk-overlay-container [role="menuitem"], .cdk-overlay-container [role="option"], .cdk-overlay-container button, .cdk-overlay-container .mat-mdc-menu-item, button, [role="button"], mat-chip, span'
        ));
        for (const el of els) {
            if (el.offsetParent === null) continue;
            if (el.closest('mat-sidenav, side-navigation, nav, aside, [role="navigation"], .conversations-container')) continue;
            const r = el.getBoundingClientRect();
            if (r.left < 260) continue; // Never touch left sidebar

            const txt = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
            if (
                txt === 'create videos' || txt === 'create video' ||
                txt === 'generate video' || txt === 'generate videos' ||
                txt === 'video' || txt === 'veo'
            ) {
                return el;
            }
        }
        return null;
        """
        direct_vid = driver.execute_script(js_find_create_video_option)
        if direct_vid:
            real_human_click(driver, direct_vid)
            print("   ✅ Clicked 'Create videos' in Chat Box!")
            time.sleep(2.2)
            return True

        # 2. Find the '+' button (or 'Tools' button) strictly anchored to the Chat Input Box
        js_find_chatbox_plus = """
        const box = document.querySelector('div[contenteditable="true"], rich-textarea, textarea');
        if (!box) return null;
        const boxRect = box.getBoundingClientRect();

        // Search buttons inside or immediately next to the chat input container
        const chatContainer = box.closest('input-container, .input-area, .input-box, form, main') || document.body;
        const btns = Array.from(chatContainer.querySelectorAll('button, [role="button"]'));

        for (const b of btns) {
            if (b.offsetParent === null) continue;
            if (b.closest('mat-sidenav, side-navigation, nav, aside')) continue;
            const r = b.getBoundingClientRect();

            // Must be horizontally near or inside the chat box (x > 260) and vertically within 140px of the text input!
            if (r.left < 260 || Math.abs(r.top - boxRect.top) > 140) continue;

            const txt = (b.innerText || '').trim().toLowerCase();
            const aria = ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('mattooltip') || '') + ' ' + (b.getAttribute('data-mat-icon-name') || '')).toLowerCase();
            const iconEl = b.querySelector('mat-icon, i, span.google-symbols, svg');
            const iconTxt = iconEl ? (iconEl.innerText || iconEl.getAttribute('data-mat-icon-name') || '').trim().toLowerCase() : '';

            if (
                txt === '+' || iconTxt === 'add' || iconTxt === 'add_circle' ||
                aria.includes('add') || aria.includes('plus') || aria.includes('upload') ||
                aria.includes('attach') || aria.includes('more') || aria.includes('tools')
            ) {
                return b;
            }
        }
        return null;
        """
        plus_btn = driver.execute_script(js_find_chatbox_plus)
        if plus_btn:
            print(f"   🖱️ Clicking '+' button inside Chat Box (Attempt {attempt+1})...")
            real_human_click(driver, plus_btn)
            time.sleep(2.0)

            vid_opt = driver.execute_script(js_find_create_video_option)
            if vid_opt:
                real_human_click(driver, vid_opt)
                print("   ✅ Selected 'Create videos' from '+' menu inside Chat Box!")
                time.sleep(2.2)
                return True

        # 3. Also check if there is a 'Tools' button right next to '+' inside the Chat Box
        js_find_chatbox_tools = """
        const box = document.querySelector('div[contenteditable="true"], rich-textarea, textarea');
        if (!box) return null;
        const boxRect = box.getBoundingClientRect();
        for (const b of document.querySelectorAll('button, [role="button"]')) {
            if (b.offsetParent === null) continue;
            if (b.closest('mat-sidenav, side-navigation, nav, aside')) continue;
            const r = b.getBoundingClientRect();
            if (r.left < 260 || Math.abs(r.top - boxRect.top) > 140) continue;
            const t = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('mattooltip') || '')).toLowerCase();
            if (t.includes('tool') || t.includes('tune') || t.includes('video')) return b;
        }
        return null;
        """
        tools_btn = driver.execute_script(js_find_chatbox_tools)
        if tools_btn:
            print("   🖱️ Clicking 'Tools' button inside Chat Box...")
            real_human_click(driver, tools_btn)
            time.sleep(2.0)
            vid_opt2 = driver.execute_script(js_find_create_video_option)
            if vid_opt2:
                real_human_click(driver, vid_opt2)
                print("   ✅ Selected 'Create videos' from Tools menu!")
                time.sleep(2.2)
                return True

        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(1.0)

    return False


def select_chatbox_portrait_9_16(driver):
    """
    Step 3: Strictly inside the Chat Box (or its popup menu), selects '9:16' / 'Portrait'.
    """
    js_find_916 = """
    const box = document.querySelector('div[contenteditable="true"], rich-textarea, textarea');
    const boxRect = box ? box.getBoundingClientRect() : {left: 320, top: window.innerHeight - 220};

    const els = Array.from(document.querySelectorAll(
        '.cdk-overlay-container [role="menuitem"], .cdk-overlay-container [role="option"], .cdk-overlay-container button, button, [role="button"], mat-chip, span'
    ));
    for (const el of els) {
        if (el.offsetParent === null) continue;
        if (el.closest('mat-sidenav, side-navigation, nav, aside')) continue;
        const r = el.getBoundingClientRect();
        if (r.left < 260) continue;

        const txt = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('mattooltip') || '')).toLowerCase();
        if ((txt.includes('9:16') || txt.includes('portrait')) && txt.length < 38) {
            return el;
        }
    }
    return null;
    """
    for _ in range(3):
        btn_916 = driver.execute_script(js_find_916)
        if btn_916:
            real_human_click(driver, btn_916)
            print("   ✅ Selected 9:16 Portrait inside Chat Box!")
            time.sleep(1.5)
            return True

        # If '16:9' or 'Aspect ratio' chip is showing inside the Chat Box, click it to open dropdown
        js_find_ratio_chip = """
        const box = document.querySelector('div[contenteditable="true"], rich-textarea, textarea');
        if (!box) return null;
        const boxRect = box.getBoundingClientRect();
        for (const el of document.querySelectorAll('button, [role="button"], mat-chip')) {
            if (el.offsetParent === null) continue;
            if (el.closest('mat-sidenav, side-navigation, nav, aside')) continue;
            const r = el.getBoundingClientRect();
            if (r.left < 260 || Math.abs(r.top - boxRect.top) > 160) continue;
            const txt = ((el.innerText || '') + ' ' + (el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('mattooltip') || '')).toLowerCase();
            if (txt.includes('16:9') || txt.includes('aspect') || txt.includes('landscape') || txt.includes('ratio') || txt.includes('crop')) {
                return el;
            }
        }
        return null;
        """
        ratio_chip = driver.execute_script(js_find_ratio_chip)
        if ratio_chip:
            print("   🖱️ Clicking Aspect Ratio chip (16:9 -> 9:16) inside Chat Box...")
            real_human_click(driver, ratio_chip)
            time.sleep(1.8)
            btn_916_menu = driver.execute_script(js_find_916)
            if btn_916_menu:
                real_human_click(driver, btn_916_menu)
                print("   ✅ Selected 9:16 Portrait from Chat Box ratio menu!")
                time.sleep(1.5)
                return True

        time.sleep(1.0)
    return False


def upload_character_images_in_chatbox(driver, foji_img, fojan_img):
    """
    Step 4: Uploads both Foji & Fojan character images directly into the current Chat Box.
    """
    js_unhide = """
    for (const inp of document.querySelectorAll('input[type="file"]')) {
        inp.style.display = 'block';
        inp.style.visibility = 'visible';
        inp.style.opacity = '1';
        inp.removeAttribute('hidden');
    }
    """
    try:
        driver.execute_script(js_unhide)
    except Exception:
        pass

    file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
    if not file_inputs:
        # Click the '+' button inside the Chat Box to spawn the file input
        js_find_chatbox_plus = """
        const box = document.querySelector('div[contenteditable="true"], rich-textarea, textarea');
        if (!box) return null;
        const boxRect = box.getBoundingClientRect();
        for (const b of document.querySelectorAll('button, [role="button"]')) {
            if (b.offsetParent === null) continue;
            if (b.closest('mat-sidenav, side-navigation, nav, aside')) continue;
            const r = b.getBoundingClientRect();
            if (r.left < 260 || Math.abs(r.top - boxRect.top) > 140) continue;
            const aria = ((b.getAttribute('aria-label') || '') + ' ' + (b.innerText || '') + ' ' + (b.getAttribute('mattooltip') || '')).toLowerCase();
            const iconEl = b.querySelector('mat-icon, span.google-symbols');
            const iconTxt = iconEl ? (iconEl.innerText || '').trim().toLowerCase() : '';
            if (iconTxt === 'add' || iconTxt === 'add_circle' || aria.includes('add') || aria.includes('upload') || aria.includes('plus') || aria.includes('attach') || aria.trim() === '+') {
                return b;
            }
        }
        return null;
        """
        plus_b = driver.execute_script(js_find_chatbox_plus)
        if plus_b:
            real_human_click(driver, plus_b)
            time.sleep(1.8)
            try:
                driver.execute_script(js_unhide)
            except Exception:
                pass
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")

            if not file_inputs:
                js_find_upload_opt = """
                const overlay = document.querySelector('.cdk-overlay-container') || document.body;
                for (const item of overlay.querySelectorAll('[role="menuitem"], [role="option"], button, .mat-mdc-menu-item, li, span')) {
                    if (item.offsetParent === null) continue;
                    const t = (item.innerText || item.getAttribute('aria-label') || '').trim().toLowerCase();
                    if ((t.includes('upload') || t.includes('files') || t.includes('image') || t.includes('photo')) && t.length < 35) {
                        return item;
                    }
                }
                return null;
                """
                up_opt = driver.execute_script(js_find_upload_opt)
                if up_opt:
                    real_human_click(driver, up_opt)
                    time.sleep(1.5)
                    try:
                        driver.execute_script(js_unhide)
                    except Exception:
                        pass
                    file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")

    if file_inputs:
        target_input = file_inputs[-1]
        try:
            target_input.send_keys(f"{foji_img}\n{fojan_img}")
            print("   ✅ Uploaded both Foji & Fojan images into Chat Box!")
            time.sleep(6)
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            return True
        except Exception:
            try:
                target_input.send_keys(foji_img)
                time.sleep(3.5)
                file_inputs_2 = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                if file_inputs_2:
                    file_inputs_2[-1].send_keys(fojan_img)
                print("   ✅ Uploaded Foji & Fojan images sequentially into Chat Box!")
                time.sleep(5)
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
                return True
            except Exception as e:
                print(f"   ⚠️ Upload warning: {e}")
    return False


def paste_and_send_prompt_in_chatbox(driver, prompt_text):
    """
    Step 5: Pastes the fresh prompt inside the Chat Box and clicks Send.
    """
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
        raise RuntimeError("Gemini chat box not found!")

    real_human_click(driver, box)
    time.sleep(0.6)

    js_insert = """
    const el = arguments[0];
    const txt = arguments[1];
    el.focus();
    document.execCommand('selectAll', false, null);
    document.execCommand('delete', false, null);
    document.execCommand('insertText', false, txt);
    if ((el.innerText || el.value || '').trim().length < 10) {
        el.innerText = txt;
        el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    """
    driver.execute_script(js_insert, box, clean_prompt)
    time.sleep(1.2)
    try:
        box.send_keys(" ")
        time.sleep(0.2)
        box.send_keys(Keys.BACKSPACE)
    except Exception:
        pass
    time.sleep(2.0)

    js_find_send = """
    const box = document.querySelector('div[contenteditable="true"], rich-textarea, textarea');
    const boxRect = box ? box.getBoundingClientRect() : {top: window.innerHeight - 200};
    for (const b of document.querySelectorAll('button, [role="button"]')) {
        if (b.offsetParent === null) continue;
        if (b.closest('mat-sidenav, side-navigation, nav, aside')) continue;
        const r = b.getBoundingClientRect();
        if (r.left < 260 || Math.abs(r.top - boxRect.top) > 160) continue;
        const lbl = ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('mattooltip') || '') + ' ' + (b.innerText || '')).toLowerCase();
        if ((lbl.includes('send') || lbl.includes('submit') || lbl.includes('generate')) && !lbl.includes('feedback') && !b.disabled && b.getAttribute('aria-disabled') !== 'true') {
            return b;
        }
    }
    return null;
    """
    for _ in range(4):
        send_btn = driver.execute_script(js_find_send)
        if send_btn:
            real_human_click(driver, send_btn)
        else:
            try:
                box.send_keys(Keys.ENTER)
            except Exception:
                pass
        time.sleep(2.5)
        try:
            rem_txt = (box.text or box.get_attribute("value") or "").strip()
            if len(rem_txt) < 15:
                print("   ✅ Prompt submitted in Chat Box!")
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
    js_find_dl = """
    const btns = Array.from(document.querySelectorAll('button, a, [role="button"]'));
    for (const b of btns) {
        if (b.offsetParent === null) continue;
        if (b.closest('mat-sidenav, side-navigation, nav, aside')) continue;
        const l = ((b.getAttribute('aria-label') || '') + ' ' + (b.getAttribute('mattooltip') || '') + ' ' + (b.innerText || '')).toLowerCase();
        if (l.includes('download')) return b;
    }
    return null;
    """
    try:
        dl_btn = driver.execute_script(js_find_dl)
        if dl_btn:
            real_human_click(driver, dl_btn)
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
    os.makedirs("data", exist_ok=True)
    if not os.path.exists("data/history.json"):
        with open("data/history.json", "w", encoding="utf-8") as f:
            json.dump({"generated_count": 0, "history": []}, f)

    with open("data/history.json", "r", encoding="utf-8") as f:
        history_data = json.load(f)

    if not pending_pkg:
        try:
            import dashboard_app
            track, next_part = dashboard_app.get_next_track_and_part(history_data)
            new_id = int(history_data.get("generated_count", 0)) + 1
            used_lines = [item.get("dialogue_line_1_hinglish", "") for item in history_data.get("history", [])]
            pending_pkg = dashboard_app.build_fresh_prompt_package(track, next_part, new_id, used_lines)
        except Exception:
            pending_pkg = {}

    video_num = pending_pkg.get("video_id", int(history_data.get("generated_count", 0)) + 1)

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

    print("🚀 [Step 1/6] Opening Fresh Gemini Chat (Ignoring Sidebar History)...")
    update_3d_telemetry(1, "Opening New Chat", "Verifying Pro Login & New Chat...", "active", 15)
    driver = create_direct_chrome_driver(raw_dir)

    try:
        load_and_ensure_login(driver)
        dismiss_popups(driver)

        # 1. Select Flash Model from Model Picker (NEVER from sidebar)
        print("⚡ [Step 1/6] Selecting Flash Model from Model Switcher...")
        update_3d_telemetry(1, "Selecting Flash", "Choosing Flash model in New Chat...", "active", 25)
        select_flash_model_strictly(driver)

        # 2. Click '+' inside Chat Box and select 'Create videos'
        print("🎬 [Step 2/6] Clicking '+' in Chat Box -> Selecting Create Videos...")
        update_3d_telemetry(2, "Create Videos Tool", "Clicking + in Chat Box -> Create Videos...", "active", 40)
        click_chatbox_plus_and_select_create_video(driver)

        # 3. Select 9:16 Portrait inside Chat Box
        print("📱 [Step 3/6] Selecting 9:16 Portrait ratio in Chat Box...")
        update_3d_telemetry(3, "9:16 Portrait", "Selecting 9:16 Portrait in Chat Box...", "active", 55)
        select_chatbox_portrait_9_16(driver)

        # 4. Upload both Character Images into Chat Box
        print("📸 [Step 4/6] Uploading Foji & Fojan character images in Chat Box...")
        update_3d_telemetry(4, "Uploading Characters", "Uploading Foji & Fojan images...", "active", 70)
        upload_character_images_in_chatbox(driver, foji_img, fojan_img)

        base_video_prompt = pending_pkg.get("gemini_video_prompt") or (
            f"Create a 9:16 Portrait 3D Pixar Disney style 8K animated video using the two uploaded character images. "
            f"Image 1 is Foji Makra (Indian Army Soldier with plain shoulder straps, NO stars). "
            f"Image 2 is Fojan Meera. Episode #{video_num}. "
            f"Foji Makra speaks in Hindi with lip-sync: 'Meera, sarhad ki har subah tumhari yaad se shuru hoti hai!' "
            f"Fojan Meera replies in Hindi with lip-sync: 'Aur meri har shaam aapke laut aane ki dua se, Foji sahab!' "
            f"Include soulful Bollywood romantic instrumental background music."
        )

        existing_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
        initial_videos = get_all_videos_count(driver)
        prev_bubbles = len(get_response_bubbles(driver))

        # 5. Paste Fresh Prompt in Chat Box & Click Generate
        print("✉️ [Step 5/6] Pasting fresh prompt in Chat Box & clicking Generate...")
        update_3d_telemetry(5, "Generating Video", "Submitting prompt & waiting for video...", "active", 82)
        paste_and_send_prompt_in_chatbox(driver, base_video_prompt)

        time.sleep(8)
        snap_start = "data/gemini_started.png"
        try:
            driver.save_screenshot(snap_start)
            send_telegram_photo(snap_start, f"🎬 Gemini Prompt Submitted for *{pending_pkg.get('emotion_name', f'Reel #{video_num}')}*!")
        except Exception:
            pass

        update_3d_telemetry(5, "Rendering Video", "Waiting for Gemini video to finish...", "active", 86)
        video_saved = False
        idle_ticks = 0

        for tick in range(180):
            time.sleep(5)
            dismiss_popups(driver)

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
                update_3d_telemetry(5, "Rendering Video", f"Gemini rendering video... ({elapsed_mins} min elapsed)", "active", prog)

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


if __name__ == "__main__":
    generate_video_in_gemini()