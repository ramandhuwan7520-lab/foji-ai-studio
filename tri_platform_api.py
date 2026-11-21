import re
import os
import json
import time
import requests
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
CONFIG_FILE = "data/tri_platform_config.json"
INSIGHTS_CACHE_FILE = "data/tri_platform_insights.json"


def load_tri_config():
    def _first_env(*names):
        for n in names:
            val = (os.getenv(n) or "").strip()
            if val:
                return val
        return ""

    yt_tok_default = "data/yt_token.json" if os.path.exists("data/yt_token.json") else "data/youtube_token.json"
    yt_sec_default = "data/yt_client_secret.json" if os.path.exists("data/yt_client_secret.json") else "data/youtube_client_secret.json"

    cfg = {
        "meta_app_id": _first_env("META_APP_ID", "FB_APP_ID"),
        "meta_app_secret": _first_env("META_APP_SECRET", "FB_APP_SECRET"),
        "ig_access_token": _first_env("IG_OFFICIAL_ACCESS_TOKEN", "IG_ACCESS_TOKEN", "INSTAGRAM_ACCESS_TOKEN", "META_ACCESS_TOKEN", "IG_TOKEN"),
        "ig_account_id": _first_env("IG_OFFICIAL_ACCOUNT_ID", "IG_ACCOUNT_ID", "INSTAGRAM_ACCOUNT_ID", "IG_USER_ID"),
        "fb_page_id": _first_env("FB_PAGE_ID"),
        "fb_page_token": _first_env("FB_PAGE_ACCESS_TOKEN", "FB_PAGE_TOKEN"),
        "yt_channel_id": _first_env("YT_CHANNEL_ID", "YOUTUBE_CHANNEL_ID"),
        "yt_api_key": _first_env("YT_API_KEY", "YOUTUBE_API_KEY"),
        "yt_client_secret_path": yt_sec_default,
        "yt_token_path": yt_tok_default,
        "ig_token_refreshed_at": 0
    }
    if os.path.exists(CONFIG_FILE):
        try:
            saved = json.load(open(CONFIG_FILE, "r", encoding="utf-8"))
            for k, v in saved.items():
                if v not in (None, ""):
                    cfg[k] = v if isinstance(v, (int, float)) else str(v).strip()
        except Exception:
            pass
    # Prefer existing local yt_token.json over stale default path
    if not os.path.exists(cfg.get("yt_token_path", "")) and os.path.exists("data/yt_token.json"):
        cfg["yt_token_path"] = "data/yt_token.json"
    return cfg




def save_tri_config(updates):
    os.makedirs("data", exist_ok=True)
    cur = load_tri_config()
    for k, v in (updates or {}).items():
        if v is not None and str(v).strip() != "":
            cur[k] = str(v).strip()
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cur, f, indent=2)
    return cur


def _ig_graph_base(token):
    # Instagram Login tokens start with "IGAA..." -> graph.instagram.com
    # Facebook Business / SUAT tokens start with "EAA..." -> graph.facebook.com
    if str(token).startswith("IG"):
        return "https://graph.instagram.com/v22.0"
    return "https://graph.facebook.com/v22.0"


def _auto_refresh_ig_login_token_if_due(cfg):
    """Auto-refreshes 60-day `IG...` long-lived token every 25 days so it NEVER expires."""
    tok = str(cfg.get("ig_access_token") or "").strip()
    if not tok.startswith("IG"):
        return tok
    last_ref = float(cfg.get("ig_token_refreshed_at") or 0)
    if last_ref > 0 and (time.time() - last_ref) < (25 * 86400):
        return tok
    try:
        r = requests.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": tok},
            timeout=10
        )
        if r.status_code == 200:
            new_tok = (r.json().get("access_token") or "").strip()
            if new_tok:
                save_tri_config({"ig_access_token": new_tok, "ig_token_refreshed_at": int(time.time())})
                return new_tok
    except Exception:
        pass
    return tok


def _format_ig_ist_time(ts_str):
    if not ts_str:
        return "Published"
    try:
        dt = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return str(ts_str)[:16]


_IG_FAST_MEM_CACHE = {"ts": 0.0, "data": None}


