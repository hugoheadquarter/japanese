# setup_environment.py
import sqlite3
from pathlib import Path
from config import DB_PATH, AUDIO_FILES_STORAGE_ROOT_ABS_PATH, BASE_APP_DATA_DIR


def create_directories():
    """Creates the base application data directory and audio root directory."""
    BASE_APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Ensured base data directory: {BASE_APP_DATA_DIR}")
    AUDIO_FILES_STORAGE_ROOT_ABS_PATH.mkdir(parents=True, exist_ok=True)
    print(f"Ensured audio directory: {AUDIO_FILES_STORAGE_ROOT_ABS_PATH}")


def initialize_database():
    """Creates the database and tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")

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
    conn.close()
    print(f"Database initialized: {DB_PATH}")


def main():
    print("Setting up environment...")
    create_directories()
    initialize_database()
    print("Setup complete.")


if __name__ == "__main__":
    main()
