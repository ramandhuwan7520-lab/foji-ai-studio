import os
import math
import wave
import glob
import random
import struct
import shutil
import subprocess

os.makedirs("assets/bgm", exist_ok=True)
os.makedirs("assets/bgm/trending", exist_ok=True)

TRENDING_YT_QUERIES = {
    "ragda_action": [
        "ytsearch1:Aarambh Hai Prachand viral reel bgm",
        "ytsearch1:Haryanvi desi gym attitude bgm reel",
        "ytsearch1:Chak De India motivational bgm instrumental"
    ],
    "agniveer_reality": [
        "ytsearch1:Teri Mitti emotional instrumental bgm reel",
        "ytsearch1:Sandese Aate Hai flute emotional bgm reel",
        "ytsearch1:Shershaah Ranjha emotional instrumental bgm"
    ],
    "duty_fatigue": [
        "ytsearch1:Lakshya title track motivational instrumental bgm",
        "ytsearch1:Zinda Bhaag Milkha Bhaag motivational bgm reel",
        "ytsearch1:Kar Har Maidaan Fateh instrumental bgm"
    ],
    "funny_masti": [
        "ytsearch1:Hera Pheri funny comedy bgm reel",
        "ytsearch1:Bollywood comedy masti viral bgm reel",
        "ytsearch1:Haryanvi funny desi beat bgm reel"
    ],
    "emotional_love": [
        "ytsearch1:Raataan Lambiyan slowed reverb bgm reel",
        "ytsearch1:Kesariya soft instrumental bgm reel",
        "ytsearch1:Ve Kamleya flute instrumental bgm reel"
    ]
}


def _get_ffmpeg_binary():
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass
    return shutil.which("ffmpeg") or "ffmpeg"


def _detect_mood_from_pkg(pkg):
    txt = ""
    if isinstance(pkg, dict):
        txt = " ".join([
            str(pkg.get("track_id", "")),
            str(pkg.get("emotion_name", "")),
            str(pkg.get("bgm_category", "")),
            str(pkg.get("title", ""))
        ]).lower()
    if any(k in txt for k in ("funny", "comedy", "masti", "bakwas", "mess")):
        return "funny_masti"
    if any(k in txt for k in ("ragda", "punish", "ustad", "training", "drill")):
        return "ragda_action"
    if any(k in txt for k in ("agniveer", "border", "desh", "patriot", "pride")):
        return "agniveer_reality"
    if any(k in txt for k in ("duty", "fatigue", "working", "guard")):
        return "duty_fatigue"
    if any(k in txt for k in ("love", "meera", "nok", "roman", "fojan")):
        return "emotional_love"
    return "ragda_action"


def fetch_trending_bollywood_bgm_clip(mood_key):
    cache_dir = os.path.join("assets", "bgm", "trending", mood_key)
    os.makedirs(cache_dir, exist_ok=True)
    cached = [f for f in glob.glob(os.path.join(cache_dir, "*.mp3")) if os.path.getsize(f) > 25 * 1024]
    if len(cached) >= 2:
        return random.choice(cached)

    q = random.choice(TRENDING_YT_QUERIES.get(mood_key, TRENDING_YT_QUERIES["ragda_action"]))
    ffmpeg_exe = _get_ffmpeg_binary()
    out_mp3 = os.path.join(cache_dir, f"trend_{mood_key}_{random.randint(100,999)}.mp3")
    raw_tmp = os.path.join(cache_dir, "raw_dl.m4a")
    try:
        yt_cmd = [
            "yt-dlp", "-f", "bestaudio[ext=m4a]/bestaudio",
            "--no-playlist", "--max-filesize", "8M",
            "--download-sections", "*0:10-0:26",
            "-o", raw_tmp, q
        ]
        res = subprocess.run(yt_cmd, capture_output=True, text=True, timeout=35)
        if res.returncode != 0 or not os.path.exists(raw_tmp):
            yt_cmd[0:1] = ["python3" if os.name != "nt" else "python", "-m", "yt_dlp"]
            subprocess.run(yt_cmd, capture_output=True, text=True, timeout=35)

        if os.path.exists(raw_tmp) and os.path.getsize(raw_tmp) > 10 * 1024:
            subprocess.run([
                ffmpeg_exe, "-y", "-i", raw_tmp, "-t", "12",
                "-af", "afade=t=in:st=0:d=0.8,afade=t=out:st=10.8:d=1.2,loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:a", "libmp3lame", "-b:a", "128k", out_mp3
            ], capture_output=True, timeout=25)
            try:
                os.remove(raw_tmp)
            except Exception:
                pass
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 20 * 1024:
                print(f"🎵 [Trending Bollywood BGM] Cut & cached '{mood_key}': {os.path.basename(out_mp3)}")
                return out_mp3
    except Exception as _ye:
        print(f"ℹ️ [Trending BGM Note] Using fallback audio ({_ye})")
    return cached[0] if cached else None


