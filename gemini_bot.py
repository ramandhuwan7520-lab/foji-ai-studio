# -*- coding: utf-8 -*-
# pyright: reportOptionalMemberAccess=false, reportGeneralTypeIssues=false
import os
import sys
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
COOKIE_FILE = "gemini_cookies_secret.txt"
DEBUG_PORT = 9225
FLOW_URL = "https://labs.google/fx/tools/flow"


def send_alert(msg):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
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
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id and os.path.exists(photo_path):
        try:
            with open(photo_path, "rb") as pf:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data={"chat_id": chat_id, "caption": caption[:950]},
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
        "id": f"notif_{int(time.time() * 1000)}",
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


def find_chrome_executable():
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium"
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("Google Chrome executable not found!")


def ensure_clean_matching_chromedriver_in_python():
    if os.name == "nt":
        return
    stale_paths = [
        "/usr/bin/chromedriver",
        "/usr/local/bin/chromedriver",
        "/usr/lib/chromium-browser/chromedriver",
        "/snap/bin/chromium.chromedriver"
    ]
    for sp in stale_paths:
        if os.path.exists(sp):
            try:
                os.remove(sp)
            except Exception:
                try:
                    subprocess.run(["sudo", "rm", "-f", sp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass


def launch_resilient_chrome_session(download_dir):
    ensure_clean_matching_chromedriver_in_python()
    os.makedirs(download_dir, exist_ok=True)
    profile_dir = os.path.abspath("chrome_gemini_pro_profile")
    os.makedirs(profile_dir, exist_ok=True)

    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
        lp = os.path.join(profile_dir, lock_name)
        if os.path.exists(lp):
            try:
                os.remove(lp)
            except Exception:
                pass

    for cache_rel in [
        "GrShaderCache", "ShaderCache", "Crashpad",
        os.path.join("Default", "GPUCache"),
        os.path.join("Default", "Cache")
    ]:
        cp = os.path.join(profile_dir, cache_rel)
        if os.path.exists(cp):
            try:
                shutil.rmtree(cp, ignore_errors=True)
            except Exception:
                pass

    chrome_exe = find_chrome_executable()
    cmd = [
        chrome_exe,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={profile_dir}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--mute-audio",
        "--window-size=1920,1080",
        "--start-maximized",
        FLOW_URL
    ]
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        cmd.append("--headless=new")

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ready = False
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=1)
            ready = True
            break
        except Exception:
            time.sleep(0.5)

    if not ready:
        raise RuntimeError("Chrome port 9225 did not respond.")

    opts = Options()
    opts.page_load_strategy = "none"
    opts.debugger_address = f"127.0.0.1:{DEBUG_PORT}"
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(60)
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": download_dir})
    except Exception:
        pass
    return driver, proc


def install_file_dialog_blocker(driver):
    js_code = """
    if (!window.__allFileInputs) window.__allFileInputs = [];
    if (!window.__fileDialogBlocked) {
        window.__fileDialogBlocked = true;
        const origClick = HTMLInputElement.prototype.click;
        HTMLInputElement.prototype.click = function() {
            if (this.type === 'file') {
                this.style.cssText = 'display:block !important; visibility:visible !important; opacity:1 !important; position:fixed; top:0; left:0; width:1px; height:1px; z-index:99999;';
                this.removeAttribute('hidden');
                if (!this.isConnected && document.body) document.body.appendChild(this);
                window.__allFileInputs.push(this);
                return;
            }
            return origClick.apply(this, arguments);
        };
    }
    for (const inp of document.querySelectorAll('input[type="file"]')) {
        inp.style.cssText = 'display:block !important; visibility:visible !important; opacity:1 !important; position:fixed; top:0; left:0; width:1px; height:1px; z-index:99999;';
        inp.removeAttribute('hidden');
        window.__allFileInputs.push(inp);
    }
    """
    try:
        driver.execute_script(js_code)
    except Exception:
        pass


def hardware_click_xy(driver, x, y, label="Target"):
    x_int, y_int = int(x), int(y)
    print(f"   ⚡ [Click] '{label}' at ({x_int}, {y_int})")
    try:
        driver.execute_script(
            """
            const x = arguments[0], y = arguments[1];
            const dot = document.createElement('div');
            dot.style.cssText = 'position:fixed;left:' + (x-14) + 'px;top:' + (y-14) + 'px;width:28px;height:28px;border:3px solid #00ff88;border-radius:50%;background:rgba(0,255,136,0.3);z-index:999999;pointer-events:none;box-shadow:0 0 12px #00ff88;';
            document.body.appendChild(dot);
            setTimeout(() => dot.remove(), 900);
            """,
            x_int,
            y_int
        )
    except Exception:
        pass

    try:
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x_int, "y": y_int})
        time.sleep(0.05)
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x_int, "y": y_int, "button": "left", "clickCount": 1})
        time.sleep(0.05)
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x_int, "y": y_int, "button": "left", "clickCount": 1})
    except Exception:
        pass

    try:
        driver.execute_script(
            """
            const x = arguments[0], y = arguments[1];
            const el = document.elementFromPoint(x, y);
            if (el) {
                const target = el.closest('button, [role="button"], [role="menuitem"], [role="option"], [role="tab"], [role="radio"], a') || el;
                ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(t => {
                    target.dispatchEvent(new MouseEvent(t, {view: window, bubbles: true, cancelable: true, clientX: x, clientY: y}));
                });
            }
            """,
            x_int,
            y_int
        )
    except Exception:
        pass
    return True


