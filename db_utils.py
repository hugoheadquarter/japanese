# db_utils.py
import sqlite3
import json
import os
from config import DATABASE_PATH # Import the DATABASE_PATH

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row # Access columns by name
    return conn

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Enable Foreign Key support
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Videos Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS Videos (
        video_id INTEGER PRIMARY KEY AUTOINCREMENT,
        youtube_url TEXT UNIQUE NOT NULL,
        video_title TEXT,
        download_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        original_audio_path TEXT, -- Relative to AUDIO_DATA_ROOT_PATH
        slowed_audio_path TEXT,   -- Relative to AUDIO_DATA_ROOT_PATH
        deepgram_transcript_json TEXT,
        full_plain_transcript TEXT,
        processing_status TEXT DEFAULT 'pending' -- e.g., pending, transcribed, analyzed, complete, error
    );
    """)

    # TranscriptSegments Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS TranscriptSegments (
        segment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL,
        segment_index INTEGER NOT NULL, -- 0-based index within the video
        text_content TEXT,
        start_time_original REAL, -- From original Deepgram transcript
        end_time_original REAL,   -- From original Deepgram transcript
        words_json TEXT,          -- JSON of Deepgram words for this segment
        gpt_analysis_json TEXT,   -- Full GPT JSON for this segment
        -- slowed_segment_audio_path TEXT, -- Decided to focus on phrase players, can add if needed
        FOREIGN KEY (video_id) REFERENCES Videos (video_id) ON DELETE CASCADE,
        UNIQUE (video_id, segment_index)
    );
    """)

    # AnalyzedPhrases Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS AnalyzedPhrases (
        phrase_id INTEGER PRIMARY KEY AUTOINCREMENT,
        segment_id INTEGER NOT NULL,
        phrase_index_in_segment INTEGER NOT NULL, -- 0-based index within its segment's GPT analysis
        text TEXT,
        meaning_korean TEXT, -- Korean translation of the phrase
        start_time_aligned REAL,
        end_time_aligned REAL,
        match_score REAL,
        slowed_phrase_audio_path TEXT, -- Relative to AUDIO_DATA_ROOT_PATH
        words_for_sync_json TEXT,      -- JSON for synchronized player (relative to phrase start)
        FOREIGN KEY (segment_id) REFERENCES TranscriptSegments (segment_id) ON DELETE CASCADE,
        UNIQUE (segment_id, phrase_index_in_segment)
    );
    """)

    # PhraseWords Table (Breakdown of words within each analyzed phrase)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS PhraseWords (
        word_id INTEGER PRIMARY KEY AUTOINCREMENT,
        phrase_id INTEGER NOT NULL,
        word_index_in_phrase INTEGER NOT NULL, -- Order of the word in the phrase
        japanese TEXT,
        kanji_chars TEXT,
        romaji TEXT,
        meaning_korean TEXT, -- Korean meaning/explanation of the word
        FOREIGN KEY (phrase_id) REFERENCES AnalyzedPhrases (phrase_id) ON DELETE CASCADE,
        UNIQUE (phrase_id, word_index_in_phrase)
    );
    """)

    # PhraseKanji Table (Kanji explanations for each phrase)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS PhraseKanji (
        phrase_kanji_id INTEGER PRIMARY KEY AUTOINCREMENT,
        phrase_id INTEGER NOT NULL,
        kanji_char TEXT NOT NULL,
        reading TEXT,
        meaning_korean_desc TEXT,
        meaning_hanja_char TEXT,
        FOREIGN KEY (phrase_id) REFERENCES AnalyzedPhrases (phrase_id) ON DELETE CASCADE,
        UNIQUE (phrase_id, kanji_char, reading) -- A kanji might appear multiple times in a phrase if different readings, but usually not. This is a reasonable constraint.
    );
    """)

    # GlobalKanji Table (For the "Kanji" tab, unique Kanji per video)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS GlobalKanji (
        global_kanji_id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL,
        kanji_char TEXT NOT NULL,
        reading TEXT, -- Representative reading for this kanji in this video
        meaning_korean_desc TEXT,
        meaning_hanja_char TEXT,
        FOREIGN KEY (video_id) REFERENCES Videos (video_id) ON DELETE CASCADE,
        UNIQUE (video_id, kanji_char) -- Ensures one entry per Kanji char per video
    );
    """)

    conn.commit()
    conn.close()
    print("Database initialized and tables created (if they didn't exist).")

# --- Insertion Functions ---

