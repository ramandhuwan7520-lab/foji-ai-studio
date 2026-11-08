import os
import sys
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Proxy all IG publishing calls directly to dashboard_app / core publisher engine
try:
    from dashboard_app import (
        _publish_specific_video_to_ig,
        get_authenticated_ig_client,
        _ensure_reel_thumbnail
    )
    post_reel_to_instagram = _publish_specific_video_to_ig
    upload_to_instagram = _publish_specific_video_to_ig
    upload_reel = _publish_specific_video_to_ig
    post_to_instagram = _publish_specific_video_to_ig
    publish_reel_to_instagram = _publish_specific_video_to_ig
except Exception as e:
    def post_reel_to_instagram(video_path, caption=""):
        raise RuntimeError(f"Instagram publisher proxy error: {e}")
    upload_to_instagram = post_reel_to_instagram
    upload_reel = post_reel_to_instagram
    post_to_instagram = post_reel_to_instagram
    publish_reel_to_instagram = post_reel_to_instagram
