PRAGMA foreign_keys = ON;

CREATE TABLE video (
    id            INTEGER PRIMARY KEY,
    yt_id         TEXT UNIQUE,
    title         TEXT NOT NULL,
    full_audio    TEXT NOT NULL,        -- media path
    transcript_json  TEXT NOT NULL,
    added_at      TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE segment (
    id            INTEGER PRIMARY KEY,
    video_id      INTEGER NOT NULL REFERENCES video(id) ON DELETE CASCADE,
    idx           INTEGER NOT NULL,
    start_sec     REAL NOT NULL,
    end_sec       REAL NOT NULL,
    text          TEXT NOT NULL,
    audio_path    TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    UNIQUE(video_id, idx)
);

CREATE TABLE phrase (
    id            INTEGER PRIMARY KEY,
    segment_id    INTEGER NOT NULL REFERENCES segment(id) ON DELETE CASCADE,
    idx           INTEGER NOT NULL,
    text          TEXT NOT NULL,
    start_sec     REAL NOT NULL,
    end_sec       REAL NOT NULL,
    audio_path    TEXT NOT NULL,
    match_score   REAL DEFAULT 0,
    UNIQUE(segment_id, idx)
);

CREATE TABLE word (
    id            INTEGER PRIMARY KEY,
    phrase_id     INTEGER NOT NULL REFERENCES phrase(id) ON DELETE CASCADE,
    idx           INTEGER NOT NULL,
    japanese      TEXT,
    kanji         TEXT,
    romaji        TEXT,
    meaning_ko    TEXT
);

CREATE TABLE kanji (
    kanji         TEXT PRIMARY KEY,
    reading       TEXT,
    meaning_ko    TEXT,
    meaning_hanja TEXT
);

CREATE TABLE phrase_kanji (
    phrase_id     INTEGER NOT NULL REFERENCES phrase(id) ON DELETE CASCADE,
    kanji         TEXT NOT NULL REFERENCES kanji(kanji),
    PRIMARY KEY (phrase_id, kanji)
);

CREATE INDEX idx_segment_video  ON segment(video_id);
CREATE INDEX idx_phrase_segment ON phrase(segment_id);
