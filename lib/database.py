# lib/database.py
"""Database access layer — all queries go through the Supabase Python client.

Every function is self-contained (fetches the client internally) so callers
never need to manage connections or transactions.
"""

from __future__ import annotations
import json
from lib.supabase_client import get_supabase


# ---------------------------------------------------------------------------
# Video CRUD
# ---------------------------------------------------------------------------

def get_all_videos() -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("videos")
        .select("id, youtube_url, video_title, video_data_directory, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data


def get_video_by_url(url: str) -> dict | None:
    sb = get_supabase()
    resp = (
        sb.table("videos")
        .select("id, video_title, video_data_directory")
        .eq("youtube_url", url)
        .execute()
    )
    if resp.data:
        return resp.data[0]
    return None


def get_video_by_id(video_id: int) -> dict | None:
    sb = get_supabase()
    resp = (
        sb.table("videos")
        .select("*")
        .eq("id", video_id)
        .execute()
    )
    if resp.data:
        return resp.data[0]
    return None


def insert_video(url: str, title: str) -> int:
    """Insert a new video row.  Returns the new ``id``."""
    sb = get_supabase()
    resp = (
        sb.table("videos")
        .insert({"youtube_url": url, "video_title": title})
        .execute()
    )
    return resp.data[0]["id"]


def update_video_directory(video_id: int, dir_name: str):
    sb = get_supabase()
    sb.table("videos").update({"video_data_directory": dir_name}).eq("id", video_id).execute()


def update_video_audio(video_id: int, audio_storage_path: str):
    sb = get_supabase()
    sb.table("videos").update({"full_slowed_audio_path": audio_storage_path}).eq("id", video_id).execute()


def update_video_transcript(
    video_id: int,
    raw_deepgram: dict,
    full_text: str,
    sync_words: list[dict],
):
    sb = get_supabase()
    sb.table("videos").update({
        "raw_deepgram_response_json": raw_deepgram,
        "full_transcript_text": full_text,
        "full_words_for_sync_json": sync_words,
    }).eq("id", video_id).execute()


def update_video_debug(video_id: int, debug_data: dict):
    """Store segmentation / analysis debug JSON."""
    sb = get_supabase()
    sb.table("videos").update({"debug_json": debug_data}).eq("id", video_id).execute()


def delete_video(video_id: int) -> str | None:
    """Delete video (CASCADE removes children).  Returns video_data_directory."""
    sb = get_supabase()
    resp = sb.rpc("delete_video_returning_dir", {"p_video_id": video_id}).execute()
    if resp.data:
        return resp.data
    return None


# ---------------------------------------------------------------------------
# Segment CRUD
# ---------------------------------------------------------------------------

def insert_segment(
    video_id: int,
    seg_idx: int,
    text: str,
    start: float,
    end: float,
    words: list[dict],
) -> int:
    """Insert one segment row.  Returns the new ``id``."""
    sb = get_supabase()
    resp = (
        sb.table("segments")
        .insert({
            "video_id": video_id,
            "segment_index": seg_idx,
            "text": text,
            "start_time": start,
            "end_time": end,
            "deepgram_segment_words_json": words,
        })
        .execute()
    )
    return resp.data[0]["id"]


def get_segments_for_video(video_id: int) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("segments")
        .select("*")
        .eq("video_id", video_id)
        .order("segment_index")
        .execute()
    )
    return resp.data


# ---------------------------------------------------------------------------
# Phrase Analysis CRUD
# ---------------------------------------------------------------------------

def insert_phrase_analysis(
    segment_id: int,
    phrase_idx: int,
    gpt_json: dict,
    audio_path: str | None,
    sync_words: list[dict],
):
    sb = get_supabase()
    sb.table("gpt_phrase_analyses").insert({
        "segment_id": segment_id,
        "phrase_index_in_segment": phrase_idx,
        "gpt_phrase_json": gpt_json,
        "phrase_slowed_audio_path": audio_path,
        "phrase_words_for_sync_json": sync_words,
    }).execute()


def batch_insert_phrase_analyses(rows: list[dict]):
    """Insert multiple phrase analyses in one call.

    Each dict: {segment_id, phrase_index_in_segment, gpt_phrase_json,
                phrase_slowed_audio_path, phrase_words_for_sync_json}
    """
    if not rows:
        return
    sb = get_supabase()
    sb.table("gpt_phrase_analyses").insert(rows).execute()


def get_phrase_analyses_for_segment(segment_id: int) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("gpt_phrase_analyses")
        .select("*")
        .eq("segment_id", segment_id)
        .order("phrase_index_in_segment")
        .execute()
    )
    return resp.data


def get_all_phrase_analyses_for_video(video_id: int) -> list[dict]:
    """Fetch all phrase analyses for a video, ordered by segment + phrase index.

    Uses an RPC function to perform the JOIN server-side.
    """
    sb = get_supabase()
    resp = sb.rpc("get_phrase_analyses_for_video", {"p_video_id": video_id}).execute()
    return resp.data


# ---------------------------------------------------------------------------
# Kanji CRUD
# ---------------------------------------------------------------------------

def get_kanji_for_video(video_id: int) -> list[dict]:
    sb = get_supabase()
    resp = (
        sb.table("kanji_entries")
        .select("character, reading, meaning")
        .eq("video_id", video_id)
        .execute()
    )
    return resp.data


def extract_and_store_kanji(video_id: int):
    """Extract unique kanji from all phrase analyses and bulk-upsert into kanji_entries."""
    rows = get_all_phrase_analyses_for_video(video_id)
    unique_kanji: dict[str, dict] = {}
    for row in rows:
        gd = row["gpt_phrase_json"]
        # gd is already a dict (JSONB → Python dict via Supabase)
        if isinstance(gd, str):
            gd = json.loads(gd)
        for ke in gd.get("kanji_explanations", []):
            char = ke.get("kanji")
            if char and char not in unique_kanji:
                unique_kanji[char] = {
                    "character": char,
                    "reading": ke.get("reading", ""),
                    "meaning": ke.get("meaning", ""),
                }
    if not unique_kanji:
        return

    entries = list(unique_kanji.values())
    sb = get_supabase()
    sb.rpc("upsert_kanji_entries", {
        "p_video_id": video_id,
        "p_entries": entries,
    }).execute()


def load_kanji_first_occurrences(video_id: int) -> dict:
    """Return ``{kanji_char: (first_start_time, sequence_index)}``."""
    rows = get_all_phrase_analyses_for_video(video_id)
    earliest: dict[str, tuple] = {}
    seq = 0
    for row in rows:
        phr = row["gpt_phrase_json"]
        if isinstance(phr, str):
            phr = json.loads(phr)
        t0 = phr.get("original_start_time") or float("inf")
        for ke in phr.get("kanji_explanations", []):
            k = ke.get("kanji")
            if k and k not in earliest:
                earliest[k] = (t0, seq)
                seq += 1
    return earliest