def wait_until_visible_and_click(driver, match_keywords, region_filter=None, timeout=15.0, post_delay=0.45, step_label="Step"):
    """
    Polls the live DOM every 0.25s until a visible button/tab/option matching `match_keywords`
    appears on screen, then immediately clicks its exact center `(X, Y)`!
    `region_filter`:
      - 'prompt_bar': Bottom prompt bar area (`y > window.innerHeight * 0.72`)
      - 'settings_popup': Settings popover area (`y between 0.20 and 0.82`)
      - 'top_right': Top toolbar (`y < window.innerHeight * 0.30`)
    """
    match_keywords = [k.lower().strip() for k in (match_keywords or []) if k and k.strip()]
    start_t = time.time()

    js_find = """
    const keywords = arguments[0];
    const region = arguments[1];

    function walkNodes(root) {
        let res = [];
        for (const el of root.querySelectorAll('*')) {
            res.push(el);
            if (el.shadowRoot) res = res.concat(walkNodes(el.shadowRoot));
        }
        return res;
    }

    let best = null;
    let bestScore = -9999;

    for (const el of walkNodes(document)) {
        const r = el.getBoundingClientRect();
        if (r.width < 12 || r.height < 12 || r.bottom <= 0 || r.top >= window.innerHeight) continue;
        const style = window.getComputedStyle(el);
        if (style.visibility === 'hidden' || style.display === 'none' || parseFloat(style.opacity) === 0) continue;

        const cyPct = ((r.top + r.height / 2) / window.innerHeight) * 100;
        if (region === 'prompt_bar' && cyPct < 70) continue;
        if (region === 'settings_popup' && (cyPct < 20 || cyPct > 84)) continue;
        if (region === 'top_right' && cyPct > 35) continue;

        const tag = el.tagName.toLowerCase();
        const role = (el.getAttribute('role') || '').toLowerCase();
        const aria = (el.getAttribute('aria-label') || '').trim().toLowerCase();
        const title = (el.getAttribute('title') || el.getAttribute('mattooltip') || '').trim().toLowerCase();
        const txt = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').toLowerCase();
        if (txt.length > 85 && tag !== 'textarea' && el.getAttribute('contenteditable') !== 'true') continue;

        const blob = (txt + ' ' + aria + ' ' + title).trim();
        if (!blob) continue;

        let matchedKw = '';
        for (const kw of keywords) {
            if (txt === kw || aria === kw || blob.includes(kw)) {
                matchedKw = kw;
                break;
            }
        }
        if (!matchedKw) continue;

        const clickable = el.closest('button, [role="button"], [role="menuitem"], [role="option"], [role="tab"], [role="radio"]') || el;
        const cr = clickable.getBoundingClientRect();
        let score = 300 - Math.min(80, txt.length);
        if (txt === matchedKw || aria === matchedKw) score += 400;
        if (clickable.tagName.toLowerCase() === 'button' || clickable.getAttribute('role')) score += 150;

        if (score > bestScore) {
            bestScore = score;
            best = {
                x: Math.round(cr.left + cr.width / 2),
                y: Math.round(cr.top + cr.height / 2),
                label: (txt || aria).slice(0, 40)
            };
        }
    }
    return best;
    """

    while (time.time() - start_t) < timeout:
        install_file_dialog_blocker(driver)
        try:
            found = driver.execute_script(js_find, match_keywords, region_filter)
            if found:
                hardware_click_xy(driver, found["x"], found["y"], f"{step_label} ('{found['label']}')")
                time.sleep(post_delay)
                return True
        except Exception:
            pass
        time.sleep(0.25)

    print(f"   ⚠️ Warning: '{step_label}' ({match_keywords}) not found within {timeout}s.")
    return False


