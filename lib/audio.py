# lib/audio.py
"""Audio processing: download, speed change, phrase clip extraction.

All operations work on local temp files.  The caller (jp.py) is responsible
for uploading final outputs to Supabase Storage.

Download strategy (in order):
  1. RapidAPI youtube-mp36 – paid API with residential proxies, works everywhere
  2. Piped API             – free proxy (unreliable, most instances dead)
  3. Invidious API         – free proxy via ?local=true (also unreliable)
  4. yt-dlp                – works locally (residential IP not blocked)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from pydub import AudioSegment
import streamlit as st
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Piped instances (most are dead as of Feb 2026, but try anyway)
PIPED_INSTANCES = [
    "https://api.piped.private.coffee",
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.leptons.xyz",
    "https://pipedapi-libre.kavin.rocks",
    "https://pipedapi.adminforge.de",
]

# Invidious instances
INVIDIOUS_INSTANCES = [
    "https://yewtu.be",
    "https://vid.puffyan.us",
    "https://iv.ggtyler.dev",
    "https://invidious.nerdvpn.de",
    "https://invidious.lunar.icu",
    "https://invidious.protokolla.fi",
    "https://inv.tux.pizza",
    "https://invidious.private.coffee",
    "https://invidious.projectsegfau.lt",
    "https://inv.nadeko.net",
]


def _extract_video_id(url: str) -> str | None:
    """Pull the 11-char YouTube video ID from any common URL format."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:embed/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
        r"^([a-zA-Z0-9_-]{11})$",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def _get_rapidapi_key() -> str:
    """Get RapidAPI key from Streamlit Cloud secrets."""
    try:
        return st.secrets["RAPIDAPI_KEY"]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Method 1: RapidAPI youtube-mp36 (RECOMMENDED — works from datacenter IPs)
# ---------------------------------------------------------------------------

