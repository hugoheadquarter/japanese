# lib/storage.py
"""Supabase Storage helpers for uploading / downloading / deleting audio files."""

from __future__ import annotations
from lib.supabase_client import get_supabase
from config import STORAGE_BUCKET


def upload_audio(local_path: str, storage_path: str) -> str:
    """Upload a local file to Supabase Storage.  Returns the storage path."""
    sb = get_supabase()
    with open(local_path, "rb") as f:
        sb.storage.from_(STORAGE_BUCKET).upload(
            path=storage_path,
            file=f,
            file_options={"content-type": "audio/mpeg", "upsert": "true"},
        )
    return storage_path


def get_public_url(storage_path: str) -> str:
    """Get the public URL for a file in the audio bucket."""
    sb = get_supabase()
    return sb.storage.from_(STORAGE_BUCKET).get_public_url(storage_path)


def download_audio_bytes(storage_path: str) -> bytes:
    """Download a file's raw bytes from storage."""
    sb = get_supabase()
    return sb.storage.from_(STORAGE_BUCKET).download(storage_path)


def delete_storage_folder(folder_path: str):
    """Delete all files under *folder_path* in the audio bucket.

    Supabase Storage list() only returns immediate children, so we handle
    both flat files and a single ``phrases/`` sub-folder.
    """
    sb = get_supabase()
    bucket = sb.storage.from_(STORAGE_BUCKET)

    def _remove_listed(prefix: str):
        try:
            items = bucket.list(prefix)
        except Exception:
            return
        if not items:
            return
        paths = []
        for item in items:
            name = item.get("name", "")
            if not name:
                continue
            full = f"{prefix}/{name}" if prefix else name
            # If it looks like a directory (no extension), recurse
            if "." not in name:
                _remove_listed(full)
            else:
                paths.append(full)
        if paths:
            try:
                bucket.remove(paths)
            except Exception as exc:
                print(f"[STORAGE] Error deleting {paths}: {exc}")

    _remove_listed(folder_path)
