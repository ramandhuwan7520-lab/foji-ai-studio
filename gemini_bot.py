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

load_dotenv()
IST = timezone(timedelta(hours=5, minutes=30))
COOKIE_FILE = "gemini_cookies_secret.txt"
BLUEPRINT_FILE = "data/flow_learned_blueprint.json"
DEBUG_PORT = 9225
FLOW_URL = "https://labs.google/fx/tools/flow"

# ==============================================================================
# 🧠 PERMANENT 20-STEP MASTER MEMORY (LOCKED FROM YOUR RECORDED SESSION)
# ==============================================================================
MASTER_SETUP_STEPS = [
    {"step": 1,  "name": "New Project",          "match": ["add new project", "new project"],                   "xpct": 52.4, "ypct": 77.4, "wait_timeout": 20.0, "post_delay": 1.5},
    {"step": 3,  "name": "Open Settings",        "match": ["settings trigger", "video · 720p", "crop_9_16"],   "xpct": 62.2, "ypct": 88.4, "wait_timeout": 20.0, "post_delay": 0.5},
    {"step": 4,  "name": "Select Video Mode",    "match": ["videocam video", "video"],                          "xpct": 63.0, "ypct": 36.1, "wait_timeout": 8.0,  "post_delay": 0.3},
    {"step": 5,  "name": "Select 9:16 Ratio",    "match": ["crop_9_16 9:16", "9:16"],                           "xpct": 62.7, "ypct": 45.1, "wait_timeout": 8.0,  "post_delay": 0.3},
    {"step": 6,  "name": "Select 720p",          "match": ["720p"],                                             "xpct": 63.0, "ypct": 61.4, "wait_timeout": 8.0,  "post_delay": 0.3},
    {"step": 7,  "name": "Select 10s Duration",  "match": ["10s"],                                              "xpct": 65.2, "ypct": 67.5, "wait_timeout": 8.0,  "post_delay": 0.3},
    {"step": 8,  "name": "Select x1 Output",     "match": ["x1"],                                               "xpct": 49.3, "ypct": 75.0, "wait_timeout": 8.0,  "post_delay": 0.3},
    {"step": 9,  "name": "Close Settings",       "match": ["settings trigger", "video · 720p"],                 "xpct": 62.9, "ypct": 89.1, "wait_timeout": 8.0,  "post_delay": 0.5},
    {"step": 10, "name": "Click + Ingredients",  "match": ["add ingredients to the prompt box"],                "xpct": 29.1, "ypct": 90.4, "wait_timeout": 12.0, "post_delay": 0.6},
    {"step": 11, "name": "Click Upload Media",   "match": ["upload upload media", "upload media"],              "xpct": 28.4, "ypct": 83.8, "wait_timeout": 10.0, "post_delay": 0.5, "action": "UPLOAD_CHARACTERS"},
    {"step": 13, "name": "Add 1st Char Prompt",  "match": ["add to prompt"],                                    "xpct": 55.3, "ypct": 81.5, "wait_timeout": 20.0, "post_delay": 0.8},
    {"step": 14, "name": "Click + 2nd Char",     "match": ["add ingredients to the prompt box"],                "xpct": 29.3, "ypct": 90.8, "wait_timeout": 12.0, "post_delay": 0.6},
    {"step": 15, "name": "Add 2nd Char Prompt",  "match": ["add to prompt", "foji", "fojan"],                   "xpct": 56.1, "ypct": 82.7, "wait_timeout": 15.0, "post_delay": 0.8},
    {"step": 16, "name": "Fill Prompt Box",      "match": ["what do you want to create?"],                      "xpct": 42.7, "ypct": 82.1, "wait_timeout": 12.0, "post_delay": 0.6, "action": "FILL_PROMPT"},
    {"step": 17, "name": "Start Generation",     "match": ["start generation", "arrow_forward"],                "xpct": 69.5, "ypct": 89.7, "wait_timeout": 12.0, "post_delay": 2.0}
]


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
    """
    PERMANENT FIX FOR GITHUB ACTIONS CHROMEDRIVER MISMATCH (155 vs 156):
    Deletes stale pre-installed `/usr/bin/chromedriver` directly from Python BEFORE
    Selenium starts, so Selenium Manager automatically uses the exact matching driver!
    """
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
                print(f"🧹 Removed stale system chromedriver: {sp}")
            except Exception:
                try:
                    subprocess.run(["sudo", "rm", "-f", sp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"🧹 Sudo-removed stale system chromedriver: {sp}")
                except Exception:
                    pass


def launch_resilient_chrome_session(download_dir, start_blank=False):
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
    initial_url = "about:blank" if start_blank else FLOW_URL
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
        initial_url
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
    print(f"   ⚡ [Fast Click] '{label}' at ({x_int}, {y_int})")
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
        time.sleep(0.04)
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x_int, "y": y_int, "button": "left", "clickCount": 1})
        time.sleep(0.04)
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


