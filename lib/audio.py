# lib/audio.pyy
"""Audio processing: download, speed change, phrase clip extraction.

All operations work on local temp files.  The caller (jp.py) is responsible
for uploading final outputs to Supabase Storage.

Download strategy (in order):
  1. Piped API     – proxied streams bypass YouTube IP blocks
  2. Invidious API – proxied streams via ?local=true
  3. yt-dlp        – works locally (residential IP not blocked)
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from pydub import AudioSegment

# ---------------------------------------------------------------------------
# Instance lists – order matters, try most reliable first
# ---------------------------------------------------------------------------

PIPED_INSTANCES = [
    # --- CONFIRMED ALIVE (from piped-instances.kavin.rocks) ---
    "https://api.piped.private.coffee",
    # --- Others to try (may come back online) ---
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.leptons.xyz",
    "https://pipedapi-libre.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://api.piped.yt",
    "https://pipedapi.nosebs.ru",
    "https://pipedapi.r4fo.com",
]

INVIDIOUS_INSTANCES = [
    "https://yewtu.be",
    "https://vid.puffyan.us",
    "https://invidious.nerdvpn.de",
    "https://iv.ggtyler.dev",
    "https://invidious.privacydev.net",
    "https://invidious.lunar.icu",
    "https://invidious.protokolla.fi",
    "https://inv.tux.pizza",
    "https://invidious.private.coffee",
    "https://invidious.flokinet.to",
    "https://invidious.projectsegfau.lt",
    "https://invidious.slipfox.xyz",
    "https://vid.priv.au",
    "https://iv.melmac.space",
    "https://inv.zzls.xyz",
    "https://invidious.no-logs.com",
    "https://invidious.io.lol",
    "https://yt.artemislena.eu",
    "https://invidious.asir.dev",
    "https://iv.nboeck.de",
    "https://yt.drgnz.club",
    "https://inv.nadeko.net",
    "https://invidious.jing.rocks",
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


# ---------------------------------------------------------------------------
# Piped API downloader
# ---------------------------------------------------------------------------

def _download_via_piped(url: str, output_dir: Path) -> tuple[str | None, str | None]:
    """
    Download audio via Piped API.

    1. Call /streams/{videoId} on a Piped instance
    2. Pick the best audio stream from the response
    3. Download the proxied audio URL (goes through Piped's proxy, NOT YouTube)
    4. Convert to MP3 with ffmpeg
    """
    import requests

    video_id = _extract_video_id(url)
    if not video_id:
        print("[piped] Could not extract video ID")
        return None, None

    stream_data = None
    for instance in PIPED_INSTANCES:
        # CRITICAL: ensure proper URL construction with /
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

    # Pick best audio stream (highest bitrate)
    audio_streams = stream_data["audioStreams"]
    audio_only = [s for s in audio_streams if not s.get("videoOnly", False)]
    if not audio_only:
        audio_only = audio_streams

    audio_only.sort(key=lambda s: s.get("bitrate", 0), reverse=True)
    best = audio_only[0]

    stream_url = best.get("url")
    mime_type = best.get("mimeType", "audio/mp4")
    quality = best.get("quality", "unknown")
    print(f"[piped] Selected: {quality} | {mime_type} | bitrate={best.get('bitrate', '?')}")

    if not stream_url:
        print("[piped] No URL in selected stream")
        return None, None

    return _download_and_convert(stream_url, title, mime_type, output_dir, "piped")


# ---------------------------------------------------------------------------
# Invidious API downloader
# ---------------------------------------------------------------------------

def _download_via_invidious(url: str, output_dir: Path) -> tuple[str | None, str | None]:
    """
    Download audio via Invidious API with ?local=true for proxied streams.

    1. Call /api/v1/videos/{videoId}?local=true on an Invidious instance
    2. The response includes adaptiveFormats with proxied URLs
    3. Pick best audio format (itag 140=m4a 128k, 251=webm/opus 160k)
    4. Download from the proxied URL
    """
    import requests

    video_id = _extract_video_id(url)
    if not video_id:
        print("[invidious] Could not extract video ID")
        return None, None

    stream_url = None
    title = "video"
    mime_type = "audio/mp4"

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

                # Get audio formats from adaptiveFormats
                adaptive = data.get("adaptiveFormats", [])
                audio_formats = [
                    f for f in adaptive
                    if f.get("type", "").startswith("audio/")
                ]

                if not audio_formats:
                    print(f"[invidious] {instance} returned no audio formats")
                    continue

                # Prefer itag 251 (opus ~160k) > 140 (m4a 128k) > others
                preferred_itags = [251, 140, 250, 249]
                best_format = None
                for itag in preferred_itags:
                    for f in audio_formats:
                        if f.get("itag") == str(itag) or f.get("itag") == itag:
                            best_format = f
                            break
                    if best_format:
                        break

                if not best_format:
                    # Fall back to highest bitrate
                    audio_formats.sort(
                        key=lambda f: int(f.get("bitrate", "0") if isinstance(f.get("bitrate"), str) else f.get("bitrate", 0)),
                        reverse=True,
                    )
                    best_format = audio_formats[0]

                fmt_url = best_format.get("url")
                if not fmt_url:
                    print(f"[invidious] {instance} format has no URL")
                    continue

                # If URL is relative, prepend instance base
                if fmt_url.startswith("/"):
                    fmt_url = f"{base}{fmt_url}"

                stream_url = fmt_url
                mime_type = best_format.get("type", "audio/mp4").split(";")[0]
                quality = best_format.get("bitrate", "?")
                print(f"[invidious] Selected: itag={best_format.get('itag')} | {mime_type} | bitrate={quality}")
                break
            else:
                print(f"[invidious] {instance} returned HTTP {resp.status_code}")
        except Exception as e:
            print(f"[invidious] {instance} error: {e}")
            continue

    if not stream_url:
        print("[invidious] All Invidious instances failed")
        return None, None

    return _download_and_convert(stream_url, title, mime_type, output_dir, "invidious")


# ---------------------------------------------------------------------------
# Shared download + convert logic
# ---------------------------------------------------------------------------

def _download_and_convert(
    stream_url: str,
    title: str,
    mime_type: str,
    output_dir: Path,
    source: str,
) -> tuple[str | None, str | None]:
    """Download a stream URL and convert to MP3."""
    import requests

    # Determine file extension from mime type
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
        # Clean up partial file
        try:
            raw_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None, None

    # Check we actually got audio data (not an error page)
    if raw_path.stat().st_size < 10000:
        print(f"[{source}] Downloaded file too small ({raw_path.stat().st_size} bytes), likely error page")
        try:
            raw_path.unlink(missing_ok=True)
        except Exception:
            pass
        return None, None

    # Convert to MP3 using ffmpeg
    try:
        print(f"[{source}] Converting to MP3...")
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(raw_path),
                "-vn",
                "-acodec", "libmp3lame",
                "-ab", "192k",
                "-ar", "44100",
                str(mp3_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            print(f"[{source}] ffmpeg error: {result.stderr[:500]}")
            try:
                audio = AudioSegment.from_file(str(raw_path))
                audio.export(str(mp3_path), format="mp3", bitrate="192k")
                print(f"[{source}] Converted via pydub fallback")
            except Exception as e2:
                print(f"[{source}] pydub fallback also failed: {e2}")
                return None, None
        else:
            print(f"[{source}] MP3 conversion complete")
    except Exception as e:
        print(f"[{source}] Conversion error: {e}")
        return None, None
    finally:
        try:
            raw_path.unlink(missing_ok=True)
        except Exception:
            pass

    if mp3_path.exists() and mp3_path.stat().st_size > 1000:
        return str(mp3_path), title
    else:
        print(f"[{source}] Output file missing or too small")
        return None, None


# ---------------------------------------------------------------------------
# yt-dlp fallback
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
      1. Try Piped API (proxied streams bypass YouTube IP blocks)
      2. Try Invidious API (proxied streams via ?local=true)
      3. Fall back to yt-dlp (works locally with residential IP)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Try Piped API first ---
    print("[download] Trying Piped API...")
    filepath, title = _download_via_piped(url, output_dir)
    if filepath:
        print(f"[download] Piped API succeeded: {title}")
        return filepath, title

    # --- 2. Try Invidious API ---
    print("[download] Piped failed, trying Invidious API...")
    filepath, title = _download_via_invidious(url, output_dir)
    if filepath:
        print(f"[download] Invidious API succeeded: {title}")
        return filepath, title

    # --- 3. Fall back to yt-dlp ---
    print("[download] Invidious failed, trying yt-dlp...")
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

        # atempo only supports 0.5-2.0 — chain filters for lower values
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
    """Extract and slow down audio clips for each phrase.

    Returns dict mapping phrase_index -> local filename (or None if failed).
    Files are written to *output_dir*.
    """
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