import os
import sys
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def upload_reel_to_instagram(video_path, caption=""):
    import dashboard_app as da
    cl = da.get_authenticated_ig_client()
    thumb = da._ensure_reel_thumbnail(video_path)
    try:
        media = cl.clip_upload(
            video_path,
            caption=caption,
            thumbnail=thumb,
            extra_data={"share_to_facebook": "1", "share_to_fb_reels": "1", "crosspost_to_facebook": "1"}
        )
    except TypeError:
        media = cl.clip_upload(video_path, caption=caption, thumbnail=thumb)
    pk = getattr(media, "pk", None) or getattr(media, "id", None)
    if not pk:
        raise RuntimeError("Instagram upload returned no Media PK!")
    return str(pk)

post_reel = upload_reel_to_instagram
upload_to_instagram = upload_reel_to_instagram
post_reel_to_instagram = upload_reel_to_instagram
publish_reel_to_instagram = upload_reel_to_instagram