def click_by_pct_fallback(driver, xpct, ypct, label="Recorded %"):
    vw_vh = driver.execute_script("return {w: window.innerWidth, h: window.innerHeight};")
    cx = int((float(xpct) / 100.0) * vw_vh["w"])
    cy = int((float(ypct) / 100.0) * vw_vh["h"])
    return hardware_click_xy(driver, cx, cy, label)


def wait_until_visible_and_click(driver, match_keywords, xpct=None, ypct=None, timeout=18.0, post_delay=0.4, step_label="Step"):
    match_keywords = [k.lower().strip() for k in (match_keywords or []) if k and k.strip()]
    start_t = time.time()

    js_fast_find = """
    const keywords = arguments[0];
    const targetXpct = arguments[1];
    const targetYpct = arguments[2];

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

        const tag = el.tagName.toLowerCase();
        const role = (el.getAttribute('role') || '').toLowerCase();
        const aria = (el.getAttribute('aria-label') || '').trim().toLowerCase();
        const title = (el.getAttribute('title') || el.getAttribute('mattooltip') || '').trim().toLowerCase();
        const txt = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').toLowerCase();
        if (txt.length > 90 && tag !== 'textarea' && el.getAttribute('contenteditable') !== 'true') continue;

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

        let score = 200 - Math.min(80, txt.length);
        if (txt === matchedKw || aria === matchedKw) score += 250;
        if (tag === 'button' || role === 'button' || role === 'menuitem' || role === 'option' || role === 'tab') score += 100;

        const curXpct = ((r.left + r.width / 2) / window.innerWidth) * 100;
        const curYpct = ((r.top + r.height / 2) / window.innerHeight) * 100;
        if (targetXpct !== null && targetYpct !== null) {
            const dist = Math.abs(curXpct - targetXpct) + Math.abs(curYpct - targetYpct);
            score -= dist * 2.0;
        }

        if (score > bestScore) {
            bestScore = score;
            best = {
                x: Math.round(r.left + r.width / 2),
                y: Math.round(r.top + r.height / 2),
                label: (txt || aria).slice(0, 35)
            };
        }
    }
    return best;
    """

    while (time.time() - start_t) < timeout:
        install_file_dialog_blocker(driver)
        try:
            found = driver.execute_script(js_fast_find, match_keywords, xpct, ypct)
            if found:
                hardware_click_xy(driver, found["x"], found["y"], f"{step_label} -> '{found['label']}'")
                time.sleep(post_delay)
                return True
        except Exception:
            pass
        time.sleep(0.25)

    if xpct is not None and ypct is not None:
        print(f"   🎯 [Fallback % Click] Clicking learned coordinates ({xpct}%, {ypct}%) for {step_label}...")
        click_by_pct_fallback(driver, xpct, ypct, step_label)
        time.sleep(post_delay)
        return True

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


# ==============================================================================
# 🔐 ALL-DOMAIN CDP COOKIE SAVER & CLOUD RESTORER (NEVER HANGS ON CLOUD!)
# ==============================================================================
def save_all_browser_cookies_via_cdp(driver):
    """
    Uses `Network.getAllCookies` so it captures EVERY cookie across `.google.com`,
    `labs.google`, `accounts.google.com`, etc. (unlike `driver.get_cookies()` which only gets 1 domain!).
    """
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
            print(f"🔐 Saved {len(essential)} multi-domain Google/Labs cookies to {COOKIE_FILE}!")
            return len(essential)
    except Exception as e:
        print(f"⚠️ Cookie save note: {e}")
    return 0