def fetch_official_instagram_insights():
    """
    HIGH-SPEED PARALLEL META GRAPH API ENGINE (~3 SECONDS TOTAL):
    - Uses 12 concurrent worker threads to fetch live reel views/likes/saves/shares
      so Render NEVER hits worker timeouts or freezes the dashboard!
    - Supports Unified Login (EAA...), Instagram Login (IG...), Explicit IG Account ID,
      Facebook Pages, and Meta Business Portfolios.
    """
    from concurrent.futures import ThreadPoolExecutor

    # 20-second burst deduplication cache (prevents duplicate hits during rapid dashboard loads)
    if _IG_FAST_MEM_CACHE.get("data") and (time.time() - float(_IG_FAST_MEM_CACHE.get("ts") or 0)) < 20:
        return _IG_FAST_MEM_CACHE["data"]

    cfg = load_tri_config()
    tok = _auto_refresh_ig_login_token_if_due(cfg)
    ig_id = str(cfg.get("ig_account_id") or "").strip()
    app_id = str(cfg.get("meta_app_id") or "").strip()
    app_sec = str(cfg.get("meta_app_secret") or "").strip()

    if not tok:
        return {
            "connected": False,
            "source": "Not Connected",
            "note": "Set IG_OFFICIAL_ACCESS_TOKEN & IG_OFFICIAL_ACCOUNT_ID in Render Environment."
        }

    prof = None
    active_base = None
    media_ep = None
    debug_scopes = []
    candidate_ids = [ig_id] if ig_id else []
    last_err = ""

    def _probe_ig_id(cid):
        nonlocal prof, active_base, media_ep, ig_id, last_err
        # Prefer Facebook Graph first for EAA... Unified tokens, Instagram Graph first for IG... tokens
        endpoints = (
            ("https://graph.facebook.com/v22.0", "id,username,followers_count,follows_count,media_count"),
            ("https://graph.instagram.com/v22.0", "user_id,id,username,followers_count,follows_count,media_count"),
        ) if not tok.startswith("IG") else (
            ("https://graph.instagram.com/v22.0", "user_id,id,username,followers_count,follows_count,media_count"),
            ("https://graph.facebook.com/v22.0", "id,username,followers_count,follows_count,media_count"),
        )
        for b_url, flds in endpoints:
            try:
                rp = requests.get(f"{b_url}/{cid}", params={"fields": flds, "access_token": tok}, timeout=7)
                if rp.status_code == 200 and rp.json().get("username"):
                    prof = rp.json()
                    ig_id = str(prof.get("user_id") or prof.get("id") or cid)
                    active_base = b_url
                    media_ep = f"{active_base}/{ig_id}/media"
                    return True
                last_err = f"{b_url.split('//')[1].split('/')[0]}/{cid} {rp.status_code}: {rp.text[:100]}"
            except Exception as _pe:
                last_err = str(_pe)[:90]
        return False

    try:
        # FAST PATH 1: Explicit IG Account ID already configured (1 single ~0.3s call!)
        if ig_id:
            _probe_ig_id(ig_id)

        # ROUTE 2: Direct `graph.instagram.com/v22.0/me`
        if not prof and tok.startswith("IG"):
            try:
                r_ig_me = requests.get(
                    "https://graph.instagram.com/v22.0/me",
                    params={"fields": "user_id,id,username,followers_count,follows_count,media_count", "access_token": tok},
                    timeout=7
                )
                if r_ig_me.status_code == 200 and r_ig_me.json().get("username"):
                    prof = r_ig_me.json()
                    ig_id = str(prof.get("user_id") or prof.get("id") or ig_id)
                    active_base = "https://graph.instagram.com/v22.0"
                    media_ep = f"{active_base}/me/media"
            except Exception as _e1:
                last_err = str(_e1)[:90]

        # ROUTE 3: Facebook Pages / Business Portfolio discovery (only if explicit ID didn't work)
        if not prof:
            try:
                r_pg = requests.get(
                    "https://graph.facebook.com/v22.0/me/accounts",
                    params={"fields": "id,name,access_token,instagram_business_account,connected_instagram_account", "access_token": tok},
                    timeout=8
                )
                if r_pg.status_code == 200:
                    for pg in (r_pg.json().get("data") or []):
                        iba = pg.get("instagram_business_account") or pg.get("connected_instagram_account") or {}
                        if iba.get("id") and _probe_ig_id(str(iba["id"])):
                            save_tri_config({
                                "ig_account_id": ig_id,
                                "fb_page_id": str(pg.get("id") or ""),
                                "fb_page_token": str(pg.get("access_token") or "")
                            })
                            break
            except Exception:
                pass

        if not prof and app_id and app_sec:
            try:
                r_dbg = requests.get(
                    "https://graph.facebook.com/v22.0/debug_token",
                    params={"input_token": tok, "access_token": f"{app_id}|{app_sec}"},
                    timeout=7
                )
                if r_dbg.status_code == 200:
                    dd = (r_dbg.json() or {}).get("data") or {}
                    debug_scopes = list(dd.get("scopes") or [])
            except Exception:
                pass

        if not prof or not active_base:
            return {
                "connected": False,
                "source": "Official API Check",
                "note": f"{last_err} | Scopes={debug_scopes[:6]}"[:260]
            }

        if ig_id and ig_id != cfg.get("ig_account_id"):
            save_tri_config({"ig_account_id": ig_id})

        # Fetch up to 40 latest reels in 1-2 fast calls
        raw_items = []
        next_url = media_ep
        params = {
            "fields": "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count,thumbnail_url,media_url",
            "limit": 40,
            "access_token": tok
        }
        for _ in range(2):
            rm = requests.get(next_url, params=params, timeout=10)
            if rm.status_code != 200:
                break
            mj = rm.json()
            raw_items.extend(mj.get("data") or [])
            if len(raw_items) >= 40:
                raw_items = raw_items[:40]
                break
            next_url = (mj.get("paging") or {}).get("next")
            params = None
            if not next_url:
                break

        def _fetch_one_reel_metrics(item):
            views_val = 0
            saved_val = 0
            shares_val = 0
            mid = item.get("id")
            if mid:
                for metric_set in ("views,reach,saved,shares", "reach"):
                    try:
                        ri = requests.get(
                            f"{active_base}/{mid}/insights",
                            params={"metric": metric_set, "access_token": tok},
                            timeout=4.5
                        )
                        if ri.status_code == 200:
                            for md in (ri.json().get("data") or []):
                                mname = md.get("name", "")
                                vals = md.get("values") or []
                                v0 = int((vals[0].get("value") if vals else 0) or 0)
                                if mname in ("views", "plays", "reach"):
                                    views_val = max(views_val, v0)
                                elif mname == "saved":
                                    saved_val = v0
                                elif mname == "shares":
                                    shares_val = v0
                            break
                    except Exception:
                        pass

            likes = int(item.get("like_count") or 0)
            comments = int(item.get("comments_count") or 0)
            er = round(((likes + comments + saved_val + shares_val) / max(1, views_val)) * 100, 2) if views_val > 0 else 0.0
            thumb = item.get("thumbnail_url") or (item.get("media_url") if item.get("media_type") == "IMAGE" else "")
            return {
                "id": mid,
                "title": (item.get("caption") or "Instagram Reel").splitlines()[0][:72],
                "views": views_val,
                "likes": likes,
                "comments": comments,
                "saved": saved_val,
                "shares": shares_val,
                "er": er,
                "thumbnail_url": thumb,
                "permalink": item.get("permalink", ""),
                "timestamp": item.get("timestamp", ""),
                "posted_at": _format_ig_ist_time(item.get("timestamp", ""))
            }

        # Parallel 12-thread fetch -> 40 reels finish in ~2-3 seconds total!
        reels = []
        if raw_items:
            with ThreadPoolExecutor(max_workers=12) as pool:
                reels = list(pool.map(_fetch_one_reel_metrics, raw_items))

        tot_views = sum(r["views"] for r in reels)
        tot_likes = sum(r["likes"] for r in reels)
        tot_comments = sum(r["comments"] for r in reels)
        avg_views = round(tot_views / max(1, len(reels)))
        for r in reels:
            delta = round(((r["views"] - avg_views) / max(1, avg_views)) * 100) if avg_views > 0 else 0
            r["delta_pct"] = delta
            r["status"] = "viral" if delta >= 35 else ("growing" if delta >= 0 else "downfall")

        result = {
            "connected": True,
            "source": "Official Meta Graph API (Live)",
            "username": f"@{prof.get('username', 'ai_foji_lovelife')}",
            "followers": int(prof.get("followers_count") or 0),
            "media_count": int(prof.get("media_count") or len(reels)),
            "total_views": tot_views,
            "total_likes": tot_likes,
            "total_comments": tot_comments,
            "avg_views": avg_views,
            "fetched_at": datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"),
            "reels": reels
        }

        _IG_FAST_MEM_CACHE["ts"] = time.time()
        _IG_FAST_MEM_CACHE["data"] = result

        try:
            os.makedirs("data", exist_ok=True)
            with open("data/ig_live_analytics.json", "w", encoding="utf-8") as af:
                json.dump({
                    "username": result["username"],
                    "followers_count": result["followers"],
                    "profile_total_posts": result["media_count"],
                    "total_views": tot_views,
                    "total_likes": tot_likes,
                    "total_comments": tot_comments,
                    "sync_source": "Official Meta Graph API (Live)",
                    "fetched_at": result["fetched_at"],
                    "reels": reels
                }, af, indent=2)
        except Exception:
            pass
        return result
    except Exception as e:
        return {"connected": False, "source": "Error", "note": str(e)[:180]}






