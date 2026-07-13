# YouTube Downloader API (MP3 & MP4)

A highly robust Flask-based API that fetches YouTube video formats and generates instant download links (MP3/MP4) using reverse-engineered downstream APIs with built-in Cloudflare bypasses and anti-bot handshake resolution.

## Features

- **MP3 & MP4 Downloads**: Instantly download audio or video formats up to 1080p.
- **Proof-of-Work Bypass**: Resolves PoW security challenges dynamically to authenticate sessions.
- **HMAC Requests Signing**: Signs payloads on-the-fly to securely bypass anti-scraping protections.
- **Vercel Serverless Ready**: Completely optimized to deploy as a serverless function.

---

## API Documentation

### Get Video Download Link

- **Endpoint**: `/download`
- **Method**: `GET`
- **Query Parameters**:
  - `url` (required): The YouTube video URL (e.g. `https://www.youtube.com/watch?v=uYhaMScwCR0`).
  - `type` (required): Download format (`mp3` or `mp4`).
  - `quality` (optional): Requested quality (e.g. `1080p`, `720p`, `480p`, `360p`, `240p`, `144p` for video).

#### Example Request

```http
GET /download?url=https://www.youtube.com/watch?v=uYhaMScwCR0&type=mp4&quality=1080p
```

#### Example Response (Success 200 OK)

```json
{
  "Title": "Ethereal (Slowed)",
  "Quality": "1080p",
  "Download Link": "https://yt1s-worker-6.dlsrv.online/tunnel?id=...",
  "Developer": "t.me/Sudhirxd",
  "Website": "www.sudhirxd.in",
  "Github": "www.github.com/sudheer729"
}
```

---

## Deployment

### Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Start the local server:
   ```bash
   python yt.py
   ```

### Vercel Deployment

Deploy directly using Vercel CLI:
```bash
vercel
```

---

## Developer Info

- **Developer**: [Telegram](https://t.me/Sudhirxd)
- **Website**: [sudhirxd.in](http://www.sudhirxd.in)
- **GitHub**: [sudheer729](https://github.com/sudheer729)
