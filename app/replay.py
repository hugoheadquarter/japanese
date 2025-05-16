import streamlit as st, json, os
from lib.db import _conn
from lib.paths import path_full
from main import create_synchronized_player, json_to_html_with_sync_players, extract_words_for_sync

st.title("📚 Replay stored videos")

with _conn() as db:
    videos = db.execute("SELECT id, title FROM video ORDER BY added_at DESC").fetchall()

vid_titles = {f"{row[0]} – {row[1]}": row[0] for row in videos}
choice = st.selectbox("Choose a video", list(vid_titles.keys()))
if not choice:
    st.stop()

vid_id = vid_titles[choice]

# Fetch metadata
with _conn() as db:
    v = db.execute("SELECT yt_id,title,full_audio,transcript_json FROM video WHERE id=?", (vid_id,)).fetchone()
yt_id, title, full_path, transcript_json = v
transcript_json = json.loads(transcript_json)

# Rebuild word timings (one shot)
words = extract_words_for_sync(transcript_json, 0.75, 0.3)

tab1, tab2, tab3 = st.tabs(["Whole clip", "Breakdown", "Kanji"])

with tab1:
    if os.path.exists(full_path):
        create_synchronized_player(full_path, words, height=800)
    else:
        st.error("Audio file missing.")

with _conn() as db:
    segments = db.execute(
        "SELECT id,idx,audio_path,analysis_json FROM segment WHERE video_id=? ORDER BY idx",
        (vid_id,)
    ).fetchall()

with tab2:
    for seg in segments:
        sid, seg_idx, seg_audio, analysis_json = seg
        analysis_json = json.loads(analysis_json)
        # phrase audio paths
        phr_files = {}
        for phr in analysis_json["phrases"]:
            p_idx = phr["number"] - 1
            phr_files[p_idx] = f"app/media/{yt_id}/phr_{seg_idx}_{p_idx}.mp3"

        html = json_to_html_with_sync_players(analysis_json, phr_files, transcript_json)
        st.components.v1.html(html, height=400*len(analysis_json["phrases"]), scrolling=True)
        st.markdown("---")

with tab3:
    kanji_rows = _conn().execute(
        """SELECT DISTINCT k.* FROM kanji k
           JOIN phrase_kanji pk ON pk.kanji=k.kanji
           JOIN phrase p ON p.id = pk.phrase_id
           JOIN segment s ON s.id = p.segment_id
           WHERE s.video_id=?""",
        (vid_id,)
    ).fetchall()
    for k in kanji_rows:
        st.write(k)
