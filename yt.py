from flask import Flask, request, jsonify
import requests, re, json, time, hashlib, hmac
import cloudscraper
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)

# ==========================================
# GLOBAL ERROR HANDLER - No HTML trash allowed!
# ==========================================
@app.errorhandler(Exception)
def handle_global_exception(e):
    """
    Catch-all exception handler to guarantee that we ALWAYS return clean, 
    crisp JSON even when everything goes to hell.
    """
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


# =========================
# HELPERS
# =========================
def extract_video_id(url):
    if "youtu.be" in url:
        return url.split("/")[-1].split("?")[0]
    if "youtube.com" in url:
        parsed = urlparse(url)
        return parse_qs(parsed.query).get("v", [None])[0]
    return None


def pick_default_quality(available, default):
    # Sort descending so we try highest quality first
    available = sorted(map(int, available), reverse=True)
    if default in available:
        return str(default)
    for q in available:
        if q < default:
            return str(q)
    return str(available[-1])


# =========================
# API ROUTE
# =========================
@app.route("/download", methods=["GET"])
def download():
    yt_url = request.args.get("url")
    mode = request.args.get("type", "mp3").lower()
    req_quality = request.args.get("quality")

    if not yt_url or mode not in ["mp3", "mp4"]:
        return jsonify({"error": "Invalid parameters", "required": "url and type (mp3/mp4)"}), 400

    video_id = extract_video_id(yt_url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL - couldn't extract video ID"}), 400

    default_quality = 320 if mode == "mp3" else 1080

    scraper = cloudscraper.create_scraper()
    base_url = 'https://embed.dlsrv.online'
    
    headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
        'origin': base_url,
        'referer': f'{base_url}/v1/full?videoId={video_id}'
    }

    # =======================================================
    # STEP 1: FETCH VIDEO FORMAT INFO (UNAUTHENTICATED)
    # =======================================================
    try:
        info_res = scraper.post(f'{base_url}/api/info', json={'videoId': video_id}, headers=headers, timeout=12)
        info_res.raise_for_status()
        info_data = info_res.json()
    except Exception as e:
        return jsonify({
            "error": "Failed to fetch format details from backend",
            "details": str(e)
        }), 502

    if info_data.get("status") == "error" or "info" not in info_data:
        return jsonify({
            "error": "Downstream service returned error or invalid format information",
            "response": info_data
        }), 502

    title = info_data.get("info", {}).get("title", "Unknown Video")
    formats = info_data.get("info", {}).get("formats", [])

    # =======================================================
    # STEP 2: QUALITY & FORMAT RESOLUTION
    # =======================================================
    download_format = ""
    download_quality = ""

    if mode == "mp3":
        # Find audio formats (typically m4a, opus)
        audio_formats = [f for f in formats if f.get("type") == "audio"]
        if not audio_formats:
            return jsonify({"error": "No audio formats found for this video"}), 502
        
        # Default to m4a or search for preferred format if specified in req_quality
        download_format = "m4a"
        if req_quality and any(f.get("format") == req_quality for f in audio_formats):
            download_format = req_quality
        else:
            # Fallback to whatever audio format is available
            download_format = audio_formats[0].get("format", "m4a")
            
        download_quality = ""  # Not used for audio download payloads
    else:
        # Find video format qualities
        video_formats = [f for f in formats if f.get("type") == "video" and f.get("format") == "mp4"]
        if not video_formats:
            return jsonify({"error": "No MP4 video formats found for this video"}), 502
        
        # Extract quality digits (e.g. '1080p' -> '1080')
        available_qualities = []
        for f in video_formats:
            q = f.get("quality", "")
            m = re.match(r'(\d+)', q)
            if m:
                available_qualities.append(m.group(1))

        if not available_qualities:
            return jsonify({"error": "Could not extract video quality options"}), 502

        available_qualities = sorted(set(available_qualities), key=int, reverse=True)

        if req_quality:
            # Normalize requested quality (e.g., '1080p' -> '1080')
            req_q_clean = re.sub(r'\D', '', req_quality)
            if req_q_clean not in available_qualities:
                return jsonify({
                    "error": "Requested quality not available",
                    "requested": req_quality,
                    "available": [f"{q}p" for q in available_qualities]
                }), 400
            download_quality = req_q_clean
        else:
            download_quality = pick_default_quality(available_qualities, default_quality)
        
        download_format = "mp4"

    # =======================================================
    # STEP 3: SESSION VERIFICATION HANDSHAKE (ANTI-BOT BYPASS)
    # =======================================================
    # 3.1 Fetch initToken from HTML page
    try:
        page_res = scraper.get(f'{base_url}/v1/full?videoId={video_id}', headers=headers, timeout=12)
        page_res.raise_for_status()
    except Exception as e:
        return jsonify({"error": "Failed to load session page", "details": str(e)}), 502

    token_match = re.search(r'id="init-token"\s+data-token="([^"]+)"', page_res.text)
    if not token_match:
        return jsonify({"error": "Verification token parsing failed"}), 502
    init_token = token_match.group(1)

    # 3.2 Request PoW Challenge
    try:
        challenge_res = scraper.post(f'{base_url}/api/challenge', headers=headers, timeout=12)
        challenge_res.raise_for_status()
        challenge = challenge_res.json()
    except Exception as e:
        return jsonify({"error": "Failed to get session challenge", "details": str(e)}), 502

    salt = challenge['salt']
    ts = challenge['ts']
    difficulty = challenge.get('difficulty', 3)

    # 3.3 Solve PoW Challenge
    prefix = '0' * difficulty
    nonce = 0
    pow_start = time.time()
    max_loops = 500000
    while nonce < max_loops:
        data_str = f"{salt}:{ts}:{nonce}".encode('utf-8')
        h = hashlib.sha256(data_str).hexdigest()
        if h.startswith(prefix):
            solved_nonce = str(nonce)
            break
        nonce += 1
    else:
        return jsonify({"error": "Proof of Work challenge calculation timed out"}), 500
    
    pow_time = int((time.time() - pow_start) * 1000)

    # 3.4 Generate fingerprint & telemetry
    fp_details = {
        "ua": headers['user-agent'],
        "lang": "en-US",
        "langs": "en-US,en",
        "screen": {"w": 1366, "h": 768, "cd": 24},
        "tzOffset": "-330",
        "tz": "Asia/Kolkata",
        "hc": "8",
        "dm": "8",
        "chrome": "true",
        "canvasHash": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAMgAAADICAYAAACt"
    }
    fp_str = "|".join([
        fp_details["ua"],
        fp_details["lang"],
        fp_details["langs"],
        "1366x768x24",
        "-330",
        "Asia/Kolkata",
        "8",
        "8",
        "true",
        fp_details["canvasHash"]
    ])
    fp_hash = hashlib.sha256(fp_str.encode('utf-8')).hexdigest()

    verify_payload = {
        "initToken": init_token,
        "fpHash": fp_hash,
        "fpDetails": fp_details,
        "salt": salt,
        "ts": ts,
        "signature": challenge['signature'],
        "nonce": solved_nonce,
        "telemetry": {
            "interactions": 15,
            "timeToVerify": max(50, pow_time)
        }
    }

    # 3.5 Submit Verification
    try:
        verify_res = scraper.post(f'{base_url}/api/verify', headers={'Content-Type': 'application/json', **headers}, json=verify_payload, timeout=12)
        verify_res.raise_for_status()
        verify_data = verify_res.json()
    except Exception as e:
        return jsonify({"error": "Verification session handshake rejected", "details": str(e)}), 502

    session_token = verify_data.get('token')
    if not session_token:
        return jsonify({"error": "Downstream verify response missing session token"}), 502

    # =======================================================
    # STEP 4: SIGN & REQUEST DOWNLOAD
    # =======================================================
    now_ms = str(int(time.time() * 1000))
    key = session_token[-32:].encode('utf-8')
    message = f"{now_ms}:{video_id}".encode('utf-8')
    sig = hmac.new(key, message, hashlib.sha256).hexdigest()

    download_headers = {
        'Authorization': f'Bearer {session_token}',
        'Content-Type': 'application/json',
        'x-fp': fp_hash,
        'x-ts': now_ms,
        'x-sig': sig,
        **headers
    }

    download_payload = {
        "videoId": video_id,
        "format": download_format,
        "quality": download_quality
    }

    try:
        download_res = scraper.post(f'{base_url}/api/download/{mode}', headers=download_headers, json=download_payload, timeout=15)
        download_res.raise_for_status()
        download_data = download_res.json()
    except Exception as e:
        return jsonify({"error": "Failed to request download link from downstream", "details": str(e)}), 502

    download_url = download_data.get("url")
    if not download_url:
        return jsonify({
            "error": "Download URL missing from downstream response",
            "raw_response": download_data
        }), 502

    return jsonify({
        "Title": title,
        "Quality": f"{download_quality}p" if download_quality else download_format,
        "Download Link": download_url,
        "Developer": "t.me/Sudhirxd",
        "Website": "www.sudhirxd.in",
        "Github": "www.github.com/sudheer729"
    })


# =========================
# RUN (TERMUX SAFE)
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)