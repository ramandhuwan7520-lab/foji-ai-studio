
def send_completed_reel_to_telegram(res_pkg):
    """Sends the newly generated reel (.mp4) + notification straight to Telegram!"""
    try:
        import requests
        tok = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        cid = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
        if os.path.exists("data/telegram_config.json"):
            try:
                cfg = json.load(open("data/telegram_config.json", "r", encoding="utf-8"))
                tok = str(cfg.get("bot_token") or tok).strip()
                cid = str(cfg.get("chat_id") or cid).strip()
            except Exception:
                pass
        if not tok or not cid:
            return
        v_file = ""
        title = "Foji AI Reel"
        sched_disp = "Scheduled in Queue"
        if isinstance(res_pkg, dict):
            v_file = res_pkg.get("video_path") or res_pkg.get("video_file") or ""
            title = res_pkg.get("title") or res_pkg.get("topic") or title
            sched_disp = res_pkg.get("scheduled_display") or res_pkg.get("scheduled_for") or sched_disp
        elif isinstance(res_pkg, str):
            v_file = res_pkg

        if v_file and not os.path.exists(v_file):
            cand = os.path.join("output", os.path.basename(v_file))
            if os.path.exists(cand):
                v_file = cand

        caption = (
            f"🎬 *Foji AI Studio — New Reel Generated!*\n\n"
            f"📌 *Title:* `{title}`\n"
            f"📁 *File:* `{os.path.basename(v_file) if v_file else 'Reel.mp4'}`\n"
            f"⏰ *Schedule:* `{sched_disp}`\n"
            f"✅ *Status:* Saved to Studio Vault & Synced!"
        )
        if v_file and os.path.exists(v_file) and os.path.getsize(v_file) > 50000:
            with open(v_file, "rb") as vf:
                r = requests.post(
                    f"https://api.telegram.org/bot{tok}/sendVideo",
                    data={"chat_id": cid, "caption": caption[:950], "parse_mode": "Markdown"},
                    files={"video": vf},
                    timeout=90
                )
            print(f"📲 [Telegram Video Sent] Delivered '{os.path.basename(v_file)}' to Telegram (HTTP {r.status_code})!")
        else:
            requests.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                data={"chat_id": cid, "text": caption, "parse_mode": "Markdown"},
                timeout=15
            )
            print("📲 [Telegram Success Message Sent]!")
    except Exception as e:
        print(f"⚠️ Telegram video delivery note: {e}")


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
        for attempt in range(1, 2):
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
                print(f"⚠️ [BATCH {i+1}/{cnt} - Attempt {attempt}/1] Error: {e}")
                time.sleep(5)

        if i < cnt - 1:
            print("⏳ Cooling down 8s before starting next video in batch...")
            time.sleep(8)

    print(f"\n🎉 BATCH FINISHED: {completed_videos}/{cnt} videos generated & synced to Studio!")
