import os, time, json, subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import foji_universe_director as fud

def save_account_2_cookies():
    print("=================================================================")
    print("?? OPENING FRESH CHROME FOR ACCOUNT #2 (NO OLD GMAIL LOGGED IN)")
    print("?? Step 1: Log into your 2nd Google/Gmail Account on https://gemini.google.com/app")
    print("?? Step 2: Once Gemini chat screen is open, come back here and press ENTER!")
    print("=================================================================")
    profile_dir = os.path.abspath("chrome_bot_profile_acc2")
    os.makedirs(profile_dir, exist_ok=True)
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    ]
    chrome_exe = next((p for p in chrome_paths if os.path.exists(p)), "chrome.exe")
    cmd = [
        chrome_exe,
        f"--user-data-dir={profile_dir}",
        "--remote-debugging-port=9229",
        "--no-first-run",
        "--no-default-browser-check",
        "https://accounts.google.com/ServiceLogin?continue=https://gemini.google.com/app"
    ]
    proc = subprocess.Popen(cmd)
    input("\n? Jab 2nd Gmail Account login ho jaye aur Gemini khul jaye, tab yahan ENTER dabao...")

    opts = Options()
    opts.debugger_address = "127.0.0.1:9229"
    driver = webdriver.Chrome(options=opts)
    driver.get("https://gemini.google.com/app")
    time.sleep(3)
    all_cookies = []
    try:
        cdp_res = driver.execute_cdp_cmd("Network.getAllCookies", {})
        all_cookies = cdp_res.get("cookies", [])
    except Exception:
        all_cookies = driver.get_cookies()

    google_cookies = [c for c in all_cookies if "google" in c.get("domain", "")]
    with open("gemini_cookies_secret_2.txt", "w", encoding="utf-8") as f:
        json.dump(google_cookies, f, indent=2)

    print(f"?? SUCCESS! Saved {len(google_cookies)} cookies for Account #2 in gemini_cookies_secret_2.txt!")
    print("??? Account #1 cookies (gemini_cookies_secret.txt) remained 100% UNTOUCHED!")
    try:
        driver.quit()
    except Exception:
        pass
    try:
        proc.terminate()
    except Exception:
        pass
    fud.push_json_to_github_instantly("gemini_cookies_secret_2.txt", "Add 2nd Gemini account cookies for failover")

if __name__ == "__main__":
    save_account_2_cookies()
