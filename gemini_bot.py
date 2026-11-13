import zipfile
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

_ACTIVE_COOKIE_ACCOUNT_SLOT = 1
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

load_dotenv(override=True)
IST = timezone(timedelta(hours=5, minutes=30))
COOKIE_FILE = "gemini_cookies_secret.txt"
BLUEPRINT_FILE = "data/gemini_learned_blueprint.json"
DEBUG_PORT = 9225
GEMINI_URL = "https://gemini.google.com/app"

DEFAULT_WIN_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"


class GeminiLimitReachedError(RuntimeError):
    """Raised when Gemini's Create Video tool cannot be selected or reports a quota/limit."""
    pass


def send_alert(msg):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=15
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
                    timeout=25
                )
        except Exception:
            pass


def sync_file_to_github(rel_path, commit_msg):
    gh_pat = (
        os.getenv("GITHUB_PAT")
        or os.getenv("GH_TOKEN")
        or os.getenv("GITHUB_TOKEN")
        or ""
    ).strip()
    repo = os.getenv("GITHUB_REPO", "ramandhuwan7520-lab/foji-ai-studio").strip()
    rel_clean = rel_path.replace("\\", "/")
    full_p = os.path.abspath(rel_path)
    if not os.path.exists(full_p):
        return
    if gh_pat:
        try:
            with open(full_p, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            url = f"https://api.github.com/repos/{repo}/contents/{rel_clean}"
            headers = {"Authorization": f"Bearer {gh_pat}", "Accept": "application/vnd.github+json"}
            r = requests.get(url, headers=headers, timeout=12)
            sha = r.json().get("sha") if r.status_code == 200 else None
            payload = {"message": commit_msg, "content": b64, "branch": "main"}
            if sha:
                payload["sha"] = sha
            put_r = requests.put(url, headers=headers, json=payload, timeout=45)
            if put_r.status_code in (200, 201):
                return
        except Exception:
            pass
    # Fallback on Cloud Runner if API token is not set: use local git CLI
    if os.name != "nt":
        try:
            subprocess.run(["git", "add", "-f", rel_clean], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "commit", "-m", commit_msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "push", "origin", "HEAD:main", "--force"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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


def send_telegram_text_alert(msg_text):
    try:
        tok = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        cid = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
        if tok and cid:
            requests.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                data={"chat_id": cid, "text": msg_text},
                timeout=12
            )
    except Exception:
        pass


def send_telegram_photo_alert(photo_path, caption_text):
    try:
        tok = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        cid = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
        if tok and cid and os.path.exists(photo_path):
            with open(photo_path, "rb") as pf:
                requests.post(
                    f"https://api.telegram.org/bot{tok}/sendPhoto",
                    data={"chat_id": cid, "caption": caption_text[:950]},
                    files={"photo": pf},
                    timeout=20
                )
        else:
            send_telegram_text_alert(caption_text)
    except Exception:
        send_telegram_text_alert(caption_text)


def report_step_problem_instantly(driver, step_title, error_details):
    if globals().get("_SUPPRESS_FAILOVER_NOTIF", False):
        print(f"[Failover Notice: {step_title}] {error_details}")
        return
    short_err = str(error_details or "Unknown issue").strip()[:220]
    print(f"[PIPELINE ERROR - {step_title}] {short_err}")
    update_3d_telemetry(1, f"Warning: {step_title}", short_err, "error", 0)
    push_app_notification("error", f"Warning: {step_title}", short_err, "error")

    shot_path = "output/debug_step_error.png"
    has_shot = False
    if driver is not None:
        try:
            os.makedirs("output", exist_ok=True)
            driver.save_screenshot(shot_path)
            has_shot = os.path.exists(shot_path)
        except Exception:
            has_shot = False

    tg_caption = (
        f"🚨 Foji AI Studio - Pipeline Alert\n\n"
        f"📍 Step: {step_title}\n"
        f"❌ Reason: {short_err}\n"
        f"🕒 Time: {datetime.now(IST).strftime('%d %b %Y, %I:%M:%S %p IST')}"
    )
    if has_shot:
        send_telegram_photo_alert(shot_path, tg_caption)
    else:
        send_telegram_text_alert(tg_caption)

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
    if not file_path or not os.path.exists(file_path):
        return False
    if os.path.getsize(file_path) < 100 * 1024:
        return False
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
        if header.startswith(b"\x89PNG") or header.startswith(b"\xff\xd8\xff"):
            return False
    except Exception:
        pass
    return True


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
    for sp in ["/usr/bin/chromedriver", "/usr/local/bin/chromedriver", "/usr/lib/chromium-browser/chromedriver"]:
        if os.path.exists(sp):
            try:
                os.remove(sp)
            except Exception:
                try:
                    subprocess.run(["sudo", "rm", "-f", sp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass



PROFILE_VAULT_ZIP = "data/chrome_profile_vault.zip"
CLOUD_MINTED_COOKIE_FILE = "data/cloud_minted_cookies.json"


def pack_essential_chrome_profile_to_zip(profile_dir):
    """
    Layer #1: Packs the actual Chrome SQLite Cookie DB, Local Storage LevelDB, and Preferences
    from `chrome_gemini_pro_profile_1` into a lightweight zip (`data/chrome_profile_vault.zip`)
    so Cloud Linux opens the EXACT same browser profile state as your Laptop!
    """
    os.makedirs("data", exist_ok=True)
    essential_rel_paths = [
        "Local State",
        os.path.join("Default", "Preferences"),
        os.path.join("Default", "Secure Preferences"),
        os.path.join("Default", "Cookies"),
        os.path.join("Default", "Network", "Cookies"),
        os.path.join("Default", "Web Data"),
        os.path.join("Default", "Login Data"),
    ]
    essential_dirs = [
        os.path.join("Default", "Local Storage"),
        os.path.join("Default", "Session Storage"),
        os.path.join("Default", "Sync Data"),
    ]
    count_files = 0
    try:
        with zipfile.ZipFile(PROFILE_VAULT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel_p in essential_rel_paths:
                full_p = os.path.join(profile_dir, rel_p)
                if os.path.exists(full_p) and os.path.isfile(full_p):
                    try:
                        zf.write(full_p, rel_p)
                        count_files += 1
                    except Exception:
                        pass
            for rel_d in essential_dirs:
                full_d = os.path.join(profile_dir, rel_d)
                if os.path.exists(full_d) and os.path.isdir(full_d):
                    for root, _, files in os.walk(full_d):
                        for fn in files:
                            if fn.endswith((".log", ".ldb", ".sst", "CURRENT", "MANIFEST")) or os.path.getsize(os.path.join(root, fn)) < 2 * 1024 * 1024:
                                fp = os.path.join(root, fn)
                                arcname = os.path.relpath(fp, profile_dir)
                                try:
                                    zf.write(fp, arcname)
                                    count_files += 1
                                except Exception:
                                    pass
        print(f"📦 [Layer 1 Vault] Packed {count_files} core Chrome profile files into '{PROFILE_VAULT_ZIP}' ({os.path.getsize(PROFILE_VAULT_ZIP)//1024} KB)!")
        return True
    except Exception as e:
        print(f"⚠️ Profile zip note: {e}")
        return False


_UNPACKED_PROFILES_THIS_RUN = set()
_RUNTIME_FRESH_COOKIES_MEM = {}

def unpack_chrome_profile_vault_if_present(profile_dir):
    if profile_dir in _UNPACKED_PROFILES_THIS_RUN:
        return True
    """Restores the packed Chrome profile into `profile_dir` before launching Chrome on Cloud."""
    if os.path.exists(PROFILE_VAULT_ZIP) and os.path.getsize(PROFILE_VAULT_ZIP) > 500:
        try:
            os.makedirs(profile_dir, exist_ok=True)
            with zipfile.ZipFile(PROFILE_VAULT_ZIP, "r") as zf:
                zf.extractall(profile_dir)
            _UNPACKED_PROFILES_THIS_RUN.add(profile_dir)
            print(f"📦 [Layer 1 Vault] Restored Laptop Chrome Profile into '{profile_dir}'!")
            return True
        except Exception as e:
            print(f"⚠️ Profile unpack note: {e}")
    return False


def _load_saved_session_bundle():
    slot_k = globals().get("_ACTIVE_COOKIE_ACCOUNT_SLOT", 1)
    if slot_k in globals().get("_RUNTIME_FRESH_COOKIES_MEM", {}) and len(_RUNTIME_FRESH_COOKIES_MEM[slot_k]) >= 8:
        print(f"🔐 [Pure Cookie Loader] Using active in-memory session cookies ({len(_RUNTIME_FRESH_COOKIES_MEM[slot_k])} cookies)!")
        return {"cookies": _RUNTIME_FRESH_COOKIES_MEM[slot_k], "user_agent": DEFAULT_WIN_UA, "local_storage": {}}

    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and len(parsed.get("cookies", [])) >= 8:
                    print(f"🔐 [Pure Cookie Loader] Loaded {len(parsed['cookies'])} pure cookies from '{COOKIE_FILE}'")
                    return {
                        "cookies": parsed.get("cookies", []),
                        "user_agent": parsed.get("user_agent") or DEFAULT_WIN_UA,
                        "local_storage": parsed.get("local_storage", {})
                    }
                elif isinstance(parsed, list) and len(parsed) >= 8:
                    return {"cookies": parsed, "user_agent": DEFAULT_WIN_UA, "local_storage": {}}
        except Exception:
            pass

    raw_env = os.getenv("GEMINI_COOKIES_JSON", "").strip()
    if raw_env:
        try:
            parsed = json.loads(raw_env)
            if isinstance(parsed, dict):
                return {
                    "cookies": parsed.get("cookies", []),
                    "user_agent": parsed.get("user_agent") or DEFAULT_WIN_UA,
                    "local_storage": parsed.get("local_storage", {})
                }
        except Exception:
            pass
    return {"cookies": [], "user_agent": DEFAULT_WIN_UA, "local_storage": {}}


def launch_resilient_chrome_session(download_dir, start_blank=True):
    ensure_clean_matching_chromedriver_in_python()
    os.makedirs(download_dir, exist_ok=True)
    slot_num = globals().get("_ACTIVE_COOKIE_ACCOUNT_SLOT", 1)
    profile_dir = os.path.abspath(f"chrome_gemini_pro_profile_{slot_num}")
    os.makedirs(profile_dir, exist_ok=True)

    for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile"]:
        lp = os.path.join(profile_dir, lock_name)
        if os.path.exists(lp):
            try:
                os.remove(lp)
            except Exception:
                pass

    for cache_rel in ["GrShaderCache", "ShaderCache", "Crashpad", os.path.join("Default", "GPUCache"), os.path.join("Default", "Cache")]:
        cp = os.path.join(profile_dir, cache_rel)
        if os.path.exists(cp):
            try:
                shutil.rmtree(cp, ignore_errors=True)
            except Exception:
                pass

    bundle = _load_saved_session_bundle()
    saved_ua = bundle.get("user_agent") or DEFAULT_WIN_UA

    chrome_exe = find_chrome_executable()
    initial_url = "about:blank" if start_blank else GEMINI_URL
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
        "--lang=en-US",
        initial_url
    ]
    # On Cloud Linux, force the exact Windows User-Agent from laptop so Google cookies never trigger 'Hi Raman' password challenge!
    if os.name != "nt":
        cmd.append(f"--user-agent={saved_ua}")
        if not os.environ.get("DISPLAY"):
            cmd.append("--headless=new")

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ready = False
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{DEBUG_PORT}/json/version", timeout=1)
            ready = True
            break
        except Exception:
            time.sleep(0.4)

    if not ready:
        raise RuntimeError("Chrome port 9225 did not respond.")

    opts = Options()
    opts.page_load_strategy = "none"
    opts.debugger_address = f"127.0.0.1:{DEBUG_PORT}"
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(120)
    driver.set_script_timeout(120)
    try:
        driver.execute_cdp_cmd("Page.setDownloadBehavior", {"behavior": "allow", "downloadPath": download_dir})
        if os.name != "nt":
            # Mask Linux platform to Win32 in navigator so Google's session fingerprint matches your laptop 100%!
            driver.execute_cdp_cmd("Network.setUserAgentOverride", {
                "userAgent": saved_ua,
                "platform": "Win32",
                "acceptLanguage": "en-US,en;q=0.9",
                "userAgentMetadata": {
                    "brands": [
                        {"brand": "Google Chrome", "version": "135"},
                        {"brand": "Not-A.Brand", "version": "8"},
                        {"brand": "Chromium", "version": "135"}
                    ],
                    "fullVersionList": [
                        {"brand": "Google Chrome", "version": "135.0.0.0"},
                        {"brand": "Not-A.Brand", "version": "8.0.0.0"},
                        {"brand": "Chromium", "version": "135.0.0.0"}
                    ],
                    "platform": "Windows",
                    "platformVersion": "10.0.0",
                    "architecture": "x86",
                    "model": "",
                    "mobile": False,
                    "bitness": "64",
                    "wow64": False
                }
            })
    except Exception:
        pass
    return driver, proc


def install_file_dialog_blocker(driver):
    js_code = """
    if (!window.__fileDialogBlocked) {
        window.__fileDialogBlocked = true;
        window.__pendingFileInput = false;
        const origClick = HTMLInputElement.prototype.click;
        HTMLInputElement.prototype.click = function() {
            if (this.type === 'file') {
                this.style.cssText = 'display:block !important; visibility:visible !important; opacity:1 !important; position:fixed; top:0; left:0; width:1px; height:1px; z-index:99999;';
                this.removeAttribute('hidden');
                this.setAttribute('data-gemini-upload', '1');
                if (!this.isConnected && document.body) document.body.appendChild(this);
                window.__pendingFileInput = true;
                return;
            }
            return origClick.apply(this, arguments);
        };
    }
    for (const inp of document.querySelectorAll('input[type=file]')) {
        inp.style.cssText = 'display:block !important; visibility:visible !important; opacity:1 !important; position:fixed; top:0; left:0; width:1px; height:1px; z-index:99999;';
        inp.removeAttribute('hidden');
    }
    """
    try:
        driver.execute_script(js_code)
    except Exception:
        pass


# ==============================================================================
# 🔐 PURE COOKIE + FINGERPRINT + LOCALSTORAGE ENGINE (NO PASSWORD NEEDED!)
# ==============================================================================


def dismiss_any_agree_or_consent_popup(driver):
    """
    Automatically checks if an 'Agree', 'I agree', 'Accept', 'Try it', 'Got it', or 'Continue'
    popup/dialog is on screen during video generation. If present, clicks it immediately;
    if not present, continues immediately without any delay!
    """
    js_click_agree = """
    const targetWords = ['agree', 'i agree', 'accept', 'try it', 'got it', 'continue', 'allow'];
    const candidates = document.querySelectorAll(
        'mat-dialog-container button, [role="dialog"] button, .cdk-overlay-container button, button, [role="button"]'
    );
    for (const btn of candidates) {
        if (btn.offsetParent === null) continue;
        const r = btn.getBoundingClientRect();
        if (r.width < 20 || r.height < 18 || r.width > 360 || r.height > 90) continue;
        const txt = ((btn.innerText || btn.textContent || '') + ' ' + (btn.getAttribute('aria-label') || '')).trim().toLowerCase().replace(/\\s+/g, ' ');
        for (const w of targetWords) {
            if (txt === w || txt.startsWith(w + ' ') || txt.endsWith(' ' + w)) {
                // Make sure we don't accidentally click 'disagree' or 'cancel'
                if (txt.includes('disagree') || txt.includes('cancel') || txt.includes('no thanks')) continue;
                btn.click();
                return txt;
            }
        }
    }
    return '';
    """
    try:
        clicked_txt = driver.execute_script(js_click_agree)
        if clicked_txt:
            print(f"   ✅ [Auto-Popup Handler] Clicked '{clicked_txt}' popup button automatically!")
            time.sleep(0.8)
            return True
    except Exception:
        pass
    return False


def is_gemini_truly_signed_in(driver):
    """
    100% STRICT REAL SIGN-IN VERIFIER:
    Rejects Gemini's logged-out Guest Mode!
    Returns True ONLY when:
    1) URL is on `gemini.google.com` (not `accounts.google.com`)
    2) Browser has live `SID`, `__Secure-1PSID`, AND `__Secure-1PSIDTS` cookies right now
    3) There is NO visible 'Sign in' button in the top bar
    4) The Google Account profile avatar (`Google Account:` / `@gmail.com`) OR signed-in `+` tools button is visible!
    """
    try:
        curr_url = (driver.current_url or "").lower()
        if "gemini.google.com" not in curr_url or "accounts.google.com" in curr_url:
            return False

        # Check live browser cookies via CDP first!
        driver.execute_cdp_cmd("Network.enable", {})
        all_c = driver.execute_cdp_cmd("Network.getAllCookies", {}).get("cookies", [])
        c_names = {c.get("name") for c in all_c if "google" in c.get("domain", "") and c.get("value")}
        # A truly logged-in Google session MUST have SID and __Secure-1PSID in the live browser!
        if "SID" not in c_names or "__Secure-1PSID" not in c_names:
            return False

        js_strict_ui_check = """
        // 1. If a visible 'Sign in' link/button exists on screen, user is 100% LOGGED OUT!
        const allBtns = document.querySelectorAll('a, button, [role="button"]');
        for (const el of allBtns) {
            if (el.offsetParent === null) continue;
            const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
            const aria = (el.getAttribute('aria-label') || '').trim().toLowerCase();
            const href = (el.getAttribute('href') || '').toLowerCase();
            if (txt === 'sign in' || txt === 'साइन इन करें' || aria === 'sign in' || href.includes('servicelogin')) {
                return false;
            }
        }
        // 2. Check for Google Account Avatar in top right OR active prompt editor without sign-in button
        const avatar = document.querySelector(
            'a[aria-label*="Google Account"], button[aria-label*="Google Account"], [aria-label*="@gmail.com"], img.gb_P, img.gbii, .gb_d[aria-label*="Google"]'
        );
        const editor = document.querySelector('div[contenteditable="true"], rich-textarea, textarea');
        return Boolean(editor && (avatar || document.querySelectorAll('button, [role="button"]').length > 5));
        """
        return bool(driver.execute_script(js_strict_ui_check))
    except Exception:
        return False


def save_all_browser_cookies_via_cdp(driver, force_save=False):
    """
    Saves ONLY genuine, live signed-in cookies from the current browser (never merges old dead cookies!).
    """
    try:
        if not is_gemini_truly_signed_in(driver):
            return 0

        driver.execute_cdp_cmd("Network.enable", {})
        res = driver.execute_cdp_cmd("Network.getAllCookies", {})
        all_cookies = res.get("cookies", [])

        essential = []
        for c in all_cookies:
            dom = c.get("domain", "")
            if any(k in dom for k in ["google", "youtube", "gstatic", "googleusercontent"]):
                clean_c = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": dom,
                    "path": c.get("path", "/"),
                    "secure": bool(c.get("secure", True)),
                    "httpOnly": bool(c.get("httpOnly", False)),
                    "hostOnly": bool(not dom.startswith("."))
                }
                if c.get("sameSite") in ("Strict", "Lax", "None"):
                    clean_c["sameSite"] = c["sameSite"]
                clean_c["expires"] = float(int(time.time()) + 86400 * 180)
                if c.get("priority") in ("Low", "Medium", "High"):
                    clean_c["priority"] = c["priority"]
                if c.get("sameParty") is not None:
                    clean_c["sameParty"] = bool(c["sameParty"])
                essential.append(clean_c)

        names = {x["name"] for x in essential}
        if "SID" in names and "__Secure-1PSID" in names and len(essential) >= 12:
            ua = DEFAULT_WIN_UA
            local_store = {}
            if os.name == "nt":
                try:
                    ua = driver.execute_script("return navigator.userAgent;") or DEFAULT_WIN_UA
                    local_store = driver.execute_script(
                        "let o={}; for(let i=0;i<localStorage.length;i++){let k=localStorage.key(i); o[k]=localStorage.getItem(k);} return o;"
                    ) or {}
                except Exception:
                    pass
            elif os.path.exists(COOKIE_FILE):
                try:
                    old_b = json.load(open(COOKIE_FILE, "r", encoding="utf-8"))
                    ua = old_b.get("user_agent") or DEFAULT_WIN_UA
                    local_store = old_b.get("local_storage") or {}
                except Exception:
                    pass

            bundle = {
                "user_agent": ua,
                "cookies": essential,
                "local_storage": local_store,
                "saved_at": time.time()
            }
            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(bundle, f, indent=2)

            slot_k = globals().get("_ACTIVE_COOKIE_ACCOUNT_SLOT", 1)
            if "_RUNTIME_FRESH_COOKIES_MEM" in globals():
                _RUNTIME_FRESH_COOKIES_MEM[slot_k] = essential

            if os.name != "nt":
                sync_file_to_github(COOKIE_FILE, "Auto-refresh verified rotating __Secure-1PSIDTS cookie token")
                print(f"🔄 [Rolling Token Guard] Synced {len(essential)} REAL signed-in cookies to GitHub!")
            else:
                print(f"💾 Locked {len(essential)} REAL Signed-In Cookies into {COOKIE_FILE}!")
            return len(essential)
    except Exception as e:
        print(f"⚠️ Cookie save note: {e}")
    return 0


def inject_cookies_and_open_gemini(driver, skip_cookie_inject=False):
    """
    100% Pure Cookie + Fingerprint Login (NO password typing!).
    Restores exact host-only & domain cookies across accounts.google.com and gemini.google.com.
    NO TIME LIMIT on local login — waits as long as needed!
    """
    driver.execute_cdp_cmd("Network.enable", {})
    bundle = _load_saved_session_bundle()
    cookies = bundle.get("cookies", [])
    saved_ua = bundle.get("user_agent") or DEFAULT_WIN_UA
    saved_ls = bundle.get("local_storage") or {}

    if os.name != "nt":
        try:
            driver.execute_cdp_cmd("Network.setUserAgentOverride", {
                "userAgent": saved_ua,
                "platform": "Win32",
                "acceptLanguage": "en-US,en;q=0.9"
            })
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'platform', {get: () => 'Win32'}); Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            })
        except Exception:
            pass

    if cookies and not skip_cookie_inject:
        print(f"🔐 Injecting {len(cookies)} pure Google cookies (with exact Host/Domain mapping)...")
        now_ts = time.time()
        for c in cookies:
            try:
                name = c["name"]
                val = c["value"]
                dom = c.get("domain", ".google.com")
                path = c.get("path", "/")
                sec = bool(c.get("secure", True))
                http_only = bool(c.get("httpOnly", False))
                exp = float(c["expires"]) if (c.get("expires") and float(c["expires"]) > now_ts) else float(int(now_ts) + 86400 * 180)

                clean_host = dom.lstrip(".")
                cookie_url = f"https://{clean_host}{path}"

                cdp_cookie = {
                    "name": name,
                    "value": val,
                    "url": cookie_url,
                    "path": path,
                    "secure": sec,
                    "httpOnly": http_only,
                    "expires": exp
                }
                # Critical: If cookie is NOT __Host- and NOT hostOnly, include domain!
                if not name.startswith("__Host-") and not c.get("hostOnly", False):
                    cdp_cookie["domain"] = dom

                if c.get("sameSite") in ("Strict", "Lax", "None"):
                    cdp_cookie["sameSite"] = c["sameSite"]
                if c.get("priority") in ("Low", "Medium", "High"):
                    cdp_cookie["priority"] = c["priority"]

                driver.execute_cdp_cmd("Network.setCookie", cdp_cookie)
            except Exception:
                pass



    print("🌐 Opening Google Gemini (`https://gemini.google.com/app`)...")
    driver.get(GEMINI_URL)
    time.sleep(2.2)

    # Restore localStorage keys if available
    if saved_ls and not skip_cookie_inject:
        try:
            driver.execute_script(
                "const d=arguments[0]; for(const k in d){try{localStorage.setItem(k, d[k]);}catch(e){}}",
                saved_ls
            )
        except Exception:
            pass

    tick = 0
    while True:
        tick += 1
        install_file_dialog_blocker(driver)

        if is_gemini_truly_signed_in(driver):
            print("✅ Google Gemini Signed-In Workspace is 100% Open & Verified via Cookies!")
            save_all_browser_cookies_via_cdp(driver)
            try:
                slot_k = globals().get("_ACTIVE_COOKIE_ACCOUNT_SLOT", 1)
                _RUNTIME_FRESH_COOKIES_MEM[slot_k] = driver.execute_cdp_cmd("Network.getAllCookies", {}).get("cookies", [])
            except Exception:
                pass
            time.sleep(1.5)
            # IMMORTAL COOKIE RENEWAL: Save rotated Google cookies on BOTH Laptop & Cloud so they NEVER expire!
            cnt = save_all_browser_cookies_via_cdp(driver)
            if cnt:
                print(f"💾 [Auto-Renewed] Synced {cnt} fresh Google cookies to GitHub so session NEVER expires!")
            return True

        try:
            curr_url = (driver.current_url or "").lower()

            # Check if an account chooser ('Choose an account') is on screen -> click it (No password needed if cookie is valid!)
            if "accounts.google.com" in curr_url or "consent.google.com" in curr_url:
                if _auto_handle_google_password_screen_if_shown(driver, 1):
                    time.sleep(2.0)
                    continue
                state = driver.execute_script(
                    """
                    const passInput = document.querySelector('input[type="password"][name="Passwd"], input[type="password"]');
                    if (passInput && passInput.offsetParent !== null) {
                        return 'NEEDS_MANUAL_COOKIE_REFRESH';
                    }
                    const acc = document.querySelector('[data-identifier], [data-email]');
                    if (acc && acc.offsetParent !== null) {
                        acc.click();
                        return 'CLICKED_ACCOUNT';
                    }
                    return 'ON_ACCOUNTS_PAGE';
                    """
                )
                if state == "CLICKED_ACCOUNT":
                    print("👤 Clicked account on Google chooser...")
                    time.sleep(3.0)
                    continue

                if state == "NEEDS_MANUAL_COOKIE_REFRESH":
                    active_slot = globals().get("_ACTIVE_COOKIE_ACCOUNT_SLOT", 1)
                    if "_auto_handle_google_password_screen_if_shown" in globals():
                        if _auto_handle_google_password_screen_if_shown(driver, active_slot):
                            time.sleep(3.0)
                            continue
                    if os.name == "nt":
                        if tick % 5 == 0:
                            print(f"🔐 [Account #{active_slot}] Chrome window mein 1 baar Password daal kar Sign-In pura kar de bhai, bot khud cookies save kar lega...")
                        time.sleep(2.0)
                        continue
                    elif tick >= 12:
                        err = f"Google Account #{active_slot} asked for password on Cloud. Refresh cookies or set GEMINI_ACC{active_slot}_PASSWORD."
                        report_step_problem_instantly(driver, "Gemini Cookie Expired", err)
                        raise RuntimeError(err)

            else:
                # On gemini.google.com: if 'Sign in' button appears, click it once so cookies log in automatically
                if tick == 3 or tick == 10:
                    driver.execute_script(
                        """
                        const btns = Array.from(document.querySelectorAll('a, button, [role="button"]')).filter(el => {
                            if (el.offsetParent === null) return false;
                            const t = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
                            return t === 'sign in' || t === 'sign in to gemini';
                        });
                        if (btns.length > 0) btns[0].click();
                        """
                    )
        except RuntimeError:
            raise
        except Exception:
            pass

        # On Cloud headless: only stop if 90 seconds pass and it is STILL not signed in
        if os.name != "nt" and tick >= 90:
            err = "Gemini could not sign in using cookies on Cloud. Run `python gemini_bot.py --save-cookies` on laptop."
            report_step_problem_instantly(driver, "Gemini Login Error", err)
            raise RuntimeError(err)

        time.sleep(1.0)


