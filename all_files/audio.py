# lib/audio.py
"""Audio processing: download, speed change, phrase clip extraction."""

import os
import shutil
from pathlib import Path
from pydub import AudioSegment


def download_audio(url: str, output_dir: Path) -> tuple[str | None, str | None]:
    """Download audio from YouTube URL. Returns (filepath, title) or (None, None)."""
    import yt_dlp

    output_dir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
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
        print(f"Download error: {e}")
        return None, None


def slow_down_audio(
    input_path: str, output_path: str, speed_factor: float = 0.75
) -> str | None:
    """Slow down audio using ffmpeg atempo filter.

    Handles speed factors below 0.5 by chaining atempo filters.
    Returns output path on success, None on failure.
    """
    try:
        inp = Path(input_path)
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        # Build atempo filter chain for factors < 0.5
        # atempo only supports 0.5-2.0, so chain multiple filters
        filters = []
        remaining = speed_factor
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={remaining}")
        filter_str = ",".join(filters)

        audio = AudioSegment.from_file(str(inp))
        temp_path = out.parent / f"_temp_{out.name}"
        audio.export(
            str(temp_path), format="mp3", parameters=["-filter:a", filter_str]
        )
        os.rename(str(temp_path), str(out))
        return str(out)
    except Exception as e:
        print(f"Slow down error: {e}")
        # Fallback: copy original
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

    Args:
        original_audio_path: Path to the original (non-slowed) full audio
        phrases_with_timings: List of (start_sec, end_sec) for each phrase
        output_dir: Directory to save phrase clips
        speed_factor: Speed factor for slowing
        segment_id: Used for naming files

    Returns:
        Dict mapping phrase_index -> filename (or None if failed)
    """
    result = {}
    if not os.path.exists(original_audio_path):
        return result

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        main_audio = AudioSegment.from_mp3(original_audio_path)

        for i, (start_s, end_s) in enumerate(phrases_with_timings):
            start_ms = int(start_s * 1000)
            end_ms = int(end_s * 1000)

            # Reduced padding: 50ms instead of 150ms to avoid overlap
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

            # Clean up temp
            try:
                os.remove(str(temp_fp))
            except OSError:
                pass

        return result
    except Exception as e:
        print(f"Phrase audio error S{segment_id}: {e}")
        return {i: None for i in range(len(phrases_with_timings))}
