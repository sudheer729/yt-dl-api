from flask import Flask, request, jsonify
import requests, re, json, os, random
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
def get_headers():
    client_ip = request.headers.get('x-forwarded-for')
    if client_ip:
        client_ip = client_ip.split(',')[0].strip()
    else:
        client_ip = request.headers.get('x-real-ip', request.remote_addr)

    if not client_ip or client_ip in ['127.0.0.1', 'localhost', '::1']:
        client_ip = f"{random.randint(73, 76)}.{random.randint(10, 200)}.{random.randint(10, 200)}.{random.randint(1, 254)}"

    return {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'referer': 'https://vidssave.com/',
        'origin': 'https://vidssave.com',
        'content-type': 'application/x-www-form-urlencoded',
        'X-Forwarded-For': client_ip,
        'X-Real-IP': client_ip,
        'Client-IP': client_ip,
        'True-Client-IP': client_ip,
        'CF-Connecting-IP': client_ip
    }


def get_proxies():
    proxy_url = os.environ.get('PROXY_URL')
    if proxy_url:
        return {
            'http': proxy_url,
            'https': proxy_url
        }
    return None


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


def strip_key(obj, key_to_remove):
    if isinstance(obj, dict):
        if key_to_remove in obj:
            del obj[key_to_remove]
        for k, v in list(obj.items()):
            strip_key(v, key_to_remove)
    elif isinstance(obj, list):
        for item in obj:
            strip_key(item, key_to_remove)


# =========================
# API ROUTE
# =========================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "Message": "Welcome to YouTube Downloader API",
        "Developer": "t.me/Sudhirxd",
        "Website": "www.sudhirxd.in",
        "Github": "www.github.com/sudheer729",
        "Endpoints": {
            "/": {
                "method": "GET",
                "description": "Show list of all available API endpoints"
            },
            "/info": {
                "method": "GET",
                "description": "Get metadata and immediate direct download links for a YouTube video",
                "parameters": {
                    "url": "Required. Full YouTube video link"
                },
                "example": "/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
            },
            "/download": {
                "method": "GET",
                "description": "Get a direct download URL for video (MP4) or audio (MP3) in a specific quality",
                "parameters": {
                    "url": "Required. Full YouTube video link",
                    "type": "Required. 'mp3' or 'mp4'",
                    "quality": "Optional. Target quality (e.g. '720p', '1080p' for video; '128kbps', '256kbps' for audio)"
                },
                "example": "/download?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ&type=mp3"
            }
        }
    })


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

    # Ensure URL is full link
    full_yt_url = f"https://www.youtube.com/watch?v={video_id}"

    # Call Vidssave API
    api_url = 'https://api.vidssave.com/api/contentsite_api/media/parse'
    payload = {
        'auth': '20250901majwlqo',
        'domain': 'api-ak.vidssave.com',
        'origin': 'source',
        'link': full_yt_url
    }
    headers = get_headers()
    proxies = get_proxies()

    try:
        api_res = requests.post(api_url, data=payload, headers=headers, proxies=proxies, timeout=15)
        api_res.raise_for_status()
        api_data = api_res.json()
    except Exception as e:
        return jsonify({
            "error": "Failed to fetch format details from backend",
            "details": str(e)
        }), 502

    if api_data.get("status") != 1 or "data" not in api_data:
        return jsonify({
            "error": "Downstream service returned error or invalid format information",
            "response": api_data
        }), 502

    video_info = api_data.get("data", {})
    title = video_info.get("title", "Unknown Video")
    resources = video_info.get("resources", [])

    if not resources:
        return jsonify({"error": "No formats or download options found for this video"}), 502

    download_url = ""
    download_quality = ""

    target_res = None
    if mode == "mp3":
        audio_resources = [r for r in resources if r.get("type") == "audio" and r.get("format") == "MP3"]
        if not audio_resources:
            return jsonify({"error": "No MP3 audio formats found for this video"}), 502
            
        if req_quality:
            req_q_clean = re.sub(r'\D', '', req_quality)
            if req_q_clean:
                for r in audio_resources:
                    q_digits = re.sub(r'\D', '', r.get("quality", ""))
                    if q_digits == req_q_clean:
                        target_res = r
                        break
        
        if not target_res:
            def get_audio_quality_num(r):
                q_digits = re.sub(r'\D', '', r.get("quality", ""))
                return int(q_digits) if q_digits.isdigit() else 0
            
            audio_resources_sorted = sorted(audio_resources, key=get_audio_quality_num, reverse=True)
            target_res = audio_resources_sorted[0]
            
        download_quality = target_res.get("quality")
    else:
        video_resources = [r for r in resources if r.get("type") == "video" and r.get("format") == "MP4"]
        if not video_resources:
            return jsonify({"error": "No MP4 video formats found for this video"}), 502
            
        avail_map = {}
        for r in video_resources:
            q = r.get("quality", "")
            m = re.match(r'(\d+)', q)
            if m:
                avail_map[m.group(1)] = r
                
        available_qualities = sorted(avail_map.keys(), key=int, reverse=True)
        if not available_qualities:
            return jsonify({"error": "Could not extract video quality options"}), 502
            
        if req_quality:
            req_q_clean = re.sub(r'\D', '', req_quality)
            if req_q_clean in avail_map:
                target_res = avail_map[req_q_clean]
            else:
                return jsonify({
                    "error": "Requested quality not available",
                    "requested": req_quality,
                    "available": [f"{q}p" for q in available_qualities]
                }), 400
        else:
            default_quality = 1080
            picked_q = pick_default_quality(available_qualities, default_quality)
            target_res = avail_map[picked_q]
            
        download_quality = target_res.get("quality")

    # Get the download URL (with SSE task polling fallback if empty)
    download_url = target_res.get("download_url")
    if not download_url:
        resource_content = target_res.get("resource_content")
        if not resource_content:
            return jsonify({"error": "No download URL or resource content available for this format"}), 502
            
        download_api_url = 'https://api.vidssave.com/api/contentsite_api/media/download'
        download_payload = {
            'auth': '20250901majwlqo',
            'domain': 'api-ak.vidssave.com',
            'origin': 'source',
            'request': resource_content,
            'no_encrypt': 1
        }
        try:
            dl_res = requests.post(download_api_url, data=download_payload, headers=headers, proxies=proxies, timeout=12)
            dl_res.raise_for_status()
            task_id = dl_res.json().get("data", {}).get("task_id")
        except Exception as e:
            return jsonify({"error": "Failed to initiate download task", "details": str(e)}), 502
            
        if not task_id:
            return jsonify({"error": "Download task did not return a task ID"}), 502
            
        # Poll Server-Sent Events stream for completion
        sse_url = "https://api.vidssave.com/sse/contentsite_api/media/download_query"
        params = {
            'task_id': task_id,
            'download_domain': 'vidssave.com',
            'origin': 'content_site',
            'auth': '20250901majwlqo'
        }
        headers_sse = {
            'Accept': 'text/event-stream',
            **headers
        }
        
        try:
            sse_res = requests.get(sse_url, params=params, headers=headers_sse, stream=True, proxies=proxies, timeout=20)
            sse_res.raise_for_status()
            
            current_event = None
            resolved_link = None
            
            for line in sse_res.iter_lines():
                if line:
                    decoded = line.decode('utf-8').strip()
                    if decoded.startswith("event:"):
                        current_event = decoded.replace("event:", "").strip()
                    elif decoded.startswith("data:"):
                        data_str = decoded.replace("data:", "").strip()
                        if current_event == "success":
                            try:
                                data_json = json.loads(data_str)
                                resolved_link = data_json.get("download_link")
                            except:
                                pass
                            break
                        elif current_event == "failed":
                            break
                            
            if resolved_link:
                download_url = resolved_link
            else:
                return jsonify({"error": "Failed to retrieve download link from downstream conversion task"}), 502
        except Exception as e:
            return jsonify({"error": "Error while waiting for download link generation", "details": str(e)}), 502

    return jsonify({
        "Title": title,
        "Quality": download_quality,
        "Download Link": download_url,
        "Developer": "t.me/Sudhirxd",
        "Website": "www.sudhirxd.in",
        "Github": "www.github.com/sudheer729"
    })


