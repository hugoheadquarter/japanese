-- =============================================================================
-- SUPABASE SETUP — Run this ENTIRE script in the Supabase SQL Editor
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. TABLES
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS videos (
    id              BIGSERIAL PRIMARY KEY,
    youtube_url     TEXT UNIQUE NOT NULL,
    video_title     TEXT,
    video_data_directory TEXT UNIQUE,
    full_slowed_audio_path TEXT,
    full_words_for_sync_json JSONB,
    raw_deepgram_response_json JSONB,
    full_transcript_text TEXT,
    debug_json      JSONB,                         -- stores segmentation + analysis debug
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS segments (
    id              BIGSERIAL PRIMARY KEY,
    video_id        BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    segment_index   INTEGER NOT NULL,
    text            TEXT,
    start_time      DOUBLE PRECISION,
    end_time        DOUBLE PRECISION,
    deepgram_segment_words_json JSONB,
    UNIQUE (video_id, segment_index)
);

CREATE TABLE IF NOT EXISTS gpt_phrase_analyses (
    id              BIGSERIAL PRIMARY KEY,
    segment_id      BIGINT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    phrase_index_in_segment INTEGER NOT NULL,
    gpt_phrase_json JSONB NOT NULL,
    phrase_slowed_audio_path TEXT,
    phrase_words_for_sync_json JSONB,
    UNIQUE (segment_id, phrase_index_in_segment)
);

CREATE TABLE IF NOT EXISTS kanji_entries (
    id              BIGSERIAL PRIMARY KEY,
    video_id        BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    character       TEXT NOT NULL,
    reading         TEXT,
    meaning         TEXT,
    UNIQUE (video_id, character)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. INDEXES
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_segments_video_id
    ON segments(video_id);

CREATE INDEX IF NOT EXISTS idx_gpt_phrases_segment_id
    ON gpt_phrase_analyses(segment_id);

CREATE INDEX IF NOT EXISTS idx_kanji_video_id
    ON kanji_entries(video_id);

CREATE INDEX IF NOT EXISTS idx_segments_video_order
    ON segments(video_id, segment_index);

CREATE INDEX IF NOT EXISTS idx_gpt_phrases_segment_order
    ON gpt_phrase_analyses(segment_id, phrase_index_in_segment);


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. RPC FUNCTIONS
-- ─────────────────────────────────────────────────────────────────────────────

-- Get all phrase analyses for a given video (ordered by segment then phrase)
CREATE OR REPLACE FUNCTION get_phrase_analyses_for_video(p_video_id BIGINT)
RETURNS TABLE (
    gpt_phrase_json JSONB,
    phrase_words_for_sync_json JSONB,
    phrase_slowed_audio_path TEXT,
    segment_index INTEGER,
    phrase_index_in_segment INTEGER
) AS $$
    SELECT
        gpa.gpt_phrase_json,
        gpa.phrase_words_for_sync_json,
        gpa.phrase_slowed_audio_path,
        s.segment_index,
        gpa.phrase_index_in_segment
    FROM gpt_phrase_analyses gpa
    JOIN segments s ON gpa.segment_id = s.id
    WHERE s.video_id = p_video_id
    ORDER BY s.segment_index, gpa.phrase_index_in_segment;
$$ LANGUAGE SQL STABLE;


-- Delete a video and return its data directory (so caller can clean up storage)
CREATE OR REPLACE FUNCTION delete_video_returning_dir(p_video_id BIGINT)
RETURNS TEXT AS $$
DECLARE
    v_dir TEXT;
BEGIN
    SELECT video_data_directory INTO v_dir FROM videos WHERE id = p_video_id;
    DELETE FROM videos WHERE id = p_video_id;   -- CASCADE handles children
    RETURN v_dir;
END;
$$ LANGUAGE plpgsql;


-- Bulk upsert kanji entries (avoids N+1 inserts)
CREATE OR REPLACE FUNCTION upsert_kanji_entries(
    p_video_id BIGINT,
    p_entries JSONB   -- array of {"character": "...", "reading": "...", "meaning": "..."}
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO kanji_entries (video_id, character, reading, meaning)
    SELECT p_video_id, e->>'character', e->>'reading', e->>'meaning'
    FROM jsonb_array_elements(p_entries) AS e
    ON CONFLICT (video_id, character) DO NOTHING;
END;
$$ LANGUAGE plpgsql;


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. STORAGE BUCKET
-- ─────────────────────────────────────────────────────────────────────────────

-- Create a public bucket for audio files
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
    'audio',
    'audio',
    true,
    52428800,          -- 50 MB max per file
    ARRAY['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/ogg', 'application/octet-stream']
)
ON CONFLICT (id) DO NOTHING;


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. STORAGE POLICIES
-- ─────────────────────────────────────────────────────────────────────────────

-- Anyone can read audio (public bucket)
CREATE POLICY "Public audio read"
    ON storage.objects FOR SELECT
    USING (bucket_id = 'audio');

-- Service role can upload
CREATE POLICY "Service audio insert"
    ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'audio');

-- Service role can update (upsert)
CREATE POLICY "Service audio update"
    ON storage.objects FOR UPDATE
    USING (bucket_id = 'audio');

-- Service role can delete
CREATE POLICY "Service audio delete"
    ON storage.objects FOR DELETE
    USING (bucket_id = 'audio');


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. ROW LEVEL SECURITY — Disable for these tables (single-user app via service key)
-- ─────────────────────────────────────────────────────────────────────────────
-- If RLS is enabled by default on your project, you need to either:
--   a) Disable it for these tables (simplest for a personal app), or
--   b) Create permissive policies.
--
-- Option (a): disable RLS
ALTER TABLE videos DISABLE ROW LEVEL SECURITY;
ALTER TABLE segments DISABLE ROW LEVEL SECURITY;
ALTER TABLE gpt_phrase_analyses DISABLE ROW LEVEL SECURITY;
ALTER TABLE kanji_entries DISABLE ROW LEVEL SECURITY;

-- Done! Your Supabase project is ready.
