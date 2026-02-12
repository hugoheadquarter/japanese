# jp.py - Main Streamlit Application
"""Japanese Learner App - Main entry point.

Thin UI layer. All logic in lib/ modules.
"""

import streamlit as st
import json
import os
import tempfile
import shutil
import traceback
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# Page config (must be first st call)
st.set_page_config(page_title="日本語")

# --- Imports from lib ---
from config import AUDIO_FILES_STORAGE_ROOT_ABS_PATH
from lib.database import (
    get_db_connection,
    get_all_videos,
    get_video_by_url,
    get_video_by_id,
    insert_video,
    update_video_directory,
    update_video_audio,
    update_video_transcript,
    delete_video,
    insert_segment,
    get_segments_for_video,
    get_phrase_analyses_for_segment,
    get_all_phrase_analyses_for_video,
    get_kanji_for_video,
    extract_and_store_kanji,
    load_kanji_first_occurrences,
    batch_insert_phrase_analyses,
)
from lib.audio import download_audio, slow_down_audio, create_phrase_audio_clips
from lib.analysis import (
    transcribe_audio,
    prepare_japanese_segments,
    extract_words_for_sync,
    extract_phrase_words_for_sync,
    analyze_japanese_segment,
    collect_vocab_with_kanji,
)
from lib.players import (
    create_synchronized_player,
    generate_breakdown_html,
    estimate_segment_height,
    create_vocab_component,
)


# ---------------------------------------------------------------------------
# Streamlit caching
# ---------------------------------------------------------------------------

@st.cache_resource
def cached_db_connection():
    """Cached database connection (one per session)."""
    return get_db_connection()


@st.cache_data(ttl=600)
def cached_segments(video_id: int):
    conn = get_db_connection()
    rows = get_segments_for_video(conn, video_id)
    result = [dict(r) for r in rows]
    conn.close()
    return result


@st.cache_data(ttl=600)
def cached_phrase_analyses(segment_id: int):
    conn = get_db_connection()
    rows = get_phrase_analyses_for_segment(conn, segment_id)
    result = [dict(r) for r in rows]
    conn.close()
    return result


@st.cache_data(ttl=600)
def cached_kanji(video_id: int):
    conn = get_db_connection()
    rows = get_kanji_for_video(conn, video_id)
    result = [dict(r) for r in rows]
    conn.close()
    return result


@st.cache_data(ttl=600)
def cached_kanji_order(video_id: int):
    conn = get_db_connection()
    result = load_kanji_first_occurrences(conn, video_id)
    conn.close()
    return result


@st.cache_data(ttl=600)
def cached_vocab_map(video_id: int) -> dict:
    """Reconstruct vocabulary map from database."""
    conn = get_db_connection()
    rows = get_all_phrase_analyses_for_video(conn, video_id)
    vocab = {}
    for row in rows:
        phrase_data = json.loads(row["gpt_phrase_json"])
        sync_words = (
            json.loads(row["phrase_words_for_sync_json"])
            if row["phrase_words_for_sync_json"]
            else None
        )
        collect_vocab_with_kanji({"phrases": [phrase_data]}, vocab, sync_words)
    conn.close()
    return vocab


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