def _synthesize_fallback_wav(mood_key, out_wav, duration_sec=12):
    sr = 44100
    n = int(sr * duration_sec)
    freqs = {
        "funny_masti": (261.6, 329.6, 392.0),
        "emotional_love": (220.0, 261.6, 329.6),
        "ragda_action": (110.0, 164.8, 220.0),
        "agniveer_reality": (196.0, 246.9, 293.7),
        "duty_fatigue": (146.8, 220.0, 293.7)
    }.get(mood_key, (196.0, 246.9, 293.7))
    with wave.open(out_wav, "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = bytearray()
        for i in range(n):
            t = i / sr
            env = min(1.0, t / 0.6) * min(1.0, (duration_sec - t) / 0.8)
            val = 0.22 * env * (
                math.sin(2 * math.pi * freqs[0] * t)
                + 0.6 * math.sin(2 * math.pi * freqs[1] * t)
                + 0.4 * math.sin(2 * math.pi * freqs[2] * t)
            )
            s = int(max(-32767, min(32767, val * 32767)))
            frames += struct.pack("<hh", s, s)
        wf.writeframes(frames)
    return out_wav


def auto_mix_genre_bgm_into_video(video_path, pending_pkg=None):
    if not video_path or not os.path.exists(video_path) or os.path.getsize(video_path) < 50 * 1024:
        return False

    mood = _detect_mood_from_pkg(pending_pkg)
    ffmpeg_exe = _get_ffmpeg_binary()
    bgm_file = fetch_trending_bollywood_bgm_clip(mood)
    if not bgm_file:
        bgm_file = os.path.join("assets", "bgm", f"synth_{mood}.wav")
        if not os.path.exists(bgm_file):
            _synthesize_fallback_wav(mood, bgm_file, 12)

    tmp_out = video_path + ".bgm_mix.mp4"
    try:
        cmd = [
            ffmpeg_exe, "-y", "-i", video_path, "-stream_loop", "-1", "-i", bgm_file,
            "-filter_complex", "[0:a]volume=1.0[a0];[1:a]volume=0.16,afade=t=in:st=0:d=0.6[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", tmp_out
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode != 0 or not os.path.exists(tmp_out) or os.path.getsize(tmp_out) < 50 * 1024:
            cmd2 = [
                ffmpeg_exe, "-y", "-i", video_path, "-stream_loop", "-1", "-i", bgm_file,
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", tmp_out
            ]
            subprocess.run(cmd2, capture_output=True, text=True, timeout=60)

        if os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 50 * 1024:
            os.replace(tmp_out, video_path)
            print(f"✅ [BGM Mastered] Mixed '{mood}' BGM ({os.path.basename(bgm_file)}) into {os.path.basename(video_path)}!")
            return True
    except Exception as _me:
        print(f"ℹ️ BGM mix skipped safely: {_me}")
    finally:
        if os.path.exists(tmp_out):
            try:
                os.remove(tmp_out)
            except Exception:
                pass
    return False