def publish_reel_official_instagram(video_public_url, caption):
    cfg = load_tri_config()
    tok = cfg.get("ig_access_token", "")
    ig_id = cfg.get("ig_account_id", "")
    if not tok or not ig_id:
        return {"ok": False, "error": "Official IG Token/ID not configured"}

    base = _ig_graph_base(tok)
    r_create = requests.post(
        f"{base}/{ig_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_public_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": tok
        },
        timeout=30
    )
    if r_create.status_code != 200:
        return {"ok": False, "error": f"IG Container failed: {r_create.text[:220]}"}
    creation_id = r_create.json().get("id")
    if not creation_id:
        return {"ok": False, "error": "Missing creation_id from Meta"}

    # Poll until container status == FINISHED (max 90s)
    for _ in range(18):
        time.sleep(5)
        r_st = requests.get(f"{base}/{creation_id}", params={"fields": "status_code,status", "access_token": tok}, timeout=12)
        if r_st.status_code == 200:
            sc = (r_st.json().get("status_code") or "").upper()
            if sc == "FINISHED":
                break
            if sc in ("ERROR", "EXPIRED"):
                return {"ok": False, "error": f"IG Container error: {r_st.text[:180]}"}

    r_pub = requests.post(
        f"{base}/{ig_id}/media_publish",
        data={"creation_id": creation_id, "access_token": tok},
        timeout=25
    )
    if r_pub.status_code != 200:
        return {"ok": False, "error": f"IG Publish failed: {r_pub.text[:220]}"}
    media_id = r_pub.json().get("id", "LIVE")
    return {"ok": True, "platform": "instagram", "media_id": str(media_id), "permalink": f"https://www.instagram.com/"}


