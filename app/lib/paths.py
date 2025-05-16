from pathlib import Path
from .settings import MEDIA_ROOT

def path_full(yt_id: str) -> Path:
    return MEDIA_ROOT / yt_id / "full_0.75.mp3"

def path_seg(yt_id: str, seg_idx: int) -> Path:
    return MEDIA_ROOT / yt_id / f"seg_{seg_idx}.mp3"

def path_phr(yt_id: str, seg_idx: int, phr_idx: int) -> Path:
    return MEDIA_ROOT / yt_id / f"phr_{seg_idx}_{phr_idx}.mp3"