def inject_cookies_and_verify_flow_login(driver):
    """
    Injects all saved cookies from `gemini_cookies_secret.txt` (or `GEMINI_COOKIES_JSON` secret)
    into Chrome via CDP BEFORE navigating to Google Flow, and verifies we are logged in!
    """
    raw_cookies = ""
    # Always prefer the latest repo file first, then fallback to env var
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
            print(f"🔐 Injecting {len(cookies)} saved Google Pro cookies into Chrome...")
            driver.execute_cdp_cmd("Network.enable", {})
            for c in cookies:
                try:
                    domain = c.get("domain", ".google.com")
                    driver.execute_cdp_cmd("Network.setCookie", {
                        "name": c["name"],
                        "value": c["value"],
                        "domain": domain,
                        "path": c.get("path", "/"),
                        "secure": True
                    })
                except Exception:
                    pass
            # Reload Flow with injected cookies
            driver.execute_cdp_cmd("Page.navigate", {"url": FLOW_URL})
            time.sleep(5)
        except Exception as e:
            print(f"⚠️ Cookie injection note: {e}")

    # Wait up to 25 seconds for Flow Home ('New project') or Editor to appear
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
                // Click 'Create with Flow' / 'Launch Flow' / 'Get started' if on marketing splash page
                for (const b of document.querySelectorAll('button, a, [role="button"]')) {
                    if (b.offsetParent === null) continue;
                    const t = (b.innerText || b.getAttribute('aria-label') || '').trim().toLowerCase();
                    if (t === 'create with flow' || t === 'launch flow' || t === 'get started' || t === 'sign in') {
                        b.click();
                        return 'CLICKED_SPLASH:' + t;
                    }
                }
                return 'WAITING';
                """
            )
            if status == "LOGGED_IN":
                print("✅ Google Flow Pro Session Verified & Ready!")
                save_all_browser_cookies_via_cdp(driver)
                return True
            if status == "SIGNIN_PAGE" and os.name != "nt" and tick > 12:
                snap = "data/flow_login_needed.png"
                driver.save_screenshot(snap)
                send_telegram_photo(snap, "🔐 Cloud needs fresh Google Flow cookies! Run `python gemini_bot.py --save-cookies` on laptop and push.")
                raise RuntimeError("Google Flow session expired on Cloud. Run `python gemini_bot.py --save-cookies` on laptop.")
        except RuntimeError:
            raise
        except Exception:
            pass
        time.sleep(0.5)

    return True


def execute_locked_20_step_flow_pipeline(driver, foji_img, fojan_img, fresh_prompt):
    install_file_dialog_blocker(driver)

    on_home = driver.execute_script("return (document.body.innerText || '').toLowerCase().includes('new project');")
    if on_home:
        wait_until_visible_and_click(
            driver,
            ["add new project", "new project"],
            xpct=52.4,
            ypct=77.4,
            timeout=20.0,
            post_delay=1.0,
            step_label="Step #1: New Project"
        )

    print("   ⏳ Waiting for Project Workspace to appear on screen...")
    editor_ready = False
    for _ in range(70):
        install_file_dialog_blocker(driver)
        has_editor = driver.execute_script(
            """
            return Boolean(
                document.querySelector('[aria-label*="Settings trigger" i], [aria-label*="Add ingredients" i], [aria-label*="What do you want to create" i]')
            );
            """
        )
        if has_editor:
            editor_ready = True
            break
        time.sleep(0.35)

    if not editor_ready:
        snap = "data/flow_workspace_error.png"
        try:
            driver.save_screenshot(snap)
            send_telegram_photo(snap, "⚠️ Google Flow Workspace did not open on Cloud (check login/cookies).")
        except Exception:
            pass
        raise RuntimeError("Google Flow Project Editor did not appear on screen!")

    for s in MASTER_SETUP_STEPS:
        if s["step"] == 1:
            continue

        step_num = s["step"]
        step_name = f"Step #{step_num}: {s['name']}"
        act = s.get("action", "CLICK")

        if act == "FILL_PROMPT":
            wait_until_visible_and_click(
                driver,
                s["match"],
                xpct=s["xpct"],
                ypct=s["ypct"],
                timeout=s["wait_timeout"],
                post_delay=0.4,
                step_label=step_name
            )
            fill_prompt_box_directly(driver, fresh_prompt)
            print("   ✉️ [Step #16] Fresh AI Script filled into Prompt Box!")
            time.sleep(0.8)
            continue

        wait_until_visible_and_click(
            driver,
            s["match"],
            xpct=s["xpct"],
            ypct=s["ypct"],
            timeout=s["wait_timeout"],
            post_delay=s["post_delay"],
            step_label=step_name
        )

        if act == "UPLOAD_CHARACTERS":
            install_file_dialog_blocker(driver)
            file_inputs = []
            for _ in range(20):
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

            print("   ⏳ Waiting for Character Upload to finish ('Add to prompt' button to appear)...")
            for _ in range(70):
                ready_add = driver.execute_script(
                    "return (document.body.innerText || '').toLowerCase().includes('add to prompt');"
                )
                if ready_add:
                    break
                time.sleep(0.35)


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
    else:
        click_by_pct_fallback(driver, 25.9, 40.9, "Step #18: Rendered Video")
    time.sleep(1.0)

    wait_until_visible_and_click(
        driver,
        ["download media", "download"],
        xpct=75.8,
        ypct=7.0,
        timeout=12.0,
        post_delay=0.8,
        step_label="Step #19: Download Media"
    )

    wait_until_visible_and_click(
        driver,
        ["720p original size", "720p"],
        xpct=77.9,
        ypct=22.6,
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
    """Opens local Chrome profile on Google Flow, verifies login, and saves all CDP cookies to gemini_cookies_secret.txt."""
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
    update_3d_telemetry(1, "Opening Google Flow", "Loading Flow & Running 20-Step Memory...", "active", 18)
    driver, chrome_proc = launch_resilient_chrome_session(raw_dir)

    try:
        existing_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
        inject_cookies_and_verify_flow_login(driver)
        initial_video_urls = set(get_flow_videos_info(driver))

        update_3d_telemetry(3, "Executing 20-Step Memory", "Settings (9:16, 720p, 10s, x1) + Characters + Script...", "active", 52)
        execute_locked_20_step_flow_pipeline(driver, foji_img, fojan_img, base_video_prompt)

        time.sleep(4)
        snap_start = "data/flow_started.png"
        try:
            driver.save_screenshot(snap_start)
            send_telegram_photo(
                snap_start,
                f"🎬 *Google Flow Generation Started!*\n📌 *{pending_pkg.get('emotion_name')}*\n🗣️ _{pending_pkg.get('dialogue_line_1_hinglish')}_"
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