@app.route("/info", methods=["GET"])
def info():
    yt_url = request.args.get("url")
    if not yt_url:
        return jsonify({"error": "Invalid parameters", "required": "url"}), 400

    video_id = extract_video_id(yt_url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL - couldn't extract video ID"}), 400

    full_yt_url = f"https://www.youtube.com/watch?v={video_id}"

    api_url = 'https://api.vidssave.com/api/contentsite_api/media/parse'
    payload = {
        'auth': '20250901majwlqo',
        'domain': 'api-ak.vidssave.com',
        'origin': 'source',
        'link': full_yt_url
    }
    headers = get_headers()
    proxies = get_proxies()

    try:
        api_res = requests.post(api_url, data=payload, headers=headers, proxies=proxies, timeout=15)
        api_res.raise_for_status()
        api_data = api_res.json()
    except Exception as e:
        return jsonify({
            "error": "Failed to fetch format details from backend",
            "details": str(e)
        }), 502

    if api_data.get("status") != 1 or "data" not in api_data:
        return jsonify({
            "error": "Downstream service returned error or invalid format information",
            "response": api_data
        }), 502

    video_data = api_data.get("data", {})
    
    # Filter out formats that do not have a download URL immediately available (empty)
    resources = video_data.get("resources", [])
    filtered_resources = [r for r in resources if r.get("download_url")]
    video_data["resources"] = filtered_resources
    
    # Recursively strip resource_content to keep the JSON output clean and lightweight
    strip_key(video_data, "resource_content")

    response_data = {
        "status": 1,
        "status_code": "success",
        "data": video_data,
        "Developer": "t.me/Sudhirxd",
        "Website": "www.sudhirxd.in",
        "Github": "www.github.com/sudheer729"
    }
    return jsonify(response_data)


# =========================
# RUN (TERMUX SAFE)
# =========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