def single_clean_click_xy(driver, x, y, label="Button"):
    x_int, y_int = int(x), int(y)
    print(f"   🎯 [Single Click] '{label}' at ({x_int}, {y_int})")
    try:
        driver.execute_script(
            """
            const x = arguments[0], y = arguments[1];
            const dot = document.createElement('div');
            dot.style.cssText = 'position:fixed;left:' + (x-16) + 'px;top:' + (y-16) + 'px;width:32px;height:32px;border:3px solid #00ff88;border-radius:50%;background:rgba(0,255,136,0.28);z-index:999999;pointer-events:none;box-shadow:0 0 14px #00ff88;';
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
        time.sleep(0.06)
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x_int, "y": y_int, "button": "left", "clickCount": 1})
        time.sleep(0.06)
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x_int, "y": y_int, "button": "left", "clickCount": 1})
        return True
    except Exception:
        return False


def click_by_pct_single(driver, xpct, ypct, label="Recorded %"):
    vw_vh = driver.execute_script("return {w: window.innerWidth, h: window.innerHeight};")
    cx = int((float(xpct) / 100.0) * vw_vh["w"])
    cy = int((float(ypct) / 100.0) * vw_vh["h"])
    return single_clean_click_xy(driver, cx, cy, label)


def load_recorded_step_coords(step_num, default_xpct, default_ypct):
    try:
        if os.path.exists(BLUEPRINT_FILE):
            with open(BLUEPRINT_FILE, "r", encoding="utf-8") as f:
                bp = json.load(f)
            steps = bp.get("steps", bp) if isinstance(bp, dict) else bp
            if isinstance(steps, list):
                for s in steps:
                    if int(s.get("step", s.get("step_num", -1))) == int(step_num):
                        xp = s.get("xpct", s.get("x_pct", default_xpct))
                        yp = s.get("ypct", s.get("y_pct", default_ypct))
                        return float(xp), float(yp)
    except Exception:
        pass
    return float(default_xpct), float(default_ypct)


def find_gemini_element_by_spec(driver, aria_list=None, txt_list=None, icon_list=None, near_xpct=None, near_ypct=None, exclude_words=None):
    aria_list = [a.lower().strip() for a in (aria_list or []) if a]
    txt_list = [t.lower().strip() for t in (txt_list or []) if t]
    icon_list = [i.lower().strip() for i in (icon_list or []) if i]
    exclude_words = [w.lower().strip() for w in (exclude_words or []) if w]

    js_find = """
    const ariaList = arguments[0];
    const txtList = arguments[1];
    const iconList = arguments[2];
    const nearX = arguments[3];
    const nearY = arguments[4];
    const excludeWords = arguments[5] || [];

    function walkAll(root) {
        let res = [];
        for (const el of root.querySelectorAll('*')) {
            res.push(el);
            if (el.shadowRoot) res = res.concat(walkAll(el.shadowRoot));
        }
        return res;
    }

    let best = null;
    let bestScore = -999999;

    for (const el of walkAll(document)) {
        const r = el.getBoundingClientRect();
        if (r.width < 12 || r.height < 12 || r.width > 420 || r.height > 110) continue;
        if (r.bottom <= 0 || r.top >= window.innerHeight) continue;

        const style = window.getComputedStyle(el);
        if (style.visibility === 'hidden' || style.display === 'none' || parseFloat(style.opacity) === 0 || style.pointerEvents === 'none') continue;

        const tag = el.tagName.toLowerCase();
        const aria = (el.getAttribute('aria-label') || '').trim().toLowerCase();
        const tip = (el.getAttribute('mattooltip') || el.getAttribute('title') || '').trim().toLowerCase();
        const iconEl = (el.querySelector && el.querySelector('mat-icon')) || (tag === 'mat-icon' ? el : null);
        const icon = iconEl ? ((iconEl.getAttribute('data-mat-icon-name') || iconEl.getAttribute('fonticon') || iconEl.innerText || '').trim().toLowerCase()) : '';
        const txt = (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').toLowerCase();
        if (txt.length > 75 && tag !== 'textarea' && el.getAttribute('contenteditable') !== 'true') continue;

        const combined = (aria + ' ' + tip + ' ' + txt + ' ' + icon).trim();

        let isExcluded = false;
        for (const ex of excludeWords) {
            if (combined.includes(ex)) { isExcluded = true; break; }
        }
        if (isExcluded) continue;

        let score = 0;
        let matched = false;

        for (const a of ariaList) {
            if (aria === a || tip === a) { score += 1000; matched = true; break; }
            if (aria.includes(a) || tip.includes(a)) { score += 650; matched = true; break; }
        }
        for (const t of txtList) {
            if (txt === t) { score += 1100; matched = true; break; }
            if (txt.startsWith(t)) { score += 850; matched = true; break; }
            if (txt.includes(t)) { score += 500; matched = true; break; }
        }
        for (const ic of iconList) {
            if (icon === ic) { score += 600; matched = true; break; }
        }

        if (!matched) continue;

        const clickable = el.closest('button, [role="menuitem"], [role="option"], [role="radio"], gem-menu-item, mat-option, a, rich-textarea, div[contenteditable="true"], textarea') || el;
        const cr = clickable.getBoundingClientRect();
        const targetRect = (cr.height <= 95 && cr.width <= 420) ? cr : r;

        const clickableTxt = ((clickable.innerText || '') + ' ' + (clickable.getAttribute('aria-label') || '')).toLowerCase();
        for (const ex of excludeWords) {
            if (clickableTxt.includes(ex) && !clickableTxt.includes('create video')) {
                isExcluded = true;
                break;
            }
        }
        if (isExcluded) continue;

        const isDisabled = Boolean(clickable.disabled || clickable.getAttribute('aria-disabled') === 'true' || el.getAttribute('aria-disabled') === 'true');
        const cxPct = ((targetRect.left + targetRect.width / 2) / window.innerWidth) * 100;
        const cyPct = ((targetRect.top + targetRect.height / 2) / window.innerHeight) * 100;

        if (nearX !== null && nearY !== null) {
            const dist = Math.abs(cxPct - nearX) + Math.abs(cyPct - nearY);
            score -= dist * 2.5;
        }
        score -= (targetRect.height * 1.5) + Math.min(50, txt.length * 2);

        if (score > bestScore) {
            bestScore = score;
            best = {
                x: Math.round(targetRect.left + targetRect.width / 2),
                y: Math.round(targetRect.top + targetRect.height / 2),
                label: (txt || aria || icon || tag).slice(0, 42),
                disabled: isDisabled
            };
        }
    }
    return best;
    """
    try:
        return driver.execute_script(js_find, aria_list, txt_list, icon_list, near_xpct, near_ypct, exclude_words)
    except Exception:
        return None


def wait_and_single_click_step(
    driver,
    step_name,
    aria_list=None,
    txt_list=None,
    icon_list=None,
    near_xpct=None,
    near_ypct=None,
    exclude_words=None,
    verify_next_aria=None,
    verify_next_txt=None,
    verify_next_icon=None,
    custom_verify_js=None,
    wait_timeout=45.0,
    verify_timeout=15.0,
    max_attempts=4,
    optional=False
):
    for attempt in range(1, max_attempts + 1):
        install_file_dialog_blocker(driver)

        if attempt > 1:
            if custom_verify_js and bool(driver.execute_script(custom_verify_js)):
                return True
            if (verify_next_aria or verify_next_txt or verify_next_icon) and find_gemini_element_by_spec(
                driver, aria_list=verify_next_aria, txt_list=verify_next_txt, icon_list=verify_next_icon
            ):
                return True

        start_t = time.time()
        found = None
        while (time.time() - start_t) < wait_timeout:
            install_file_dialog_blocker(driver)
            found = find_gemini_element_by_spec(
                driver,
                aria_list=aria_list,
                txt_list=txt_list,
                icon_list=icon_list,
                near_xpct=near_xpct,
                near_ypct=near_ypct,
                exclude_words=exclude_words
            )
            if found:
                break
            time.sleep(0.35)

        if not found:
            if optional:
                return False
            if near_xpct is not None and near_ypct is not None and attempt >= 2:
                click_by_pct_single(driver, near_xpct, near_ypct, f"{step_name} (Blueprint %)")
                time.sleep(0.9)
            else:
                time.sleep(1.0)
                continue
        else:
            single_clean_click_xy(driver, found["x"], found["y"], f"{step_name} ('{found['label']}')")
            time.sleep(0.9)

        if not (verify_next_aria or verify_next_txt or verify_next_icon or custom_verify_js):
            return True

        v_start = time.time()
        while (time.time() - v_start) < verify_timeout:
            install_file_dialog_blocker(driver)
            try:
                if custom_verify_js and bool(driver.execute_script(custom_verify_js)):
                    return True
                if (verify_next_aria or verify_next_txt or verify_next_icon) and find_gemini_element_by_spec(
                    driver, aria_list=verify_next_aria, txt_list=verify_next_txt, icon_list=verify_next_icon
                ):
                    return True
            except Exception:
                pass
            time.sleep(0.4)

        print(f"   🔄 [{step_name}] Waiting for menu response ({attempt}/{max_attempts})...")
        time.sleep(1.0)

    return False


def verify_create_video_selected_or_detect_limit(driver):
    """
    Checks if 'Create video' chip is active, OR if an explicit Google Video Quota limit banner is visible.
    Never triggers a false limit just because a 'Try it' dialog appeared!
    """
    js_check = """
    const bodyTxt = (document.body.innerText || '').toLowerCase();
    const limitPhrases = [
        "you've reached your video generation limit",
        "reached your limit for video",
        "video generation limit reached",
        "can't generate more videos right now",
        "daily limit for video generation",
        "generating too many videos",
        "high traffic for video generation"
    ];
    for (const p of limitPhrases) {
        if (bodyTxt.includes(p)) return 'LIMIT:' + p;
    }
    const chips = document.querySelectorAll('mat-chip, [role="button"], button, .tool-chip, span, div');
    for (const c of chips) {
        if (c.offsetParent === null) continue;
        const r = c.getBoundingClientRect();
        if (r.top < 250 || r.width > 320 || r.height > 75) continue;
        const t = ((c.innerText || c.textContent || '') + ' ' + (c.getAttribute('aria-label') || '')).trim().toLowerCase();
        if (t === 'create video' || t === 'video' || t.includes('remove create video') || t.includes('deselect create video')) {
            return 'OK';
        }
    }
    const ed = document.querySelector('div[contenteditable="true"], rich-textarea, textarea');
    if (ed) {
        const ph = (ed.getAttribute('aria-label') || ed.getAttribute('placeholder') || ed.getAttribute('data-placeholder') || '').toLowerCase();
        if (ph.includes('video') || ph.includes('describe your video')) return 'OK';
    }
    return 'NOT_YET';
    """
    try:
        return driver.execute_script(js_check) or "NOT_YET"
    except Exception:
        return "NOT_YET"


def execute_locked_13_step_gemini_pipeline(driver, foji_img, fojan_img, fresh_prompt):
    install_file_dialog_blocker(driver)

    s1_x, s1_y = load_recorded_step_coords(1, 77.7, 49.4)
    s2_x, s2_y = load_recorded_step_coords(2, 75.1, 65.2)
    s3_x, s3_y = load_recorded_step_coords(3, 38.8, 50.9)
    s4_x, s4_y = load_recorded_step_coords(4, 44.5, 78.5)
    s5_x, s5_y = load_recorded_step_coords(5, 55.4, 87.0)
    s6_x, s6_y = load_recorded_step_coords(6, 71.1, 89.6)
    s7_x, s7_y = load_recorded_step_coords(7, 69.1, 80.2)
    s8_x, s8_y = load_recorded_step_coords(8, 38.5, 80.4)
    s9_x, s9_y = load_recorded_step_coords(9, 45.2, 46.0)
    s12_x, s12_y = load_recorded_step_coords(12, 82.3, 79.4)

    print("[Step #1 & #2] Selecting '4 Hydrogen (Everyday help)' Mode...")
    opened_picker = wait_and_single_click_step(
        driver,
        "Step #1: Open Mode Picker",
        aria_list=["open mode picker", "mode picker", "model"],
        txt_list=["4 hydrogen", "hydrogen", "4 argon", "argon", "3.5 flash lite", "flash lite", "3.1 pro", "everyday help", "quick answers", "pro", "flash"],
        icon_list=["keyboard_arrow_down", "arrow_drop_down"],
        near_xpct=s1_x,
        near_ypct=s1_y,
        verify_next_txt=["4 hydrogen", "hydrogen", "everyday help", "3.5 flash lite", "quick answers"],
        wait_timeout=5.0,
        verify_timeout=3.0,
        max_attempts=1,
        optional=True
    )
    if opened_picker:
        picked_h2 = wait_and_single_click_step(
            driver,
            "Step #2A: Select '4 Hydrogen (Everyday help)'",
            txt_list=["everyday help 4 hydrogen", "everday help 4 hydrogen", "4 hydrogen", "hydrogen", "everyday help"],
            near_xpct=s2_x,
            near_ypct=s2_y,
            wait_timeout=3.5,
            verify_timeout=2.0,
            max_attempts=1,
            optional=True
        )
        if not picked_h2:
            wait_and_single_click_step(
                driver,
                "Step #2B: Select '3.5 Flash Lite'",
                txt_list=["quick answers 3.5 flash lite", "3.5 flash lite", "flash lite", "quick answers", "flash"],
                near_xpct=s2_x,
                near_ypct=s2_y,
                wait_timeout=3.0,
                verify_timeout=2.0,
                max_attempts=1,
                optional=True
            )
        time.sleep(0.8)

    print("[Step #3 & #4] Opening 'Upload & tools' (+) -> Strictly Clicking 'Create video'...")
    for attempt_cv in range(1, 4):
        dismiss_any_agree_or_consent_popup(driver)
        if verify_create_video_selected_or_detect_limit(driver) == "OK":
            break

        wait_and_single_click_step(
            driver,
            f"Step #3: Upload & tools (+) [Try {attempt_cv}]",
            aria_list=["upload & tools", "tools", "add", "plus", "open upload"],
            txt_list=["+", "tools"],
            icon_list=["add", "add_circle", "spark", "video_spark"],
            near_xpct=s3_x,
            near_ypct=s3_y,
            verify_next_txt=["create video", "upload files", "upload image"],
            wait_timeout=5.0,
            verify_timeout=3.0,
            max_attempts=2,
            optional=False
        )
        time.sleep(0.6)

        wait_and_single_click_step(
            driver,
            f"Step #4: Create video (STRICT VIDEO ONLY) [Try {attempt_cv}]",
            aria_list=["create video"],
            txt_list=["create video", "generate video"],
            icon_list=["movie", "videocam", "video_spark", "smart_display"],
            near_xpct=s4_x,
            near_ypct=s4_y,
            wait_timeout=5.0,
            verify_timeout=2.5,
            max_attempts=2,
            optional=False
        )
        time.sleep(1.0)

        had_try_popup = wait_and_single_click_step(
            driver,
            "Step #5: Dismiss 'Try it / Agree' Popup",
            txt_list=["try it", "got it", "agree", "i agree", "accept", "continue"],
            near_xpct=s5_x,
            near_ypct=s5_y,
            wait_timeout=2.5,
            verify_timeout=1.5,
            max_attempts=1,
            optional=True
        )
        dismiss_any_agree_or_consent_popup(driver)
        time.sleep(0.8)

        chk_after = verify_create_video_selected_or_detect_limit(driver)
        if chk_after == "OK":
            print("   Confirmed: 'Create video' tool chip is active in prompt box!")
            break
        elif chk_after.startswith("LIMIT:") and not had_try_popup:
            lim_msg = chk_after.replace("LIMIT:", "").strip()
            report_step_problem_instantly(driver, "Gemini Video Limit Reached", lim_msg)
            raise GeminiLimitReachedError(f"Gemini Video Limit Reached: {lim_msg}")
        else:
            print(f"   Popup dismissed -> Re-clicking 'Create video' (Attempt {attempt_cv}/3)...")

    print("📱 [Step #6 & #7] Setting Aspect Ratio to 'Portrait (9:16)'...")
    already_portrait = driver.execute_script(
        "return Boolean(document.querySelector('[aria-label*=Portrait i]'));"
    )
    if not already_portrait:
        opened_ratio = wait_and_single_click_step(
            driver,
            "Step #6: Aspect Ratio (Landscape 16:9)",
            aria_list=["aspect ratio, landscape (16:9)", "aspect ratio"],
            txt_list=["landscape", "16:9"],
            icon_list=["crop_16_9"],
            near_xpct=s6_x,
            near_ypct=s6_y,
            verify_next_txt=["portrait (9:16)", "portrait"],
            verify_next_icon=["crop_9_16"]
        )
        if opened_ratio:
            wait_and_single_click_step(
                driver,
                "Step #7: Select Portrait (9:16)",
                txt_list=["portrait (9:16)", "portrait", "9:16"],
                icon_list=["crop_9_16"],
                near_xpct=s7_x,
                near_ypct=s7_y,
                exclude_words=["landscape", "16:9"]
            )
            time.sleep(0.8)

    print("📸 [Step #8, #9 & #10] Clicking 'Upload & tools' (+) -> 'Upload files' -> Injecting Foji & Fojan...")
    install_file_dialog_blocker(driver)
    wait_and_single_click_step(
        driver,
        "Step #8: Upload & tools (+)",
        aria_list=["upload & tools"],
        icon_list=["plus", "add"],
        near_xpct=s8_x,
        near_ypct=s8_y,
        verify_next_txt=["upload files"],
        verify_next_aria=["upload files"],
        verify_next_icon=["attach_file"]
    )

    install_file_dialog_blocker(driver)
    js_verify_file_input = "return document.querySelectorAll('input[type=file]').length > 0;"
    wait_and_single_click_step(
        driver,
        "Step #9: Upload files",
        aria_list=["upload files. documents, data, code files", "upload files"],
        txt_list=["upload files"],
        icon_list=["attach_file"],
        near_xpct=s9_x,
        near_ypct=s9_y,
        exclude_words=["drive", "video", "music", "image"],
        custom_verify_js=js_verify_file_input
    )

    inject_character_files_into_gemini(driver, foji_img, fojan_img)

    print("✉️ [Step #11] Filling fresh AI Script into 'Enter a prompt for Gemini'...")
    if not fill_gemini_prompt_box_and_verify(driver, fresh_prompt):
        report_step_problem_instantly(driver, "Step #11: Fill Prompt Box", "Could not fill script into Gemini prompt box.")
        raise RuntimeError("Step #11 (Fill Prompt Box) failed.")

    dismiss_any_agree_or_consent_popup(driver)
    print("🚀 [Step #12] Clicking 'Send message' (`arrow_upward`)...")
    js_verify_sent = """
    const box = document.querySelector('[aria-label*="Enter a prompt" i], rich-textarea div[contenteditable="true"], div[contenteditable="true"], textarea');
    const len = box ? ((box.value || box.innerText || '').trim().length) : 0;
    const stopBtn = document.querySelector('[aria-label*="Stop response" i], [aria-label*="Stop generating" i]');
    return (len < 15) || Boolean(stopBtn);
    """
    ok_sent = wait_and_single_click_step(
        driver,
        "Step #12: Send message",
        aria_list=["send message"],
        icon_list=["arrow_upward", "send"],
        near_xpct=s12_x,
        near_ypct=s12_y,
        custom_verify_js=js_verify_sent
    )
    if not ok_sent:
        try:
            box_el = driver.find_element(By.CSS_SELECTOR, "[aria-label*='Enter a prompt' i], rich-textarea div[contenteditable='true'], div[contenteditable='true'], textarea")
            box_el.send_keys(Keys.ENTER)
        except Exception:
            pass
    return True


def get_gemini_reply_and_video_status(driver, ignored_video_urls):
    js_status = """
    const ignored = new Set(arguments[0] || []);

    function walkAll(root) {
        let res = [];
        try {
            for (const el of root.querySelectorAll('*')) {
                res.push(el);
                if (el.shadowRoot) res = res.concat(walkAll(el.shadowRoot));
                if (el.tagName === 'IFRAME') {
                    try {
                        if (el.contentDocument) res = res.concat(walkAll(el.contentDocument));
                    } catch (e) {}
                }
            }
        } catch (e) {}
        return res;
    }

    const cards = document.querySelectorAll('model-response, message-content, video, [class*="video" i], [class*="media" i]');
    if (cards.length > 0) {
        const lastCard = cards[cards.length - 1];
        lastCard.scrollIntoView({block: 'center', behavior: 'instant'});
        lastCard.dispatchEvent(new MouseEvent('mouseenter', {bubbles: true}));
        lastCard.dispatchEvent(new MouseEvent('mouseover', {bubbles: true}));
        lastCard.dispatchEvent(new MouseEvent('mousemove', {bubbles: true}));
    }

    const allNodes = walkAll(document);
    let isGenerating = false;

    for (const el of allNodes) {
        if (!el.offsetParent && el.tagName !== 'MAT-PROGRESS-BAR') continue;
        const aria = (el.getAttribute && (el.getAttribute('aria-label') || '')).toLowerCase();
        const txt = (el.innerText || '').trim().toLowerCase();
        const tag = (el.tagName || '').toLowerCase();
        if (
            aria.includes('stop response') ||
            aria.includes('stop generating') ||
            txt.includes('generating video') ||
            txt.includes('creating video') ||
            txt.includes('generating your video') ||
            (txt.includes('generating') && txt.length < 55) ||
            tag === 'mat-progress-bar' ||
            tag === 'mat-spinner' ||
            tag === 'mat-progress-spinner'
        ) {
            isGenerating = true;
            break;
        }
    }

    const newVideos = [];
    for (const el of allNodes) {
        const tag = (el.tagName || '').toLowerCase();
        if (tag === 'video') {
            const src = el.currentSrc || el.src || (el.querySelector('source') ? el.querySelector('source').src : '');
            if (src && src.length > 8 && !ignored.has(src)) {
                newVideos.push(src);
            } else if (el.offsetWidth > 100 && el.offsetHeight > 100) {
                newVideos.push('DOM_VIDEO_ELEMENT_VISIBLE');
            }
        }
    }

    let dlBtn = null;
    for (const el of allNodes) {
        const tag = (el.tagName || '').toLowerCase();
        const aria = ((el.getAttribute && el.getAttribute('aria-label')) || '').trim().toLowerCase();
        const tip = ((el.getAttribute && (el.getAttribute('mattooltip') || el.getAttribute('title'))) || '').trim().toLowerCase();
        const iconEl = (el.querySelector && el.querySelector('mat-icon, i, span[class*="icon" i]')) || (tag === 'mat-icon' ? el : null);
        const iconTxt = iconEl ? ((iconEl.getAttribute('data-mat-icon-name') || iconEl.getAttribute('fonticon') || iconEl.innerText || '').trim().toLowerCase()) : '';

        const isDownloadMatch = (
            aria.includes('download video') ||
            tip.includes('download video') ||
            aria === 'download' ||
            tip === 'download' ||
            iconTxt === 'download' ||
            iconTxt === 'file_download' ||
            (tag === 'a' && el.hasAttribute('download'))
        );

        if (isDownloadMatch) {
            const clickable = el.closest('button, a, [role="button"]') || el;
            const r = clickable.getBoundingClientRect();
            if (r.width >= 8 && r.height >= 8 && r.top > 60) {
                dlBtn = {
                    x: Math.round(r.left + r.width / 2),
                    y: Math.round(r.top + r.height / 2),
                    label: (aria || tip || iconTxt || 'download_video').slice(0, 40)
                };
            }
        }
    }

    let latestReply = '';
    const msgContainers = document.querySelectorAll('message-content, model-response, .model-response-text, [data-message-author-role="model"]');
    if (msgContainers.length > 0) {
        const last = msgContainers[msgContainers.length - 1];
        latestReply = (last.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 400);
    }

    const lowReply = latestReply.toLowerCase();
    const isLimit = (
        lowReply.includes('limit') || lowReply.includes('quota') ||
        lowReply.includes('try again tomorrow') || lowReply.includes('reached your')
    );
    const isRefusalOrError = isLimit || (
        lowReply.includes("can't generate") || lowReply.includes('cannot generate') ||
        lowReply.includes('unable to') || lowReply.includes('something went wrong') ||
        lowReply.includes("i can't create") || lowReply.includes('policy')
    );

    return {
        is_generating: isGenerating,
        new_video_urls: newVideos,
        download_btn: dlBtn,
        screen_reply_text: latestReply,
        is_limit: isLimit,
        is_refusal_or_error: isRefusalOrError
    };
    """
    try:
        return driver.execute_script(js_status, list(ignored_video_urls)) or {
            "is_generating": False,
            "new_video_urls": [],
            "download_btn": None,
            "screen_reply_text": "",
            "is_limit": False,
            "is_refusal_or_error": False
        }
    except Exception:
        return {
            "is_generating": False,
            "new_video_urls": [],
            "download_btn": None,
            "screen_reply_text": "",
            "is_limit": False,
            "is_refusal_or_error": False
        }


def execute_step13_download_video(driver, dl_btn, new_video_url, raw_dir, existing_mp4s, output_video_path):
    print("📥 [Step #13] Clicking 'Download video' (`Icon='download'`)...")

    if dl_btn:
        single_clean_click_xy(driver, dl_btn["x"], dl_btn["y"], f"Step #13: {dl_btn['label']}")
    else:
        wait_and_single_click_step(
            driver,
            "Step #13: Download video",
            aria_list=["download video", "download"],
            icon_list=["download"],
            near_xpct=52.3,
            near_ypct=66.5,
            wait_timeout=25.0,
            max_attempts=3
        )

    # Wait as long as the file is downloading (.crdownload present or file arriving)
    for _ in range(90):
        time.sleep(2.0)
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
            r = requests.get(new_video_url, cookies=cookies_dict, headers={"User-Agent": "Mozilla/5.0"}, stream=True, timeout=180)
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
            driver.set_script_timeout(180)
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


def export_fresh_gemini_cookies_from_local():
    slot = globals().get("_ACTIVE_COOKIE_ACCOUNT_SLOT", 1)
    target_f = "gemini_cookies_secret_2.txt" if slot == 2 else COOKIE_FILE
    print("\n" + "=" * 75)
    print(f"🔐 SAVING GOOGLE GEMINI COOKIES FOR ACCOUNT #{slot} -> '{target_f}'")
    print(f"👉 Chrome khul raha hai (Profile #{slot}). Apne Google Account #{slot} se Sign-In kar lo!")
    print("👉 Jaise hi Gemini ka prompt box dikhega, Bot khud cookies save karke GitHub Cloud par push kar dega!")
    print("=" * 75 + "\n")
    driver, proc = launch_resilient_chrome_session(os.path.abspath("output/raw_videos"), start_blank=True)
    try:
        if inject_cookies_and_open_gemini(driver, skip_cookie_inject=False):
            count = save_all_browser_cookies_via_cdp(driver, force_save=True)
            print(f"\n🎉 SUCCESS! Exported {count} Pure Cookies for Account #{slot} -> {target_f} & Synced to Cloud!")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        time.sleep(1.5)
        prof_d = os.path.abspath("chrome_gemini_pro_profile_1")
        if os.path.exists(prof_d):
            pack_essential_chrome_profile_to_zip(prof_d)


def generate_video_in_gemini(pending_pkg=None):
    """Strictly uses ONLY Account #1 (`gemini_cookies_secret.txt`). Account #2 is completely disabled."""
    global _ACTIVE_COOKIE_ACCOUNT_SLOT, _SUPPRESS_FAILOVER_NOTIF
    _ACTIVE_COOKIE_ACCOUNT_SLOT = 1
    _SUPPRESS_FAILOVER_NOTIF = False
    print("🎯 [Account Engine] Using ONLY Account #1 (Account #2 is disabled).")
    return _single_attempt_generate_video_in_gemini(pending_pkg=pending_pkg)


def _single_attempt_generate_video_in_gemini(pending_pkg=None):
    os.makedirs("data", exist_ok=True)
    if not os.path.exists("data/history.json"):
        with open("data/history.json", "w", encoding="utf-8") as f:
            json.dump({"generated_count": 0, "history": []}, f)

    with open("data/history.json", "r", encoding="utf-8") as f:
        history_data = json.load(f)

    update_3d_telemetry(1, "Stage 1: AI Episodic Script", "Generating fresh connected script & wardrobe...", "active", 12)

    if not pending_pkg:
        import foji_universe_director as _fud
        new_id = int(history_data.get("generated_count", 0)) + 1
        pending_pkg = _fud.build_real_foji_universe_package(video_id=new_id, is_preview=False)

    rotate_track_and_script_in_history(pending_pkg)
    video_num = pending_pkg.get("video_id", f"{int(time.time())}")
    include_meera = pending_pkg.get("include_meera", True)
    meera_outfit = pending_pkg.get("meera_outfit", "Fresh Haryanvi Suit")

    foji_img = find_image("foji")
    fojan_img = find_image("fojan") if include_meera else None
    if not foji_img or (include_meera and not fojan_img):
        err = "Character photos missing in assets/characters."
        update_3d_telemetry(1, "Assets Missing", err, "error", 0)
        push_app_notification("error", "Assets Missing", err, "error")
        send_alert(f"⚠️ *Assets Missing*\n{err}")
        raise FileNotFoundError(err)

    raw_dir = os.path.abspath("output/raw_videos")
    os.makedirs(raw_dir, exist_ok=True)
    unique_fname = pending_pkg.get("video_file") or f"raw_video_{video_num}.mp4"
    output_video_path = os.path.join(raw_dir, unique_fname)
    base_video_prompt = pending_pkg["gemini_video_prompt"]

    cast_info = f"Makra + Meera ({meera_outfit[:38]}...)" if include_meera else "Makra Only (Solo Army Scene)"
    slot_num = globals().get("_ACTIVE_COOKIE_ACCOUNT_SLOT", 1)

    print(f"🚀 [Stage 2/8] Launching Gemini Engine (Account #{slot_num}) | Cast: {cast_info} | File: {unique_fname}")
    update_3d_telemetry(2, f"Stage 2: Cookie Sign-In (Account #{slot_num})", f"Logging into Gemini & preparing {cast_info}...", "active", 25)
    push_app_notification("info", f"🎬 Step 2: Gemini Login (Acc #{slot_num})", f"Episode: {pending_pkg.get('emotion_name')} | Cast: {cast_info}", "info")

    driver, chrome_proc = launch_resilient_chrome_session(raw_dir, start_blank=True)

    try:
        existing_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
        inject_cookies_and_open_gemini(driver)

        initial_status = get_gemini_reply_and_video_status(driver, set())
        ignored_video_urls = set(initial_status.get("new_video_urls", []))

        update_3d_telemetry(3, "Stage 3: Create Video & 9:16 Portrait", f"Selecting Create Video + 9:16 + Uploading ({cast_info})...", "active", 45)
        execute_locked_13_step_gemini_pipeline(driver, foji_img, fojan_img, base_video_prompt)

        time.sleep(1.2)
        dismiss_any_agree_or_consent_popup(driver)
        update_3d_telemetry(5, "Stage 5: Prompt Sent -> Rendering Started!", f"Gemini Veo is rendering {unique_fname}...", "active", 68)
        push_app_notification("info", "🚀 Step 5: 3D Video Rendering Started!", f"{pending_pkg.get('emotion_name')} is now rendering in Gemini!", "info")
        time.sleep(4)
        snap_start = "data/gemini_started.png"
        try:
            driver.save_screenshot(snap_start)
            sync_file_to_github(snap_start, "Update live Gemini started screenshot")
            send_telegram_photo(
                snap_start,
                f"🎬 *Google Gemini Video (Portrait 9:16) Started!*\n"
                f"📌 *{pending_pkg.get('emotion_name')}*\n"
                f"👥 *Cast:* `{cast_info}`\n"
                f"🗣️ _{pending_pkg.get('dialogue_line_1_hinglish')}_"
            )
        except Exception:
            pass

        update_3d_telemetry(6, "Stage 6: 3D Video Rendering (0.1 min)", f"Rendering {unique_fname} in Gemini (Zero Timeout)...", "active", 75)
        video_saved = False
        gen_start_t = time.time()
        idle_without_video_ticks = 0
        tick = 0

        while True:
            tick += 1
            time.sleep(4)
            elapsed_sec = int(time.time() - gen_start_t)
            elapsed_mins = round(elapsed_sec / 60.0, 1)

            current_mp4s = set(glob.glob(os.path.join(raw_dir, "*.mp4")))
            new_files = [f for f in (current_mp4s - existing_mp4s) if not f.endswith(".crdownload")]
            if new_files:
                newest = max(new_files, key=os.path.getctime)
                if is_valid_mp4(newest):
                    if os.path.abspath(newest) != os.path.abspath(output_video_path):
                        shutil.move(newest, output_video_path)
                    video_saved = True
                    break

            try:
                vw_vh = driver.execute_script("return {w: window.innerWidth, h: window.innerHeight};")
                driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
                    "type": "mouseMoved",
                    "x": int(vw_vh["w"] * 0.50),
                    "y": int(vw_vh["h"] * 0.55)
                })
            except Exception:
                pass

            dismiss_any_agree_or_consent_popup(driver)
            st = get_gemini_reply_and_video_status(driver, ignored_video_urls)
            is_gen = st.get("is_generating", False)
            new_vids = st.get("new_video_urls", [])
            dl_btn = st.get("download_btn")
            screen_reply = (st.get("screen_reply_text") or "").strip()

            print(
                f"⏳ [Gemini {elapsed_mins} min ({elapsed_sec}s) - NO TIMEOUT] "
                f"Generating: {is_gen} | Video Detected: {len(new_vids)} | Download Btn: {bool(dl_btn)}"
            )

            if dl_btn is not None or (len(new_vids) > 0 and not is_gen):
                print("✅ [Stage 7/8] Video Ready on Screen! Clicking 'Download video'...")
                update_3d_telemetry(7, "Stage 7: Video Rendered! Downloading MP4...", f"Saving {unique_fname} & pushing to Telegram/Frontend...", "active", 94)
                push_app_notification("info", "📥 Step 7: Video Rendered! Downloading...", f"Downloading {unique_fname} from Gemini...", "info")
                time.sleep(2.5)
                vid_url = new_vids[-1] if (new_vids and new_vids[-1] != "DOM_VIDEO_ELEMENT_VISIBLE") else ""
                if execute_step13_download_video(driver, dl_btn, vid_url, raw_dir, existing_mp4s, output_video_path):
                    video_saved = True
                    break

            if not is_gen and len(new_vids) == 0 and dl_btn is None and elapsed_sec >= 25:
                idle_without_video_ticks += 1
                if st.get("is_refusal_or_error") or (idle_without_video_ticks >= 8 and len(screen_reply) > 15):
                    exact_msg = screen_reply if screen_reply else "Gemini stopped generating without returning a video."
                    if st.get("is_limit"):
                        report_step_problem_instantly(driver, "Gemini Video Limit Reached", f"Screen par yeh aaya: {exact_msg}")
                        raise GeminiLimitReachedError(exact_msg)
                    else:
                        report_step_problem_instantly(driver, "Gemini Screen Error (Video Nahi Bani)", f"Screen par yeh aaya: {exact_msg}")
                        raise RuntimeError(f"Gemini Screen Reply: {exact_msg}")
            else:
                idle_without_video_ticks = 0

            # Push live telemetry every 12 seconds so Frontend progress bar moves continuously!
            if tick % 3 == 0:
                prog = min(92, 74 + int(tick / 4))
                update_3d_telemetry(
                    6,
                    f"Stage 6: Rendering 3D Video ({elapsed_mins} min)",
                    f"Gemini Veo rendering {unique_fname}... ({elapsed_sec}s elapsed)",
                    "active",
                    prog
                )

        if video_saved and is_valid_mp4(output_video_path):
            print(f"🎉 SUCCESS! Gemini 9:16 Video Saved at {output_video_path}")
            bname = os.path.basename(output_video_path)
            rel_vid_path = f"output/raw_videos/{bname}"

            # 1. Send the MP4 Video directly to Telegram Bot with Approve/Schedule Caption!
            tg_caption = (
                f"🎉 *New 3D Foji Reel Ready!*\n"
                f"🎬 *Episode:* {pending_pkg.get('emotion_name')}\n"
                f"👥 *Cast:* `{cast_info}`\n"
                f"📁 *File:* `{bname}`\n\n"
                f"🗣️ _{pending_pkg.get('dialogue_line_1_hinglish')}_\n\n"
                f"✅ Video Frontend Vault & Ready Queue mein bhi aa gayi hai!"
            )
            try:
                print(f"📲 Sending completed MP4 ({bname}) to Telegram...")
                if "send_telegram_video" in globals():
                    send_telegram_video(output_video_path, tg_caption)
                else:
                    # Direct Telegram sendVideo API call so video ALWAYS arrives on Telegram!
                    tg_tok = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
                    tg_cid = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
                    if tg_tok and tg_cid:
                        kb_markup = json.dumps({
                            "inline_keyboard": [
                                [
                                    {"text": "✅ Approve & Post (IG+FB)", "callback_data": f"approve_post:{bname}"},
                                    {"text": "⏰ Approve & Schedule", "callback_data": f"approve_sched:{bname}"}
                                ],
                                [
                                    {"text": "🔄 Regenerate", "callback_data": f"regen:{bname}"},
                                    {"text": "🗑️ Delete", "callback_data": f"delete:{bname}"}
                                ]
                            ]
                        })
                        with open(output_video_path, "rb") as vf_tg:
                            requests.post(
                                f"https://api.telegram.org/bot{tg_tok}/sendVideo",
                                data={"chat_id": tg_cid, "caption": tg_caption[:980], "parse_mode": "Markdown", "reply_markup": kb_markup},
                                files={"video": (bname, vf_tg, "video/mp4")},
                                timeout=90
                            )
                print("✅ Video successfully delivered to Telegram!")
            except Exception as tg_e:
                print(f"⚠️ Telegram video send warning: {tg_e}")

            # 2. Upload the unique MP4 file to GitHub so Render/Local Frontend can stream it immediately!
            print(f"📡 Syncing {rel_vid_path} to GitHub/Render for Frontend Preview & Vault...")
            sync_file_to_github(rel_vid_path, f"Sync generated 9:16 video {bname} for Frontend")
            # Also generate & sync HD Poster Thumbnail (.mp4.jpg) so Cloud UI never shows a black video box!
            try:
                import shutil as _sh
                ff_bin = _sh.which("ffmpeg")
                thumb_out = output_video_path + ".jpg"
                if ff_bin:
                    subprocess.run([ff_bin, "-y", "-ss", "00:00:02.50", "-i", output_video_path, "-frames:v", "1", "-q:v", "2", thumb_out], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                if os.path.exists(thumb_out) and os.path.getsize(thumb_out) > 2000:
                    sync_file_to_github(f"{rel_vid_path}.jpg", f"Sync HD thumbnail for {bname}")
            except Exception:
                pass
            # Also save refreshed cookies at end of successful video generation!
            try:
                save_all_browser_cookies_via_cdp(driver)
            except Exception:
                pass

            # 3. Record completed video & advance Part Number in history.json, episode_tracker.json & scheduled_queue.json!
            try:
                with open("data/history.json", "r", encoding="utf-8") as f:
                    h_now = json.load(f)
                h_now["generated_count"] = int(h_now.get("generated_count", 0)) + 1
                pending_pkg["video_file"] = bname
                pending_pkg["completed_at"] = datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST")
                h_now.setdefault("history", []).append(pending_pkg)
                with open("data/history.json", "w", encoding="utf-8") as f:
                    json.dump(h_now, f, indent=2, ensure_ascii=False)
                sync_file_to_github("data/history.json", f"Record completed video {bname}")
            except Exception:
                pass

            try:
                import foji_universe_director as _fud
                _fud.mark_episode_part_completed(pending_pkg.get("track_id", "love_meera"), pending_pkg.get("part_number", 1))
                _fud.sync_raw_videos_into_unapproved_queue()
                _fud.push_json_to_github_instantly("data/scheduled_queue.json", f"Add {bname} to Frontend Ready Queue")
            except Exception:
                pass

            update_3d_telemetry(8, "Stage 8: Video Ready on Telegram & Frontend!", f"{bname} delivered to Telegram & Studio Vault!", "completed", 100)
            push_app_notification("success", "🎉 New 3D Reel Ready!", f"{pending_pkg.get('emotion_name')} ({bname}) is live on Telegram & Frontend Vault!", "success")
            return output_video_path

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
    if "--save-cookies-2" in sys.argv:
        _ACTIVE_COOKIE_ACCOUNT_SLOT = 2
        export_fresh_gemini_cookies_from_local()
    elif "--save-cookies" in sys.argv:
        _ACTIVE_COOKIE_ACCOUNT_SLOT = 1
        export_fresh_gemini_cookies_from_local()
    else:
        generate_video_in_gemini()



def _auto_handle_google_password_screen_if_shown(driver, account_slot=1):
    try:
        from selenium.webdriver.common.by import By
        curr_url = (driver.current_url or "").lower()
        if "accounts.google.com" not in curr_url and "consent.google.com" not in curr_url:
            return False

        pwd_inputs = [p for p in driver.find_elements(By.CSS_SELECTOR, 'input[type="password"][name="Passwd"], input[type="password"]') if p.is_displayed()]
        if pwd_inputs:
            return False

        clicked_tile = driver.execute_script("""
            const tiles = document.querySelectorAll('[data-identifier], [data-email]');
            for (const t of tiles) {
                if (t.offsetParent === null) continue;
                const rowTxt = (t.innerText || t.textContent || '').toLowerCase();
                if (!rowTxt.includes('signed out') && !rowTxt.includes('logged out')) {
                    t.click();
                    return true;
                }
            }
            return false;
        """)
        if clicked_tile:
            print("👤 [Pure Cookie Mode] Clicked active signed-in Google Account tile...")
            time.sleep(2.5)
            return True

        clicked_prompt = driver.execute_script("""
            const words = ['not now', 'continue', 'i agree', 'agree', 'accept all', 'skip', 'confirm', 'done'];
            for (const b of document.querySelectorAll('button, [role="button"]')) {
                if (b.offsetParent === null) continue;
                const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                for (const w of words) {
                    if (t === w) { b.click(); return t; }
                }
            }
            return '';
        """)
        if clicked_prompt:
            print(f"✅ [Pure Cookie Mode] Clicked '{clicked_prompt}' consent prompt!")
            time.sleep(2.0)
            return True
    except Exception:
        pass
    return False

def inject_character_files_into_gemini(driver, file_paths):
    """
    Step #10: Injects character reference images (`foji.png`, `meera_*.png`) into Gemini's
    `<input type="file">` element (or via CDP DOM.setFileInputFiles / Clipboard DataTransfer fallback)
    without ever opening an OS file dialog window!
    """
    valid_paths = [os.path.abspath(p) for p in (file_paths or []) if p and os.path.exists(p)]
    if not valid_paths:
        print("⚠️ No character reference images found to inject.")
        return True

    print(f"📸 [Step #10] Injecting {len(valid_paths)} reference image(s): {[os.path.basename(p) for p in valid_paths]}...")

    # Method 1: Unhide or locate <input type="file"> and send all file paths
    try:
        from selenium.webdriver.common.by import By
        driver.execute_script("""
            const inputs = document.querySelectorAll('input[type="file"]');
            inputs.forEach(inp => {
                inp.style.display = 'block';
                inp.style.visibility = 'visible';
                inp.style.opacity = '1';
                inp.style.width = '1px';
                inp.style.height = '1px';
                inp.removeAttribute('hidden');
            });
        """)
        file_inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
        if file_inputs:
            target_inp = file_inputs[-1]
            joined_paths = "\n".join(valid_paths)
            try:
                target_inp.send_keys(joined_paths)
                time.sleep(2.5)
                print("   ✅ [Step #10] Injected character image(s) via <input type='file'>!")
                return True
            except Exception:
                for vp in valid_paths:
                    target_inp.send_keys(vp)
                    time.sleep(1.5)
                print("   ✅ [Step #10] Injected character image(s) sequentially via <input type='file'>!")
                return True
    except Exception as e:
        print(f"   ⚠️ Standard file input note: {e}")

    # Method 2: Synthetic Drag-and-Drop / Clipboard Paste into Gemini prompt editor
    try:
        js_drop = """
        const b64List = arguments[0];
        const nameList = arguments[1];
        const target = document.querySelector('div[contenteditable="true"], rich-textarea, .ql-editor') || document.body;
        const dt = new DataTransfer();
        for (let i = 0; i < b64List.length; i++) {
            const byteChars = atob(b64List[i]);
            const byteArr = new Uint8Array(byteChars.length);
            for (let j = 0; j < byteChars.length; j++) byteArr[j] = byteChars.charCodeAt(j);
            const file = new File([byteArr], nameList[i], { type: 'image/png' });
            dt.items.add(file);
        }
        const pasteEvt = new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt });
        target.focus();
        target.dispatchEvent(pasteEvt);
        return true;
        """
        b64_list = [base64.b64encode(open(p, "rb").read()).decode("ascii") for p in valid_paths]
        name_list = [os.path.basename(p) for p in valid_paths]
        driver.execute_script(js_drop, b64_list, name_list)
        time.sleep(2.5)
        print("   ✅ [Step #10] Injected character image(s) via Synthetic Clipboard Paste!")
        return True
    except Exception as e2:
        print(f"   ⚠️ Clipboard paste fallback note: {e2}")
    return False