def fetch_official_facebook_insights():
    cfg = load_tri_config()
    pg_id = cfg.get("fb_page_id", "")
    pg_tok = cfg.get("fb_page_token", "")
    if not pg_id or not pg_tok:
        return {"connected": False, "source": "Not Connected", "followers": 0, "total_views": 0, "total_likes": 0, "media_count": 0}
    try:
        r = requests.get(
            f"https://graph.facebook.com/v22.0/{pg_id}",
            params={"fields": "name,followers_count,fan_count", "access_token": pg_tok},
            timeout=12
        )
        if r.status_code != 200:
            return {"connected": False, "source": "Token Error", "note": r.text[:140], "followers": 0, "total_views": 0, "total_likes": 0, "media_count": 0}
        pj = r.json()
        rv = requests.get(
            f"https://graph.facebook.com/v22.0/{pg_id}/video_reels",
            params={"fields": "id,description,views,likes.summary(true)", "limit": 25, "access_token": pg_tok},
            timeout=12
        )
        vids = (rv.json().get("data") or []) if rv.status_code == 200 else []
        tot_v = sum(int(v.get("views") or 0) for v in vids)
        tot_l = sum(int(((v.get("likes") or {}).get("summary") or {}).get("total_count") or 0) for v in vids)
        return {
            "connected": True,
            "source": "Official Facebook Graph API",
            "page_name": pj.get("name", "Facebook Page"),
            "followers": int(pj.get("followers_count") or pj.get("fan_count") or 0),
            "media_count": len(vids),
            "total_views": tot_v,
            "total_likes": tot_l
        }
    except Exception as e:
        return {"connected": False, "source": "Error", "note": str(e)[:140], "followers": 0, "total_views": 0, "total_likes": 0, "media_count": 0}


