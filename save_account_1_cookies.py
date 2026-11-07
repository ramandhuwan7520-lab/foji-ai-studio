import os
import time
import json
import shutil
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def save_new_account_1_cookies():
    print("=================================================================")
    print("?? OPENING BRAND-NEW CLEAN CHROME FOR ACCOUNT #1 (NEW GMAIL)")
    print("?? Purana Account #1 hata diya gaya hai. Yeh bilkul fresh Chrome hai!")
    print("?? Step 1: Apne NAYE Gmail Account ka ID aur Password daal kar login karo.")
    print("?? Step 2: Jab https://gemini.google.com/app poori tarah khul jaye (Prompt box dikhe),")
    print("           tabhi wapas is terminal mein aakar ENTER dabana!")
    print("=================================================================")

    profile_dir = os.path.abspath("chrome_bot_profile_acc1_fresh")
    if os.path.exists(profile_dir):
        try:
            shutil.rmtree(profile_dir, ignore_errors=True)
        except Exception:
            pass
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
        "--remote-debugging-port=9228",
        "--no-first-run",
        "--no-default-browser-check",
        "https://gemini.google.com/app"
    ]
    proc = subprocess.Popen(cmd)

    opts = Options()
    opts.debugger_address = "127.0.0.1:9228"

    while True:
        input("\n? Jab NAYA Gmail Account #1 poori tarah login ho jaye aur Gemini khul jaye, tab ENTER dabao...")
        driver = webdriver.Chrome(options=opts)

        curr_url = (driver.current_url or "").lower()
        print(f"?? Checking current URL: {curr_url}")
        if "accounts.google.com" in curr_url or "signin" in curr_url or "servicelogin" in curr_url:
            print("?? ABHI LOGIN POORA NAHI HUA HAI! Chrome abhi bhi Sign-In/Password page par hai.")
            print("?? Pehle Chrome mein password/2-step poora karke Gemini chat screen khulne do, phir ENTER dabao!")
            continue

        driver.get("https://gemini.google.com/app")
        time.sleep(4)

        cdp_res = driver.execute_cdp_cmd("Network.getAllCookies", {})
        all_cookies = cdp_res.get("cookies", [])
        google_cookies = [
            c for c in all_cookies
            if any(d in c.get("domain", "") for d in ["google.com", "gemini.google.com", "accounts.google.com"])
        ]
        cookie_names = {c.get("name", "") for c in google_cookies}

        if not any(k in cookie_names for k in ["SID", "__Secure-1PSID", "__Host-1PSID"]):
            print("?? Auth cookies (SID / __Secure-1PSID) abhi nahi mili! Pehle login poora karo phir ENTER dabao!")
            continue

        exact_ua = driver.execute_script("return navigator.userAgent;")
        local_storage_data = driver.execute_script(
            """
            const out = {};
            try {
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i);
                    out[k] = localStorage.getItem(k);
                }
            } catch (e) {}
            return out;
            """
        )

        driver.get("https://accounts.google.com/")
        time.sleep(2.5)
        cdp_res2 = driver.execute_cdp_cmd("Network.getAllCookies", {})
        all_cookies_final = cdp_res2.get("cookies", [])
        google_cookies_final = [
            c for c in all_cookies_final
            if any(d in c.get("domain", "") for d in ["google.com", "gemini.google.com", "accounts.google.com"])
        ]

        bundle = {
            "cookies": google_cookies_final,
            "user_agent": exact_ua,
            "local_storage": local_storage_data,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        with open("gemini_cookies_secret.txt", "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)

        print("=================================================================")
        print(f"?? 100% VERIFIED! Saved {len(google_cookies_final)} Auth Cookies + UA + LocalStorage in gemini_cookies_secret.txt (Account #1)!")
        print("??? Account #2 cookies (gemini_cookies_secret_2.txt) remained 100% SAFE & UNTOUCHED!")
        print("=================================================================")
        break

    try:
        driver.quit()
    except Exception:
        pass
    try:
        proc.terminate()
    except Exception:
        pass


if __name__ == "__main__":
    save_new_account_1_cookies()
