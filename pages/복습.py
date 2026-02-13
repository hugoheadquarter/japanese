# pages/복습.py — Review / Replay page
"""Review previously analyzed videos.  Streamlit multipage app."""

from __future__ import annotations

import streamlit as st
import json

st.set_page_config(layout="wide", page_title="복습")

from lib.database import (
    get_all_videos,
    get_video_by_id,
    delete_video,
    get_segments_for_video,
    get_phrase_analyses_for_segment,
    get_all_phrase_analyses_for_video,
    get_kanji_for_video,
    load_kanji_first_occurrences,
)
from lib.storage import delete_storage_folder
from lib.analysis import collect_vocab_with_kanji
from lib.players import (
    create_synchronized_player,
    generate_breakdown_html,
    estimate_segment_height,
    create_vocab_component,
)


# --- Caching ---
@st.cache_data(ttl=600)
def _cached_segments(video_id: int):
    return get_segments_for_video(video_id)


@st.cache_data(ttl=600)
def _cached_phrases(segment_id: int):
    return get_phrase_analyses_for_segment(segment_id)


@st.cache_data(ttl=600)
def _cached_kanji(video_id: int):
    return get_kanji_for_video(video_id)


@st.cache_data(ttl=600)
def _cached_vocab(video_id: int):
    rows = get_all_phrase_analyses_for_video(video_id)
    vocab: dict = {}
    for row in rows:
        pd = row["gpt_phrase_json"]
        if isinstance(pd, str):
            pd = json.loads(pd)
        sw = row.get("phrase_words_for_sync_json")
        if isinstance(sw, str):
            sw = json.loads(sw)
        collect_vocab_with_kanji({"phrases": [pd]}, vocab, sw)
    return vocab


# --- CSS ---
st.markdown("""
<style>
.phrase-player audio{display:none!important;}
div[data-testid="stHtml"]{margin-bottom:0!important;padding-bottom:0!important;}
.stHtml{margin-bottom:0!important;padding-bottom:0!important;}
.element-container:has(iframe){margin-bottom:0!important;padding-bottom:0!important;}
rt{font-size:0.7em;opacity:0.9;user-select:none;}
ul.kanji-list{padding-left:0!important;list-style-type:none!important;}
.kanji-card-container{padding-top:10px;}
.kanji-card{border:1px solid #e0e0e0;padding:20px;margin-bottom:20px;border-radius:10px;
    background:#fff;display:flex;align-items:center;transition:box-shadow 0.2s,transform 0.2s;
    height:180px;box-sizing:border-box;}
.kanji-card:hover{box-shadow:0 8px 16px rgba(0,0,0,0.15);transform:translateY(-3px);}
.kanji-char-display{font-size:4em;font-weight:bold;margin-right:25px;min-width:80px;
    text-align:center;color:#2c3e50;line-height:1;}
.kanji-info{display:flex;flex-direction:column;justify-content:center;font-size:1.1em;flex-grow:1;}
.kanji-info div{margin-bottom:8px;line-height:1.5;display:flex;align-items:baseline;}
.kanji-info strong{font-weight:500;color:#6c757d;margin-right:8px;}
.kanji-info .value{font-weight:600;color:#343a40;}
</style>
""", unsafe_allow_html=True)


# --- State ---
if "sel_vid" not in st.session_state:
    st.session_state.sel_vid = None
if "confirm_del" not in st.session_state:
    st.session_state.confirm_del = None


# --- Sidebar ---
st.sidebar.title("복습")
videos = get_all_videos()

if not videos:
    st.sidebar.info("분석된 영상이 없습니다.")
    st.stop()

options: dict[int | None, str] = {None: "--- 영상 선택 ---"}
for v in videos:
    t = v.get("video_title") or f"Video ID: {v['id']}"
    options[v["id"]] = f"{t[:50]}{'...' if len(t) > 50 else ''}"

chosen = st.sidebar.selectbox(
    "영상 목록:",
    list(options.keys()),
    format_func=lambda k: options[k],
    key="review_select",
)

if chosen is not None:
    if st.session_state.sel_vid != chosen:
        st.session_state.confirm_del = None
    st.session_state.sel_vid = chosen

if st.session_state.sel_vid is None:
    st.info("왼쪽 사이드바에서 영상을 선택해주세요.")
    st.stop()


# --- Main content ---
vid_id = st.session_state.sel_vid
video = get_video_by_id(vid_id)

if not video:
    st.error("영상을 찾을 수 없습니다.")
    st.session_state.sel_vid = None
    st.rerun()

video_dir = video.get("video_data_directory", "")
audio_fn = video.get("full_slowed_audio_path", "")
title = video.get("video_title", "")