def publish_reel_official_facebook(video_public_url, caption):
    cfg = load_tri_config()
    pg_id = cfg.get("fb_page_id", "")
    pg_tok = cfg.get("fb_page_token", "")
    if not pg_id or not pg_tok:
        return {"ok": False, "error": "FB Page ID/Token not configured"}
    try:
        # Step 1: Start FB Reels upload session
        r1 = requests.post(
            f"https://graph.facebook.com/v22.0/{pg_id}/video_reels",
            data={"upload_phase": "start", "access_token": pg_tok},
            timeout=20
        )
        if r1.status_code != 200:
            return {"ok": False, "error": f"FB start failed: {r1.text[:180]}"}
        j1 = r1.json()
        vid_id = j1.get("video_id")
        up_url = j1.get("upload_url")

        # Step 2: Hosted URL upload
        r2 = requests.post(
            up_url,
            headers={"Authorization": f"OAuth {pg_tok}", "file_url": video_public_url},
            timeout=45
        )
        if r2.status_code != 200:
            return {"ok": False, "error": f"FB upload failed: {r2.text[:180]}"}

        # Step 3: Finish & Publish
        r3 = requests.post(
            f"https://graph.facebook.com/v22.0/{pg_id}/video_reels",
            data={
                "upload_phase": "finish",
                "video_id": vid_id,
                "video_state": "PUBLISHED",
                "description": caption,
                "access_token": pg_tok
            },
            timeout=25
        )
        if r3.status_code != 200:
            return {"ok": False, "error": f"FB publish failed: {r3.text[:180]}"}
        return {"ok": True, "platform": "facebook", "video_id": str(vid_id)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _load_youtube_oauth_dict():
    """Loads YouTube OAuth JSON cleanly from Render Env `YT_TOKEN_JSON` OR local token files."""
    env_raw = (os.getenv("YT_TOKEN_JSON") or os.getenv("YOUTUBE_TOKEN_JSON") or "").strip()
    if env_raw:
        try:
            obj = json.loads(env_raw)
            if isinstance(obj, dict) and (obj.get("refresh_token") or obj.get("token")):
                return obj
        except Exception:
            pass
    cfg = load_tri_config()
    for p in (cfg.get("yt_token_path", ""), "data/yt_token.json", "data/youtube_token.json"):
        if p and os.path.exists(p):
            try:
                obj = json.load(open(p, "r", encoding="utf-8"))
                if isinstance(obj, dict) and (obj.get("refresh_token") or obj.get("token")):
                    return obj
            except Exception:
                pass
    return None


def is_youtube_upload_ready():
    tok = _load_youtube_oauth_dict()
    return bool(tok and (tok.get("refresh_token") or tok.get("token")))


def _get_fresh_youtube_access_token():
    """Exchanges permanent refresh_token for a fresh OAuth2 access_token via pure HTTP (zero googleapiclient needed)."""
    tok_obj = _load_youtube_oauth_dict()
    if not tok_obj:
        return None, "YouTube OAuth token missing (Set YT_TOKEN_JSON in Render Environment)"

    refresh_tok = (tok_obj.get("refresh_token") or "").strip()
    client_id = (tok_obj.get("client_id") or "").strip()
    client_secret = (tok_obj.get("client_secret") or "").strip()
    token_uri = (tok_obj.get("token_uri") or "https://oauth2.googleapis.com/token").strip()

    if refresh_tok and client_id and client_secret:
        try:
            r = requests.post(
                token_uri,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_tok,
                    "grant_type": "refresh_token"
                },
                timeout=15
            )
            if r.status_code == 200 and r.json().get("access_token"):
                return r.json()["access_token"], None
            return None, f"YouTube OAuth refresh HTTP {r.status_code}: {r.text[:160]}"
        except Exception as e:
            return None, f"YouTube OAuth refresh error: {e}"

    if tok_obj.get("token"):
        return tok_obj["token"], None
    return None, "YouTube refresh_token/client_id/client_secret incomplete"


