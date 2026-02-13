# lib/audio.py
"""Audio processing: download, speed change, phrase clip extraction.

All operations work on local temp files.  The caller (jp.py) is responsible
for uploading final outputs to Supabase Storage.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from pydub import AudioSegment


def download_audio(url: str, output_dir: Path) -> tuple[str | None, str | None]:
    """Download audio from YouTube URL. Tries pybalt (cobalt) first, falls back to yt-dlp."""
    import yt_dlp

    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Get title via yt-dlp metadata (always works, even on cloud) ---
    title = "video"
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get("title", "video")
    except Exception as e:
        print(f"[meta] Title extraction failed: {e}")

    # --- Try pybalt (cobalt instances) first ---
    try:
        import asyncio
        from pybalt import download as pybalt_download

        async def _download():
            return await pybalt_download(
                url,
                downloadMode="audio",
                audioFormat="mp3",
                audioBitrate="192",
                filepath=str(output_dir),
            )

        loop = asyncio.new_event_loop()
        file_path = loop.run_until_complete(_download())
        loop.close()

        if file_path and os.path.exists(file_path):
            # Rename to match expected title-based naming
            safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:80]
            target = output_dir / f"{safe_title}.mp3"
            if str(file_path) != str(target):
                os.rename(file_path, str(target))
            print(f"[pybalt] Downloaded: {target.name}")
            return str(target), title
        else:
            print(f"[pybalt] No file returned")
    except Exception as e:
        print(f"[pybalt] Error: {e}")

    # --- Fallback to yt-dlp ---
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
        "source_address": "0.0.0.0",
        "extractor_args": {
            "youtube": {
                "player_client": ["android_vr", "web"],
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        },
        "sleep_interval": 3,
        "max_sleep_interval": 6,
        "format_sort": ["proto:m3u8"],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", title)
            mp3_files = list(output_dir.glob("*.mp3"))
            if not mp3_files:
                return None, None
            filepath = max(mp3_files, key=os.path.getctime)
            return str(filepath), title
    except Exception as e:
        print(f"[yt-dlp] Download error: {e}")
        return None, None


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
