import os
import time
import json
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import foji_universe_director as fud


def save_account_2_cookies():
    print("=================================================================")
    print("🔐 OPENING CHROME FOR ACCOUNT #2 (FULL SESSION + FINGERPRINT SAVER)")
    print("👉 Step 1: Chrome khulega -> Apni 2nd Gmail ka ID aur Password daal kar login karo.")
    print("👉 Step 2: Jab https://gemini.google.com/app poori tarah khul jaye (jahan 'Enter a prompt for Gemini' box dikhe),")
    print("           tabhi wapas is terminal mein aakar ENTER dabana!")
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
        "https://gemini.google.com/app"
    ]
    proc = subprocess.Popen(cmd)

    opts = Options()
    opts.debugger_address = "127.0.0.1:9229"

    while True:
        input("\n✅ Jab 2nd Gmail poori tarah login ho jaye aur Gemini ka prompt box dikhne lage, tab ENTER dabao...")
        driver = webdriver.Chrome(options=opts)

        # Ensure we are on gemini.google.com/app and NOT on accounts.google.com password screen!
        curr_url = (driver.current_url or "").lower()
        print(f"🔎 Checking current URL: {curr_url}")
        if "accounts.google.com" in curr_url or "signin" in curr_url or "servicelogin" in curr_url:
            print("⚠️ ABHI LOGIN POORA NAHI HUA HAI! Chrome abhi bhi Sign-In/Password page par hai.")
            print("👉 Pehle Chrome mein password/2-step poora karke Gemini chat screen khulne do, phir ENTER dabao!")
            continue

        driver.get("https://gemini.google.com/app")
        time.sleep(4)

        # Verify actual signed-in state by checking auth cookies (__Secure-1PSID / SID)
        cdp_res = driver.execute_cdp_cmd("Network.getAllCookies", {})
        all_cookies = cdp_res.get("cookies", [])
        google_cookies = [
            c for c in all_cookies
            if any(d in c.get("domain", "") for d in ["google.com", "gemini.google.com", "accounts.google.com"])
        ]
        cookie_names = {c.get("name", "") for c in google_cookies}

        if not any(k in cookie_names for k in ["SID", "__Secure-1PSID", "__Host-1PSID"]):
            print("⚠️ Auth cookies (SID / __Secure-1PSID) abhi nahi mili! Iska matlab Account #2 abhi sign-in nahi hua hai.")
            print("👉 Chrome mein check karo ki top-right corner mein aapki 2nd Gmail ki profile photo dikh rahi hai, phir ENTER dabao!")
            continue

        # Capture exact User-Agent and LocalStorage so Cloud Linux runner never asks for password!
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

        # Touch accounts.google.com briefly so all account session tokens are fresh
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

        with open("gemini_cookies_secret_2.txt", "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2)

        print("=================================================================")
        print(f"🎉 100% VERIFIED! Saved {len(google_cookies_final)} Auth Cookies + User-Agent + LocalStorage ({len(local_storage_data)} keys) in gemini_cookies_secret_2.txt!")
        print("🛡️ Ab Cloud par 2nd Account kabhi Password nahi maangega!")
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

    fud.push_json_to_github_instantly("gemini_cookies_secret_2.txt", "Save full verified session bundle for Account 2")


if __name__ == "__main__":
    save_account_2_cookies()