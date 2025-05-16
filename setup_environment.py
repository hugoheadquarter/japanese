import sqlite3
import os
from pathlib import Path
import json # If you decide to use a JSON config file

# --- Configuration (Option 1: Defined directly in the script) ---
APP_NAME = "JapaneseLearnerApp"
BASE_APP_DATA_DIR_DEFAULT = Path.home() / f".{APP_NAME.lower()}_data"
AUDIO_ROOT_DIR_NAME_DEFAULT = "audio_files"
DB_FILENAME_DEFAULT = "learning_data.sqlite3"

# --- Configuration (Option 2: Load from a JSON file) ---
# CONFIG_FILENAME = "config.json"
# DEFAULT_CONFIG = {
#     "app_name": "JapaneseLearnerApp",
#     "base_app_data_dir": str(Path.home() / ".japaneslearnerapp_data"), # Store as string in JSON
#     "audio_root_dir_name": "audio_files",
#     "db_filename": "learning_data.sqlite3"
# }

# def load_or_create_config(config_path):
#     if not config_path.exists():
#         with open(config_path, 'w') as f:
#             json.dump(DEFAULT_CONFIG, f, indent=4)
#         print(f"Created default configuration file: {config_path}")
#         return DEFAULT_CONFIG
#     else:
#         with open(config_path, 'r') as f:
#             return json.load(f)

def get_app_paths(base_dir_str, audio_root_name, db_name):
    """Helper to derive all necessary paths from base config."""
    base_dir = Path(base_dir_str)
    db_path = base_dir / db_name
    audio_files_base_path = base_dir / audio_root_name
    return {
        "base_app_data_dir": base_dir,
        "db_path": db_path,
        "audio_files_base_path": audio_files_base_path
    }

def create_directories(paths_dict):
    """Creates the base application data directory and the audio root directory."""
    try:
        paths_dict["base_app_data_dir"].mkdir(parents=True, exist_ok=True)
        print(f"Ensured base data directory exists: {paths_dict['base_app_data_dir']}")
        paths_dict["audio_files_base_path"].mkdir(parents=True, exist_ok=True)
        print(f"Ensured audio files directory exists: {paths_dict['audio_files_base_path']}")
    except OSError as e:
        print(f"Error creating directories: {e}")
        raise

def initialize_database(db_path):
    """Creates the database and tables if they don't exist."""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print(f"Connected to database: {db_path}")

        # Videos Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            youtube_url TEXT UNIQUE NOT NULL,
            video_title TEXT,
            video_data_directory TEXT UNIQUE,
            full_slowed_audio_path TEXT,
            full_words_for_sync_json TEXT,
            raw_deepgram_response_json TEXT,
            full_transcript_text TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")

        # Segments Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS Segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            segment_index INTEGER NOT NULL,
            text TEXT,
            start_time REAL,
            end_time REAL,
            deepgram_segment_words_json TEXT,
            FOREIGN KEY (video_id) REFERENCES Videos(id) ON DELETE CASCADE,
            UNIQUE (video_id, segment_index)
        )""")

        # GptPhraseAnalyses Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS GptPhraseAnalyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_id INTEGER NOT NULL,
            phrase_index_in_segment INTEGER NOT NULL,
            gpt_phrase_json TEXT NOT NULL,
            phrase_slowed_audio_path TEXT,
            phrase_words_for_sync_json TEXT,
            FOREIGN KEY (segment_id) REFERENCES Segments(id) ON DELETE CASCADE,
            UNIQUE (segment_id, phrase_index_in_segment)
        )""")

        # KanjiEntries Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS KanjiEntries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER NOT NULL,
            character TEXT NOT NULL,
            reading TEXT,
            meaning TEXT,
            FOREIGN KEY (video_id) REFERENCES Videos(id) ON DELETE CASCADE,
            UNIQUE (video_id, character)
        )""")

        conn.commit()
        print("Database tables ensured.")
    except sqlite3.Error as e:
        print(f"Database error during initialization: {e}")
        raise
    finally:
        if conn:
            conn.close()

def main():
    print("Setting up environment for Japanese Learner App...")

    # Option 1: Use hardcoded defaults
    base_dir_to_use = BASE_APP_DATA_DIR_DEFAULT
    audio_root_name_to_use = AUDIO_ROOT_DIR_NAME_DEFAULT
    db_filename_to_use = DB_FILENAME_DEFAULT

    # Option 2: Use config file (Uncomment and adapt if you choose this)
    # config_file_path = Path(CONFIG_FILENAME)
    # config = load_or_create_config(config_file_path)
    # base_dir_to_use = Path(config["base_app_data_dir"])
    # audio_root_name_to_use = config["audio_root_dir_name"]
    # db_filename_to_use = config["db_filename"]

    app_paths = get_app_paths(base_dir_to_use, audio_root_name_to_use, db_filename_to_use)

    create_directories(app_paths)
    initialize_database(app_paths["db_path"])

    print("-" * 30)
    print("Environment setup complete.")
    print(f"  Base Data Directory: {app_paths['base_app_data_dir']}")
    print(f"  Audio Files Root:    {app_paths['audio_files_base_path']}")
    print(f"  Database File:       {app_paths['db_path']}")
    print("-" * 30)
    print("You can now run the main Streamlit application.")

if __name__ == "__main__":
    main()