st.markdown(
    """
<style>
body,h1,h2,h3,h4,h5,h6,p,td,th,li,div,ul,ol{
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Oxygen,Ubuntu,Cantarell,'Open Sans','Helvetica Neue',sans-serif!important;}
.stAudio{margin-bottom:0!important;width:100%!important;}
.stAudio>div{height:40px!important;width:100%!important;}
rt{font-size:0.7em;opacity:0.9;user-select:none;}
.phrase-player audio{display:none!important;}
.phrase-player div[id^="text-phr-"]{margin-top:0!important;padding-top:5px;}
h3{font-size:18px!important;line-height:1.6!important;padding-left:10px!important;margin-top:20px!important;font-weight:600!important;}
h2{font-size:22px!important;font-weight:bold!important;margin-bottom:15px!important;padding:8px!important;border-radius:5px!important;background-color:#f8f8f8!important;}
table{width:100%!important;margin-bottom:15px!important;border-collapse:collapse!important;}
th,td{border:1px solid #e0e0e0!important;padding:8px 12px!important;text-align:left!important;font-size:14px!important;line-height:1.5!important;}
th{background-color:#f2f2f2!important;font-weight:600!important;}
ul.kanji-list{margin-top:5px!important;padding-left:0!important;list-style-type:none!important;}
ul.kanji-list li{font-size:14px!important;line-height:1.6!important;margin-bottom:4px!important;}
div.meaning-paragraph p{font-size:20px!important;line-height:1.6!important;margin-top:5px!important;}
hr{margin-top:20px!important;margin-bottom:20px!important;border:0!important;height:1px!important;background-color:#e0e0e0!important;}
.phrase-player{margin-bottom:15px!important;border-radius:4px!important;overflow:hidden!important;}
.kanji-card-container{padding-top:10px;}
.kanji-card{border:1px solid #e0e0e0;padding:20px;margin-bottom:20px;border-radius:10px;background:#fff;
    display:flex;align-items:center;transition:box-shadow 0.2s,transform 0.2s;height:180px;box-sizing:border-box;}
.kanji-card:hover{box-shadow:0 8px 16px rgba(0,0,0,0.15);transform:translateY(-3px);}
.kanji-char-display{font-size:4em;font-weight:bold;margin-right:25px;min-width:80px;text-align:center;color:#2c3e50;line-height:1;}
.kanji-info{display:flex;flex-direction:column;justify-content:center;font-size:1.1em;flex-grow:1;}
.kanji-info div{margin-bottom:8px;line-height:1.5;display:flex;align-items:baseline;}
.kanji-info div:last-child{margin-bottom:0;}
.kanji-info strong{font-weight:500;color:#6c757d;margin-right:8px;display:inline-block;}
.kanji-info .value{font-weight:600;color:#343a40;}
@media(prefers-color-scheme:dark){
    th{background-color:#2e2e2e!important;}
    th,td{border-color:#4e4e4e!important;}
    h2{background-color:#2a2a2a!important;}
    hr{background-color:#3e3e3e!important;}
    .kanji-card{background-color:#262626;border-color:#444;}
    .kanji-char-display{color:#e8e8e8;}
    .kanji-info strong{color:#adb5bd;}
    .kanji-info .value{color:#f1f1f1;}
}
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def sidebar_history():
    conn = get_db_connection()
    rows = get_all_videos(conn)
    conn.close()
    if not rows:
        st.info("분석된 영상이 없습니다.")
        return
    st.markdown("##### 🔍 처리 내역")
    for r in rows:
        title = r["video_title"] or r["youtube_url"]
        st.markdown(f"- [{title}]({r['youtube_url']})")


# ---------------------------------------------------------------------------
# Tab population helpers
# ---------------------------------------------------------------------------

def populate_transcript_tab(tab, video_dir: str, audio_fn: str, sync_json: str):
    """Fill the full transcript tab."""
    with tab:
        if audio_fn and video_dir and sync_json:
            words = json.loads(sync_json)
            create_synchronized_player(video_dir, audio_fn, words)
        else:
            st.info("스크립트 데이터가 없습니다.")


def populate_breakdown_tab(tab, video_id: int, video_dir: str):
    """Fill the breakdown tab with lazy-loaded segments."""
    with tab:
        segments = cached_segments(video_id)
        if not segments:
            st.info("분석 데이터가 없습니다.")
            return

        for seg in segments:
            seg_id = seg["id"]
            seg_text = seg.get("text", "")

            # Lazy rendering with expander
            with st.expander(f"#{seg['segment_index']+1}: {seg_text[:40]}...", expanded=True):
                analyses = cached_phrase_analyses(seg_id)
                if not analyses:
                    st.info("이 세그먼트에 대한 분석이 없습니다.")
                    continue

                phrases_data = []
                audio_map = {}
                sync_map = {}

                for a in analyses:
                    idx = a["phrase_index_in_segment"]
                    phrases_data.append(json.loads(a["gpt_phrase_json"]))
                    audio_map[idx] = a.get("phrase_slowed_audio_path")
                    sync_words = (
                        json.loads(a["phrase_words_for_sync_json"])
                        if a.get("phrase_words_for_sync_json")
                        else []
                    )
                    sync_map[idx] = sync_words

                html = generate_breakdown_html(
                    phrases_data, audio_map, sync_map, video_dir, seg_id
                )
                px = estimate_segment_height(phrases_data)
                st.components.v1.html(html, height=px, scrolling=True)


def populate_vocab_tab(tab, video_id: int, video_dir: str, audio_fn: str | None):
    """Fill the vocabulary tab."""
    with tab:
        vocab = cached_vocab_map(video_id)
        if not vocab:
            st.info("한자가 포함된 단어가 없습니다.")
            return

        col1, col2 = st.columns([3, 1])
        with col1:
            fq = st.text_input("검색", "", key=f"vf_{video_id}")
        with col2:
            sort = st.selectbox("정렬", ["시간순", "일본어순", "한자순"], key=f"vs_{video_id}")

        html = create_vocab_component(vocab, video_dir, audio_fn, fq, sort)
        h = min(800, len(vocab) * 150 + 200)
        st.components.v1.html(html, height=h, scrolling=True)


def populate_kanji_tab(tab, video_id: int):
    """Fill the kanji tab."""
    with tab:
        entries = cached_kanji(video_id)
        if not entries:
            st.info("한자 데이터가 없습니다.")
            return

        order = cached_kanji_order(video_id)
        sorted_entries = sorted(
            entries, key=lambda r: order.get(r["character"], (float("inf"), 0))
        )

        num_cols = 4
        cols = st.columns(num_cols)
        st.markdown('<div class="kanji-card-container">', unsafe_allow_html=True)
        for idx, k in enumerate(sorted_entries):
            with cols[idx % num_cols]:
                k_desc, h_mean = "", ""
                meaning = k["meaning"]
                if " / " in meaning:
                    parts = meaning.split(" / ", 1)
                    k_desc = parts[0]
                    h_mean = parts[1] if len(parts) > 1 else ""
                else:
                    k_desc = meaning
                hanja_div = (
                    f'<div><strong></strong> <span class="value">{h_mean}</span></div>'
                    if h_mean
                    else ""
                )
                st.markdown(
                    f"""<div class="kanji-card">
                    <div class="kanji-char-display">{k['character']}</div>
                    <div class="kanji-info">
                        <div><strong></strong><span class="value">{k['reading']}</span></div>
                        <div><strong></strong><span class="value">{k_desc}</span></div>
                        {hanja_div}
                    </div></div>""",
                    unsafe_allow_html=True,
                )
        st.markdown("</div>", unsafe_allow_html=True)


def populate_text_tab(tab, full_text: str, title: str):
    with tab:
        if full_text:
            st.text_area("전체 텍스트", full_text, height=300, label_visibility="collapsed")
            st.download_button(
                "Download",
                full_text.encode("utf-8"),
                f"{title or 'video'}_text.txt",
                "text/plain",
            )


def populate_json_tab(tab, raw_json_str: str, title: str):
    with tab:
        if raw_json_str:
            try:
                st.json(json.loads(raw_json_str))
            except json.JSONDecodeError:
                st.error("JSON data corrupted.")
            st.download_button(
                "Download",
                raw_json_str.encode("utf-8"),
                f"{title or 'video'}_deepgram.json",
                "application/json",
            )


# ---------------------------------------------------------------------------
# Display existing analysis
# ---------------------------------------------------------------------------

def display_existing_video(video_id: int):
    """Display all tabs for an already-analyzed video."""
    conn = get_db_connection()
    video = get_video_by_id(conn, video_id)
    if not video:
        st.error("영상을 찾을 수 없습니다.")
        conn.close()
        return

    video = dict(video)
    video_dir = video.get("video_data_directory", "")
    audio_fn = video.get("full_slowed_audio_path", "")
    title = video.get("video_title", "")

    # Ensure derived fields exist
    if not video.get("full_words_for_sync_json") and video.get("raw_deepgram_response_json"):
        raw = json.loads(video["raw_deepgram_response_json"])
        words = extract_words_for_sync(raw)
        conn.execute(
            "UPDATE Videos SET full_words_for_sync_json=? WHERE id=?",
            (json.dumps(words), video_id),
        )
        video["full_words_for_sync_json"] = json.dumps(words)
        conn.commit()

    if not video.get("full_transcript_text") and video.get("raw_deepgram_response_json"):
        raw = json.loads(video["raw_deepgram_response_json"])
        txt = raw["results"]["channels"][0]["alternatives"][0]["transcript"].replace(" ", "")
        conn.execute("UPDATE Videos SET full_transcript_text=? WHERE id=?", (txt, video_id))
        video["full_transcript_text"] = txt
        conn.commit()

    conn.close()

    # Create tabs
    tabs = st.tabs(["스크립트", "문장", "단어", "한자", "텍스트", "JSON"])
    tab_script, tab_breakdown, tab_vocab, tab_kanji, tab_text, tab_json = tabs

    populate_transcript_tab(
        tab_script, video_dir, audio_fn, video.get("full_words_for_sync_json", "[]")
    )
    populate_breakdown_tab(tab_breakdown, video_id, video_dir)
    populate_vocab_tab(tab_vocab, video_id, video_dir, audio_fn)
    populate_kanji_tab(tab_kanji, video_id)
    populate_text_tab(tab_text, video.get("full_transcript_text", ""), title)
    populate_json_tab(tab_json, video.get("raw_deepgram_response_json", ""), title)


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_full_pipeline(url: str, force: bool):
    """Execute the complete analysis pipeline."""
    status = st.empty()
    status.info("1단계: 준비 중...")

    conn = get_db_connection()
    temp_dir_obj = None

    try:
        # Check existing
        existing = get_video_by_url(conn, url)
        if existing and not force:
            status.success(f"'{existing['video_title']}' 이미 분석됨. 결과를 표시합니다.")
            vid = existing["id"]
            st.session_state["last_video_id"] = vid
            conn.close()
            display_existing_video(vid)
            return {"video_id": vid}

        if existing and force:
            status.info("재처리: 기존 데이터 삭제 중...")
            old_dir = existing["video_data_directory"]
            if old_dir:
                shutil.rmtree(
                    AUDIO_FILES_STORAGE_ROOT_ABS_PATH / old_dir, ignore_errors=True
                )
            delete_video(conn, existing["id"])
            # Clear caches
            cached_segments.clear()
            cached_phrase_analyses.clear()
            cached_kanji.clear()
            cached_kanji_order.clear()
            cached_vocab_map.clear()

        # --- STAGE 1: Download & Transcribe ---
        status.info("1단계: 다운로드 중...")
        temp_dir_obj = tempfile.TemporaryDirectory(prefix="yt_dl_")
        temp_dir = Path(temp_dir_obj.name)

        audio_path, title = download_audio(url, temp_dir)
        if not audio_path:
            status.error("다운로드 실패.")
            return None

        video_id = insert_video(conn, url, title)
        video_dir = f"video_{video_id}"
        video_dir_abs = AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_dir
        (video_dir_abs / "phrases").mkdir(parents=True, exist_ok=True)
        update_video_directory(conn, video_id, video_dir)

        # Slow down full audio
        slowed_fn = f"full_slowed_{video_id}.mp3"
        slowed_path = str(video_dir_abs / slowed_fn)
        slow_down_audio(audio_path, slowed_path)
        update_video_audio(conn, video_id, slowed_fn)

        status.info("2단계: 스크립트 변환 중...")
        transcript = transcribe_audio(audio_path)
        if not transcript:
            status.error("스크립트 변환 실패.")
            return None

        full_text, segments_list = prepare_japanese_segments(transcript)
        if full_text is None:
            status.error("세그먼트 준비 실패.")
            return None

        sync_words = extract_words_for_sync(transcript)
        update_video_transcript(
            conn, video_id, json.dumps(transcript), full_text, json.dumps(sync_words)
        )

        # Insert segments
        for seg_idx, seg in enumerate(segments_list):
            db_id = insert_segment(
                conn,
                video_id,
                seg_idx,
                seg["text"],
                seg["start"],
                seg["end"],
                json.dumps(seg["words"]),
            )
            seg["db_id"] = db_id
        conn.commit()

        # Create tabs
        tabs = st.tabs(["스크립트", "문장", "단어", "한자", "텍스트", "JSON"])
        tab_script, tab_breakdown, tab_vocab, tab_kanji, tab_text, tab_json = tabs

        # Fill tab 1: Full transcript
        with tab_script:
            create_synchronized_player(video_dir, slowed_fn, sync_words)

        # Fill tab 5: Text
        with tab_text:
            st.text_area("전체 텍스트", full_text, height=300, label_visibility="collapsed")

        # Fill tab 6: JSON
        with tab_json:
            st.json(transcript)

        # --- STAGE 2: Claude analysis ---
        status.info("3단계: 구문 분석 시작...")

        with tab_breakdown:
            seg_container = st.container()

        vocab_map = {}
        total = len(segments_list)

        for i, seg in enumerate(segments_list):
            status.info(f"세그먼트 {i+1}/{total} 분석 중...")
            db_seg_id = seg["db_id"]

            analysis = analyze_japanese_segment(
                seg["text"], seg["start"], seg["end"], seg["words"]
            )

            phrases = analysis.get("phrases", [])
            timings = [
                (p.get("original_start_time", 0), p.get("original_end_time", 0))
                for p in phrases
            ]

            # Create phrase audio clips
            audio_map = create_phrase_audio_clips(
                audio_path, timings, video_dir_abs / "phrases", 0.75, db_seg_id
            )

            # Prepare batch insert data
            batch_rows = []
            sync_map = {}
            for p_idx, p_item in enumerate(phrases):
                p_audio_fn = audio_map.get(p_idx)
                p_sync = extract_phrase_words_for_sync(
                    transcript,
                    p_item.get("original_start_time", 0),
                    p_item.get("original_end_time", 0),
                )
                sync_map[p_idx] = p_sync
                collect_vocab_with_kanji({"phrases": [p_item]}, vocab_map, p_sync)
                batch_rows.append(
                    (
                        db_seg_id,
                        p_idx,
                        json.dumps(p_item),
                        p_audio_fn,
                        json.dumps(p_sync),
                    )
                )

            # Batch insert all phrases for this segment
            batch_insert_phrase_analyses(conn, batch_rows)
            conn.commit()

            # Render segment HTML immediately
            with seg_container:
                html = generate_breakdown_html(
                    phrases, audio_map, sync_map, video_dir, db_seg_id
                )
                px = estimate_segment_height(phrases)
                st.components.v1.html(html, height=px, scrolling=True)
                st.markdown(
                    "<hr style='border-top:1.5px solid #ddd;margin:20px 0'>",
                    unsafe_allow_html=True,
                )

        # --- STAGE 3: Kanji & Vocab ---
        status.info("4단계: 한자 추출 중...")
        extract_and_store_kanji(conn, video_id)

        # Populate vocab tab
        populate_vocab_tab(tab_vocab, video_id, video_dir, slowed_fn)

        # Populate kanji tab
        populate_kanji_tab(tab_kanji, video_id)

        status.success("모든 처리 완료!")
        st.session_state["last_video_id"] = video_id

        # Clear caches to pick up new data
        cached_segments.clear()
        cached_phrase_analyses.clear()
        cached_kanji.clear()
        cached_kanji_order.clear()
        cached_vocab_map.clear()

        return {"video_id": video_id, "video_title": title}

    except Exception as e:
        status.error(f"처리 오류: {e}")
        traceback.print_exc()
        return None
    finally:
        conn.close()
        if temp_dir_obj:
            try:
                temp_dir_obj.cleanup()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

st.title("일본어 🇯🇵")

DEEPGRAM_KEY = os.getenv("DEEPGRAM_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

side = st.sidebar
choice = side.radio("", ("Home", "History", "Sources"), index=0)

if not ANTHROPIC_KEY:
    side.error("Anthropic API key missing.")
if not DEEPGRAM_KEY:
    side.error("Deepgram API key missing.")

if choice == "Home":
    url_input = side.text_input("YouTube URL:", placeholder="")
    force = side.checkbox("재처리")
    go = side.button("분석 시작")

    if go:
        if not url_input.strip():
            st.warning("YouTube URL을 입력해주세요.")
        elif not (ANTHROPIC_KEY and DEEPGRAM_KEY):
            st.warning("API 키가 누락되었습니다.")
        else:
            run_full_pipeline(url_input.strip(), force)
    elif "last_video_id" in st.session_state:
        display_existing_video(st.session_state["last_video_id"])

elif choice == "History":
    sidebar_history()

else:
    st.markdown(
        """
### 📰 News
<https://www.youtube.com/@tbsnewsdig/videos>

### 🎙️ Podcast
<https://www.youtube.com/watch?v=wqdtCeFufQc&list=PLkK7KO2TnEczjRVTgW2fSGxRgWay3Z5a4>

### 🎞️ Anime
<https://www.youtube.com/@TMSanimeJP/videos>
"""
    )
