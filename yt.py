from flask import Flask, request, jsonify
import yt_dlp
import os
import time
import tempfile
import shutil
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# ==========================================
# CONFIG & VERCEL COOKIES
# ==========================================
# Vercel and serverless platforms have a read-only filesystem except for the temp folder.
# Since yt-dlp attempts to write/save updated session cookies back to the cookie file,
# we must host the active cookie file in a writable temp directory to prevent [Errno 30] errors.
TEMP_DIR = tempfile.gettempdir()
COOKIE_FILE = os.path.join(TEMP_DIR, "yt_api_cookies.txt")

ENV_COOKIES = os.environ.get("YOUTUBE_COOKIES")
LOCAL_COOKIE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.txt")

if ENV_COOKIES:
    try:
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            f.write(ENV_COOKIES)
    except Exception as e:
        print(f"Failed to write environment cookies to temp: {e}")
elif os.path.isfile(LOCAL_COOKIE_PATH):
    try:
        shutil.copy2(LOCAL_COOKIE_PATH, COOKIE_FILE)
    except Exception as e:
        print(f"Failed to copy local cookies.txt to temp: {e}")


# ==========================================
# IN-MEMORY CACHE (Avoid duplicate YouTube hits)
# ==========================================
INFO_CACHE = {}
CACHE_TTL = 300  # 5 minutes in seconds

def get_cached_info(video_id, cache_key):
    """Retrieve info from cache if not expired."""
    now = time.time()
    if cache_key in INFO_CACHE:
        cached_time, data = INFO_CACHE[cache_key]
        if now - cached_time < CACHE_TTL:
            return data
    return None

def set_cached_info(cache_key, data):
    """Store info in cache."""
    INFO_CACHE[cache_key] = (time.time(), data)

# ==========================================
# GLOBAL ERROR HANDLER - clean JSON output
# ==========================================
@app.errorhandler(Exception)
def handle_global_exception(e):
    code = 500
    if hasattr(e, "code"):
        code = e.code
    
    response = {
        "error": "Internal Server Error" if code == 500 else getattr(e, "name", "Error"),
        "message": str(e),
        "Developer": "t.me/Sudhirxd",
        "Website": "www.sudhirxd.in",
        "Github": "www.github.com/sudheer729"
    }
    return jsonify(response), code

def get_quality_num(q):
    """Extract numeric value from quality strings like '720p', '128kbps', '48kbs' for sorting."""
    s = str(q).lower().strip()
    for suffix in ("p", "kbps", "kbs", "kb", "k"):
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
            break
    try:
        return int(float(s))
    except Exception:
        return 0

def format_abr(abr):
    """Safely format audio bitrate (abr) into a standard 'kbps' string."""
    if not abr:
        return "best"
    if isinstance(abr, (int, float)):
        return f"{int(abr)}kbps"
    s = str(abr).lower().strip()
    for suffix in ("kbps", "kbs", "kb", "k"):
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
            break
    try:
        return f"{int(float(s))}kbps"
    except Exception:
        return f"{abr}kbps" if "kb" not in s else abr

# ==========================================
# HELPERS
# ==========================================
def extract_video_id(url):
    if "youtu.be" in url:
        return url.split("/")[-1].split("?")[0]
    if "youtube.com" in url:
        parsed = urlparse(url)
        return parse_qs(parsed.query).get("v", [None])[0]
    return url  # raw video ID passthrough

def build_yt_url(video_id):
    """Always give yt-dlp a full URL — it's happier that way."""
    if video_id.startswith("http"):
        return video_id
    return f"https://www.youtube.com/watch?v={video_id}"

def get_cookie_opts():
    """
    Build cookie options for yt-dlp.
    Priority:
      1. ?browser= query param (live extraction from browser)
      2. ?cookie_file= query param (custom path)
      3. cookies.txt (auto-detect)
    """
    opts = {}
    
    browser = request.args.get("browser")
    if browser and browser.lower() in ("chrome", "firefox", "edge", "opera", "brave", "vivaldi", "safari", "chromium"):
        opts["cookiesfrombrowser"] = (browser.lower(),)
        return opts
    
    custom_cookie = request.args.get("cookie_file")
    if custom_cookie and os.path.isfile(custom_cookie):
        opts["cookiefile"] = custom_cookie
        return opts
    
    if os.path.isfile(COOKIE_FILE):
        opts["cookiefile"] = COOKIE_FILE
    
    return opts