def _download_via_rapidapi(url: str, output_dir: Path) -> tuple[str | None, str | None]:
    """
    Download audio via RapidAPI youtube-mp36 service.

    Free tier: ~500 req/month.  Works from ANY IP including datacenter.
    API key stored in Streamlit Cloud secrets as RAPIDAPI_KEY.

    API: GET https://youtube-mp36.p.rapidapi.com/dl?id={videoId}
    Returns: { "status": "ok", "link": "https://...", "title": "..." }
    """
    api_key = _get_rapidapi_key()
    if not api_key:
        print("[rapidapi] No RAPIDAPI_KEY found in Streamlit secrets — skipping")
        print("[rapidapi] Add it in Streamlit Cloud: Settings → Secrets → RAPIDAPI_KEY = \"your-key\"")
        return None, None

    video_id = _extract_video_id(url)
    if not video_id:
        print("[rapidapi] Could not extract video ID")
        return None, None

    api_url = f"https://youtube-mp36.p.rapidapi.com/dl?id={video_id}"
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "youtube-mp36.p.rapidapi.com",
    }

    try:
        print(f"[rapidapi] Converting {video_id}...")
        resp = requests.get(api_url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Some videos need processing time — poll if needed
        if data.get("status") != "ok":
            msg = data.get("msg", "unknown error")
            print(f"[rapidapi] API response: {msg}")

            if "process" in str(msg).lower() or "progress" in str(msg).lower() or data.get("status") == "processing":
                for attempt in range(6):
                    print(f"[rapidapi] Still processing... waiting 5s ({attempt + 1}/6)")
                    time.sleep(5)
                    resp = requests.get(api_url, headers=headers, timeout=30)
                    data = resp.json()
                    if data.get("status") == "ok":
                        break
                else:
                    print("[rapidapi] Timed out waiting for conversion")
                    return None, None

        if data.get("status") != "ok":
            print(f"[rapidapi] Final status not ok: {data}")
            return None, None

        download_link = data.get("link")
        title = data.get("title", "video")

        if not download_link:
            print("[rapidapi] No download link in response")
            return None, None

        print(f"[rapidapi] Got MP3 link for: {title}")

        # Download the MP3 from the CDN
        safe_title = re.sub(r'[^\w\s\-]', '', title)[:80].strip() or "audio"
        mp3_path = output_dir / f"{safe_title}.mp3"

        # Download MP3 — retry with fresh link if CDN returns 404
        for dl_attempt in range(3):
            if dl_attempt > 0:
                print(f"[rapidapi] CDN failed, requesting fresh link (attempt {dl_attempt + 1}/3)...")
                time.sleep(3)
                resp = requests.get(api_url, headers=headers, timeout=30)
                data = resp.json()
                if data.get("status") == "ok" and data.get("link"):
                    download_link = data["link"]
                    print(f"[rapidapi] Got fresh link")
                else:
                    continue

            print(f"[rapidapi] Downloading MP3...")
            try:
                with requests.get(download_link, stream=True, timeout=180) as r:
                    if r.status_code == 404:
                        print(f"[rapidapi] CDN returned 404 — link expired")
                        continue
                    r.raise_for_status()
                    total = 0
                    with open(mp3_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=65536):
                            f.write(chunk)
                            total += len(chunk)
                print(f"[rapidapi] Downloaded {total / 1024 / 1024:.1f} MB")

                if mp3_path.exists() and mp3_path.stat().st_size > 10000:
                    print(f"[rapidapi] Success: {title}")
                    return str(mp3_path), title
                else:
                    print("[rapidapi] File too small or missing")
                    mp3_path.unlink(missing_ok=True)
                    continue
            except requests.exceptions.HTTPError as e:
                print(f"[rapidapi] Download HTTP error: {e}")
                continue

        print("[rapidapi] All download attempts failed")
        return None, None

    except Exception as e:
        print(f"[rapidapi] Error: {e}")
        return None, None


# ---------------------------------------------------------------------------
# Method 2: Piped API (free, but unreliable — most instances dead)
# ---------------------------------------------------------------------------

def _download_via_piped(url: str, output_dir: Path) -> tuple[str | None, str | None]:
    """Download audio via Piped API proxy."""
    video_id = _extract_video_id(url)
    if not video_id:
        print("[piped] Could not extract video ID")
        return None, None

    stream_data = None
    for instance in PIPED_INSTANCES:
        base = instance.rstrip("/")
        api_url = f"{base}/streams/{video_id}"
        try:
            print(f"[piped] Trying {instance}...")
            resp = requests.get(api_url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code == 200:
                data = resp.json()
                if data.get("audioStreams"):
                    stream_data = data
                    print(f"[piped] Got {len(data['audioStreams'])} audio streams from {instance}")
                    break
                else:
                    print(f"[piped] {instance} returned no audio streams")
            else:
                print(f"[piped] {instance} returned HTTP {resp.status_code}")
        except Exception as e:
            print(f"[piped] {instance} error: {e}")
            continue

    if not stream_data or not stream_data.get("audioStreams"):
        print("[piped] All Piped instances failed")
        return None, None

    title = stream_data.get("title", "video")
    audio_streams = stream_data["audioStreams"]
    audio_only = [s for s in audio_streams if not s.get("videoOnly", False)]
    if not audio_only:
        audio_only = audio_streams
    audio_only.sort(key=lambda s: s.get("bitrate", 0), reverse=True)
    best = audio_only[0]

    stream_url = best.get("url")
    mime_type = best.get("mimeType", "audio/mp4")
    print(f"[piped] Selected: {best.get('quality', '?')} | {mime_type}")

    if not stream_url:
        return None, None

    return _download_and_convert(stream_url, title, mime_type, output_dir, "piped")


# ---------------------------------------------------------------------------
# Method 3: Invidious API (free, unreliable)
# ---------------------------------------------------------------------------

def _download_via_invidious(url: str, output_dir: Path) -> tuple[str | None, str | None]:
    """Download audio via Invidious API with ?local=true for proxied streams."""
    video_id = _extract_video_id(url)
    if not video_id:
        return None, None

    for instance in INVIDIOUS_INSTANCES:
        base = instance.rstrip("/")
        api_url = f"{base}/api/v1/videos/{video_id}?local=true"
        try:
            print(f"[invidious] Trying {instance}...")
            resp = requests.get(api_url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code == 200:
                data = resp.json()
                title = data.get("title", "video")
                adaptive = data.get("adaptiveFormats", [])
                audio_formats = [f for f in adaptive if f.get("type", "").startswith("audio/")]

                if not audio_formats:
                    print(f"[invidious] {instance} returned no audio formats")
                    continue

                # Prefer itag 251 (opus ~160k) > 140 (m4a 128k)
                best_format = None
                for itag in [251, 140, 250, 249]:
                    for f in audio_formats:
                        if str(f.get("itag")) == str(itag):
                            best_format = f
                            break
                    if best_format:
                        break
                if not best_format:
                    audio_formats.sort(
                        key=lambda f: int(f.get("bitrate", 0) if not isinstance(f.get("bitrate"), str) else f.get("bitrate", "0")),
                        reverse=True,
                    )
                    best_format = audio_formats[0]

                fmt_url = best_format.get("url")
                if not fmt_url:
                    continue
                if fmt_url.startswith("/"):
                    fmt_url = f"{base}{fmt_url}"

                mime_type = best_format.get("type", "audio/mp4").split(";")[0]
                print(f"[invidious] Selected: itag={best_format.get('itag')} | {mime_type}")
                return _download_and_convert(fmt_url, title, mime_type, output_dir, "invidious")
            else:
                print(f"[invidious] {instance} returned HTTP {resp.status_code}")
        except Exception as e:
            print(f"[invidious] {instance} error: {e}")
            continue

    print("[invidious] All Invidious instances failed")
    return None, None


# ---------------------------------------------------------------------------
# Shared download + convert helper
# ---------------------------------------------------------------------------

def _download_and_convert(
    stream_url: str, title: str, mime_type: str, output_dir: Path, source: str,
) -> tuple[str | None, str | None]:
    """Download a stream URL and convert to MP3."""
    ext = "m4a"
    if "webm" in mime_type or "opus" in mime_type:
        ext = "webm"
    elif "ogg" in mime_type:
        ext = "ogg"

    safe_title = re.sub(r'[^\w\s\-]', '', title)[:80].strip() or "audio"
    raw_path = output_dir / f"{safe_title}.{ext}"
    mp3_path = output_dir / f"{safe_title}.mp3"

    try:
        print(f"[{source}] Downloading audio stream...")
        with requests.get(stream_url, stream=True, timeout=180, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }) as r:
            r.raise_for_status()
            total = 0
            with open(raw_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
                    total += len(chunk)
        print(f"[{source}] Downloaded {total / 1024 / 1024:.1f} MB")
    except Exception as e:
        print(f"[{source}] Download error: {e}")
        raw_path.unlink(missing_ok=True)
        return None, None

    if raw_path.stat().st_size < 10000:
        print(f"[{source}] File too small, likely error page")
        raw_path.unlink(missing_ok=True)
        return None, None

    # Convert to MP3
    try:
        print(f"[{source}] Converting to MP3...")
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(raw_path), "-vn",
             "-acodec", "libmp3lame", "-ab", "192k", "-ar", "44100",
             str(mp3_path)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            try:
                audio = AudioSegment.from_file(str(raw_path))
                audio.export(str(mp3_path), format="mp3", bitrate="192k")
            except Exception:
                return None, None
    except Exception:
        return None, None
    finally:
        raw_path.unlink(missing_ok=True)

    if mp3_path.exists() and mp3_path.stat().st_size > 1000:
        return str(mp3_path), title
    return None, None


# ---------------------------------------------------------------------------
# Method 4: yt-dlp fallback (local/residential IP only)
# ---------------------------------------------------------------------------

def _download_via_ytdlp(url: str, output_dir: Path) -> tuple[str | None, str | None]:
    """Download audio via yt-dlp (works on residential IPs)."""
    import yt_dlp

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
        "verbose": False,
        "noplaylist": True,
        "nocheckcertificate": True,
        "retries": 10,
        "fragment_retries": 10,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video")
            mp3_files = list(output_dir.glob("*.mp3"))
            if not mp3_files:
                return None, None
            filepath = max(mp3_files, key=os.path.getctime)
            return str(filepath), title
    except Exception as e:
        print(f"[yt-dlp] Download error: {e}")
        return None, None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def download_audio(url: str, output_dir: Path) -> tuple[str | None, str | None]:
    """Download audio from YouTube URL.  Returns (filepath, title) or (None, None).

    Strategy:
      1. RapidAPI youtube-mp36 (paid, works everywhere)
      2. Piped API (free, unreliable)
      3. Invidious API (free, unreliable)
      4. yt-dlp (local/residential IP only)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. RapidAPI (best option for cloud) ---
    print("[download] Trying RapidAPI...")
    filepath, title = _download_via_rapidapi(url, output_dir)
    if filepath:
        print(f"[download] RapidAPI succeeded: {title}")
        return filepath, title

    # --- 2. Piped API ---
    print("[download] Trying Piped API...")
    filepath, title = _download_via_piped(url, output_dir)
    if filepath:
        print(f"[download] Piped API succeeded: {title}")
        return filepath, title

    # --- 3. Invidious API ---
    print("[download] Trying Invidious API...")
    filepath, title = _download_via_invidious(url, output_dir)
    if filepath:
        print(f"[download] Invidious API succeeded: {title}")
        return filepath, title

    # --- 4. yt-dlp fallback ---
    print("[download] Trying yt-dlp...")
    filepath, title = _download_via_ytdlp(url, output_dir)
    if filepath:
        print(f"[download] yt-dlp succeeded: {title}")
        return filepath, title

    print("[download] All download methods failed")
    return None, None


# ---------------------------------------------------------------------------
# Audio processing utilities (unchanged)
# ---------------------------------------------------------------------------

def slow_down_audio(
    input_path: str, output_path: str, speed_factor: float = 0.75
) -> str | None:
    """Slow down audio using ffmpeg atempo filter.  Returns output path or None."""
    try:
        inp = Path(input_path)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        filters = []
        remaining = speed_factor
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={remaining}")
        filter_str = ",".join(filters)

        audio = AudioSegment.from_file(str(inp))
        temp_path = out.parent / f"_temp_{out.name}"
        audio.export(str(temp_path), format="mp3", parameters=["-filter:a", filter_str])
        os.rename(str(temp_path), str(out))
        return str(out)
    except Exception as e:
        print(f"Slow down error: {e}")
        if os.path.exists(input_path):
            shutil.copy(input_path, output_path)
            return output_path
        return None


def create_phrase_audio_clips(
    original_audio_path: str,
    phrases_with_timings: list[tuple[float, float]],
    output_dir: Path,
    speed_factor: float,
    segment_id: int,
) -> dict[int, str | None]:
    """Extract and slow down audio clips for each phrase."""
    result: dict[int, str | None] = {}
    if not os.path.exists(original_audio_path):
        return result

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        main_audio = AudioSegment.from_mp3(original_audio_path)

        for i, (start_s, end_s) in enumerate(phrases_with_timings):
            start_ms = int(start_s * 1000)
            end_ms = int(end_s * 1000)
            start_ms = max(0, start_ms - 50)
            end_ms = min(len(main_audio), end_ms + 50)

            if start_ms >= end_ms:
                result[i] = None
                continue

            clip = main_audio[start_ms:end_ms]
            temp_fn = f"_temp_S{segment_id}_P{i}.mp3"
            temp_fp = output_dir / temp_fn
            clip.export(str(temp_fp), format="mp3")

            final_fn = f"phrase_S{segment_id}_P{i}.mp3"
            final_fp = output_dir / final_fn
            slowed = slow_down_audio(str(temp_fp), str(final_fp), speed_factor)
            result[i] = final_fn if slowed else None

            try:
                os.remove(str(temp_fp))
            except OSError:
                pass

        return result
    except Exception as e:
        print(f"Phrase audio error S{segment_id}: {e}")
        return {i: None for i in range(len(phrases_with_timings))}