def generate_gemini_youtube_seo_package(video_filename, ig_caption="", fallback_title=""):
    """
    DEDICATED GEMINI YOUTUBE SHORTS SEO ENGINE:
    Generates a separate, YouTube-optimized High-CTR Title (#Shorts), SEO Description,
    18 searchable Tags, and 5 focused Hashtags tailored to the exact reel!
    """
    raw_cap = (ig_caption or "").strip()
    base_slug = os.path.splitext(os.path.basename(str(video_filename or "Foji_3D_Short")))[0]
    clean_base = re.sub(r"_\d{4}_\d{6}$", "", base_slug).replace("_", " ").strip()
    first_line = (fallback_title or (raw_cap.splitlines()[0] if raw_cap else clean_base)).strip()
    first_line = re.sub(r"#\S+", "", first_line).strip() or "Indian Army 3D Fauji Life Story"

    default_tags = [
        "Indian Army", "Fauji Life", "Indian Army Shorts", "Agniveer",
        "Foji Zindagi 3D", "Indian Army 3D Animation", "Army Training",
        "Fauji Status", "Haryanvi Fauji Comedy", "Ustad Ka Ragda",
        "Foji Fojan", "Army Motivation Shorts", "Soldier Life Reality",
        "Deshbhakti Shorts", "Viral Army Reels", "3D Animated Shorts",
        "Indian Army Emotion", "Shorts"
    ]
    default_hashtags = ["#shorts", "#indianarmy", "#faujilife", "#agniveer", "#fojizindagi3d"]

    default_title = first_line[:78].strip()
    if "#shorts" not in default_title.lower():
        default_title = f"{default_title} #shorts"

    default_desc = (
        f"{first_line}\n\n"
        f"🇮🇳 Bharat ke veer jawano ki asli zindagi, training grit aur dil chhoo lene wali 3D kahani!\n"
        f"Roz naye realistic 3D Indian Army Shorts dekhne ke liye channel ko Subscribe karein aur Video ko Like & Share zaroor karein. 🪖🔥\n\n"
        f"📲 Instagram: @ai_foji_lovelife\n"
        f"Jai Hind! 🇮🇳\n\n"
        f"{' '.join(default_hashtags)}"
    )

    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        return {
            "title": default_title[:95],
            "description": default_desc,
            "tags": default_tags,
            "hashtags": default_hashtags,
            "via": "smart_template"
        }

    prompt = f"""You are an elite Indian YouTube Shorts SEO Strategist for the 3D animated Indian Army channel "Foji Zindagi 3D" (@fojizindagi3d).
Create a 100% YouTube-native, high-CTR viral SEO package SEPARATE from the Instagram caption.

VIDEO FILE CONTEXT: {clean_base}
INSTAGRAM CAPTION CONTEXT: {raw_cap[:700]}

STRICT RULES:
1. "title": Punchy Hinglish/Hindi curiosity hook (max 75 chars) + 1 relevant emoji + ends with " #shorts". MUST be completely optimized for YouTube Shorts feed CTR.
2. "description": 4-6 crisp lines in natural Hinglish explaining the emotional/funny Fauji story, a strong Subscribe CTA for "Foji Zindagi 3D", Instagram credit "@ai_foji_lovelife", and "Jai Hind 🇮🇳". Do NOT dump 20 hashtags inside description.
3. "tags": JSON array of 16-20 high-search YouTube keywords (mix of Hindi-in-English & English: Indian Army, Fauji life, Agniveer, exact topic keywords from this video, 3D animation shorts, etc. — no '#' symbol in tags, total < 420 chars).
4. "hashtags": JSON array of EXACTLY 5 sharp hashtags starting with "#shorts", "#indianarmy", "#faujilife", plus 2 exact topic hashtags.

Return ONLY valid raw JSON with keys: title, description, tags, hashtags."""

    for model_name in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-lite-latest"):
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.75, "responseMimeType": "application/json"}
                },
                timeout=14
            )
            if r.status_code != 200:
                continue
            cand = (((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}])[0].get("text", "")
            cand = re.sub(r"^```(?:json)?\s*|\s*```$", "", cand.strip())
            parsed = json.loads(cand)
            if isinstance(parsed, dict) and parsed.get("title"):
                yt_title = str(parsed.get("title") or default_title).strip()
                if "#shorts" not in yt_title.lower():
                    yt_title = (yt_title[:84] + " #shorts").strip()
                yt_title = yt_title[:98]

                raw_ht = parsed.get("hashtags") or default_hashtags
                clean_ht = []
                for h in raw_ht:
                    hs = "#" + re.sub(r"[^a-zA-Z0-9_]", "", str(h).lstrip("#"))
                    if len(hs) > 2 and hs.lower() not in [x.lower() for x in clean_ht]:
                        clean_ht.append(hs)
                if not any(x.lower() == "#shorts" for x in clean_ht):
                    clean_ht.insert(0, "#shorts")
                clean_ht = clean_ht[:5]

                yt_desc = str(parsed.get("description") or default_desc).strip()
                if "#shorts" not in yt_desc.lower():
                    yt_desc = yt_desc + "\n\n" + " ".join(clean_ht)

                raw_tags = parsed.get("tags") or default_tags
                clean_tags = []
                total_len = 0
                for t in raw_tags:
                    ts = re.sub(r"[#<>]", "", str(t)).strip()[:40]
                    if ts and ts.lower() not in [x.lower() for x in clean_tags] and (total_len + len(ts) + 2) < 460:
                        clean_tags.append(ts)
                        total_len += len(ts) + 2

                return {
                    "title": yt_title,
                    "description": yt_desc[:4800],
                    "tags": clean_tags or default_tags,
                    "hashtags": clean_ht,
                    "via": model_name
                }
        except Exception:
            continue

    return {
        "title": default_title[:95],
        "description": default_desc,
        "tags": default_tags,
        "hashtags": default_hashtags,
        "via": "smart_template"
    }