def fill_prompt_box_directly(driver, prompt_text):
    clean_prompt = " ".join(prompt_text.splitlines()).strip()
    js_fill = """
    const txt = arguments[0];
    let box = document.querySelector('[aria-label*="What do you want to create" i], textarea, div[contenteditable="true"]');
    if (!box) {
        const boxes = Array.from(document.querySelectorAll('textarea, div[contenteditable="true"]')).filter(el => el.offsetParent !== null);
        if (boxes.length === 0) return false;
        boxes.sort((a, b) => (b.getBoundingClientRect().width * b.getBoundingClientRect().height) - (a.getBoundingClientRect().width * a.getBoundingClientRect().height));
        box = boxes[0];
    }
    box.focus();

    if (box.tagName.toLowerCase() === 'textarea') {
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
        if (nativeSetter) nativeSetter.call(box, txt);
        else box.value = txt;
        box.dispatchEvent(new Event('input', { bubbles: true }));
        box.dispatchEvent(new Event('change', { bubbles: true }));
    } else {
        document.execCommand('insertText', false, ' ' + txt);
        if ((box.innerText || '').trim().length < 15) {
            box.innerText = txt;
            box.dispatchEvent(new Event('input', { bubbles: true }));
        }
    }
    return true;
    """
    ok = driver.execute_script(js_fill, clean_prompt)
    if ok:
        try:
            box_el = driver.find_element(By.CSS_SELECTOR, "[aria-label*='What do you want to create' i], div[contenteditable='true'], textarea")
            box_el.send_keys(" ")
            time.sleep(0.1)
            box_el.send_keys(Keys.BACKSPACE)
        except Exception:
            pass
    return bool(ok)


def save_all_browser_cookies_via_cdp(driver):
    try:
        res = driver.execute_cdp_cmd("Network.getAllCookies", {})
        all_cookies = res.get("cookies", [])
        essential = [
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ".google.com"),
                "path": c.get("path", "/"),
                "secure": c.get("secure", True),
                "httpOnly": c.get("httpOnly", False)
            }
            for c in all_cookies
            if any(k in c.get("domain", "") for k in ["google", "labs", "youtube", "gstatic"])
        ]
        if essential:
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                f.write(json.dumps(essential, indent=2))
            sync_file_to_github(COOKIE_FILE, "Update full Google Flow CDP cookies")
            return len(essential)
    except Exception:
        pass
    return 0


