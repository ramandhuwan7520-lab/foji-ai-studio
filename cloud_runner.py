import os
import sys
import shutil
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import os
import foji_universe_director as fud
import gemini_bot

if __name__ == "__main__":
    cnt_str = (os.getenv("BATCH_COUNT", "1") or "1").strip()
    cnt = max(1, min(5, int(cnt_str) if cnt_str.isdigit() else 1))
    tid = (os.getenv("FORCE_TRACK_ID", "") or "").strip() or None
    idea = (os.getenv("CUSTOM_IDEA", "") or "").strip()

    for i in range(cnt):
        print(f"=== Starting Video {i+1}/{cnt} ===")
        pkg = fud.build_real_foji_universe_package(
            force_track_id=tid,
            custom_idea=(idea if i == 0 else ""),
            is_preview=False
        )
        gemini_bot.generate_video_in_gemini(pending_pkg=pkg)
