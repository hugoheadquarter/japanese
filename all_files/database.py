# lib/database.py
"""Single canonical database module.

All DB access goes through this module.
Uses a single connection per call-site, passed through the pipeline.
"""

import sqlite3
import json
from pathlib import Path
from config import DB_PATH


def get_db_connection() -> sqlite3.Connection:
    """Get a database connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ---------------------------------------------------------------------------
# Video CRUD
# ---------------------------------------------------------------------------

def get_all_videos(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT id, youtube_url, video_title, video_data_directory, created_at "
        "FROM Videos ORDER BY created_at DESC"
    ).fetchall()


def get_video_by_url(conn: sqlite3.Connection, url: str):
    return conn.execute(
        "SELECT id, video_title, video_data_directory FROM Videos WHERE youtube_url = ?",
        (url,),
    ).fetchone()


def get_video_by_id(conn: sqlite3.Connection, video_id: int):
    return conn.execute("SELECT * FROM Videos WHERE id = ?", (video_id,)).fetchone()


def insert_video(conn: sqlite3.Connection, url: str, title: str) -> int:
    cursor = conn.execute(
        "INSERT INTO Videos (youtube_url, video_title) VALUES (?, ?)", (url, title)
    )
    conn.commit()
    return cursor.lastrowid


def update_video_directory(conn: sqlite3.Connection, video_id: int, dir_name: str):
    conn.execute(
        "UPDATE Videos SET video_data_directory = ? WHERE id = ?",
        (dir_name, video_id),
    )


def update_video_audio(conn: sqlite3.Connection, video_id: int, audio_filename: str):
    conn.execute(
        "UPDATE Videos SET full_slowed_audio_path = ? WHERE id = ?",
        (audio_filename, video_id),
    )


def update_video_transcript(
    conn: sqlite3.Connection,
    video_id: int,
    raw_json_str: str,
    full_text: str,
    sync_words_json: str,
):
    conn.execute(
        "UPDATE Videos SET raw_deepgram_response_json=?, full_transcript_text=?, "
        "full_words_for_sync_json=? WHERE id=?",
        (raw_json_str, full_text, sync_words_json, video_id),
    )


def delete_video(conn: sqlite3.Connection, video_id: int):
    """Delete video and all cascading data."""
    conn.execute("DELETE FROM Videos WHERE id = ?", (video_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Segment CRUD
# ---------------------------------------------------------------------------

def insert_segment(
    conn: sqlite3.Connection,
    video_id: int,
    seg_idx: int,
    text: str,
    start: float,
    end: float,
    words_json: str,
) -> int:
    cursor = conn.execute(
        "INSERT INTO Segments (video_id, segment_index, text, start_time, end_time, "
        "deepgram_segment_words_json) VALUES (?,?,?,?,?,?)",
        (video_id, seg_idx, text, start, end, words_json),
    )
    return cursor.lastrowid


def get_segments_for_video(conn: sqlite3.Connection, video_id: int):
    return conn.execute(
        "SELECT * FROM Segments WHERE video_id = ? ORDER BY segment_index",
        (video_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Phrase Analysis CRUD
# ---------------------------------------------------------------------------

def insert_phrase_analysis(
    conn: sqlite3.Connection,
    segment_id: int,
    phrase_idx: int,
    gpt_json_str: str,
    audio_path: str | None,
    sync_words_json: str,
):
    conn.execute(
        "INSERT INTO GptPhraseAnalyses "
        "(segment_id, phrase_index_in_segment, gpt_phrase_json, "
        "phrase_slowed_audio_path, phrase_words_for_sync_json) "
        "VALUES (?,?,?,?,?)",
        (segment_id, phrase_idx, gpt_json_str, audio_path, sync_words_json),
    )


def get_phrase_analyses_for_segment(conn: sqlite3.Connection, segment_id: int):
    return conn.execute(
        "SELECT * FROM GptPhraseAnalyses WHERE segment_id = ? "
        "ORDER BY phrase_index_in_segment",
        (segment_id,),
    ).fetchall()


def get_all_phrase_analyses_for_video(conn: sqlite3.Connection, video_id: int):
    return conn.execute(
        "SELECT gpa.gpt_phrase_json, gpa.phrase_words_for_sync_json "
        "FROM GptPhraseAnalyses gpa "
        "JOIN Segments s ON gpa.segment_id = s.id "
        "WHERE s.video_id = ?",
        (video_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Kanji CRUD
# ---------------------------------------------------------------------------

def insert_kanji_entry(
    conn: sqlite3.Connection, video_id: int, char: str, reading: str, meaning: str
):
    try:
        conn.execute(
            "INSERT INTO KanjiEntries (video_id, character, reading, meaning) "
            "VALUES (?,?,?,?)",
            (video_id, char, reading, meaning),
        )
    except sqlite3.IntegrityError:
        pass  # Already exists


def get_kanji_for_video(conn: sqlite3.Connection, video_id: int):
    return conn.execute(
        "SELECT character, reading, meaning FROM KanjiEntries WHERE video_id = ?",
        (video_id,),
    ).fetchall()


def extract_and_store_kanji(conn: sqlite3.Connection, video_id: int):
    """Extract unique kanji from all phrase analyses and store in KanjiEntries."""
    rows = get_all_phrase_analyses_for_video(conn, video_id)
    unique_kanji = {}
    for row in rows:
        gd = json.loads(row["gpt_phrase_json"])
        for ke in gd.get("kanji_explanations", []):
            char = ke.get("kanji")
            if char and char not in unique_kanji:
                unique_kanji[char] = {
                    "reading": ke.get("reading", ""),
                    "meaning": ke.get("meaning", ""),
                }
    for char, info in unique_kanji.items():
        insert_kanji_entry(conn, video_id, char, info["reading"], info["meaning"])
    conn.commit()


def load_kanji_first_occurrences(conn: sqlite3.Connection, video_id: int) -> dict:
    """Return {kanji_char: (first_start_time, sequence_index)}."""
    earliest = {}
    seq = 0
    rows = get_all_phrase_analyses_for_video(conn, video_id)
    for row in rows:
        phr = json.loads(row["gpt_phrase_json"])
        t0 = phr.get("original_start_time") or float("inf")
        for ke in phr.get("kanji_explanations", []):
            k = ke.get("kanji")
            if k and k not in earliest:
                earliest[k] = (t0, seq)
                seq += 1
    return earliest


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------

def batch_insert_phrase_analyses(
    conn: sqlite3.Connection,
    rows: list[tuple],
):
    """Insert multiple phrase analyses in one executemany call.

    Each tuple: (segment_id, phrase_idx, gpt_json_str, audio_path, sync_json)
    """
    conn.executemany(
        "INSERT INTO GptPhraseAnalyses "
        "(segment_id, phrase_index_in_segment, gpt_phrase_json, "
        "phrase_slowed_audio_path, phrase_words_for_sync_json) "
        "VALUES (?,?,?,?,?)",
        rows,
    )
