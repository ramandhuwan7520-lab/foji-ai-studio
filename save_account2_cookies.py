import os
import json
import time
from dotenv import load_dotenv

os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(override=True)
import gemini_bot as gb

print("======================================================================")
print("🔐 ACCOUNT #2 COOKIE LINKER (2X DAILY VIDEO QUOTA FAILOVER)")
print("1. Chrome will open to https://gemini.google.com/app")
print("2. Sign in to your 2nd Google Account (with Gemini Video enabled).")
print("3. Once Gemini chat opens, come back here and press ENTER!")
print("======================================================================")

raw_dir = os.path.abspath("output/raw_videos")
os.makedirs(raw_dir, exist_ok=True)
driver, proc = gb.launch_resilient_chrome_session(raw_dir, start_blank=False)
try:
    driver.get("https://accounts.google.com/Logout?continue=https://gemini.google.com/app")
    time.sleep(2)
    driver.get("https://gemini.google.com/app")
    input("\n👉 Login your 2nd Gmail inside Chrome until Gemini chat loads, then press ENTER here... ")
    cookies = driver.execute_cdp_cmd("Network.getAllCookies", {}).get("cookies", [])
    google_ck = [c for c in cookies if "google." in (c.get("domain") or "")]
    payload = {"saved_at": time.strftime("%Y-%m-%d %H:%M:%S"), "account_slot": 2, "cookies": google_ck}
    with open("gemini_cookies_secret_2.txt", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    with open("data/acc2_master_backup.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"✅ Saved {len(google_ck)} fresh Account #2 cookies to 'gemini_cookies_secret_2.txt'!")
    gb.sync_file_to_github("gemini_cookies_secret_2.txt", "Add Account #2 cookies for failover [skip render] [skip ci]")
    print("☁️ Synced Account #2 cookies to GitHub! Dual-Account Failover is now LIVE!")
finally:
    try:
        driver.quit()
    except Exception:
        pass