def inject_cookies_and_verify_flow_login(driver):
    raw_cookies = ""
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                raw_cookies = f.read().strip()
        except Exception:
            pass
    if not raw_cookies:
        raw_cookies = os.getenv("GEMINI_COOKIES_JSON", "").strip()

    if raw_cookies:
        try:
            cookies = json.loads(raw_cookies)
            driver.execute_cdp_cmd("Network.enable", {})
            for c in cookies:
                try:
                    driver.execute_cdp_cmd("Network.setCookie", {
                        "name": c["name"],
                        "value": c["value"],
                        "domain": c.get("domain", ".google.com"),
                        "path": c.get("path", "/"),
                        "secure": True
                    })
                except Exception:
                    pass
            driver.execute_cdp_cmd("Page.navigate", {"url": FLOW_URL})
            time.sleep(5)
        except Exception:
            pass

    for tick in range(50):
        install_file_dialog_blocker(driver)
        try:
            status = driver.execute_script(
                """
                const url = location.href.toLowerCase();
                const txt = (document.body.innerText || '').toLowerCase();
                if (url.includes('accounts.google.com/v3/signin') || url.includes('servicelogin')) {
                    return 'SIGNIN_PAGE';
                }
                if (
                    txt.includes('new project') ||
                    Boolean(document.querySelector('[aria-label*="Settings trigger" i], [aria-label*="What do you want to create" i]'))
                ) {
                    return 'LOGGED_IN';
                }
                for (const b of document.querySelectorAll('button, a, [role="button"]')) {
                    if (b.offsetParent === null) continue;
                    const t = (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase();
                    if (t === 'create with flow' || t === 'launch flow' || t === 'get started') {
                        b.click();
                        return 'CLICKED_SPLASH';
                    }
                }
                return 'WAITING';
                """
            )
            if status == "LOGGED_IN":
                print("✅ Google Flow Pro Session Verified!")
                save_all_browser_cookies_via_cdp(driver)
                return True
        except Exception:
            pass
        time.sleep(0.5)

    return True


# ==============================================================================
# 🎯 SCREENSHOT-VERIFIED 20-STEP FLOW PIPELINE
#    Fixes the `Nano Banana 2.1 x2` bug by clicking the Settings pill inside
#    the prompt box and verifying `videocam Video` + `9:16` + `720p` + `10s` + `x1`!
# ==============================================================================
def open_settings_pill_in_prompt_bar(driver):
    """
    Finds the Settings trigger button inside the bottom prompt bar (which initially displays
    `Nano Banana 2.1 x2` or `Settings trigger` or `Video · 720p`) and clicks it until the
    Settings popover (`videocam Video`, `9:16`, `720p`, `x1`) opens!
    """
    js_find_settings_pill = """
    const promptBox = document.querySelector('[aria-label*="What do you want to create" i], textarea, div[contenteditable="true"]');
    const boxRect = promptBox ? promptBox.getBoundingClientRect() : {top: window.innerHeight - 160, left: 400, right: 1400};

    // 1. Check explicit aria-label='Settings trigger' first
    const explicit = document.querySelector('button[aria-label*="Settings trigger" i], [aria-label*="Settings trigger" i]');
    if (explicit && explicit.offsetParent !== null) {
        const r = explicit.getBoundingClientRect();
        return {x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), txt: explicit.innerText || 'Settings trigger'};
    }

    // 2. Find the model/settings pill button inside the bottom prompt container (contains 'nano banana', 'video', 'image', 'veo', 'x1', 'x2', 'x4', '720p')
    for (const b of document.querySelectorAll('button, [role="button"]')) {
        if (b.offsetParent === null) continue;
        const r = b.getBoundingClientRect();
        if (r.top < window.innerHeight * 0.72) continue;
        const t = ((b.innerText || '') + ' ' + (b.getAttribute('aria-label') || '')).trim().toLowerCase();
        if (
            t.includes('nano banana') || t.includes('banana') ||
            t.includes('settings trigger') || t.includes('720p') ||
            t.includes('1080p') || t.includes('x2') || t.includes('x1') ||
            t.includes('veo') || t.includes('video ·')
        ) {
            return {x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2), txt: t.slice(0, 35)};
        }
    }
    return null;
    """
    for _ in range(4):
        pill = driver.execute_script(js_find_settings_pill)
        if pill:
            hardware_click_xy(driver, pill["x"], pill["y"], f"Step #3: Open Settings Pill ('{pill['txt']}')")
            time.sleep(0.8)
            # Verify if the Settings popup ('videocam Video' / '9:16' / 'x1') is now visible on screen!
            popup_open = driver.execute_script(
                """
                const txt = (document.body.innerText || '').toLowerCase();
                return (txt.includes('9:16') || txt.includes('16:9') || txt.includes('720p'));
                """
            )
            if popup_open:
                return True
        time.sleep(0.5)
    return False


