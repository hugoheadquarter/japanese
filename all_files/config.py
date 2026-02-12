# config.py
from pathlib import Path
import json

CONFIG_FILENAME = "app_config.json"

DEFAULT_CONFIG = {
    "app_name": "JapaneseLearnerApp",
    "base_app_data_dir": str(Path.home() / ".japaneselearnerapp_data"),
    "audio_root_dir_name": "audio_files",
    "db_filename": "learning_data.sqlite3",
}


def load_or_create_config():
    config_path = Path(CONFIG_FILENAME)
    if not config_path.exists():
        with open(config_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return dict(DEFAULT_CONFIG)
    with open(config_path, "r") as f:
        return json.load(f)


APP_CONFIG = load_or_create_config()

BASE_APP_DATA_DIR = Path(APP_CONFIG["base_app_data_dir"])
AUDIO_ROOT_DIR_NAME = APP_CONFIG["audio_root_dir_name"]
DB_FILENAME = APP_CONFIG["db_filename"]

DB_PATH = BASE_APP_DATA_DIR / DB_FILENAME
AUDIO_FILES_STORAGE_ROOT_ABS_PATH = BASE_APP_DATA_DIR / AUDIO_ROOT_DIR_NAME

# The static directory Streamlit will serve at /_app/static/
# We symlink or point this to the audio root so files are accessible via URL.
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Ensure directories exist
BASE_APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_FILES_STORAGE_ROOT_ABS_PATH.mkdir(parents=True, exist_ok=True)

# Create symlink: ./static -> audio storage root
# This lets Streamlit serve audio at /_app/static/video_X/file.mp3
if not STATIC_DIR.exists():
    try:
        STATIC_DIR.symlink_to(AUDIO_FILES_STORAGE_ROOT_ABS_PATH)
    except OSError:
        # Fallback: if symlink fails (Windows), just use the path directly
        STATIC_DIR = AUDIO_FILES_STORAGE_ROOT_ABS_PATH