# Header with delete
col1, col2 = st.columns([0.85, 0.15])
with col1:
    st.caption(title)
with col2:
    if st.button("🗑️ Delete", key=f"del_{vid_id}"):
        st.session_state.confirm_del = vid_id

# Delete confirmation
if st.session_state.confirm_del == vid_id:
    st.warning(f"'{title}' 의 모든 데이터를 영구 삭제하시겠습니까?")
    c1, c2, _ = st.columns([1, 1, 5])
    if c1.button("Yes, Delete", key=f"yes_del_{vid_id}"):
        delete_video(vid_id)
        if video_dir:
            delete_storage_folder(video_dir)
        st.session_state.sel_vid = None
        st.session_state.confirm_del = None
        _cached_segments.clear()
        _cached_phrases.clear()
        _cached_kanji.clear()
        _cached_vocab.clear()
        st.rerun()
    if c2.button("Cancel", key=f"cancel_del_{vid_id}"):
        st.session_state.confirm_del = None
        st.rerun()
    st.stop()


# --- Tabs ---
tabs = st.tabs(["스크립트", "문장", "단어", "한자", "텍스트", "VIDEO"])
tab1, tab2, tab_vocab, tab3, tab4, tab_video = tabs


# Tab 1: Full transcript
with tab1:
    sync_json = video.get("full_words_for_sync_json")
    if audio_fn and video_dir and sync_json:
        words = sync_json if isinstance(sync_json, list) else json.loads(sync_json)
        create_synchronized_player(video_dir, audio_fn, words)
    else:
        st.info("Audio or transcript data missing.")


# Tab 2: Breakdown
with tab2:
    segments = _cached_segments(vid_id)
    all_html_parts = []
    total_height = 30
    for seg in segments:
        seg_id = seg["id"]
        analyses = _cached_phrases(seg_id)
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

        html = generate_breakdown_html(phrases_data, audio_map, sync_map, video_dir, seg_id)
        all_html_parts.append(html)
        total_height += estimate_segment_height(phrases_data)

    if all_html_parts:
        combined = "".join(all_html_parts)
        st.components.v1.html(combined, height=total_height, scrolling=False)


# Tab 3 (vocab): 단어
with tab_vocab:
    vocab = _cached_vocab(vid_id)
    if not vocab:
        st.info("한자가 포함된 단어가 없습니다.")
    else:
        html = create_vocab_component(vocab, video_dir, audio_fn)
        h = min(800, len(vocab) * 150 + 200)
        st.components.v1.html(html, height=h, scrolling=True)


# Tab 4: Kanji
with tab3:
    entries = _cached_kanji(vid_id)
    if entries:
        order = load_kanji_first_occurrences(vid_id)
        sorted_k = sorted(entries, key=lambda r: order.get(r["character"], (float("inf"), 0)))
        cols = st.columns(4)
        st.markdown('<div class="kanji-card-container">', unsafe_allow_html=True)
        for idx, k in enumerate(sorted_k):
            with cols[idx % 4]:
                k_desc, h_mean = "", ""
                meaning = k.get("meaning", "")
                if " / " in meaning:
                    parts = meaning.split(" / ", 1)
                    k_desc = parts[0]
                    h_mean = parts[1] if len(parts) > 1 else ""
                else:
                    k_desc = meaning
                hanja = f'<div><span class="value">{h_mean}</span></div>' if h_mean else ""
                st.markdown(
                    f"""<div class="kanji-card"><div class="kanji-char-display">{k['character']}</div>
                    <div class="kanji-info"><div><span class="value">{k.get('reading','')}</span></div>
                    <div><span class="value">{k_desc}</span></div>{hanja}</div></div>""",
                    unsafe_allow_html=True,
                )
        st.markdown("</div>", unsafe_allow_html=True)


# Tab 5: Text
with tab4:
    ft = video.get("full_transcript_text")
    if ft:
        st.text_area("", ft, height=300, label_visibility="collapsed")
        st.download_button("Download", ft.encode("utf-8"), f"{title}_text.txt", "text/plain")


# Tab 6: VIDEO
with tab_video:
    import re as _re
    yt_url = video.get("youtube_url", "")
    yt_match = _re.search(r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})', yt_url)
    if yt_match:
        yt_id = yt_match.group(1)
        st.components.v1.html(
            f'<iframe width="100%" height="500" src="https://www.youtube.com/embed/{yt_id}" '
            f'frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
            f'gyroscope; picture-in-picture" allowfullscreen></iframe>',
            height=520,
        )
    else:
        st.warning("YouTube URL을 인식할 수 없습니다.")
        if yt_url:
            st.markdown(f"[YouTube에서 열기]({yt_url})")
