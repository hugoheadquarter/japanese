# jp.py — Main Streamlit Application
"""Japanese Learner App — Cloud version.

Streamlit Cloud + Supabase (PostgreSQL + Storage).
Thin UI layer.  All logic in lib/ modules.
"""

from __future__ import annotations

import streamlit as st
import json
import time
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from lib.ensure_deno import ensure_deno
ensure_deno()

# Page config (must be first st call)s
st.set_page_config(layout="wide", page_title="日本語")


# --- Imports from lib ---
from lib.database import (
    get_all_videos,
    get_video_by_url,
    get_video_by_id,
    insert_video,
    update_video_directory,
    update_video_audio,
    update_video_transcript,
    update_video_debug,
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
from lib.storage import upload_audio, delete_storage_folder
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
# Streamlit caching — wraps Supabase queries with TTL
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600)
def cached_segments(video_id: int) -> list[dict]:
    return get_segments_for_video(video_id)


@st.cache_data(ttl=600)
def cached_phrase_analyses(segment_id: int) -> list[dict]:
    return get_phrase_analyses_for_segment(segment_id)


@st.cache_data(ttl=600)
def cached_kanji(video_id: int) -> list[dict]:
    return get_kanji_for_video(video_id)


@st.cache_data(ttl=600)
def cached_kanji_order(video_id: int) -> dict:
    return load_kanji_first_occurrences(video_id)


@st.cache_data(ttl=600)
def cached_vocab_map(video_id: int) -> dict:
    """Reconstruct vocabulary map from database."""
    rows = get_all_phrase_analyses_for_video(video_id)
    vocab: dict = {}
    for row in rows:
        phrase_data = row["gpt_phrase_json"]
        if isinstance(phrase_data, str):
            phrase_data = json.loads(phrase_data)
        sync_words = row.get("phrase_words_for_sync_json")
        if isinstance(sync_words, str):
            sync_words = json.loads(sync_words)
        collect_vocab_with_kanji({"phrases": [phrase_data]}, vocab, sync_words)
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
div[data-testid="stHtml"]{margin-bottom:0!important;padding-bottom:0!important;}
.stHtml{margin-bottom:0!important;padding-bottom:0!important;}
.element-container:has(iframe){margin-bottom:0!important;padding-bottom:0!important;}
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
    rows = get_all_videos()
    if not rows:
        st.info("분석된 영상이 없습니다.")
        return
    st.markdown("##### 🔍 처리 내역")
    for r in rows:
        title = r.get("video_title") or r.get("youtube_url", "")
        st.markdown(f"- [{title}]({r['youtube_url']})")


# ---------------------------------------------------------------------------
# Tab population helpers
# ---------------------------------------------------------------------------

def populate_transcript_tab(tab, video_dir: str, audio_fn: str, sync_words):
    with tab:
        if audio_fn and video_dir and sync_words:
            # sync_words is already a list (JSONB → Python list via Supabase)
            words = sync_words if isinstance(sync_words, list) else json.loads(sync_words)
            create_synchronized_player(video_dir, audio_fn, words)
        else:
            st.info("스크립트 데이터가 없습니다.")


def populate_breakdown_tab(tab, video_id: int, video_dir: str):
    with tab:
        segments = cached_segments(video_id)
        if not segments:
            st.info("분석 데이터가 없습니다.")
            return

        all_html_parts = []
        total_height = 30

        for seg in segments:
            seg_id = seg["id"]
            analyses = cached_phrase_analyses(seg_id)
            if not analyses:
                continue

            phrases_data = []
            audio_map = {}
            sync_map = {}

            for a in analyses:
                idx = a["phrase_index_in_segment"]
                pd = a["gpt_phrase_json"]
                if isinstance(pd, str):
                    pd = json.loads(pd)
                phrases_data.append(pd)
                audio_map[idx] = a.get("phrase_slowed_audio_path")
                sw = a.get("phrase_words_for_sync_json")
                if isinstance(sw, str):
                    sw = json.loads(sw)
                sync_map[idx] = sw if sw else []

            html = generate_breakdown_html(
                phrases_data, audio_map, sync_map, video_dir, seg_id,
            )
            all_html_parts.append(html)
            total_height += estimate_segment_height(phrases_data)

        if all_html_parts:
            combined = "".join(all_html_parts)
            st.components.v1.html(combined, height=total_height, scrolling=False)


def populate_vocab_tab(tab, video_id: int, video_dir: str, audio_fn: str | None):
    with tab:
        vocab = cached_vocab_map(video_id)
        if not vocab:
            st.info("한자가 포함된 단어가 없습니다.")
            return
        html = create_vocab_component(vocab, video_dir, audio_fn)
        h = min(800, len(vocab) * 150 + 200)
        st.components.v1.html(html, height=h, scrolling=True)


