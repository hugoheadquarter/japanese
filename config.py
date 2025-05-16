# config.py
from pathlib import Path
import json

# This should match what setup_environment.py uses/creates
CONFIG_FILENAME = "app_config.json"

DEFAULT_CONFIG = {
    "app_name": "JapaneseLearnerApp",
    "base_app_data_dir": str(Path.home() / ".japaneselearnerapp_data"),
    "audio_root_dir_name": "audio_files",
    "db_filename": "learning_data.sqlite3",
    "deepgram_api_key": None, # Loaded from .env in app.py
    "openai_api_key": None    # Loaded from .env in app.py
}

def load_or_create_config():
    config_path = Path(CONFIG_FILENAME)
    if not config_path.exists():
        print(f"Warning: Configuration file {CONFIG_FILENAME} not found. Creating with default values.")
        print(f"Ensure setup_environment.py has been run to create directories and the database.")
        with open(config_path, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        app_cfg = DEFAULT_CONFIG
    else:
        with open(config_path, 'r') as f:
            app_cfg = json.load(f)
    return app_cfg

APP_CONFIG = load_or_create_config()

BASE_APP_DATA_DIR = Path(APP_CONFIG["base_app_data_dir"])
AUDIO_ROOT_DIR_NAME = APP_CONFIG["audio_root_dir_name"] # This is the name of the subfolder like "audio_files"
DB_FILENAME = APP_CONFIG["db_filename"]

DB_PATH = BASE_APP_DATA_DIR / DB_FILENAME
# This is the absolute path to the root directory where all audio (e.g. "audio_files/") is stored
AUDIO_FILES_STORAGE_ROOT_ABS_PATH = BASE_APP_DATA_DIR / AUDIO_ROOT_DIR_NAME

# Ensure these directories exist (setup_environment.py should do this, but good for safety)
BASE_APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_FILES_STORAGE_ROOT_ABS_PATH.mkdir(parents=True, exist_ok=True)

# API keys will be loaded from .env in the main app.py
# You could also store them in config.json if not using .env, but .env is generally safer.