def fetch_official_youtube_insights():
    """
    LIVE YOUTUBE DATA API v3 ANALYTICS (FAST PARALLEL):
    Works with `YT_API_KEY` + `YT_CHANNEL_ID` OR OAuth `YT_TOKEN_JSON`!
    Returns live Subscribers, Total Views, Video Count, AND latest 20 Shorts metrics!
    """
    cfg = load_tri_config()
    yt_key = (cfg.get("yt_api_key") or "").strip()
    yt_cid = (cfg.get("yt_channel_id") or "").strip()
    has_oauth = is_youtube_upload_ready()

    if not yt_key and not has_oauth:
        return {
            "connected": False,
            "source": "Not Connected",
            "subscribers": 0,
            "total_views": 0,
            "video_count": 0,
            "oauth_upload_ready": False,
            "reels": []
        }

    headers = {}
    params_ch = {"part": "snippet,statistics,contentDetails"}
    if yt_key and yt_cid:
        params_ch["id"] = yt_cid
        params_ch["key"] = yt_key
    elif has_oauth:
        acc_tok, err_t = _get_fresh_youtube_access_token()
        if not acc_tok:
            return {"connected": False, "source": "OAuth Refresh Needed", "note": err_t, "oauth_upload_ready": False, "reels": []}
        headers["Authorization"] = f"Bearer {acc_tok}"
        if yt_cid:
            params_ch["id"] = yt_cid
        else:
            params_ch["mine"] = "true"
    else:
        return {"connected": False, "source": "Missing YT_CHANNEL_ID", "oauth_upload_ready": has_oauth, "reels": []}

    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/channels", headers=headers, params=params_ch, timeout=10)
        if r.status_code != 200:
            return {"connected": False, "source": f"YT API HTTP {r.status_code}", "note": r.text[:140], "oauth_upload_ready": has_oauth, "reels": []}
        items = r.json().get("items") or []
        if not items:
            return {"connected": False, "source": "Channel Not Found", "oauth_upload_ready": has_oauth, "reels": []}

        ch = items[0]
        sn = ch.get("snippet") or {}
        st = ch.get("statistics") or {}
        uploads_pl = ((ch.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads", "")

        # Fetch latest 20 uploaded Shorts/videos + live views/likes/comments in just 2 ultra-fast API calls!
        shorts_list = []
        if uploads_pl:
            p_pl = {"part": "snippet,contentDetails", "playlistId": uploads_pl, "maxResults": 20}
            if yt_key and not headers:
                p_pl["key"] = yt_key
            r_pl = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", headers=headers, params=p_pl, timeout=10)
            if r_pl.status_code == 200:
                vids = [x.get("contentDetails", {}).get("videoId") for x in (r_pl.json().get("items") or []) if x.get("contentDetails", {}).get("videoId")]
                if vids:
                    p_vs = {"part": "snippet,statistics", "id": ",".join(vids[:20])}
                    if yt_key and not headers:
                        p_vs["key"] = yt_key
                    r_vs = requests.get("https://www.googleapis.com/youtube/v3/videos", headers=headers, params=p_vs, timeout=10)
                    if r_vs.status_code == 200:
                        for vobj in (r_vs.json().get("items") or []):
                            vsn = vobj.get("snippet") or {}
                            vst = vobj.get("statistics") or {}
                            vid_id = vobj.get("id", "")
                            vw = int(vst.get("viewCount") or 0)
                            lk = int(vst.get("likeCount") or 0)
                            cm = int(vst.get("commentCount") or 0)
                            th = ((vsn.get("thumbnails") or {}).get("high") or (vsn.get("thumbnails") or {}).get("medium") or {}).get("url", "")
                            shorts_list.append({
                                "id": vid_id,
                                "title": (vsn.get("title") or "YouTube Short")[:78],
                                "views": vw,
                                "likes": lk,
                                "comments": cm,
                                "er": round(((lk + cm) / max(1, vw)) * 100, 2) if vw > 0 else 0.0,
                                "thumbnail_url": th,
                                "permalink": f"https://youtube.com/shorts/{vid_id}",
                                "timestamp": vsn.get("publishedAt", ""),
                                "posted_at": _format_ig_ist_time(vsn.get("publishedAt", ""))
                            })

        avg_v = round(sum(x["views"] for x in shorts_list) / max(1, len(shorts_list))) if shorts_list else 0
        for x in shorts_list:
            delta = round(((x["views"] - avg_v) / max(1, avg_v)) * 100) if avg_v > 0 else 0
            x["delta_pct"] = delta
            x["status"] = "viral" if delta >= 35 else ("growing" if delta >= 0 else "downfall")

        return {
            "connected": True,
            "source": "Official YouTube Data API v3 (Live)",
            "channel_name": sn.get("title", "Foji Zindagi 3D"),
            "username": sn.get("customUrl") or sn.get("title", "@fojizindagi3d"),
            "subscribers": int(st.get("subscriberCount") or 0),
            "followers": int(st.get("subscriberCount") or 0),
            "total_views": int(st.get("viewCount") or 0),
            "total_likes": sum(x["likes"] for x in shorts_list),
            "total_comments": sum(x["comments"] for x in shorts_list),
            "video_count": int(st.get("videoCount") or len(shorts_list)),
            "oauth_upload_ready": has_oauth,
            "fetched_at": datetime.now(IST).strftime("%d %b %Y, %I:%M %p IST"),
            "reels": shorts_list
        }
    except Exception as e:
        return {"connected": False, "source": "Error", "note": str(e)[:160], "oauth_upload_ready": has_oauth, "reels": []}


def publish_short_official_youtube(local_video_path, title="", description="", ig_caption="", tags=None):
    """
    PURE-REQUESTS PRO YOUTUBE SHORTS AUTO-PUBLISHER:
    - Generates dedicated Gemini YouTube SEO (Title, Description, 18 Tags, 5 Hashtags)
    - Uses official YouTube Data API v3 Resumable Upload with auto-refreshed OAuth token
    - Works 24x7 on Render Free Tier with ZERO heavy SDK dependencies!
    """
    if not local_video_path or not os.path.exists(local_video_path):
        return {"ok": False, "error": f"Video file missing for YouTube upload: {local_video_path}"}

    acc_tok, err_t = _get_fresh_youtube_access_token()
    if not acc_tok:
        return {"ok": False, "error": err_t or "YouTube OAuth token not configured"}

    # Always generate dedicated Gemini YouTube SEO package unless explicit tags were passed
    seo = generate_gemini_youtube_seo_package(
        video_filename=os.path.basename(local_video_path),
        ig_caption=(ig_caption or description or ""),
        fallback_title=title
    )
    final_title = seo["title"]
    final_desc = seo["description"]
    final_tags = tags if (isinstance(tags, list) and tags) else seo["tags"]

    metadata = {
        "snippet": {
            "title": final_title,
            "description": final_desc,
            "tags": final_tags,
            "categoryId": "24",
            "defaultLanguage": "hi",
            "defaultAudioLanguage": "hi"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "embeddable": True
        }
    }

    try:
        file_bytes = open(local_video_path, "rb").read()
        file_size = len(file_bytes)

        # Step 1: Initiate official YouTube Resumable Upload session
        init_headers = {
            "Authorization": f"Bearer {acc_tok}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(file_size),
            "X-Upload-Content-Type": "video/mp4"
        }
        r_init = requests.post(
            "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
            headers=init_headers,
            json=metadata,
            timeout=25
        )
        if r_init.status_code not in (200, 201):
            return {"ok": False, "error": f"YT Init HTTP {r_init.status_code}: {r_init.text[:220]}"}

        upload_url = r_init.headers.get("Location")
        if not upload_url:
            return {"ok": False, "error": "YouTube did not return resumable upload Location header"}

        # Step 2: Upload MP4 bytes directly to YouTube
        r_up = requests.put(
            upload_url,
            headers={
                "Authorization": f"Bearer {acc_tok}",
                "Content-Type": "video/mp4",
                "Content-Length": str(file_size)
            },
            data=file_bytes,
            timeout=150
        )
        if r_up.status_code in (200, 201):
            vid_id = (r_up.json() or {}).get("id", "")
            short_url = f"https://youtube.com/shorts/{vid_id}" if vid_id else ""
            print(f"✅ [YouTube Shorts LIVE] {short_url} | SEO via {seo.get('via')} | Title: {final_title}")
            return {
                "ok": True,
                "video_id": vid_id,
                "url": short_url,
                "title": final_title,
                "tags_count": len(final_tags),
                "seo_via": seo.get("via")
            }
        return {"ok": False, "error": f"YT Upload HTTP {r_up.status_code}: {r_up.text[:220]}"}
    except Exception as e:
        return {"ok": False, "error": f"YT Upload Exception: {str(e)[:180]}"}





def get_unified_tri_platform_summary():
    ig = fetch_official_instagram_insights()
    fb = fetch_official_facebook_insights()
    yt = fetch_official_youtube_insights()

    # Fallback IG numbers from verified local cache if official token isn't pasted yet
    if not ig.get("connected") and os.path.exists("data/ig_live_analytics.json"):
        try:
            cached = json.load(open("data/ig_live_analytics.json", "r", encoding="utf-8"))
            ig.update({
                "username": cached.get("username", "@ai_foji_lovelife"),
                "followers": int(cached.get("followers_count") or 0),
                "media_count": int(cached.get("total_reels_posted") or 0),
                "total_views": int(cached.get("total_views_reach") or 0),
                "total_likes": int(cached.get("total_likes") or 0),
                "source": "Session Sync (Paste Official Token to Upgrade)"
            })
        except Exception:
            pass

    summary = {
        "ok": True,
        "updated_at_ist": datetime.now(IST).strftime("%I:%M:%S %p IST"),
        "combined_views": int(ig.get("total_views") or 0) + int(fb.get("total_views") or 0) + int(yt.get("total_views") or 0),
        "combined_audience": int(ig.get("followers") or 0) + int(fb.get("followers") or 0) + int(yt.get("subscribers") or 0),
        "instagram": ig,
        "facebook": fb,
        "youtube": yt
    }
    try:
        with open(INSIGHTS_CACHE_FILE, "w", encoding="utf-8") as cf:
            json.dump(summary, cf, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return summary


def get_combined_tri_platform_insights(force_refresh=False):
    if force_refresh and os.path.exists(INSIGHTS_CACHE_FILE):
        try:
            os.remove(INSIGHTS_CACHE_FILE)
        except Exception:
            pass
    try:
        return get_unified_tri_platform_summary(force_refresh=force_refresh)
    except TypeError:
        return get_unified_tri_platform_summary()
