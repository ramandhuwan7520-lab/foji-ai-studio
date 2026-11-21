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

    cfg = {
        "meta_app_id": _first_env("META_APP_ID", "FB_APP_ID"),
        "meta_app_secret": _first_env("META_APP_SECRET", "FB_APP_SECRET"),
        "ig_access_token": _first_env("IG_OFFICIAL_ACCESS_TOKEN", "IG_ACCESS_TOKEN", "INSTAGRAM_ACCESS_TOKEN", "META_ACCESS_TOKEN", "IG_TOKEN"),
        "ig_account_id": _first_env("IG_OFFICIAL_ACCOUNT_ID", "IG_ACCOUNT_ID", "INSTAGRAM_ACCOUNT_ID", "IG_USER_ID"),
        "fb_page_id": _first_env("FB_PAGE_ID"),
        "fb_page_token": _first_env("FB_PAGE_ACCESS_TOKEN", "FB_PAGE_TOKEN"),
        "yt_channel_id": _first_env("YT_CHANNEL_ID"),
        "yt_api_key": _first_env("YT_API_KEY"),
        "yt_client_secret_path": "data/youtube_client_secret.json",
        "yt_token_path": "data/youtube_token.json",
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


def fetch_official_instagram_insights():
    """
    META UNIFIED LOGIN + INSTAGRAM LOGIN + BUSINESS PORTFOLIO + FACEBOOK PAGE ENGINE:
    Discovers the exact Instagram Account ID across ALL official Meta Graph routes
    and fetches live views, likes, comments, saves, shares & followers.
    """
    cfg = load_tri_config()
    tok = _auto_refresh_ig_login_token_if_due(cfg)
    ig_id = str(cfg.get("ig_account_id") or "").strip()
    app_id = str(cfg.get("meta_app_id") or "").strip()
    app_sec = str(cfg.get("meta_app_secret") or "").strip()

    if not tok:
        return {
            "connected": False,
            "source": "Not Connected",
            "note": "Open /auth/instagram_login OR set IG_OFFICIAL_ACCESS_TOKEN in Render Environment."
        }

    prof = None
    active_base = None
    media_ep = None
    debug_scopes = []
    candidate_ids = []
    pages_summary = []
    biz_ig_found = []
    if ig_id:
        candidate_ids.append(ig_id)
    last_err = ""

    def _probe_ig_id(cid):
        nonlocal prof, active_base, media_ep, ig_id, last_err
        for b_url, flds in (
            ("https://graph.instagram.com/v22.0", "user_id,id,username,followers_count,follows_count,media_count"),
            ("https://graph.facebook.com/v22.0", "id,username,followers_count,follows_count,media_count"),
        ):
            try:
                rp = requests.get(f"{b_url}/{cid}", params={"fields": flds, "access_token": tok}, timeout=10)
                if rp.status_code == 200 and rp.json().get("username"):
                    prof = rp.json()
                    ig_id = str(prof.get("user_id") or prof.get("id") or cid)
                    active_base = b_url
                    media_ep = f"{active_base}/{ig_id}/media"
                    return True
                else:
                    last_err = f"{b_url.split('//')[1].split('/')[0]}/{cid} {rp.status_code}: {rp.text[:100]}"
            except Exception as _pe:
                last_err = str(_pe)[:90]
        return False

    try:
        # ROUTE 1: Direct `graph.instagram.com/v22.0/me` (Instagram Login & IG-scoped Unified tokens)
        try:
            r_ig_me = requests.get(
                "https://graph.instagram.com/v22.0/me",
                params={"fields": "user_id,id,username,followers_count,follows_count,media_count", "access_token": tok},
                timeout=12
            )
            if r_ig_me.status_code == 200 and r_ig_me.json().get("username"):
                prof = r_ig_me.json()
                ig_id = str(prof.get("user_id") or prof.get("id") or ig_id)
                active_base = "https://graph.instagram.com/v22.0"
                media_ep = f"{active_base}/me/media"
            else:
                last_err = f"IG/me {r_ig_me.status_code}: {r_ig_me.text[:110]}"
        except Exception as _e1:
            last_err = str(_e1)[:100]

        # ROUTE 2: Meta `debug_token` granular_scopes target_ids
        if not prof and app_id and app_sec:
            try:
                r_dbg = requests.get(
                    "https://graph.facebook.com/v22.0/debug_token",
                    params={"input_token": tok, "access_token": f"{app_id}|{app_sec}"},
                    timeout=12
                )
                if r_dbg.status_code == 200:
                    dd = (r_dbg.json() or {}).get("data") or {}
                    debug_scopes = list(dd.get("scopes") or [])
                    for gs in (dd.get("granular_scopes") or []):
                        sc = str(gs.get("scope") or "").lower()
                        if "instagram" in sc:
                            for tid in (gs.get("target_ids") or []):
                                tid_s = str(tid).strip()
                                if tid_s and tid_s not in candidate_ids:
                                    candidate_ids.append(tid_s)
            except Exception:
                pass

        # ROUTE 3: Probe explicit `ig_account_id` & granular target_ids
        if not prof and candidate_ids:
            for cid in candidate_ids:
                if _probe_ig_id(cid):
                    break

        # ROUTE 4: `/me/accounts` -> check BOTH `instagram_business_account` AND `connected_instagram_account`
        if not prof:
            try:
                r_pg = requests.get(
                    "https://graph.facebook.com/v22.0/me/accounts",
                    params={"fields": "id,name,access_token,instagram_business_account,connected_instagram_account", "access_token": tok},
                    timeout=12
                )
                if r_pg.status_code == 200:
                    for pg in (r_pg.json().get("data") or []):
                        iba = pg.get("instagram_business_account") or pg.get("connected_instagram_account") or {}
                        pages_summary.append(f"{pg.get('name','?')}(ig={bool(iba.get('id'))})")
                        if iba.get("id") and _probe_ig_id(str(iba["id"])):
                            save_tri_config({
                                "ig_account_id": ig_id,
                                "fb_page_id": str(pg.get("id") or ""),
                                "fb_page_token": str(pg.get("access_token") or "")
                            })
                            break
            except Exception:
                pass

        # ROUTE 5: Meta Business Portfolio -> `owned_instagram_accounts` & `instagram_accounts`
        if not prof:
            try:
                r_bz = requests.get("https://graph.facebook.com/v22.0/me/businesses", params={"fields": "id,name", "access_token": tok}, timeout=10)
                if r_bz.status_code == 200:
                    for bz in (r_bz.json().get("data") or [])[:5]:
                        bid = bz.get("id")
                        for edge in ("owned_instagram_accounts", "instagram_accounts", "client_instagram_accounts"):
                            r_bi = requests.get(f"https://graph.facebook.com/v22.0/{bid}/{edge}", params={"fields": "id,username", "access_token": tok}, timeout=8)
                            if r_bi.status_code == 200:
                                for ig_obj in (r_bi.json().get("data") or []):
                                    if ig_obj.get("id"):
                                        biz_ig_found.append(f"{ig_obj.get('username','?')}:{ig_obj['id']}")
                                        if _probe_ig_id(str(ig_obj["id"])):
                                            break
                            if prof:
                                break
                        if prof:
                            break
            except Exception:
                pass

        if not prof or not active_base:
            diag_parts = [
                f"Err={last_err}",
                f"Pages={pages_summary[:4]}",
                f"BizIG={biz_ig_found[:4]}",
                f"Scopes={debug_scopes[:8]}",
                "Action: Open /auth/instagram_login to connect @ai_foji_lovelife via Unified Login"
            ]
            return {
                "connected": False,
                "source": "Needs Unified IG OAuth",
                "note": " | ".join(diag_parts)[:320]
            }

        if ig_id and ig_id != cfg.get("ig_account_id"):
            save_tri_config({"ig_account_id": ig_id})

        reels = []
        next_url = media_ep
        params = {
            "fields": "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count,thumbnail_url,media_url",
            "limit": 25,
            "access_token": tok
        }
        for _ in range(3):
            rm = requests.get(next_url, params=params, timeout=14)
            if rm.status_code != 200:
                break
            mj = rm.json()
            for item in (mj.get("data") or []):
                views_val = 0
                saved_val = 0
                shares_val = 0
                for metric_set in ("views,reach,saved,shares", "views", "reach"):
                    try:
                        ri = requests.get(
                            f"{active_base}/{item['id']}/insights",
                            params={"metric": metric_set, "access_token": tok},
                            timeout=6
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
                            if views_val > 0:
                                break
                    except Exception:
                        pass

                likes = int(item.get("like_count") or 0)
                comments = int(item.get("comments_count") or 0)
                er = round(((likes + comments + saved_val + shares_val) / max(1, views_val)) * 100, 2) if views_val > 0 else 0.0
                thumb = item.get("thumbnail_url") or (item.get("media_url") if item.get("media_type") == "IMAGE" else "")
                reels.append({
                    "id": item.get("id"),
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
                })
            next_url = (mj.get("paging") or {}).get("next")
            params = None
            if not next_url:
                break

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
            "source": "Official Meta Graph API (Unified)",
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
                    "sync_source": "Official Meta Graph API (Unified)",
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


def fetch_official_youtube_insights():
    cfg = load_tri_config()
    yt_key = cfg.get("yt_api_key", "")
    yt_cid = cfg.get("yt_channel_id", "")
    has_oauth = os.path.exists(cfg.get("yt_token_path", "data/youtube_token.json"))
    if not yt_key and not has_oauth:
        return {"connected": False, "source": "Not Connected", "subscribers": 0, "total_views": 0, "video_count": 0}
    try:
        if yt_key and yt_cid:
            r = requests.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "snippet,statistics", "id": yt_cid, "key": yt_key},
                timeout=12
            )
            if r.status_code == 200:
                items = r.json().get("items") or []
                if items:
                    sn = items[0].get("snippet") or {}
                    st = items[0].get("statistics") or {}
                    return {
                        "connected": True,
                        "source": "Official YouTube Data API v3",
                        "channel_name": sn.get("title", "YouTube Channel"),
                        "subscribers": int(st.get("subscriberCount") or 0),
                        "total_views": int(st.get("viewCount") or 0),
                        "video_count": int(st.get("videoCount") or 0),
                        "oauth_upload_ready": has_oauth
                    }
        return {"connected": has_oauth, "source": "YouTube OAuth Ready" if has_oauth else "Add Channel ID + API Key", "subscribers": 0, "total_views": 0, "video_count": 0}
    except Exception as e:
        return {"connected": False, "source": "Error", "note": str(e)[:140], "subscribers": 0, "total_views": 0, "video_count": 0}


def publish_short_official_youtube(local_video_path, title, description):
    cfg = load_tri_config()
    tok_p = cfg.get("yt_token_path", "data/youtube_token.json")
    if not os.path.exists(tok_p) or not os.path.exists(local_video_path):
        return {"ok": False, "error": "YouTube OAuth token or video file missing"}
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = Credentials.from_authorized_user_file(tok_p, ["https://www.googleapis.com/auth/youtube.upload"])
        yt = build("youtube", "v3", credentials=creds)
        clean_title = (title or "Foji 3D Story #Shorts").strip()[:88]
        if "#shorts" not in clean_title.lower():
            clean_title = (clean_title[:80] + " #Shorts").strip()
        body = {
            "snippet": {
                "title": clean_title,
                "description": (description or "") + "\n\n#Shorts #FojiAIStudio",
                "tags": ["Shorts", "3DAnimation", "IndianArmy", "FaujiLife", "ViralShorts"],
                "categoryId": "24"
            },
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
        }
        media = MediaFileUpload(local_video_path, mimetype="video/mp4", resumable=True)
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = req.execute()
        vid_id = resp.get("id", "")
        return {"ok": True, "platform": "youtube", "video_id": vid_id, "url": f"https://youtube.com/shorts/{vid_id}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


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
