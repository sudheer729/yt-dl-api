# YouTube Downloader API 🚀

A lightning-fast, Vercel-friendly, lightweight, and pure Python YouTube extractor API powered by `yt-dlp` and `Flask`.

This API serves raw direct CDN URLs (no server-side storage, no heavy downloads, and **no FFmpeg binary required**). It solves the infamous "1080p separate video/audio" stream issue dynamically by serving separate URLs and instructing the client on merging them, while serving progressive streams (with audio baked in) for 360p, 480p, and 720p instantly.

---

## ✨ Features

- **⚡ Fast Extractor Options**: Bypasses heavy URL format validations (`check_formats=False`) to retrieve URLs up to 3x faster.
- **💾 In-Memory Caching**: Caches metadata and download links for 5 minutes (`CACHE_TTL`), avoiding hitting YouTube's rate limits and making subsequent requests instant.
- **🍪 Premium & Age-Restricted Support**:
  - **Local**: Drop a standard Netscape-formatted `cookies.txt` in the root folder.
  - **Live Browser**: Extract live cookies from your browser dynamically on request with `?browser=chrome`.
  - **Vercel / Cloud**: Set your cookies inside the `YOUTUBE_COOKIES` environment variable (the app writes it to `/tmp/cookies.txt` automatically).
- **☁️ Vercel Serverless Ready**: Zero file-writing dependency during requests, fully compatible with the read-only environment of Vercel.
- **🔊 Zero FFmpeg Requirement**: No binary installation needed on the host. Handles progressive stream extraction up to 720p natively, and provides separate paths for 1080p+ merging.

---

## 🛠️ Requirements

Install Python dependencies:
```bash
pip install -r requirements.txt
```

---

## 🚀 Local Run

Start the server:
```bash
python yt.py
```
The server will boot up by default on `http://localhost:5000`.

---

## 📡 API Endpoints

### 1. `GET /info`
Fetch video metadata, thumbnails, and clean tables of available progressive/DASH video formats and audio bitrates.

**Parameters**:
- `url` (Required): YouTube Video URL or video ID.
- `browser` (Optional): Extract cookies live from your browser (`chrome`, `firefox`, `edge`, `opera`, `brave`, `vivaldi`, `safari`, `chromium`).

**Example**:
`http://localhost:5000/info?url=dQw4w9WgXcQ`

---

### 2. `GET /download`
Retrieve direct CDN links for a video or audio stream.

**Parameters**:
- `url` (Required): YouTube Video URL or video ID.
- `type` (Optional): `'video'` (default) or `'audio'`.
- `quality` (Optional): `'360p'`, `'480p'`, `'720p'`, `'1080p'`, `'1440p'`, `'2160p'`, `'best'`.
- `browser` (Optional): Live browser cookie extraction.

#### 💡 How it handles audio:
1. **360p / 480p / 720p**: Resolves to a progressive stream. The JSON returns a single `video_url` with **audio already working** (`needs_merge: false`).
2. **1080p / 2K / 4K / 8K**: YouTube does not offer progressive formats at these heights. The JSON returns both `video_url` and `audio_url` with `needs_merge: true` so the client can merge them.

**Example**:
`http://localhost:5000/download?url=dQw4w9WgXcQ&quality=1080p`

---

### 3. `GET /cookie/status`
Debug endpoint to verify if cookies are successfully loaded from `cookies.txt` or Vercel's `YOUTUBE_COOKIES` environment variables.

---

## ☁️ Vercel Deployment

Deploy with one click using the Vercel CLI.

1. Create a `vercel.json` in the root directory:
```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/yt.py" }]
}
```
2. Export your YouTube cookies as a string using a browser extension (like "Get cookies.txt LOCALLY").
3. Set the environment variable on Vercel:
   - **Key**: `YOUTUBE_COOKIES`
   - **Value**: *(Paste the contents of your cookies.txt file)*
4. Run:
```bash
vercel --prod
```

---

## 👤 Developer
- **Telegram**: [Sudhirxd](https://t.me/Sudhirxd)
- **Website**: [sudhirxd.in](http://www.sudhirxd.in)
- **Github**: [sudheer729](https://www.github.com/sudheer729)