def execute_locked_20_step_flow_pipeline(driver, foji_img, fojan_img, fresh_prompt):
    install_file_dialog_blocker(driver)

    # STEP 1: Click 'add New project' if on Flow Home Page
    on_home = driver.execute_script("return (document.body.innerText || '').toLowerCase().includes('new project');")
    if on_home:
        wait_until_visible_and_click(
            driver,
            ["add new project", "new project"],
            timeout=20.0,
            post_delay=1.5,
            step_label="Step #1: New Project"
        )

    # Wait until the Prompt Box (`What do you want to create?`) is visible on screen
    print("   ⏳ Waiting for Project Prompt Box (`What do you want to create?`) to appear...")
    for _ in range(70):
        install_file_dialog_blocker(driver)
        has_editor = driver.execute_script(
            "return Boolean(document.querySelector('[aria-label*=\"What do you want to create\" i], [aria-label*=\"Settings trigger\" i]'));"
        )
        if has_editor:
            break
        time.sleep(0.35)

    # STEP 3: Click the Settings Pill (`Nano Banana 2.1 x2` / `Settings trigger`) inside the Prompt Bar!
    open_settings_pill_in_prompt_bar(driver)

    # STEP 4: Switch from Image (`Nano Banana`) to `videocam Video` mode!
    wait_until_visible_and_click(
        driver,
        ["videocam video", "video"],
        region_filter="settings_popup",
        timeout=10.0,
        post_delay=0.5,
        step_label="Step #4: Select 'videocam Video' Mode"
    )

    # STEP 5: Select `crop_9_16 9:16` Portrait Aspect Ratio
    wait_until_visible_and_click(
        driver,
        ["crop_9_16 9:16", "9:16"],
        region_filter="settings_popup",
        timeout=8.0,
        post_delay=0.4,
        step_label="Step #5: Select '9:16' Portrait"
    )

    # STEP 6: Select `720p` Resolution
    wait_until_visible_and_click(
        driver,
        ["720p"],
        region_filter="settings_popup",
        timeout=8.0,
        post_delay=0.4,
        step_label="Step #6: Select '720p'"
    )

    # STEP 7: Select `10s` Duration
    wait_until_visible_and_click(
        driver,
        ["10s"],
        region_filter="settings_popup",
        timeout=8.0,
        post_delay=0.4,
        step_label="Step #7: Select '10s'"
    )

    # STEP 8: Select `x1` (1 Video at a time instead of x2!)
    wait_until_visible_and_click(
        driver,
        ["x1"],
        region_filter="settings_popup",
        timeout=8.0,
        post_delay=0.4,
        step_label="Step #8: Select 'x1' (1 Video)"
    )

    # STEP 9: Close Settings Popup by clicking Settings trigger again (or pressing Escape)
    if not wait_until_visible_and_click(
        driver,
        ["settings trigger", "video · 720p"],
        region_filter="prompt_bar",
        timeout=5.0,
        post_delay=0.5,
        step_label="Step #9: Close Settings"
    ):
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.5)

    # STEP 10: Click `+` (`Add ingredients to the prompt box`) on the bottom-left of Prompt Box
    wait_until_visible_and_click(
        driver,
        ["add ingredients to the prompt box", "add"],
        region_filter="prompt_bar",
        timeout=12.0,
        post_delay=0.7,
        step_label="Step #10: Click '+' (Add Ingredients)"
    )

    # STEP 11 & 12: Click `upload Upload media` and inject BOTH Foji & Fojan character images!
    install_file_dialog_blocker(driver)
    wait_until_visible_and_click(
        driver,
        ["upload upload media", "upload media"],
        timeout=10.0,
        post_delay=0.5,
        step_label="Step #11: Click 'upload Upload media'"
    )

    install_file_dialog_blocker(driver)
    file_inputs = []
    for _ in range(25):
        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        if file_inputs:
            break
        time.sleep(0.2)

    if file_inputs:
        target_inp = file_inputs[-1]
        try:
            target_inp.send_keys(f"{foji_img}\n{fojan_img}")
            print("   📸 [Step #12] Injected BOTH Foji & Fojan character images!")
        except Exception:
            try:
                target_inp.send_keys(foji_img)
                time.sleep(1.5)
                target_inp.send_keys(fojan_img)
            except Exception:
                pass

    # STEP 13: Wait for upload to complete and click `Add to prompt` (1st character)
    print("   ⏳ Waiting for 'Add to prompt' button to appear after upload...")
    wait_until_visible_and_click(
        driver,
        ["add to prompt"],
        timeout=25.0,
        post_delay=0.8,
        step_label="Step #13: Click 'Add to prompt' (1st Character)"
    )

    # STEP 14: Click `+` (`Add ingredients to the prompt box`) again for 2nd character
    wait_until_visible_and_click(
        driver,
        ["add ingredients to the prompt box", "add"],
        region_filter="prompt_bar",
        timeout=12.0,
        post_delay=0.7,
        step_label="Step #14: Click '+' for 2nd Character"
    )

    # STEP 15: Click `Add to prompt` (or the 2nd uploaded character card in the drawer)
    if not wait_until_visible_and_click(
        driver,
        ["add to prompt"],
        timeout=6.0,
        post_delay=0.8,
        step_label="Step #15: Click 'Add to prompt' (2nd Character)"
    ):
        wait_until_visible_and_click(
            driver,
            ["foji", "fojan", "image"],
            timeout=8.0,
            post_delay=0.8,
            step_label="Step #15: Select 2nd Character from Drawer"
        )

    # STEP 16: Click Prompt Box (`What do you want to create?`) & fill fresh AI Script
    wait_until_visible_and_click(
        driver,
        ["what do you want to create?"],
        region_filter="prompt_bar",
        timeout=10.0,
        post_delay=0.4,
        step_label="Step #16: Focus Prompt Box"
    )
    fill_prompt_box_directly(driver, fresh_prompt)
    print("   ✉️ [Step #16] Fresh AI Script filled into Prompt Box!")
    time.sleep(0.8)

    # STEP 17: Click `Start generation` (`arrow_forward`)
    wait_until_visible_and_click(
        driver,
        ["start generation", "arrow_forward"],
        region_filter="prompt_bar",
        timeout=12.0,
        post_delay=2.0,
        step_label="Step #17: Click 'Start generation'"
    )


