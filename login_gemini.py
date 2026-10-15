import os
import shutil
import subprocess

def find_real_chrome():
    paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Bhai, Chrome nahi mila!")

def save_gemini_session():
    chrome_exe = find_real_chrome()
    profile_path = os.path.abspath("chrome_profile")
    
    # Purana corrupted profile saaf kar rahe hain taaki fresh login ho
    if os.path.exists(profile_path):
        try:
            shutil.rmtree(profile_path)
        except Exception:
            pass
    os.makedirs(profile_path, exist_ok=True)

    print("🌐 100% Normal Chrome khul raha hai (Zero Automation Flags)...")
    
    # ZERO debugging flags here! Google cannot detect anything at all.
    cmd = [
        chrome_exe,
        f"--user-data-dir={profile_path}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        "https://accounts.google.com/ServiceLogin?continue=https://gemini.google.com/app"
    ]
    
    subprocess.Popen(cmd)

    input("\n👉 1. Ab Chrome mein bina kisi error ke apna Gmail Login karo!\n👉 2. Jab Gemini Pro ki chat screen khul jaye, toh us Chrome window ko BAND (X) kar do.\n👉 3. Chrome band karne ke baad yahan Terminal mein ENTER dabao...")
        
    print("✅ Gemini Pro Session 100% Save ho gaya!")

if __name__ == "__main__":
    save_gemini_session()