def add_video(youtube_url, video_title):
    """Adds a new video entry or returns existing video_id if URL matches."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO Videos (youtube_url, video_title, processing_status)
        VALUES (?, ?, 'pending')
        """, (youtube_url, video_title))
        video_id = cursor.lastrowid
        conn.commit()
        print(f"Added new video: ID {video_id}, URL: {youtube_url}")
        return video_id, "new"
    except sqlite3.IntegrityError: # youtube_url is UNIQUE
        conn.rollback()
        cursor.execute("SELECT video_id FROM Videos WHERE youtube_url = ?", (youtube_url,))
        result = cursor.fetchone()
        video_id = result['video_id'] if result else None
        print(f"Video already exists: ID {video_id}, URL: {youtube_url}")
        return video_id, "exists"
    finally:
        conn.close()

def update_video_paths(video_id, original_audio_path=None, slowed_audio_path=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if original_audio_path:
        cursor.execute("UPDATE Videos SET original_audio_path = ? WHERE video_id = ?", (original_audio_path, video_id))
    if slowed_audio_path:
        cursor.execute("UPDATE Videos SET slowed_audio_path = ? WHERE video_id = ?", (slowed_audio_path, video_id))
    conn.commit()
    conn.close()
    print(f"Updated paths for video ID {video_id}")

def update_video_transcript_data(video_id, deepgram_json_str, full_plain_transcript_str, status='transcribed'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE Videos SET deepgram_transcript_json = ?, full_plain_transcript = ?, processing_status = ?
    WHERE video_id = ?
    """, (deepgram_json_str, full_plain_transcript_str, status, video_id))
    conn.commit()
    conn.close()
    print(f"Updated transcript data for video ID {video_id}, status: {status}")

def update_video_status(video_id, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE Videos SET processing_status = ? WHERE video_id = ?", (status, video_id))
    conn.commit()
    conn.close()
    print(f"Updated status for video ID {video_id} to {status}")

def add_transcript_segment(video_id, segment_index, text_content, start_time, end_time, words_json_str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO TranscriptSegments (video_id, segment_index, text_content, start_time_original, end_time_original, words_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (video_id, segment_index, text_content, start_time, end_time, words_json_str))
        segment_id = cursor.lastrowid
        conn.commit()
        return segment_id
    except sqlite3.IntegrityError: # (video_id, segment_index) UNIQUE
        conn.rollback()
        cursor.execute("SELECT segment_id FROM TranscriptSegments WHERE video_id = ? AND segment_index = ?", (video_id, segment_index))
        result = cursor.fetchone()
        return result['segment_id'] if result else None
    finally:
        conn.close()

def update_segment_gpt_analysis(segment_id, gpt_analysis_json_str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE TranscriptSegments SET gpt_analysis_json = ? WHERE segment_id = ?", (gpt_analysis_json_str, segment_id))
    conn.commit()
    conn.close()

def add_analyzed_phrase(segment_id, phrase_index, text, meaning_korean, start_aligned, end_aligned, match_score, slowed_audio_path, words_sync_json):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO AnalyzedPhrases (segment_id, phrase_index_in_segment, text, meaning_korean, start_time_aligned, end_time_aligned, match_score, slowed_phrase_audio_path, words_for_sync_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (segment_id, phrase_index, text, meaning_korean, start_aligned, end_aligned, match_score, slowed_audio_path, words_sync_json))
        phrase_id = cursor.lastrowid
        conn.commit()
        return phrase_id
    except sqlite3.IntegrityError: # (segment_id, phrase_index_in_segment) UNIQUE
        conn.rollback()
        cursor.execute("SELECT phrase_id FROM AnalyzedPhrases WHERE segment_id = ? AND phrase_index_in_segment = ?", (segment_id, phrase_index))
        result = cursor.fetchone()
        return result['phrase_id'] if result else None
    finally:
        conn.close()

def add_phrase_word(phrase_id, word_index, japanese, kanji_chars, romaji, meaning_korean):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO PhraseWords (phrase_id, word_index_in_phrase, japanese, kanji_chars, romaji, meaning_korean)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (phrase_id, word_index, japanese, kanji_chars, romaji, meaning_korean))
        conn.commit()
    except sqlite3.IntegrityError: # (phrase_id, word_index_in_phrase) UNIQUE
        conn.rollback() # Word already exists for this phrase and index, skip.
        print(f"Warning: PhraseWord already exists for phrase_id {phrase_id}, index {word_index}")
        pass
    finally:
        conn.close()

def add_phrase_kanji(phrase_id, kanji_char, reading, k_desc, h_mean):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO PhraseKanji (phrase_id, kanji_char, reading, meaning_korean_desc, meaning_hanja_char)
        VALUES (?, ?, ?, ?, ?)
        """, (phrase_id, kanji_char, reading, k_desc, h_mean))
        conn.commit()
    except sqlite3.IntegrityError: # (phrase_id, kanji_char, reading) UNIQUE
        conn.rollback() # Kanji already exists for this phrase and reading, skip.
        print(f"Warning: PhraseKanji already exists for phrase_id {phrase_id}, kanji {kanji_char}, reading {reading}")
        pass
    finally:
        conn.close()

def add_global_kanji(video_id, kanji_char, reading, k_desc, h_mean):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO GlobalKanji (video_id, kanji_char, reading, meaning_korean_desc, meaning_hanja_char)
        VALUES (?, ?, ?, ?, ?)
        """, (video_id, kanji_char, reading, k_desc, h_mean))
        conn.commit()
    except sqlite3.IntegrityError: # (video_id, kanji_char) UNIQUE
        conn.rollback() # This specific kanji for this video already recorded, skip.
        pass
    finally:
        conn.close()

# --- Query/Checking Functions ---

def get_video_by_url(youtube_url):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Videos WHERE youtube_url = ?", (youtube_url,))
    video_data = cursor.fetchone() # Returns a Row object or None
    conn.close()
    return video_data

def get_video_by_id(video_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Videos WHERE video_id = ?", (video_id,))
    video_data = cursor.fetchone()
    conn.close()
    return video_data

def check_if_analysis_complete(video_id):
    """Checks if a video's processing_status is 'complete'."""
    video = get_video_by_id(video_id)
    if video and video['processing_status'] == 'complete':
        return True
    
    # Fallback: More detailed check if needed (e.g., count segments and phrases)
    # For now, relying on processing_status is simpler.
    # conn = get_db_connection()
    # cursor = conn.cursor()
    # cursor.execute("SELECT COUNT(*) FROM TranscriptSegments WHERE video_id = ?", (video_id,))
    # segment_count = cursor.fetchone()[0]
    # cursor.execute("""
    #     SELECT COUNT(ap.phrase_id)
    #     FROM AnalyzedPhrases ap
    #     JOIN TranscriptSegments ts ON ap.segment_id = ts.segment_id
    #     WHERE ts.video_id = ?
    # """, (video_id,))
    # phrase_count = cursor.fetchone()[0]
    # conn.close()
    # return segment_count > 0 and phrase_count > 0 # Basic check, refine as needed
    return False


def get_segments_for_video(video_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM TranscriptSegments WHERE video_id = ? ORDER BY segment_index ASC", (video_id,))
    segments = cursor.fetchall()
    conn.close()
    return segments

def get_phrases_for_segment(segment_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM AnalyzedPhrases WHERE segment_id = ? ORDER BY phrase_index_in_segment ASC", (segment_id,))
    phrases = cursor.fetchall()
    conn.close()
    return phrases

def get_words_for_phrase(phrase_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM PhraseWords WHERE phrase_id = ? ORDER BY word_index_in_phrase ASC", (phrase_id,))
    words = cursor.fetchall()
    conn.close()
    return words

def get_kanji_for_phrase(phrase_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM PhraseKanji WHERE phrase_id = ?", (phrase_id,))
    kanji_list = cursor.fetchall()
    conn.close()
    return kanji_list

def get_global_kanji_for_video(video_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT kanji_char, reading, meaning_korean_desc, meaning_hanja_char FROM GlobalKanji WHERE video_id = ? ORDER BY kanji_char ASC", (video_id,))
    kanji_data = cursor.fetchall() # Returns a list of Row objects
    conn.close()
    # Convert Row objects to simple dicts if preferred for consistency elsewhere
    return [dict(row) for row in kanji_data]


if __name__ == '__main__':
    # This will create the DB and tables if you run `python db_utils.py`
    init_db()
    print(f"Database utility script finished. DB should be at {DATABASE_PATH}")

    # Example usage (optional, for testing db_utils.py directly)
    # video_id_new, status = add_video("https://www.youtube.com/watch?v=test123xyz", "Test Video Title")
    # if status == "new":
    #     update_video_paths(video_id_new, original_audio_path="test/original.mp3", slowed_audio_path="test/slowed.mp3")
    #     update_video_transcript_data(video_id_new, '{"some": "json"}', "Full text here", status='transcribed')
    #     update_video_status(video_id_new, 'complete')

    # existing_video = get_video_by_url("https://www.youtube.com/watch?v=test123xyz")
    # if existing_video:
    #     print(f"Fetched existing video: {dict(existing_video)}")
    #     print(f"Is analysis complete? {check_if_analysis_complete(existing_video['video_id'])}")

# In db_utils.py
def update_analyzed_phrase_audio_path(phrase_id, audio_path):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE AnalyzedPhrases SET slowed_phrase_audio_path = ? WHERE phrase_id = ?", (audio_path, phrase_id))
    conn.commit()
    conn.close()

def update_video_title(video_id, title):
    """Updates the title of an existing video."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE Videos SET video_title = ? WHERE video_id = ?", (title, video_id))
        conn.commit()
        print(f"Updated title for video ID {video_id} to '{title}'")
    except sqlite3.Error as e:
        print(f"Database error updating video title for ID {video_id}: {e}")
        conn.rollback() # Rollback on error
    finally:
        conn.close()