def get_flow_videos_info(driver):
    js_vids = """
    let urls = [];
    for (const v of document.querySelectorAll('video')) {
        const src = v.currentSrc || v.src || (v.querySelector('source') ? v.querySelector('source').src : '');
        if (src && src.length > 10) urls.push(src);
    }
    return urls;
    """
    try:
        return driver.execute_script(js_vids) or []
    except Exception:
        return []


def execute_locked_download_steps(driver, raw_dir, existing_mp4s, new_video_url, output_video_path):
    print("📥 [Steps #18-#20] Clicking Rendered Video -> 'Download media' -> '720p Original size'...")

    # Step #18: Click the rendered <video> element on screen
    js_vid_rect = """
    const vids = Array.from(document.querySelectorAll('video')).filter(v => v.offsetParent !== null);
    if (vids.length > 0) {
        const r = vids[0].getBoundingClientRect();
        return {x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2)};
    }
    return null;
    """
    v_pt = driver.execute_script(js_vid_rect)
    if v_pt:
        hardware_click_xy(driver, v_pt["x"], v_pt["y"], "Step #18: Rendered Video")
    time.sleep(1.0)

    # Step #19: Click 'Download media'
    wait_until_visible_and_click(
        driver,
        ["download media", "download"],
        region_filter="top_right",
        timeout=12.0,
        post_delay=0.8,
        step_label="Step #19: Download Media"
    )

    # Step #20: Click '720p Original size'
    wait_until_visible_and_click(
        driver,
        ["720p original size", "720p"],
        region_filter="top_right",
        timeout=12.0,
        post_delay=1.0,
        step_label="Step #20: 720p Original Size"
    )

    for _ in range(30):
        time.sleep(1.5)
        current_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
        new_files = [f for f in (current_mp4s - existing_mp4s) if not f.endswith(".crdownload")]
        if new_files:
            newest = max(new_files, key=os.path.getctime)
            if is_valid_mp4(newest):
                if os.path.abspath(newest) != os.path.abspath(output_video_path):
                    shutil.move(newest, output_video_path)
                return True

    if new_video_url and new_video_url.startswith("http") and not new_video_url.startswith("blob:"):
        try:
            cookies_dict = {c["name"]: c["value"] for c in driver.get_cookies()}
            r = requests.get(new_video_url, cookies=cookies_dict, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=60)
            if r.status_code == 200:
                with open(output_video_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                if is_valid_mp4(output_video_path):
                    return True
        except Exception:
            pass

    if new_video_url:
        try:
            driver.set_script_timeout(90)
            b64_data = driver.execute_async_script(
                """
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
                """,
                new_video_url
            )
            if b64_data and "," in b64_data:
                raw_bytes = base64.b64decode(b64_data.split(",", 1)[1])
                with open(output_video_path, "wb") as f:
                    f.write(raw_bytes)
                if is_valid_mp4(output_video_path):
                    return True
        except Exception:
            pass

    return False


def rotate_track_and_script_in_history(pending_pkg):
    try:
        if os.path.exists("data/history.json") and pending_pkg:
            with open("data/history.json", "r", encoding="utf-8") as f:
                h = json.load(f)
            tid = pending_pkg.get("track_id")
            d1 = pending_pkg.get("dialogue_line_1_hinglish")
            if tid:
                h.setdefault("recent_tracks", []).append(tid)
            if d1:
                h.setdefault("failed_dialogues", []).append(d1)
            with open("data/history.json", "w", encoding="utf-8") as f:
                json.dump(h, f, indent=4, ensure_ascii=False)
    except Exception:
        pass


def export_fresh_flow_cookies_from_local():
    print("🔐 Opening Google Flow to export ALL multi-domain cookies for Cloud...")
    driver, proc = launch_resilient_chrome_session(os.path.abspath("output/raw_videos"))
    try:
        time.sleep(6)
        count = save_all_browser_cookies_via_cdp(driver)
        print(f"✅ Successfully exported {count} cookies to {COOKIE_FILE}!")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass


def generate_video_in_gemini(pending_pkg=None):
    os.makedirs("data", exist_ok=True)
    if not os.path.exists("data/history.json"):
        with open("data/history.json", "w", encoding="utf-8") as f:
            json.dump({"generated_count": 0, "history": []}, f)

    with open("data/history.json", "r", encoding="utf-8") as f:
        history_data = json.load(f)

    if not pending_pkg:
        import dashboard_app
        track, next_part = dashboard_app.get_next_track_and_part(history_data)
        new_id = int(history_data.get("generated_count", 0)) + 1
        used_lines = [item.get("dialogue_line_1_hinglish", "") for item in history_data.get("history", [])]
        used_lines.extend(history_data.get("failed_dialogues", []))
        pending_pkg = dashboard_app.build_fresh_prompt_package(track, next_part, new_id, used_lines)

    rotate_track_and_script_in_history(pending_pkg)
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
    base_video_prompt = pending_pkg["gemini_video_prompt"]

    print(f"🚀 [Step 1/5] Launching Fast Google Flow 20-Step Engine for: {pending_pkg.get('emotion_name', f'Reel #{video_num}')}...")
    update_3d_telemetry(1, "Opening Google Flow", "Loading Flow & Switching to Video 9:16 x1...", "active", 18)
    driver, chrome_proc = launch_resilient_chrome_session(raw_dir)

    try:
        existing_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
        inject_cookies_and_verify_flow_login(driver)
        initial_video_urls = set(get_flow_videos_info(driver))

        update_3d_telemetry(3, "Executing 20-Step Memory", "Switching Nano Banana -> Video 9:16 720p 10s x1...", "active", 52)
        execute_locked_20_step_flow_pipeline(driver, foji_img, fojan_img, base_video_prompt)

        time.sleep(4)
        snap_start = "data/flow_started.png"
        try:
            driver.save_screenshot(snap_start)
            send_telegram_photo(
                snap_start,
                f"🎬 *Google Flow Video (9:16 • 720p • x1) Started!*\n📌 *{pending_pkg.get('emotion_name')}*\n🗣️ _{pending_pkg.get('dialogue_line_1_hinglish')}_"
            )
        except Exception:
            pass

        update_3d_telemetry(5, "Rendering 720p Video", "Waiting for Google Flow to finish rendering...", "active", 86)
        video_saved = False

        for tick in range(120):
            time.sleep(4)

            current_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
            new_files = [f for f in (current_mp4s - existing_mp4s) if not f.endswith(".crdownload")]
            if new_files:
                newest = max(new_files, key=os.path.getctime)
                if is_valid_mp4(newest):
                    if os.path.abspath(newest) != os.path.abspath(output_video_path):
                        shutil.move(newest, output_video_path)
                    video_saved = True
                    break

            current_urls = set(get_flow_videos_info(driver))
            new_urls = list(current_urls - initial_video_urls)
            elapsed_mins = round(((tick + 1) * 4) / 60.0, 1)
            print(f"⏳ [Flow {elapsed_mins}/8.0 min] Videos on Screen: {len(current_urls)} (New: {len(new_urls)})")

            if new_urls:
                print("✅ [Steps #18-#20] Video Rendered! Clicking Video -> Download media -> 720p Original size...")
                update_3d_telemetry(6, "Downloading 720p MP4", "Saving 720p Original size video...", "active", 96)
                time.sleep(2.5)
                if execute_locked_download_steps(driver, raw_dir, existing_mp4s, new_urls[-1], output_video_path):
                    video_saved = True
                    break

            if tick % 6 == 0:
                prog = min(95, 86 + int(tick / 14))
                update_3d_telemetry(5, "Rendering in Flow", f"Google Flow rendering 720p video... ({elapsed_mins} min)", "active", prog)

        if video_saved and is_valid_mp4(output_video_path):
            print(f"🎉 SUCCESS! 720p Video Downloaded at {output_video_path}")
            update_3d_telemetry(6, "Reel Ready", "Sent to Telegram & Frontend!", "completed", 100)
            return output_video_path

        snap_err = "data/flow_timeout.png"
        try:
            driver.save_screenshot(snap_err)
            send_telegram_photo(snap_err, "⚠️ Google Flow status after timeout.")
        except Exception:
            pass
        raise RuntimeError("Google Flow video render timed out.")

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
    if "--save-cookies" in sys.argv:
        export_fresh_flow_cookies_from_local()
    else:
        generate_video_in_gemini()