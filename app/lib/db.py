import sqlite3, json, hashlib, shutil
from pathlib import Path
from .settings import MEDIA_ROOT

_DB_PATH = "database.db"

def _conn():
    return sqlite3.connect(_DB_PATH, isolation_level=None,
                           detect_types=sqlite3.PARSE_DECLTYPES)

# ---------- insert helpers ----------
def upsert_video(yt_id, title, transcript_json, full_audio_src: Path):
    dest = MEDIA_ROOT / yt_id / "full_0.75.mp3"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(full_audio_src), dest)

    with _conn() as db:
        vid = db.execute(
            """INSERT INTO video(yt_id,title,full_audio,transcript_json)
               VALUES(?,?,?,?)
               ON CONFLICT(yt_id) DO UPDATE
               SET title=excluded.title,
                   full_audio=excluded.full_audio,
                   transcript_json=excluded.transcript_json
            """,
            (yt_id, title, str(dest), json.dumps(transcript_json))
        ).lastrowid
    return vid

def insert_segment(vid, idx, start, end, text, seg_audio_src: Path, analysis_json):
    dest = MEDIA_ROOT / get_yt(vid) / f"seg_{idx}.mp3"
    shutil.move(str(seg_audio_src), dest)
    with _conn() as db:
        sid = db.execute(
            """INSERT INTO segment(video_id,idx,start_sec,end_sec,text,audio_path,analysis_json)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(video_id,idx) DO UPDATE
               SET start_sec=excluded.start_sec,
                   end_sec  =excluded.end_sec,
                   text     =excluded.text,
                   audio_path=excluded.audio_path,
                   analysis_json=excluded.analysis_json""",
            (vid, idx, start, end, text, str(dest), json.dumps(analysis_json))
        ).lastrowid
    return sid

def insert_phrase(sid, idx, text, start, end, phr_audio_src: Path, score):
    dest = MEDIA_ROOT / get_yt_from_segment(sid) / f"phr_{get_seg_idx(sid)}_{idx}.mp3"
    shutil.move(str(phr_audio_src), dest)
    with _conn() as db:
        pid = db.execute(
            """INSERT INTO phrase(segment_id,idx,text,start_sec,end_sec,audio_path,match_score)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(segment_id,idx) DO UPDATE
               SET text=excluded.text,
                   start_sec=excluded.start_sec,
                   end_sec  =excluded.end_sec,
                   audio_path=excluded.audio_path,
                   match_score=excluded.match_score""",
            (sid, idx, text, start, end, str(dest), score)
        ).lastrowid
    return pid

def insert_word(pid, idx, w):
    with _conn() as db:
        db.execute(
            "INSERT OR REPLACE INTO word(phrase_id,idx,japanese,kanji,romaji,meaning_ko)"
            "VALUES(?,?,?,?,?,?)",
            (pid, idx, w["japanese"], w["kanji"], w["romaji"], w["meaning"])
        )

def insert_kanji(pid, k):
    with _conn() as db:
        db.execute(
            "INSERT OR IGNORE INTO kanji(kanji,reading,meaning_ko,meaning_hanja)"
            "VALUES(?,?,?,?)",
            (k["kanji"], k["reading"],
             k["meaning"].split(' / ')[0],
             k["meaning"].split(' / ')[1] if ' / ' in k["meaning"] else '')
        )
        db.execute(
            "INSERT OR IGNORE INTO phrase_kanji(phrase_id, kanji) VALUES (?,?)",
            (pid, k["kanji"])
        )

# ---------- convenience ----------
def get_yt(video_id: int) -> str:
    with _conn() as db:
        return db.execute("SELECT yt_id FROM video WHERE id=?", (video_id,)).fetchone()[0]

def get_yt_from_segment(segment_id):
    with _conn() as db:
        return db.execute(
            """SELECT v.yt_id FROM video v
               JOIN segment s ON s.video_id = v.id
               WHERE s.id=?""",
            (segment_id,)
        ).fetchone()[0]

def get_seg_idx(segment_id):
    with _conn() as db:
        return db.execute("SELECT idx FROM segment WHERE id=?", (segment_id,)).fetchone()[0]
