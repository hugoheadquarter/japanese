from pathlib import Path
MEDIA_ROOT = Path(__file__).resolve().parents[2] / "media"
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
