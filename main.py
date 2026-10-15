import os
import time
import schedule
from brain import generate_video_package
from gemini_bot import generate_video_in_gemini
from studio import build_final_reel
from telegram_bot import send_reel_for_approval

def run_fast_pipeline():
    print("\n🚀 [FAST PIPELINE TRIGGERED]: Starting Foji Video Generation...")
    
    try:
        # Step 1: Brain Concept
        print("\n--- [1/4] Generating Concept ---")
        package = generate_video_package()
        
        # Step 2: Raw Video (Smart Limit Aware)
        print("\n--- [2/4] Generating Raw Video ---")
        raw_video = generate_video_in_gemini()
        
        # Step 3: Studio Mix (Uses local cached BGM instantly if available)
        print("\n--- [3/4] Mixing Bollywood BGM & 10s Pacing ---")
        final_reel = build_final_reel()
        
        # Step 4: Telegram Preview
        print("\n--- [4/4] Sending to Telegram ---")
        send_reel_for_approval(final_reel, package)
        
        print("\n🎉 Fast Pipeline Cycle Complete! Check your Telegram.")
        
    except Exception as e:
        print(f"\n❌ [PIPELINE ERROR]: {e}")

if __name__ == "__main__":
    print("⚡ Foji AI Super-Fast Automation Engine Started!")
    
    # Run instantly for test
    run_fast_pipeline()

    # Schedule for 3 times a day
    schedule.every().day.at("08:00").do(run_fast_pipeline)
    schedule.every().day.at("14:00").do(run_fast_pipeline)
    schedule.every().day.at("20:00").do(run_fast_pipeline)

    while True:
        schedule.run_pending()
        time.sleep(30)  # Check every 30 seconds for scheduler