def base_ydl_opts():
    """Base yt-dlp options — optimized for max speed & Vercel."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "check_formats": False,       # BIG SPEEDUP: bypass format URL verification HEAD requests
        "playlistend": 1,             # Prevent loading full playlist metadata if URL is a playlist
        "extract_flat": False,
        "no_color": True,
    }
    opts.update(get_cookie_opts())
    return opts

# ==========================================
# FORMAT SELECTORS
# ==========================================
QUALITY_MAP = {
    # Prioritize progressive (video + audio in one file) for 360p, 480p, and 720p
    "360p":   "best[height<=360][ext=mp4]/best[height<=360]/bestvideo[height<=360]",
    "480p":   "best[height<=480][ext=mp4]/best[height<=480]/bestvideo[height<=480]",
    "720p":   "best[height<=720][ext=mp4]/best[height<=720]/bestvideo[height<=720]",
    # 1080p and higher are always video-only (DASH) on YouTube and require separate audio URLs
    "1080p":  "bestvideo[height<=1080][ext=mp4]/bestvideo[height<=1080]",
    "1440p":  "bestvideo[height<=1440]",
    "2160p":  "bestvideo[height<=2160]",
    "4320p":  "bestvideo[height<=4320]",
    "best":   "bestvideo[ext=mp4]/bestvideo",
}

# =========================
# API ENDPOINTS
# =========================
@app.route("/", methods=["GET"])
def home():
    cookie_status = "cookies.txt found ✅" if os.path.isfile(COOKIE_FILE) else "No cookies.txt (place one next to yt.py)"
    
    return jsonify({
        "Message": "YouTube Downloader API — Powered by yt-dlp 🚀 (JSON only, no ffmpeg)",
        "Developer": "t.me/Sudhirxd",
        "Website": "www.sudhirxd.in",
        "cookie_status": cookie_status,
        "Endpoints": {
            "/info": {
                "method": "GET",
                "description": "Fetch video metadata & all available formats.",
                "parameters": {
                    "url": "Required. YouTube Video URL or video ID",
                    "browser": "Optional. Extract cookies from: chrome, firefox, edge, brave, opera, vivaldi"
                },
                "example": "/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            },
            "/download": {
                "method": "GET",
                "description": "Get direct CDN download URLs (video + audio). Returns JSON, no server-side download.",
                "parameters": {
                    "url": "Required. YouTube Video URL or ID",
                    "type": "Optional. 'audio' or 'video' (default: 'video')",
                    "quality": "Optional. '360p', '480p', '720p', '1080p', '1440p', '2160p', 'best' (default: 'best')",
                    "browser": "Optional. Extract cookies from browser"
                },
                "example": "/download?url=dQw4w9WgXcQ&type=video&quality=1080p"
            },
            "/cookie/status": {
                "method": "GET",
                "description": "Check if cookies.txt is loaded and valid."
            }
        }
    })

def fetch_info_dict(video_id, full_url, ydl_opts):
    """Retrieve info_dict using cache if available, otherwise fetch and cache it."""
    fmt = ydl_opts.get("format", "")
    cache_key = f"{video_id}_{request.args.get('browser','')}_{request.args.get('cookie_file','')}_{fmt}"
    cached = get_cached_info(video_id, cache_key)
    if cached:
        return cached
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(full_url, download=False)
    
    set_cached_info(cache_key, info_dict)
    return info_dict

# ========================================
# /info — Video metadata + format listing
# ========================================
@app.route("/info", methods=["GET"])
def info():
    yt_url = request.args.get("url")
    if not yt_url:
        return jsonify({"error": "Missing parameter", "required": "url"}), 400
    
    video_id = extract_video_id(yt_url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL — couldn't extract video ID"}), 400
    
    full_url = build_yt_url(video_id)
    ydl_opts = base_ydl_opts()
    
    try:
        info_dict = fetch_info_dict(video_id, full_url, ydl_opts)
        
        formats = []
        seen = set()
        for f in info_dict.get("formats", []):
            height = f.get("height")
            ext = f.get("ext", "")
            acodec = f.get("acodec", "none")
            vcodec = f.get("vcodec", "none")
            
            if height and vcodec != "none":
                label = f"{height}p"
                has_audio = acodec != "none"
                key = f"{label}_{ext}"
                if key not in seen:
                    seen.add(key)
                    formats.append({
                        "quality": label,
                        "format": ext,
                        "has_audio": has_audio,
                        "filesize_approx": f.get("filesize") or f.get("filesize_approx"),
                        "vcodec": vcodec,
                        "acodec": acodec if has_audio else None,
                        "fps": f.get("fps"),
                        "note": "video+audio" if has_audio else "video only"
                    })
            elif acodec != "none" and vcodec == "none":
                abr = f.get("abr")
                if abr:
                    label = format_abr(abr)
                    key = f"audio_{label}_{ext}"
                    if key not in seen:
                        seen.add(key)
                        formats.append({
                            "quality": label,
                            "format": ext,
                            "has_audio": True,
                            "filesize_approx": f.get("filesize") or f.get("filesize_approx"),
                            "acodec": acodec,
                            "type": "audio_only"
                        })
        
        formats.sort(key=lambda x: (
            0 if x.get("type") == "audio_only" else 1,
            -get_quality_num(x["quality"])
        ))
        
        return jsonify({
            "status": "success",
            "video_id": video_id,
            "title": info_dict.get("title"),
            "author": info_dict.get("uploader"),
            "duration": info_dict.get("duration"),
            "duration_string": info_dict.get("duration_string"),
            "thumbnail": info_dict.get("thumbnail"),
            "view_count": info_dict.get("view_count"),
            "upload_date": info_dict.get("upload_date"),
            "description": (info_dict.get("description") or "")[:500],
            "formats": formats,
            "cookies_used": bool(get_cookie_opts()),
            "Developer": "t.me/Sudhirxd",
            "Website": "www.sudhirxd.in"
        })
    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": "yt-dlp extraction failed", "details": str(e)}), 502
    except Exception as e:
        return jsonify({"error": "Failed to fetch video info", "details": str(e)}), 500
 
# ============================================================
# /download — Returns JSON with direct CDN URLs
# NO server-side download. Pure JSON response.
# For 1080p+ returns video_url + audio_url separately.
# ============================================================
@app.route("/download", methods=["GET"])
def download():
    yt_url = request.args.get("url")
    mode = request.args.get("type", "video").lower()
    quality = request.args.get("quality", "best").lower()
    
    if not yt_url or mode not in ["audio", "video"]:
        return jsonify({"error": "Invalid parameters", "required": "url, type (audio/video)"}), 400
    
    video_id = extract_video_id(yt_url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL — couldn't extract video ID"}), 400
    
    full_url = build_yt_url(video_id)
    ydl_opts = base_ydl_opts()
    
    if mode == "audio":
        ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio"
    else:
        fmt = QUALITY_MAP.get(quality, QUALITY_MAP["best"])
        ydl_opts["format"] = fmt
    
    try:
        info_dict = fetch_info_dict(video_id, full_url, ydl_opts)
        
        title = info_dict.get("title")
        
        result = {
            "status": "success",
            "video_id": video_id,
            "title": title,
            "thumbnail": info_dict.get("thumbnail"),
            "duration": info_dict.get("duration"),
            "type": mode,
            "quality": quality,
            "cookies_used": bool(get_cookie_opts()),
        }
        
        if mode == "audio":
            result["audio_url"] = info_dict.get("url")
            result["audio_ext"] = info_dict.get("ext")
            result["audio_quality"] = format_abr(info_dict.get('abr'))
            result["needs_merge"] = False
        else:
            # Video stream
            result["video_url"] = info_dict.get("url")
            result["video_ext"] = info_dict.get("ext")
            result["video_quality"] = f"{info_dict.get('height', '?')}p"
            result["video_fps"] = info_dict.get("fps")
            result["filesize"] = info_dict.get("filesize") or info_dict.get("filesize_approx")
            
            has_audio = info_dict.get("acodec", "none") != "none"
            result["has_audio"] = has_audio
            
            if has_audio:
                # Progressive — video+audio in one URL
                result["needs_merge"] = False
            else:
                # Video-only — also fetch the best audio stream URL
                result["needs_merge"] = True
                
                audio_opts = base_ydl_opts()
                audio_opts["format"] = "bestaudio[ext=m4a]/bestaudio"
                
                with yt_dlp.YoutubeDL(audio_opts) as ydl2:
                    audio_info = ydl2.extract_info(full_url, download=False)
                
                result["audio_url"] = audio_info.get("url")
                result["audio_ext"] = audio_info.get("ext")
                result["audio_quality"] = format_abr(audio_info.get('abr'))
        
        result["Developer"] = "t.me/Sudhirxd"
        result["Website"] = "www.sudhirxd.in"
        return jsonify(result)
    
    except yt_dlp.utils.DownloadError as e:
        return jsonify({"error": "yt-dlp extraction failed", "details": str(e)}), 502
    except Exception as e:
        return jsonify({"error": "Failed to get download URLs", "details": str(e)}), 500

# ==========================================
# /cookie/status — Check cookie config
# ==========================================
@app.route("/cookie/status", methods=["GET"])
def cookie_status():
    has_file = os.path.isfile(COOKIE_FILE)
    file_size = os.path.getsize(COOKIE_FILE) if has_file else 0
    file_age = None
    if has_file:
        file_age = round(time.time() - os.path.getmtime(COOKIE_FILE), 1)
    
    using_env = bool(os.environ.get("YOUTUBE_COOKIES"))
    
    return jsonify({
        "cookie_file_path": COOKIE_FILE,
        "cookie_file_exists": has_file,
        "cookie_file_size_bytes": file_size,
        "cookie_file_age_seconds": file_age,
        "using_env_cookies": using_env,
        "status": "loaded ✅" if (has_file or using_env) else "not found ❌",
        "hint": "Set YOUTUBE_COOKIES env var (Vercel) or save cookies.txt next to yt.py (local)",
        "supported_browsers": "chrome, firefox, edge, brave, opera, vivaldi (use ?browser=chrome to extract live)",
    })

# ==========================================
# MAIN
# ==========================================
if __name__ == "__main__":
    cookie_info = "✅ cookies.txt loaded" if os.path.isfile(COOKIE_FILE) else "⚠️  No cookies.txt (optional)"
    print("🚀 yt-dlp API starting... (JSON only, no ffmpeg, no downloads)")
    print(f"🍪 Cookies: {cookie_info}")
    app.run(host="0.0.0.0", port=5000, debug=True)