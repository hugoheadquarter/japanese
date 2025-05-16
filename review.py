# review_app.py (Continuing from the cleaner version)
import streamlit as st
import sqlite3
import json
from pathlib import Path
import base64
import os
import sys
import shutil # For deleting directories

# --- Config Import, get_db_connection, CSS, Helper Functions (as before) ---
# ... (Assume these are all present and correct from the previous full code for review_app.py)
# --- Attempt to Load Application Configuration ---


try:
    from config import DB_PATH, AUDIO_FILES_STORAGE_ROOT_ABS_PATH
except ImportError:
    print("CRITICAL ERROR: config.py not found or essential paths are missing.")
    sys.exit(1)

st.set_page_config(layout="wide", page_title="복습")

def get_db_connection():
    if not DB_PATH.exists():
        st.error(f"Database file not found at {DB_PATH}. Please ensure it was created by 'setup_environment.py'.")
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        st.error(f"SQLite connection error: {e}")
        return None

st.markdown("""<style> ... </style>""", unsafe_allow_html=True) # Your full CSS

# --- All your display helper functions (create_synchronized_player, etc.) go here ---
# For brevity, I'm not repeating them, but they are needed.
# Make sure create_phrase_synchronized_player has the font-family fix.
# (Copy them from the previous "FULL CODE NO SNIPPETS" response for review_app.py)