def populate_kanji_tab(tab, video_id: int):
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
                meaning = k.get("meaning", "")
                if " / " in meaning:
                    parts = meaning.split(" / ", 1)
                    k_desc = parts[0]
                    h_mean = parts[1] if len(parts) > 1 else ""
                else:
                    k_desc = meaning
                hanja_div = (
                    f'<div><strong></strong> <span class="value">{h_mean}</span></div>'
                    if h_mean else ""
                )
                st.markdown(
                    f"""<div class="kanji-card">
                    <div class="kanji-char-display">{k['character']}</div>
                    <div class="kanji-info">
                        <div><strong></strong><span class="value">{k.get('reading','')}</span></div>
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


def _extract_youtube_id(url: str) -> str | None:
    import re
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def populate_video_tab(tab, youtube_url: str):
    with tab:
        vid_id = _extract_youtube_id(youtube_url)
        if vid_id:
            st.components.v1.html(
                f'<iframe width="100%" height="500" src="https://www.youtube.com/embed/{vid_id}" '
                f'frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
                f'gyroscope; picture-in-picture" allowfullscreen></iframe>',
                height=520,
            )
        else:
            st.warning("YouTube URL을 인식할 수 없습니다.")
            st.markdown(f"[YouTube에서 열기]({youtube_url})")


# ---------------------------------------------------------------------------
# Display existing analysis
# ---------------------------------------------------------------------------

def display_existing_video(video_id: int):
    video = get_video_by_id(video_id)
    if not video:
        st.error("영상을 찾을 수 없습니다.")
        return

    video_dir = video.get("video_data_directory", "")
    audio_fn = video.get("full_slowed_audio_path", "")
    title = video.get("video_title", "")

    tabs = st.tabs(["스크립트", "문장", "단어", "한자", "텍스트", "VIDEO"])
    tab_script, tab_breakdown, tab_vocab, tab_kanji, tab_text, tab_video = tabs

    populate_transcript_tab(
        tab_script, video_dir, audio_fn,
        video.get("full_words_for_sync_json", []),
    )
    populate_breakdown_tab(tab_breakdown, video_id, video_dir)
    populate_vocab_tab(tab_vocab, video_id, video_dir, audio_fn)
    populate_kanji_tab(tab_kanji, video_id)
    populate_text_tab(tab_text, video.get("full_transcript_text", ""), title)
    populate_video_tab(tab_video, video.get("youtube_url", ""))


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_full_pipeline(url: str, force: bool):
    status = st.empty()
    status.info("1단계: 준비 중...")

    temp_dir_obj = None

    try:
        # Check existing
        existing = get_video_by_url(url)
        if existing and not force:
            status.success(f"'{existing['video_title']}' 이미 분석됨. 결과를 표시합니다.")
            vid = existing["id"]
            st.session_state["last_video_id"] = vid
            display_existing_video(vid)
            return {"video_id": vid}

        if existing and force:
            status.info("재처리: 기존 데이터 삭제 중...")
            old_dir = existing.get("video_data_directory")
            delete_video(existing["id"])
            if old_dir:
                delete_storage_folder(old_dir)
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

        video_id = insert_video(url, title)
        video_dir = f"video_{video_id}"
        update_video_directory(video_id, video_dir)

        # Slow down full audio (locally in temp dir)
        slowed_fn = f"full_slowed_{video_id}.mp3"
        slowed_local = str(temp_dir / slowed_fn)
        slow_down_audio(audio_path, slowed_local)

        # Upload slowed audio to Supabase Storage
        storage_audio_path = f"{video_dir}/{slowed_fn}"
        upload_audio(slowed_local, storage_audio_path)
        update_video_audio(video_id, slowed_fn)

        status.info("2단계: 스크립트 변환 중...")
        transcript = transcribe_audio(audio_path)
        if not transcript:
            status.error("스크립트 변환 실패.")
            return None

        full_text, segments_list, seg_debug = prepare_japanese_segments(transcript)
        if full_text is None:
            status.error("세그먼트 준비 실패.")
            return None

        sync_words = extract_words_for_sync(transcript)
        update_video_transcript(video_id, transcript, full_text, sync_words)

        # Insert segments
        for seg_idx, seg in enumerate(segments_list):
            db_id = insert_segment(
                video_id, seg_idx, seg["text"], seg["start"], seg["end"], seg["words"],
            )
            seg["db_id"] = db_id

        # Create tabs
        tabs = st.tabs(["스크립트", "문장", "단어", "한자", "텍스트", "VIDEO"])
        tab_script, tab_breakdown, tab_vocab, tab_kanji, tab_text, tab_video = tabs

        # Fill tab 1: Full transcript
        with tab_script:
            create_synchronized_player(video_dir, slowed_fn, sync_words)

        # Fill tab 5: Text
        with tab_text:
            st.text_area("전체 텍스트", full_text, height=300, label_visibility="collapsed")

        # Fill tab 6: VIDEO
        populate_video_tab(tab_video, url)

        # Save segmentation debug
        debug_data = {"segmentation": seg_debug, "analyses": []}

        # --- STAGE 2: Claude analysis (concurrent) ---
        status.info("3단계: 구문 분석 시작...")

        vocab_map: dict = {}
        total = len(segments_list)
        all_claude_analyses: list[dict] = []

        contexts = []
        for i in range(total):
            if i >= 2:
                contexts.append(segments_list[i-2]["text"] + " " + segments_list[i-1]["text"])
            elif i >= 1:
                contexts.append(segments_list[i-1]["text"])
            else:
                contexts.append("")

        def analyze_with_retry(seg_index):
            seg = segments_list[seg_index]
            max_retries = 3
            last_error = None
            for attempt in range(max_retries):
                try:
                    result = analyze_japanese_segment(
                        seg["text"], seg["start"], seg["end"], seg["words"],
                        previous_context=contexts[seg_index],
                    )
                    if result and result.get("phrases"):
                        return (seg_index, result, None)
                    last_error = "Empty response from Claude"
                except Exception as e:
                    last_error = str(e)
                    is_rate_limit = "429" in str(e) or "rate" in str(e).lower() or "overloaded" in str(e).lower()
                    if attempt < max_retries - 1:
                        if is_rate_limit:
                            wait = (5 * (attempt + 1)) + (2 * seg_index % 10)
                        else:
                            wait = (2 ** attempt) + (0.5 * attempt)
                        time.sleep(wait)
            return (seg_index, {"phrases": []}, last_error)

        analysis_results: list[dict | None] = [None] * total
        completed_count = 0

        with ThreadPoolExecutor(max_workers=min(50, total)) as executor:
            futures = {
                executor.submit(analyze_with_retry, i): i
                for i in range(total)
            }
            for future in as_completed(futures):
                seg_idx_done, analysis, error = future.result()
                analysis_results[seg_idx_done] = analysis
                completed_count += 1
                if error:
                    status.warning(f"세그먼트 {seg_idx_done+1}/{total}: 재시도 실패 - {error}")
                else:
                    status.info(f"구문 분석 {completed_count}/{total} 완료...")

        # --- Process results: audio clips, DB, HTML ---
        status.info("3단계: 오디오 클립 생성 및 저장 중...")

        # Create temp dir for phrase clips
        phrases_local_dir = temp_dir / "phrases"
        phrases_local_dir.mkdir(exist_ok=True)

        all_html_parts = []
        total_height = 30

        for i, seg in enumerate(segments_list):
            db_seg_id = seg["db_id"]
            analysis = analysis_results[i]

            all_claude_analyses.append({
                "segment_index": i,
                "segment_text": seg["text"],
                "claude_response": analysis,
            })

            phrases = analysis.get("phrases", [])
            if not phrases:
                continue

            timings = [
                (p.get("original_start_time", 0), p.get("original_end_time", 0))
                for p in phrases
            ]

            # Create phrase audio clips locally
            audio_map = create_phrase_audio_clips(
                audio_path, timings, phrases_local_dir, 0.75, db_seg_id,
            )

            # Upload each phrase clip to Supabase Storage
            for p_idx, local_fn in audio_map.items():
                if local_fn:
                    local_fp = str(phrases_local_dir / local_fn)
                    storage_path = f"{video_dir}/phrases/{local_fn}"
                    try:
                        upload_audio(local_fp, storage_path)
                    except Exception as exc:
                        print(f"[UPLOAD] Failed phrase clip {local_fn}: {exc}")
                        audio_map[p_idx] = None

            # Prepare batch insert
            batch_rows = []
            sync_map: dict[int, list] = {}
            for p_idx, p_item in enumerate(phrases):
                p_audio_fn = audio_map.get(p_idx)
                p_sync = extract_phrase_words_for_sync(
                    transcript,
                    p_item.get("original_start_time", 0),
                    p_item.get("original_end_time", 0),
                )
                sync_map[p_idx] = p_sync
                collect_vocab_with_kanji({"phrases": [p_item]}, vocab_map, p_sync)
                batch_rows.append({
                    "segment_id": db_seg_id,
                    "phrase_index_in_segment": p_idx,
                    "gpt_phrase_json": p_item,           # dict → JSONB
                    "phrase_slowed_audio_path": p_audio_fn,
                    "phrase_words_for_sync_json": p_sync, # list → JSONB
                })

            batch_insert_phrase_analyses(batch_rows)

            # Collect HTML
            html = generate_breakdown_html(
                phrases, audio_map, sync_map, video_dir, db_seg_id,
            )
            all_html_parts.append(html)
            total_height += estimate_segment_height(phrases)

        # Render breakdown
        if all_html_parts:
            with tab_breakdown:
                combined = "".join(all_html_parts)
                st.components.v1.html(combined, height=total_height, scrolling=False)

        # Save debug
        debug_data["analyses"] = all_claude_analyses
        update_video_debug(video_id, debug_data)

        # --- STAGE 3: Kanji & Vocab ---
        status.info("4단계: 한자 추출 중...")
        extract_and_store_kanji(video_id)

        populate_vocab_tab(tab_vocab, video_id, video_dir, slowed_fn)
        populate_kanji_tab(tab_kanji, video_id)

        status.success("모든 처리 완료!")
        st.session_state["last_video_id"] = video_id

        # Clear caches
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
        if temp_dir_obj:
            try:
                temp_dir_obj.cleanup()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

st.title("일본어 🇯🇵")

DEEPGRAM_KEY = st.secrets.get("DEEPGRAM_API_KEY")
ANTHROPIC_KEY = st.secrets.get("ANTHROPIC_API_KEY")

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
