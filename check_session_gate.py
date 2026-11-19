import os
import sys
import json
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
event_name = os.getenv("GITHUB_EVENT_NAME", "schedule")

# Manual runs from dashboard or GitHub button ALWAYS run!
if event_name == "workflow_dispatch":
    print("SHOULD_RUN=true")
    print("REASON=Manual trigger requested", file=sys.stderr)
    sys.exit(0)

now_ist = datetime.now(IST)
today_str = now_ist.strftime("%Y-%m-%d")
now_mins = now_ist.hour * 60 + now_ist.minute

cfg_p = "data/studio_sessions_config.json"
if os.path.exists(cfg_p):
    cfg = json.load(open(cfg_p, "r", encoding="utf-8"))
    if not cfg.get("master_auto_enabled", True):
        print("SHOULD_RUN=false")
        print("REASON=Master Auto-Render Switch is PAUSED in Dashboard", file=sys.stderr)
        sys.exit(0)

    # Find closest session within +/- 45 minutes of current IST time
    matched_sess = None
    for s in (cfg.get("sessions") or []):
        hh, mm = map(int, str(s.get("time_ist", "00:19")).split(":"))
        s_mins = hh * 60 + mm
        diff = min(abs(now_mins - s_mins), 1440 - abs(now_mins - s_mins))
        if diff <= 55:
            matched_sess = s
            break

    if matched_sess:
        if not matched_sess.get("enabled", True):
            print("SHOULD_RUN=false")
            print(f"REASON=Session {matched_sess.get('display')} is turned OFF in Dashboard", file=sys.stderr)
            sys.exit(0)
        if matched_sess.get("skip_date") == today_str:
            print("SHOULD_RUN=false")
            print(f"REASON=Session {matched_sess.get('display')} is SKIPPED for today ({today_str})", file=sys.stderr)
            sys.exit(0)

# Smart Buffer Protection: If 12+ unposted videos are already ready in queue, skip auto-render to save GitHub minutes!
q_p = "data/scheduled_queue.json"
if os.path.exists(q_p):
    q = json.load(open(q_p, "r", encoding="utf-8"))
    ready_cnt = len(q.get("scheduled_posts") or []) + len(q.get("unapproved_videos") or [])
    if ready_cnt >= 12:
        print("SHOULD_RUN=false")
        print(f"REASON=Smart Minute Saver: Already {ready_cnt} ready/scheduled reels in buffer (>=12)!", file=sys.stderr)
        sys.exit(0)

print("SHOULD_RUN=true")
print(f"REASON=Approved for {now_ist.strftime('%I:%M %p IST')}", file=sys.stderr)