def create_synchronized_player(audio_abs_path_str: str, words_for_sync_list: list, height=700):
    try:
        if not os.path.exists(audio_abs_path_str):
            return "<p style='color:orange; text-align:center; padding:10px;'>Full transcript audio file not found.</p>"
        with open(audio_abs_path_str, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        words_json = json.dumps(words_for_sync_list if words_for_sync_list else [])
        player_id_main = "main-player-instance" 
        audio_id_main = f"audio-{player_id_main}"
        text_id_main = f"text-{player_id_main}"

        html = f"""
        <div id="player-container-{player_id_main}" style="width: 100%; font-family: sans-serif;">
            <audio id="{audio_id_main}" controls style="width: 100%;">
                <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
            </audio>
            <div id="{text_id_main}" style="margin-top: 10px; font-size: 18px; line-height: 1.8; max-height: {height-100}px; overflow-y: auto;"></div>
        </div>
        <script>
        (function() {{
            const words = {words_json};
            const audioPlayer = document.getElementById('{audio_id_main}');
            const textDisplay = document.getElementById('{text_id_main}');
            if (!audioPlayer || !textDisplay) {{ console.error("Main player elements not found for {player_id_main}."); return; }}
            if (!words || words.length === 0) {{ textDisplay.innerHTML = "<p>No transcript words.</p>"; return; }}
            function formatText() {{ 
                let phrases = []; let currentPhrase = []; let lastEnd = 0;
                words.forEach((word, index) => {{
                    const isConnected = index > 0 && Math.abs(word.start - lastEnd) < 0.3;
                    const isPunctuation = ['。', '、', '！', '？'].some(p => word.text.includes(p));
                    currentPhrase.push(word); lastEnd = word.end;
                    if (isPunctuation || (!isConnected && currentPhrase.length > 0)) {{
                        if (currentPhrase.length > 0) {{ phrases.push([...currentPhrase]); currentPhrase = []; }}
                    }}
                }});
                if (currentPhrase.length > 0) {{ phrases.push(currentPhrase); }}
                let mergedPhrases = [];
                for (let i = 0; i < phrases.length; i++) {{
                    const phraseText = phrases[i].map(w => w.text).join('');
                    if (phraseText.length <= 3 && i < phrases.length - 1) {{
                        phrases[i+1] = [...phrases[i], ...phrases[i+1]];
                    }} else {{ mergedPhrases.push(phrases[i]); }}
                }}
                return mergedPhrases;
            }}
            function renderText() {{ 
                textDisplay.innerHTML = ''; const phrases = formatText();
                let overallWordIdx = 0;
                phrases.forEach((phrase) => {{
                    const phraseContainer = document.createElement('div');
                    phraseContainer.style.marginBottom = '10px';
                    phrase.forEach((word) => {{
                        const wordSpan = document.createElement('span');
                        wordSpan.textContent = word.text;
                        wordSpan.id = `word-{player_id_main}-${{overallWordIdx}}`; 
                        overallWordIdx++;
                        wordSpan.style.cursor = 'pointer';
                        wordSpan.style.transition = 'color 0.2s, font-weight 0.2s';
                        wordSpan.onclick = () => {{ audioPlayer.currentTime = word.start; audioPlayer.play().catch(e => console.error("Play error for {player_id_main}:", e)); }};
                        phraseContainer.appendChild(wordSpan);
                    }});
                    textDisplay.appendChild(phraseContainer);
                }});
            }}
            function updateHighlights() {{ 
                const currentTime = audioPlayer.currentTime; let activeWordElement = null;
                let overallWordIdx = 0;
                const phrases = formatText(); 
                phrases.forEach(phrase => {{
                    phrase.forEach(word => {{
                        const wordElement = document.getElementById(`word-{player_id_main}-${{overallWordIdx}}`);
                        overallWordIdx++;
                        if (wordElement) {{
                            if (currentTime >= word.start && currentTime <= word.end) {{
                                wordElement.style.color = '#ff4b4b'; wordElement.style.fontWeight = 'bold';
                                activeWordElement = wordElement;
                            }} else {{ wordElement.style.color = ''; wordElement.style.fontWeight = ''; }}
                        }}
                    }});
                }});
                if (activeWordElement && textDisplay.contains(activeWordElement)) {{
                    const containerRect = textDisplay.getBoundingClientRect();
                    const elementRect = activeWordElement.getBoundingClientRect();
                    if (elementRect.top < containerRect.top + 30 || elementRect.bottom > containerRect.bottom - 30) {{
                         textDisplay.scrollTop += (elementRect.top - containerRect.top - (containerRect.height / 2) + (elementRect.height / 2));
                    }}
                }}
            }}
            renderText(); audioPlayer.addEventListener('timeupdate', updateHighlights);
        }})();
        </script>
        """
        st.components.v1.html(html, height=height)
    except Exception as e:
        st.warning(f"Could not generate main synchronized player: {e}")

def create_phrase_synchronized_player(phrase_audio_abs_path_str: str,
                                      phrase_words_for_sync_list: list,
                                      phrase_unique_id: str,
                                      kanji_map_for_js_str: str):
    try:
        audio_b64 = ""
        audio_available = False
        if phrase_audio_abs_path_str and os.path.exists(phrase_audio_abs_path_str):
            with open(phrase_audio_abs_path_str, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode()
            audio_available = True
        
        words_json = json.dumps(phrase_words_for_sync_list if phrase_words_for_sync_list else [])
        
        player_container_id = f"player-container-phrase-{phrase_unique_id}"
        audio_element_id = f"audio-player-phrase-{phrase_unique_id}" 
        text_display_id = f"text-display-phrase-{phrase_unique_id}"

        audio_html_tag = ""
        if audio_available:
            audio_html_tag = f"""<audio id="{audio_element_id}" loop><source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3"></audio>"""
        
        html_content = f"""
        <div id="{player_container_id}" class="phrase-player">
            {audio_html_tag}
            <div id="{text_display_id}" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif; font-size:30px; line-height:1.8; padding: 5px 10px;">
            </div>
        </div>
        <script>
            (function() {{
                "use strict";
                const wordsForPhrase_{phrase_unique_id} = {words_json};
                const kanjiReadingsMap_{phrase_unique_id} = {kanji_map_for_js_str};
                const audioElement_{phrase_unique_id} = document.getElementById('{audio_element_id}');
                const textDisplayElement_{phrase_unique_id} = document.getElementById('{text_display_id}');

                if (!textDisplayElement_{phrase_unique_id}) {{ console.error("Text display element for phrase {phrase_unique_id} not found."); return; }}
                if (!wordsForPhrase_{phrase_unique_id} || wordsForPhrase_{phrase_unique_id}.length === 0) {{
                    textDisplayElement_{phrase_unique_id}.innerHTML = "<p style='font-size:16px; color:grey; text-align:center;'>No text for this phrase.</p>";
                    return;
                }}
                function generateFuriganaHTMLForText(text, readingsMap) {{
                    let html = '';
                    for (let i = 0; i < text.length; i++) {{
                        const char = text[i]; const charCode = char.charCodeAt(0);
                        const isKanji = ((charCode >= 0x4E00 && charCode <= 0x9FFF) || (charCode >= 0x3400 && charCode <= 0x4DBF) || (charCode >= 0xF900 && charCode <= 0xFAFF) || (charCode >= 0x20000 && charCode <= 0x2A6DF));
                        if (isKanji && readingsMap && readingsMap[char]) {{
                            html += `<ruby><rb>${{char}}</rb><rt>${{readingsMap[char]}}</rt></ruby>`;
                        }} else {{ html += char; }}
                    }}
                    return html;
                }}
                function renderTextForPhrase_{phrase_unique_id}() {{
                    textDisplayElement_{phrase_unique_id}.innerHTML = ''; 
                    const phraseWordsContainer = document.createElement('div');
                    wordsForPhrase_{phrase_unique_id}.forEach((wordObj, idx) => {{ 
                        const wordSpan = document.createElement('span');
                        wordSpan.innerHTML = generateFuriganaHTMLForText(wordObj.text, kanjiReadingsMap_{phrase_unique_id});
                        wordSpan.id = `word-phrase-{phrase_unique_id}-word-${{idx}}`;
                        wordSpan.style.cursor = 'pointer'; wordSpan.style.transition = 'color 0.2s, font-weight 0.2s';
                        wordSpan.style.marginRight = '2px'; 
                        wordSpan.onclick = () => {{ 
                            if (audioElement_{phrase_unique_id}) {{ 
                                audioElement_{phrase_unique_id}.currentTime = wordObj.start; 
                                audioElement_{phrase_unique_id}.play().catch(e => console.warn(`Play attempt error {phrase_unique_id}:`, e)); 
                            }}
                        }};
                        wordSpan.ondblclick = (event) => {{ event.preventDefault(); if (audioElement_{phrase_unique_id}) {{ audioElement_{phrase_unique_id}.pause(); }} }};
                        phraseWordsContainer.appendChild(wordSpan);
                    }});
                    textDisplayElement_{phrase_unique_id}.appendChild(phraseWordsContainer);
                }}
                function updateHighlightsForPhrase_{phrase_unique_id}() {{
                    if (!audioElement_{phrase_unique_id} || !wordsForPhrase_{phrase_unique_id} || wordsForPhrase_{phrase_unique_id}.length === 0) return;
                    const currentTime = audioElement_{phrase_unique_id}.currentTime;
                    wordsForPhrase_{phrase_unique_id}.forEach((wordObj, idx) => {{ 
                        const wordElem = document.getElementById(`word-phrase-{phrase_unique_id}-word-${{idx}}`);
                        if (wordElem) {{
                            if (currentTime >= wordObj.start && currentTime <= wordObj.end) {{
                                wordElem.style.color = '#ff4b4b'; wordElem.style.fontWeight = 'bold';
                            }} else {{ wordElem.style.color = ''; wordElem.style.fontWeight = ''; }}
                        }}
                    }});
                }}
                try {{
                    renderTextForPhrase_{phrase_unique_id}(); 
                    if (audioElement_{phrase_unique_id}) {{
                        audioElement_{phrase_unique_id}.addEventListener('timeupdate', updateHighlightsForPhrase_{phrase_unique_id});
                    }}
                }} catch (e) {{
                    console.error(`Render error for {phrase_unique_id}:`, e);
                    textDisplayElement_{phrase_unique_id}.innerHTML = "<p style='color:red;'>Error initializing player.</p>";
                }}
            }})();
        </script>
        """
        return html_content
    except Exception as e:
        print(f"Python error creating phrase player for {phrase_unique_id}: {str(e)}")
        return f"<div class='phrase-player'><p style='color:red;'>Failed to create player for phrase {phrase_unique_id}.</p></div>"

def generate_breakdown_html_for_segment(conn: sqlite3.Connection,
                                        db_segment_id: int,
                                        video_data_dir_name_from_db: str):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT gpt_phrase_json, phrase_slowed_audio_path, phrase_words_for_sync_json, phrase_index_in_segment
        FROM GptPhraseAnalyses WHERE segment_id = ? ORDER BY phrase_index_in_segment
    """, (db_segment_id,))
    gpt_phrase_analyses_rows = cursor.fetchall()
    if not gpt_phrase_analyses_rows: return "" 

    segment_html_parts = []
    video_specific_audio_root_abs_path = AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_data_dir_name_from_db

    for row_idx, gpt_phrase_row in enumerate(gpt_phrase_analyses_rows):
        gpt_phrase_detail = json.loads(gpt_phrase_row["gpt_phrase_json"])
        phrase_audio_filename = gpt_phrase_row["phrase_slowed_audio_path"]
        phrase_html = ""
        kanji_reading_map = {k_expl["kanji"]: k_expl["reading"] for k_expl in gpt_phrase_detail.get("kanji_explanations", []) if k_expl.get("kanji") and k_expl.get("reading")}
        kanji_map_for_js = json.dumps(kanji_reading_map, ensure_ascii=False)

        phrase_audio_abs_path = None
        if phrase_audio_filename:
            phrase_audio_abs_path = video_specific_audio_root_abs_path / "phrases" / phrase_audio_filename
        
        phrase_sync_words_list = []
        if gpt_phrase_row["phrase_words_for_sync_json"]:
            try: phrase_sync_words_list = json.loads(gpt_phrase_row["phrase_words_for_sync_json"])
            except json.JSONDecodeError: pass
        
        phrase_player_html = create_phrase_synchronized_player(
            str(phrase_audio_abs_path) if phrase_audio_abs_path else None, 
            phrase_sync_words_list,
            f"S{db_segment_id}_P{gpt_phrase_row['phrase_index_in_segment']}", kanji_map_for_js
        )
        phrase_html += phrase_player_html

        phrase_html += "<table style='width: 100%; border-collapse: collapse; margin-bottom: 15px; font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif;'>\n"
        phrase_html += "<tr><th style='border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; background-color: #f2f2f2; font-size: 15px;'>일본어</th><th style='border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; background-color: #f2f2f2; font-size: 15px;'>로마자</th><th style='border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; background-color: #f2f2f2; font-size: 15px;'>품사/설명</th><th style='border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; background-color: #f2f2f2; font-size: 15px;'>한자</th></tr>\n"
        for word in gpt_phrase_detail.get("words", []):
            phrase_html += f"<tr><td style='border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; font-size: 15px;'>{word.get('japanese','')}</td><td style='border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; font-size: 15px;'>{word.get('romaji','')}</td><td style='border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; font-size: 15px;'>{word.get('meaning','')}</td><td style='border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; font-size: 15px;'>{word.get('kanji','')}</td></tr>\n"
        phrase_html += "</table>\n\n"
        
        if gpt_phrase_detail.get("kanji_explanations"):
            phrase_html += "<div style='margin-top: 5px; margin-bottom: 10px; font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif;'>\n"
            phrase_html += "<strong class='section-header-strong'></strong>\n"
            phrase_html += "<ul class='kanji-list'>\n" 
            for kanji in gpt_phrase_detail.get("kanji_explanations", []):
                original_meaning = kanji.get('meaning', ''); formatted_kanji_meaning = original_meaning
                if ' / ' in original_meaning: parts = original_meaning.split(' / ', 1); formatted_kanji_meaning = f"{parts[0]} <strong>{parts[1] if len(parts) > 1 else ''}</strong>"
                phrase_html += f"""<li style="display: flex; align-items: baseline; margin-bottom: 6px; font-size: 15px; line-height: 1.6;"><strong style="flex-basis: 40px; flex-shrink: 0; font-weight: bold; text-align: center;">{kanji.get('kanji','')}</strong><span style="flex-basis: 100px; flex-shrink: 0; color: #4A4A4A; padding-left: 8px; padding-right: 8px;">({kanji.get('reading','')})</span><span style="flex-grow: 1;">{formatted_kanji_meaning}</span></li>"""
            phrase_html += "</ul></div>\n"
        
        if gpt_phrase_detail.get("meaning"):
            phrase_html += "<div class='meaning-paragraph' style='margin-top: 5px; margin-bottom: 15px; font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif;'>\n"
            phrase_html += "<strong class='section-header-strong'></strong>\n"
            phrase_html += f"<p style='font-size: 20px; line-height: 1.6; margin-top: 0px;'>{gpt_phrase_detail.get('meaning','')}</p>\n</div>\n\n"
        
        segment_html_parts.append(phrase_html)
        if row_idx < len(gpt_phrase_analyses_rows) - 1:
            segment_html_parts.append("<hr style='margin-top: 15px; margin-bottom: 15px; border: 0; height: 1px; background-color: #e0e0e0;'>\n\n")
    return "".join(segment_html_parts)

def delete_video_data(conn: sqlite3.Connection, video_id: int):
    """Deletes a video and all its associated data from DB and filesystem."""
    cursor = conn.cursor()
    video_info = cursor.execute("SELECT video_data_directory, video_title FROM Videos WHERE id = ?", (video_id,)).fetchone()
    if not video_info:
        st.error(f"Video with ID {video_id} not found for deletion.")
        return False

    video_data_dir_name = video_info["video_data_directory"]
    video_title = video_info["video_title"]

    try:
        # Using ON DELETE CASCADE, so just deleting from Videos should be enough for DB.
        # However, being explicit can be safer if CASCADE is not guaranteed or for clarity.
        # For GptPhraseAnalyses, which depends on Segments:
        segment_ids_to_delete = [row['id'] for row in cursor.execute("SELECT id FROM Segments WHERE video_id = ?", (video_id,)).fetchall()]
        if segment_ids_to_delete:
            placeholders = ','.join('?' for _ in segment_ids_to_delete)
            cursor.execute(f"DELETE FROM GptPhraseAnalyses WHERE segment_id IN ({placeholders})", segment_ids_to_delete)
        
        cursor.execute("DELETE FROM Segments WHERE video_id = ?", (video_id,))
        cursor.execute("DELETE FROM KanjiEntries WHERE video_id = ?", (video_id,))
        cursor.execute("DELETE FROM Videos WHERE id = ?", (video_id,))
        conn.commit()
        
        # Delete associated audio files directory
        if video_data_dir_name:
            video_specific_dir_abs_path = AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_data_dir_name
            if video_specific_dir_abs_path.exists() and video_specific_dir_abs_path.is_dir():
                shutil.rmtree(video_specific_dir_abs_path)
        
        st.success(f"Successfully deleted all data for video: '{video_title}' (ID: {video_id}).")
        return True
    except Exception as e:
        conn.rollback() # Rollback any partial DB changes if an error occurs
        st.error(f"Error deleting video data for '{video_title}': {e}")
        return False

# --- Main Application UI and Logic ---
conn = get_db_connection()
if conn is None: st.stop()

if 'selected_video_id_review' not in st.session_state:
    st.session_state.selected_video_id_review = None
if 'confirm_delete_video_id' not in st.session_state:
    st.session_state.confirm_delete_video_id = None # To manage delete confirmation

st.sidebar.title("복습")
videos_list = conn.execute("SELECT id, video_title FROM Videos ORDER BY created_at DESC").fetchall()

if not videos_list:
    st.sidebar.info("분석된 영상이 없습니다.")
else:
    video_options_review = {None: "--- 영상 선택 ---"}
    for v_row in videos_list:
        title = v_row["video_title"] if v_row["video_title"] else f"Video ID: {v_row['id']}"
        video_options_review[v_row["id"]] = f"{title[:50]}{'...' if len(title)>50 else ''}"

    chosen_video_id = st.sidebar.selectbox(
        "영상 목록:", options=list(video_options_review.keys()),
        format_func=lambda v_id: video_options_review[v_id],
        key="review_video_select_dropdown_cleanest", index=0
    )
    if chosen_video_id is not None:
        # If selection changes, clear any pending delete confirmation
        if st.session_state.selected_video_id_review != chosen_video_id:
            st.session_state.confirm_delete_video_id = None
        st.session_state.selected_video_id_review = chosen_video_id


if st.session_state.selected_video_id_review is not None:
    video_id_to_display = st.session_state.selected_video_id_review
    video_info = conn.execute("SELECT * FROM Videos WHERE id = ?", (video_id_to_display,)).fetchone()

    if not video_info:
        st.error(f"Error: Could not retrieve details for video ID {video_id_to_display}.")
        st.session_state.selected_video_id_review = None # Reset selection
        st.rerun() # Force a rerun to update UI
    else:
        # Display a small header with video title and a delete button
        col1, col2 = st.columns([0.85, 0.15])
        with col1:
            st.caption(f"{video_info['video_title']}")
        with col2:
            if st.button("🗑️ Delete", key=f"delete_btn_{video_id_to_display}", help="Delete this video and all its analysis data"):
                st.session_state.confirm_delete_video_id = video_id_to_display # Set video ID for confirmation

        # Confirmation dialog for delete
        if st.session_state.confirm_delete_video_id == video_id_to_display:
            st.warning(f"Are you sure you want to permanently delete all data for '{video_info['video_title']}'?")
            col_confirm, col_cancel, _ = st.columns([1,1,5])
            if col_confirm.button("Yes, Delete Permanently", key=f"confirm_delete_yes_{video_id_to_display}"):
                if delete_video_data(conn, video_id_to_display):
                    st.session_state.selected_video_id_review = None
                    st.session_state.confirm_delete_video_id = None
                    st.rerun() # Rerun to refresh the video list and UI
                else: # Deletion failed, error message shown in delete_video_data
                    st.session_state.confirm_delete_video_id = None # Reset confirmation
                    st.rerun()
            if col_cancel.button("Cancel", key=f"confirm_delete_cancel_{video_id_to_display}"):
                st.session_state.confirm_delete_video_id = None
                st.rerun()
        
        # If not in delete confirmation mode, show tabs
        if st.session_state.confirm_delete_video_id != video_id_to_display:
            video_data_dir_name_from_db = video_info["video_data_directory"]
            tab_titles = ["Full Transcript", "Breakdown", "Kanji", "Text", "JSON"]
            tab1, tab2, tab3, tab4, tab5 = st.tabs(tab_titles)

            with tab1:
                full_audio_filename = video_info["full_slowed_audio_path"]
                if full_audio_filename and video_data_dir_name_from_db:
                    full_audio_abs_path = AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_data_dir_name_from_db / full_audio_filename
                    main_sync_words_list = json.loads(video_info["full_words_for_sync_json"] or "[]")
                    create_synchronized_player(str(full_audio_abs_path), main_sync_words_list)

            with tab2:
                dg_segments_rows = conn.execute("SELECT id, segment_index FROM Segments WHERE video_id = ? ORDER BY segment_index", (video_id_to_display,)).fetchall()
                if dg_segments_rows:
                    for dg_segment_row in dg_segments_rows:
                        segment_breakdown_html = generate_breakdown_html_for_segment(conn, dg_segment_row["id"], video_data_dir_name_from_db)
                        if segment_breakdown_html:
                            num_phrases_in_segment = conn.execute("SELECT COUNT(*) FROM GptPhraseAnalyses WHERE segment_id = ?", (dg_segment_row["id"],)).fetchone()[0]
                            html_display_height = max(150, num_phrases_in_segment * 380) 
                            st.components.v1.html(segment_breakdown_html, height=html_display_height, scrolling=True)

            with tab3:
                kanji_entries = conn.execute("SELECT character, reading, meaning FROM KanjiEntries WHERE video_id = ?", (video_id_to_display,)).fetchall()
                if kanji_entries:
                    sorted_kanji_items = sorted(kanji_entries, key=lambda x: x['character'])
                    num_columns_kanji = 2
                    cols_kanji = st.columns(num_columns_kanji)
                    st.markdown('<div class="kanji-card-container">', unsafe_allow_html=True)
                    for idx, kanji_info in enumerate(sorted_kanji_items):
                        with cols_kanji[idx % num_columns_kanji]:
                            k_desc, h_mean = "", ""; original_meaning = kanji_info["meaning"]
                            parts = [] # Define parts before conditional assignment
                            if " / " in original_meaning: parts = original_meaning.split(" / ", 1); k_desc = parts[0];
                            if len(parts) > 1 and len(parts[1]) > 0 : h_mean = parts[1]
                            else: k_desc = original_meaning
                            html_kanji_card = f"""<div class="kanji-card"><div class="kanji-char-display">{kanji_info['character']}</div><div class="kanji-info"><div class="reading"><strong>Reading:</strong> <span class="value">{kanji_info['reading']}</span></div><div class="meaning-korean"><strong>Korean:</strong> <span class="value">{k_desc}</span></div>{'<div class="meaning-hanja"><strong>Hanja:</strong> <span class="value">' + h_mean + '</span></div>' if h_mean else ''}</div></div>"""
                            st.markdown(html_kanji_card, unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)

            with tab4:
                full_text_content = video_info["full_transcript_text"]
                if full_text_content:
                    st.text_area("", full_text_content, height=300, key=f"review_full_text_area_cleaner_{video_id_to_display}", label_visibility="collapsed")
                    st.download_button(label="Download Text", data=full_text_content.encode('utf-8'), file_name=f"{video_info['video_title'] or 'video'}_full_text.txt", mime="text/plain")

            with tab5:
                raw_json_content = video_info["raw_deepgram_response_json"]
                if raw_json_content:
                    try: st.json(json.loads(raw_json_content))
                    except json.JSONDecodeError: st.error("Stored JSON data is corrupted.")
                    st.download_button(label="Download JSON", data=raw_json_content.encode('utf-8'), file_name=f"{video_info['video_title'] or 'video'}_deepgram_response.json", mime="application/json")
else:
    if videos_list:
        st.info("왼쪽 사이드바에서 영상을 선택해주세요.")

if conn:
    conn.close()