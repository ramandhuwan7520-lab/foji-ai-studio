import os
import sys
import time
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import foji_universe_director as fud
import gemini_bot

if __name__ == "__main__":
    cnt_str = (os.getenv("BATCH_COUNT", "1") or "1").strip()
    cnt = max(1, min(5, int(cnt_str) if cnt_str.isdigit() else 1))
    tid = (os.getenv("FORCE_TRACK_ID", "") or "").strip() or None
    idea = (os.getenv("CUSTOM_IDEA", "") or "").strip()

    completed_videos = 0
    for i in range(cnt):
        print(f"\n=======================================================")
        print(f"🎬 [BATCH ENGINE] Starting Video {i+1} of {cnt}...")
        print(f"=======================================================")
        success_this_slot = False
        for attempt in range(1, 3):
            try:
                # Pull latest part tracker before each video so Part numbers & Equal-Part Balancer are 100% accurate!
                pkg = fud.build_real_foji_universe_package(
                    force_track_id=tid,
                    custom_idea=(idea if i == 0 else ""),
                    is_preview=False
                )
                out_vid = gemini_bot.generate_video_in_gemini(pending_pkg=pkg)
                if out_vid and os.path.exists(out_vid):
                    completed_videos += 1
                    success_this_slot = True
                    print(f"✅ [BATCH {i+1}/{cnt}] Completed: {os.path.basename(out_vid)}")
                    break
            except Exception as e:
                last_err_msg = str(e)
                print(f"⚠️ [BATCH {i+1}/{cnt} - Attempt {attempt}/2] Error: {e}")
                time.sleep(5)

        if i < cnt - 1:
            print("⏳ Cooling down 8s before starting next video in batch...")
            time.sleep(8)

    print(f"\n🎉 BATCH FINISHED: {completed_videos}/{cnt} videos generated & synced to Studio!")
