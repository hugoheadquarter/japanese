# analysis_app.py
import streamlit as st
import yt_dlp
import os
import requests
import json
import tempfile
import base64
from dotenv import load_dotenv
from pydub import AudioSegment
from openai import OpenAI
import re
import time
import sqlite3
from pathlib import Path
import shutil 
import traceback
import sys # For sys.exit

# Set page config here (once only)
st.set_page_config(page_title="動画分析")

# Load environment variables early
load_dotenv()
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Import fuzzy matching early so it's available to all helper functions
try:
    from rapidfuzz import process, fuzz
    FUZZY_MATCHING_AVAILABLE = True
except ImportError:
    FUZZY_MATCHING_AVAILABLE = False
    # print("[INFO] RapidFuzz not installed.")

# --- Application Configuration & Setup ---
try:
    from config import DB_PATH, AUDIO_FILES_STORAGE_ROOT_ABS_PATH, BASE_APP_DATA_DIR
except ImportError:
    print("CRITICAL ERROR: config.py not found or essential paths are missing.")
    print("Please ensure config.py exists and defines DB_PATH, AUDIO_FILES_STORAGE_ROOT_ABS_PATH, BASE_APP_DATA_DIR.")
    sys.exit(1)

# --- Database Connection ---
def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        st.error(f"Database connection error: {e}")
        return None

# OpenAI client setup
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    client = None

# --- CSS ---
st.markdown("""
<style>
    /* Global font settings for consistency */
    body, h1, h2, h3, h4, h5, h6, p, td, th, li, div, ul, ol {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif !important;
    }
    .stAudio { margin-bottom: 0 !important; width: 100% !important; }
    .stAudio > div { height: 40px !important; width: 100% !important; }
    rt { font-size: 0.7em; opacity: 0.9; user-select: none; }
    div[id^="player-container-main-player-instance"] audio { height: 30px !important; width: 100% !important; display: block !important; }
    .phrase-player audio[id^="audio-player-phrase-"] { display: none !important; }
    .phrase-player div[id^="text-display-phrase-"] { margin-top: 0px !important; padding-top: 5px; }
    .column-divider { border-right: 1px solid #e0e0e0; height: 100%; padding-right: 10px; }
    h3 { font-size: 18px !important; line-height: 1.6 !important; padding-left: 10px !important; margin-top: 20px !important; font-weight: 600 !important; }
    h2 { font-size: 22px !important; font-weight: bold !important; margin-bottom: 15px !important; padding: 8px !important; border-radius: 5px !important; background-color: #f8f8f8 !important; }
    table { width: 100% !important; margin-bottom: 15px !important; border-collapse: collapse !important; }
    th, td { border: 1px solid #e0e0e0 !important; padding: 8px 12px !important; text-align: left !important; font-size: 14px !important; line-height: 1.5 !important; }
    th { background-color: #f2f2f2 !important; font-weight: 600 !important; }
    .section-header-strong { display: block !important; margin-top: 15px !important; margin-bottom: 5px !important; font-weight: 600 !important; font-size: 15px !important; }
    ul.kanji-list { margin-top: 5px !important; padding-left: 0px !important; list-style-type: none !important; }
    ul.kanji-list li { font-size: 14px !important; line-height: 1.6 !important; margin-bottom: 4px !important; }
    div.meaning-paragraph p { font-size: 20px !important; line-height: 1.6 !important; margin-top: 5px !important; }
    hr { margin-top: 20px !important; margin-bottom: 20px !important; border: 0 !important; height: 1px !important; background-color: #e0e0e0 !important; }
    .stColumn > div { padding-left: 0 !important; padding-right: 0 !important; }
    .phrase-player { margin-bottom: 15px !important; border-radius: 4px !important; overflow: hidden !important; }
    @media (prefers-color-scheme: dark) {
        th { background-color: #2e2e2e !important; }
        th, td { border-color: #4e4e4e !important; }
        h2 { background-color: #2a2a2a !important; }
        hr { background-color: #3e3e3e !important; }
        .kanji-card { background-color: #262626; border-color: #444444; }
        .kanji-char-display { color: #e8e8e8; }
        .kanji-info strong { color: #adb5bd; }
        .kanji-info .value { color: #f1f1f1; }
        .kanji-info .reading .value { color: #8ab4f8; }
        .kanji-info .meaning-korean .value { color: #81c995; }
        .kanji-info .meaning-hanja .value { color: #f28b82; font-weight: bold; }
    }
    .kanji-card-container { padding-top: 10px; }
    .kanji-card { border: 1px solid #e0e0e0; padding: 20px; margin-bottom: 20px; border-radius: 10px; background-color: #ffffff; display: flex; align-items: center; transition: box-shadow 0.2s ease-in-out, transform 0.2s ease-in-out; height: 100%; box-sizing: border-box; }
    .kanji-card:hover { box-shadow: 0 8px 16px rgba(0,0,0,0.15); transform: translateY(-3px); }
    .kanji-char-display { font-size: 4em; font-weight: bold; margin-right: 25px; min-width: 80px; text-align: center; color: #2c3e50; line-height: 1; }
    .kanji-info { display: flex; flex-direction: column; justify-content: center; font-size: 1.1em; flex-grow: 1; }
    .kanji-info div { margin-bottom: 8px; line-height: 1.5; display: flex; align-items: baseline; }
    .kanji-info div:last-child { margin-bottom: 0; }
    .kanji-info strong { font-weight: 500; color: #6c757d; margin-right: 8px; min-width: 70px; display: inline-block; }
    .kanji-info .value { font-weight: 600; color: #343a40; }
</style>
""", unsafe_allow_html=True)

# --- Helper Function Definitions ---
def download_audio(url, output_dir_path: Path):
    output_dir_path.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        'outtmpl': str(output_dir_path / '%(title)s.%(ext)s'), 'verbose': False, 'noplaylist': True,
        'nocheckcertificate': True, 'retries': 10, 'fragment_retries': 10,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            original_title = info.get('title', 'video')
            mp3_files = list(output_dir_path.glob("*.mp3"))
            filepath = None
            if mp3_files: filepath = max(mp3_files, key=os.path.getctime) # Get most recent
            if not filepath: st.error("MP3 file not found after download."); return None, None
            return str(filepath), original_title
    except Exception as e: st.error(f"Download error: {e}"); return None, None

def slow_down_audio(input_audio_path_str: str, output_audio_path_str: str, speed_factor=0.75):
    try:
        input_path, output_path = Path(input_audio_path_str), Path(output_audio_path_str)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        audio = AudioSegment.from_file(str(input_path))
        temp_stretched_filename = f"temp_stretched_{output_path.name}" # Unique temp name
        temp_file_path = output_path.parent / temp_stretched_filename
        audio.export(str(temp_file_path), format="mp3", parameters=["-filter:a", f"atempo={speed_factor}"])
        os.rename(str(temp_file_path), str(output_path))
        return str(output_path)
    except Exception as e:
        st.error(f"Slow down error for '{Path(input_audio_path_str).name}': {e}")
        # Fallback: copy original if slowing fails
        if os.path.exists(input_audio_path_str):
            shutil.copy(input_audio_path_str, output_audio_path_str)
            return output_audio_path_str
        return None

def transcribe_audio(audio_path_str: str):
    if not DEEPGRAM_API_KEY: st.error("Deepgram API key missing."); return None
    headers = {'Authorization': f'Token {DEEPGRAM_API_KEY}', 'Content-Type': 'audio/mp3'}
    url = 'https://api.deepgram.com/v1/listen?model=nova-2&language=ja&smart_format=true&punctuation=true&utterances=true'
    try:
        with open(audio_path_str, 'rb') as audio_file: response = requests.post(url, headers=headers, data=audio_file)
        if response.status_code == 200: return response.json()
        else:
            st.error(f"Deepgram (nova-2) Error: {response.status_code} - {response.text[:200]}");
            if "No such model" in response.text or response.status_code == 400:
                alt_url = 'https://api.deepgram.com/v1/listen?model=general&tier=enhanced&language=ja&smart_format=true&punctuation=true&utterances=true'
                with open(audio_path_str, 'rb') as af_alt: response_alt = requests.post(alt_url, headers=headers, data=af_alt)
                if response_alt.status_code == 200: return response_alt.json()
                else: st.error(f"Deepgram (fallback) Error: {response_alt.status_code} - {response_alt.text[:200]}")
            return None
    except Exception as e: st.error(f"Transcription exception: {e}"); return None

def prepare_japanese_segments(transcript_data):
    try:
        if not transcript_data or not transcript_data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("words"):
            st.warning("Transcript data structure issue for segmentation."); return "", []
        full_transcript = transcript_data["results"]["channels"][0]["alternatives"][0].get("transcript", "").replace(" ", "")
        all_words = transcript_data["results"]["channels"][0]["alternatives"][0].get("words", [])
        if not all_words: return full_transcript, []
            
        initial_segments, current_segment_words, MAX_WORDS_PER_SEGMENT = [], [], 30
        for i, word_info in enumerate(all_words):
            current_segment_words.append(word_info)
            word_text = word_info.get('punctuated_word', word_info['word']).strip()
            is_punct = '。' in word_text or '？' in word_text or '！' in word_text
            is_max_len = len(current_segment_words) >= MAX_WORDS_PER_SEGMENT
            form_now = is_punct or is_max_len or (i == len(all_words) - 1 and current_segment_words)
            if form_now and current_segment_words:
                start_t = current_segment_words[0]['start']; end_t = current_segment_words[-1]['end']
                text_c = "".join([w.get('punctuated_word', w.get('word', '')).strip().replace(" ", "") for w in current_segment_words])
                initial_segments.append({'start': start_t, 'end': end_t, 'text': text_c, 'words': [dict(w) for w in current_segment_words]})
                current_segment_words = []
        if current_segment_words:
            start_t = current_segment_words[0]['start']; end_t = current_segment_words[-1]['end']
            text_c = "".join([w.get('punctuated_word', w.get('word', '')).strip().replace(" ", "") for w in current_segment_words])
            initial_segments.append({'start': start_t, 'end': end_t, 'text': text_c, 'words': [dict(w) for w in current_segment_words]})
        return full_transcript, initial_segments
    except Exception as e: st.error(f"Segment prep error: {e}"); print(traceback.format_exc()); return None, []

def extract_words_for_sync(transcript_data, speed_factor=0.75, time_offset=0.3):
    try:
        if not transcript_data or not transcript_data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("words",[]): return []
        words, raw_words = [], transcript_data["results"]["channels"][0]["alternatives"][0]["words"]
        adj = 1 / speed_factor
        for word in raw_words:
            s, e_time = word.get("start",0)*adj, word.get("end",0)*adj
            words.append({"text":word.get("punctuated_word",word.get("word","")), "start":max(0,s-time_offset), "end":max(0.01,e_time-time_offset)})
        return words
    except Exception as e: st.warning(f"Word sync extract error: {e}"); return []

def extract_phrase_words_for_sync(transcript_data, phrase_start_orig, phrase_end_orig, speed_factor=0.75, time_offset=0.3):
    try:
        if not transcript_data or not transcript_data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("words",[]): return []
        p_words, raw_words = [], transcript_data["results"]["channels"][0]["alternatives"][0]["words"]
        adj = 1 / speed_factor
        for word in raw_words:
            ws, we = word.get("start",0), word.get("end",0)
            if we >= phrase_start_orig and ws <= phrase_end_orig:
                rs, re_ = (ws-phrase_start_orig)*adj, (we-phrase_start_orig)*adj
                p_words.append({"text":word.get("punctuated_word",word.get("word","")), "start":max(0,rs-time_offset), "end":max(0.01,re_-time_offset)})
        return p_words
    except Exception as e: st.warning(f"Phrase word sync extract error: {e}"); return []

def normalize_japanese(text): return re.sub(r'[「」『』（）\(\)]', '', text.replace(" ", "")).strip() if text else ""

def align_gpt_phrase_to_deepgram_words(gpt_phrase_text, deepgram_segment_words, min_match_score=70):
    if not gpt_phrase_text or not deepgram_segment_words: return 0,0,0
    norm_phrase = normalize_japanese(gpt_phrase_text);
    if not norm_phrase: return 0,0,0
    if FUZZY_MATCHING_AVAILABLE: return _align_with_fuzzy_matching(norm_phrase, deepgram_segment_words, min_match_score)
    else: return _align_with_fallback(norm_phrase, deepgram_segment_words)

def _align_with_fuzzy_matching(normalized_phrase, deepgram_words, min_match_score):
    bs, bsi, bei = 0,0,0
    for ws in range(1, len(deepgram_words)+1):
        for si in range(len(deepgram_words)-ws+1):
            ee = si+ws; ww = deepgram_words[si:ee]
            wt = "".join([normalize_japanese(w.get('punctuated_word', w.get('word',''))) for w in ww])
            if not wt: continue
            sc = fuzz.ratio(normalized_phrase, wt); adj_sc = sc * (1 + 0.01 * len(wt))
            if adj_sc > bs: bs, bsi, bei = adj_sc, si, ee-1
    if bs >= min_match_score and bei < len(deepgram_words): return deepgram_words[bsi]['start'], deepgram_words[bei]['end'], bs
    if deepgram_words: return deepgram_words[0]['start'], deepgram_words[-1]['end'], 0
    return 0,0,0
    
def _align_with_fallback(normalized_phrase, deepgram_words):
    ft = "".join([normalize_japanese(w.get('punctuated_word', w.get('word',''))) for w in deepgram_words])
    if not ft: return 0,0,0
    pos = ft.find(normalized_phrase)
    if pos >=0:
        cs, ce, swi, ewi, cp = pos, pos+len(normalized_phrase)-1, None, None, 0
        for i,w_obj in enumerate(deepgram_words):
            wt_norm = normalize_japanese(w_obj.get('punctuated_word',w_obj.get('word','')))
            ncp = cp + len(wt_norm)
            if swi is None and cp <= cs < ncp: swi = i
            if cp <= ce < ncp: ewi=i; break
            cp = ncp
        if swi is not None and ewi is not None: return deepgram_words[swi]['start'], deepgram_words[ewi]['end'], 100
    if deepgram_words: return deepgram_words[0]['start'], deepgram_words[-1]['end'], 0
    return 0,0,0

def assign_phrase_timings(sentence_text, phrases_from_gpt, sentence_start_time, sentence_end_time):
    clean_sentence = normalize_japanese(sentence_text)
    if not clean_sentence: return [(sentence_start_time, sentence_end_time)] * len(phrases_from_gpt)
    sentence_duration = sentence_end_time - sentence_start_time; phrase_timings = []; current_char_offset = 0
    for i, phrase_obj in enumerate(phrases_from_gpt):
        clean_phrase = normalize_japanese(phrase_obj["text"])
        if not clean_phrase: 
            est_start = sentence_start_time + (sentence_duration * (i / len(phrases_from_gpt) if len(phrases_from_gpt) > 0 else 0))
            est_end = sentence_start_time + (sentence_duration * ((i + 1) / len(phrases_from_gpt) if len(phrases_from_gpt) > 0 else 1))
            phrase_timings.append((est_start, est_end)); continue
        position = clean_sentence.find(clean_phrase, current_char_offset)
        if position != -1:
            start_ratio = position/len(clean_sentence); end_ratio = (position+len(clean_phrase))/len(clean_sentence)
            start_time = sentence_start_time + (sentence_duration*start_ratio)-0.1; end_time = sentence_start_time+(sentence_duration*end_ratio)+0.1
            start_time=max(sentence_start_time,start_time); end_time=min(sentence_end_time,end_time); current_char_offset=position+len(clean_phrase)
        else: 
            start_ratio=i/len(phrases_from_gpt) if len(phrases_from_gpt) > 0 else 0
            end_ratio=(i+1)/len(phrases_from_gpt) if len(phrases_from_gpt) > 0 else 1
            start_time=sentence_start_time+(sentence_duration*start_ratio); end_time=sentence_start_time+(sentence_duration*end_ratio)
        phrase_timings.append((start_time, end_time))
    return phrase_timings

def create_phrase_audio_segments(original_full_audio_path_str, gpt_phrases_list, timings_list, phrase_output_dir_abs_path, speed_factor, db_segment_id_for_naming):
    phrase_audio_filenames = {}
    if not os.path.exists(original_full_audio_path_str): return phrase_audio_filenames
    try:
        phrase_output_dir_abs_path.mkdir(parents=True,exist_ok=True); main_audio=AudioSegment.from_mp3(original_full_audio_path_str)
        for i, phrase_detail in enumerate(gpt_phrases_list):
            if i >= len(timings_list): continue
            ost_s, oet_s = timings_list[i]; sms,ems = int(ost_s*1000), int(oet_s*1000)
            sms,ems = max(0,sms-150), min(len(main_audio),ems+150)
            if sms >= ems: phrase_audio_filenames[i]=None; continue
            phrase_seg = main_audio[sms:ems]
            temp_fn = f"temp_orig_S{db_segment_id_for_naming}_P{i}.mp3"; temp_fp = phrase_output_dir_abs_path/temp_fn
            phrase_seg.export(str(temp_fp),format="mp3")
            slowed_fn = f"phrase_S{db_segment_id_for_naming}_P{i}.mp3"; final_fp = phrase_output_dir_abs_path/slowed_fn
            slowed_audio_path = slow_down_audio(str(temp_fp),str(final_fp),speed_factor)
            if slowed_audio_path: phrase_audio_filenames[i]=slowed_fn
            else: phrase_audio_filenames[i]=None # Indicate failure
            try: os.remove(str(temp_fp))
            except OSError: pass
        return phrase_audio_filenames
    except Exception as e: st.error(f"Phrase audio error S{db_segment_id_for_naming}: {e}"); return {idx:None for idx in range(len(gpt_phrases_list))}

def create_fallback_json(segment_text):
    kanji_chars=[c for c in segment_text if 0x4E00<=ord(c)<=0x9FFF]; ke=[{"kanji":c,"reading":"","meaning":"분석 실패"} for c in kanji_chars]
    return {"phrases":[{"number":1,"text":segment_text,"words":[{"japanese":segment_text,"kanji":"".join(kanji_chars),"romaji":"","meaning":"분석 실패"}],"kanji_explanations":ke,"meaning":segment_text}]}

def analyze_japanese_segment(segment_text, segment_start_orig_time, segment_end_orig_time, deepgram_segment_words):
    if not client: st.error("OpenAI client not set."); return create_fallback_json(segment_text)
    prompt = """You are an expert Japanese language analyst and tutor for Korean learners. Your task is to take a Japanese sentence, break it down into smaller, grammatically logical phrases or clauses, and then provide a detailed analysis for EACH phrase/clause.

Return your analysis as a JSON object with the following structure:
{
  "phrases": [
    {
      "number": 1,
      "text": "phrase text here",
      "words": [
        {
          "japanese": "word in Japanese",
          "kanji": "kanji if used, otherwise empty string",
          "romaji": "romaji transcription",
          "meaning": "Korean meaning/explanation"
        }
      ],
      "kanji_explanations": [
        {
          "kanji": "大", 
          "reading": "だい", 
          "meaning": "클 / 대"
        }
      ],
      "meaning": "Korean translation of the phrase"
    }
  ]
}
Guidelines:
1. Break the sentence into natural grammatical phrases or clauses. Try to make phrases shorter than 15 Japanese characters if possible, but prioritize grammatical soundness.
2. Number each phrase sequentially (1, 2, 3, etc.).
3. For each phrase, break down all words, particles, and verb endings.
4. For each word, provide:
   - japanese: The word in Japanese.
   - kanji: The kanji characters if used (empty string if none).
   - romaji: Hepburn romanization.
   - meaning: Korean equivalent and grammatical explanation. Be concise.
5. For kanji_explanations, list ONLY kanji used in the current phrase.
   - Include the kanji character, its reading as used in this context, and Korean meaning (e.g., "클 / 대" where "클" is Korean descriptive meaning and "대" is the Hanja character's sound).
6. Provide a natural Korean translation of each phrase. It should be a direct translation of the Japanese phrase.

Example analysis for this sentence: "ロシア大統領府によりますと代表団は2022年の停戦交渉にあたった"
Your JSON should look similar to:
{
  "phrases": [
    {
      "number": 1,
      "text": "ロシア大統領府によりますと",
      "words": [
        {"japanese": "ロシア", "kanji": "", "romaji": "Roshia", "meaning": "러시아"},
        {"japanese": "大統領府", "kanji": "大統領府", "romaji": "Daitōryōfu", "meaning": "대통령부"},
        {"japanese": "に", "kanji": "", "romaji": "ni", "meaning": "~에"},
        {"japanese": "よりますと", "kanji": "", "romaji": "yorimasu to", "meaning": "~의하면"}
      ],
      "kanji_explanations": [
        {"kanji": "大", "reading": "だい", "meaning": "클 / 대"},
        {"kanji": "統", "reading": "とう", "meaning": "거느릴 / 통"},
        {"kanji": "領", "reading": "りょう", "meaning": "거느릴 / 령"},
        {"kanji": "府", "reading": "ふ", "meaning": "마을 / 부"}
      ],
      "meaning": "러시아 대통령부에 의하면"
    },
    {
      "number": 2,
      "text": "代表団は",
      "words": [
        {"japanese": "代表団", "kanji": "代表団", "romaji": "Daihyōdan", "meaning": "대표단"},
        {"japanese": "は", "kanji": "", "romaji": "wa", "meaning": "~은/는"}
      ],
      "kanji_explanations": [
        {"kanji": "代", "reading": "だい", "meaning": "대신할 / 대"},
        {"kanji": "表", "reading": "ひょう", "meaning": "겉 / 표"},
        {"kanji": "団", "reading": "だん", "meaning": "둥글 / 단"}
      ],
      "meaning": "대표단은"
    },
    {
    "number": 3,
    "text": "2022年の停戦交渉にあたった",
    "words": [
        {"japanese": "2022年", "kanji": "年", "romaji": "nisen nijūni nen", "meaning": "2022년"},
        {"japanese": "の", "kanji": "", "romaji": "no", "meaning": "~의"},
        {"japanese": "停戦交渉", "kanji": "停戦交渉", "romaji": "teisen kōshō", "meaning": "정전교섭"},
        {"japanese": "に", "kanji": "", "romaji": "ni", "meaning": "~에"},
        {"japanese": "あたった", "kanji": "", "romaji": "atatta", "meaning": "임했다, 담당했다 (当たる의 과거형)"}
    ],
    "kanji_explanations": [
        {"kanji": "年", "reading": "ねん", "meaning": "해 / 년"},
        {"kanji": "停", "reading": "てい", "meaning": "머무를 / 정"},
        {"kanji": "戦", "reading": "せん", "meaning": "싸울 / 전"},
        {"kanji": "交", "reading": "こう", "meaning": "사귈 / 교"},
        {"kanji": "渉", "reading": "しょう", "meaning": "건널 / 섭"}
    ],
    "meaning": "2022년의 정전교섭에 임했다"
    }
    ...continue
  ]
}
Ensure your JSON is well-formed and follows this exact structure. Provide ONLY the JSON object as the response.
"""
    max_retries=2; retry_delay=3
    for attempt in range(max_retries):
        try:
            response=client.chat.completions.create(model="gpt-4o",messages=[{"role":"system","content":prompt},{"role":"user","content":f"Analyze this Japanese segment: {segment_text}"}],max_tokens=4090,temperature=0.1,response_format={"type":"json_object"}) # Increased max_tokens
            gpt_data=json.loads(response.choices[0].message.content)
            if "phrases" in gpt_data and deepgram_segment_words:
                for p_detail in gpt_data["phrases"]:
                    s_orig,e_orig,m_score=align_gpt_phrase_to_deepgram_words(p_detail.get("text",""),deepgram_segment_words)
                    p_detail["original_start_time"]=s_orig;p_detail["original_end_time"]=e_orig;p_detail["match_score"]=m_score
            elif "phrases" in gpt_data:
                p_timings=assign_phrase_timings(segment_text,gpt_data["phrases"],segment_start_orig_time,segment_end_orig_time)
                for i,p_detail in enumerate(gpt_data["phrases"]): p_detail["original_start_time"]=p_timings[i][0];p_detail["original_end_time"]=p_timings[i][1];p_detail["match_score"]=0
            return gpt_data
        except json.JSONDecodeError as e_json: st.warning(f"GPT JSON parse error (try {attempt+1}): {e_json}"); time.sleep(retry_delay*(attempt+1))
        except Exception as e_gpt: st.error(f"GPT analysis error (try {attempt+1}): {e_gpt}"); time.sleep(retry_delay*(attempt+1))
    return create_fallback_json(segment_text)

def create_synchronized_player(audio_abs_path_str: str, words_for_sync_list: list, height=700):
    """
    Creates the main HTML5 player with synchronized text highlighting.
    Audio path is absolute.
    """
    try:
        if not os.path.exists(audio_abs_path_str):
            # For the main player, an error message in the UI is appropriate
            st.error(f"Main audio file not found: {audio_abs_path_str}")
            return # Don't generate HTML if audio is missing
            
        with open(audio_abs_path_str, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        
        words_json = json.dumps(words_for_sync_list if words_for_sync_list else [])
        
        # Using a more unique base ID for player elements to avoid any theoretical collisions
        player_instance_id = f"main-transcript-player-{int(time.time()*1000)}"
        audio_element_id = f"audio-{player_instance_id}"
        text_display_id = f"text-display-{player_instance_id}"
        container_id = f"player-container-{player_instance_id}"

        html = f"""
        <div id="{container_id}" style="width: 100%; font-family: sans-serif;">
            <audio id="{audio_element_id}" controls style="width: 100%;">
                <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
                Your browser does not support the audio element.
            </audio>
            <div id="{text_display_id}" 
                 style="margin-top: 10px; font-size: 18px; line-height: 1.8; max-height: {height-100}px; overflow-y: auto; padding: 5px;">
                {'' if words_for_sync_list else '<p style="color:grey;text-align:center;">No transcript data to display.</p>'}
            </div>
        </div>

        <script>
        (function() {{ // IIFE to encapsulate scope
            "use strict";
            const wordsData = {words_json};
            const audioPlayer = document.getElementById('{audio_element_id}');
            const textDisplay = document.getElementById('{text_display_id}');

            if (!audioPlayer || !textDisplay) {{
                console.error("Main synchronized player elements not found: {audio_element_id} or {text_display_id}");
                return;
            }}

            if (!wordsData || wordsData.length === 0) {{
                // textDisplay.innerHTML = "<p style='color:grey;text-align:center;'>No transcript words to display.</p>"; // Already handled by Python conditional rendering
                return; // No words, no player logic needed
            }}

            // Groups words into logical phrases for display
            function formatTextIntoPhrases(wordsArray) {{
                let phrases = [];
                let currentPhraseWords = [];
                let lastWordEndTime = 0;

                wordsArray.forEach((word, index) => {{
                    const isConnectedToPrevious = index > 0 && Math.abs(word.start - lastWordEndTime) < 0.3; // Small gap = connected
                    const containsPunctuation = ['。', '、', '！', '？'].some(p => word.text.includes(p));
                    
                    currentPhraseWords.push(word);
                    lastWordEndTime = word.end;

                    if (containsPunctuation || (!isConnectedToPrevious && currentPhraseWords.length > 0)) {{
                        if (currentPhraseWords.length > 0) {{
                            phrases.push([...currentPhraseWords]);
                            currentPhraseWords = [];
                        }}
                    }}
                }});

                if (currentPhraseWords.length > 0) {{ // Add any remaining words
                    phrases.push(currentPhraseWords);
                }}

                // Optional: Merge very short phrases (e.g., <= 3 chars) with the next one
                let mergedPhrases = [];
                for (let i = 0; i < phrases.length; i++) {{
                    const currentPhraseText = phrases[i].map(w => w.text).join('');
                    if (currentPhraseText.length <= 3 && i < phrases.length - 1) {{
                        phrases[i+1] = [...phrases[i], ...phrases[i+1]]; // Prepend short phrase to next
                    }} else {{
                        mergedPhrases.push(phrases[i]);
                    }}
                }}
                return mergedPhrases;
            }}

            // Renders the transcript text as clickable spans
            function renderTranscriptText() {{
                textDisplay.innerHTML = ''; // Clear previous content
                const displayPhrases = formatTextIntoPhrases(wordsData);
                let overallWordCounter = 0;

                displayPhrases.forEach((phraseWords) => {{
                    const phraseContainerDiv = document.createElement('div');
                    phraseContainerDiv.style.marginBottom = '10px'; // Spacing between phrases

                    phraseWords.forEach((wordObj) => {{
                        const wordSpanElement = document.createElement('span');
                        wordSpanElement.textContent = wordObj.text;
                        // Use a consistent IDing scheme, referencing the overall word index
                        wordSpanElement.id = `word-{player_instance_id}-${{overallWordCounter}}`;
                        overallWordCounter++;
                        
                        wordSpanElement.style.cursor = 'pointer';
                        wordSpanElement.style.transition = 'color 0.2s ease-in-out, font-weight 0.2s ease-in-out';
                        
                        wordSpanElement.onclick = () => {{
                            audioPlayer.currentTime = wordObj.start; // Seek audio
                            audioPlayer.play().catch(e => console.warn("Audio play failed:", e));
                        }};
                        phraseContainerDiv.appendChild(wordSpanElement);
                    }});
                    textDisplay.appendChild(phraseContainerDiv);
                }});
            }}

            // Updates word highlighting based on audio playback time
            function updateWordHighlights() {{
                const currentTime = audioPlayer.currentTime;
                let activeWordDOMElement = null;
                let overallWordCounter = 0;
                const displayPhrases = formatTextIntoPhrases(wordsData); // Re-get phrases to iterate consistently

                displayPhrases.forEach((phraseWords) => {{
                    phraseWords.forEach((wordObj) => {{
                        const wordElement = document.getElementById(`word-{player_instance_id}-${{overallWordCounter}}`);
                        overallWordCounter++;
                        if (wordElement) {{
                            if (currentTime >= wordObj.start && currentTime < wordObj.end) {{ // Use < end for clearer highlighting
                                wordElement.style.color = '#ff4b4b'; // Highlight color
                                wordElement.style.fontWeight = 'bold';
                                activeWordDOMElement = wordElement;
                            }} else {{
                                wordElement.style.color = ''; // Reset style
                                wordElement.style.fontWeight = 'normal';
                            }}
                        }}
                    }});
                }});

                // Auto-scroll logic
                if (activeWordDOMElement && textDisplay.contains(activeWordDOMElement)) {{
                    const displayRect = textDisplay.getBoundingClientRect();
                    const wordRect = activeWordDOMElement.getBoundingClientRect();

                    // Scroll if the active word is not (mostly) visible
                    if (wordRect.top < displayRect.top + 30 || wordRect.bottom > displayRect.bottom - 30) {{
                        // Scroll to center the word, or just bring into view
                        textDisplay.scrollTop += (wordRect.top - displayRect.top) - (displayRect.height / 2) + (wordRect.height / 2);
                    }}
                }}
            }}

            // Initialize
            renderTranscriptText();
            audioPlayer.addEventListener('timeupdate', updateWordHighlights);
            // Optional: Handle audio end to remove highlights
            audioPlayer.addEventListener('ended', () => {{
                 const displayPhrases = formatTextIntoPhrases(wordsData);
                 let overallWordCounter = 0;
                 displayPhrases.forEach((phraseWords) => {{
                    phraseWords.forEach(() => {{
                        const wordElement = document.getElementById(`word-{player_instance_id}-${{overallWordCounter}}`);
                        if(wordElement) {{
                           wordElement.style.color = '';
                           wordElement.style.fontWeight = 'normal';
                        }}
                        overallWordCounter++;
                    }});
                 }});
            }});

        }})();
        </script>
        """
        st.components.v1.html(html, height=height)
    except Exception as e:
        st.warning(f"Could not generate main synchronized player: {e}")

def create_phrase_synchronized_player(phrase_audio_abs_path_str: str,
                                      phrase_words_for_sync_list: list,
                                      phrase_unique_id: str, # e.g., "S1_P0"
                                      kanji_map_for_js_str: str):
    """
    Creates HTML/JS for an individual phrase player.
    Audio element is hidden by global CSS. Text display div has explicit font-family.
    """
    try:
        audio_b64 = ""
        audio_available = False
        if phrase_audio_abs_path_str and os.path.exists(phrase_audio_abs_path_str):
            with open(phrase_audio_abs_path_str, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode()
            audio_available = True
        
        words_json = json.dumps(phrase_words_for_sync_list if phrase_words_for_sync_list else [])
        
        # Element IDs using the unique phrase ID
        player_container_id = f"player-container-phrase-{phrase_unique_id}"
        audio_element_id = f"audio-player-phrase-{phrase_unique_id}"
        text_display_id = f"text-display-phrase-{phrase_unique_id}"

        audio_html_tag = ""
        if audio_available:
            # The audio tag is hidden by global CSS (e.g., .phrase-player audio[id^="audio-player-phrase-"])
            audio_html_tag = f"""
            <audio id="{audio_element_id}" loop>
                <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
            </audio>
            """
        
        # Phrase text will be populated by JavaScript.
        # Explicit font-family for the main phrase text display.
        html_content = f"""
        <div id="{player_container_id}" class="phrase-player">
            {audio_html_tag}
            <div id="{text_display_id}" 
                 style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif; 
                        font-size:30px; 
                        line-height:1.8; 
                        padding: 5px 10px;
                        cursor: pointer;">
                {'' if phrase_words_for_sync_list else '<p style="font-size:16px; color:grey; text-align:center;">No text for this phrase.</p>'}
            </div>
        </div>

        <script>
        (function() {{ // IIFE for encapsulation
            "use strict";
            const wordsDataPhrase = {words_json};
            const kanjiReadingsMap = JSON.parse('{kanji_map_for_js_str}'); // Parse the JSON string
            const audioPlayerPhrase = document.getElementById('{audio_element_id}'); // Might be null
            const textDisplayPhrase = document.getElementById('{text_display_id}');

            if (!textDisplayPhrase) {{
                console.error("Text display element not found for phrase player: {text_display_id}");
                return;
            }}

            if (!wordsDataPhrase || wordsDataPhrase.length === 0) {{
                // textDisplayPhrase.innerHTML = "<p style='font-size:16px; color:grey; text-align:center;'>No text for this phrase.</p>"; // Already handled by Python
                return; 
            }}

            function generateFuriganaHTML(text, readingsMap) {{
                let htmlOutput = '';
                for (let i = 0; i < text.length; i++) {{
                    const char = text[i];
                    const charCode = char.charCodeAt(0);
                    const isKanji = (
                        (charCode >= 0x4E00 && charCode <= 0x9FFF) || 
                        (charCode >= 0x3400 && charCode <= 0x4DBF) || 
                        (charCode >= 0x20000 && charCode <= 0x2A6DF) ||
                        (charCode >= 0x2A700 && charCode <= 0x2B73F) ||
                        (charCode >= 0x2B740 && charCode <= 0x2B81F) ||
                        (charCode >= 0x2B820 && charCode <= 0x2CEAF) ||
                        (charCode >= 0x2CEB0 && charCode <= 0x2EBEF) ||
                        (charCode >= 0xF900 && charCode <= 0xFAFF)
                    );
                    if (isKanji && readingsMap && readingsMap[char]) {{
                        htmlOutput += `<ruby><rb>${{char}}</rb><rt>${{readingsMap[char]}}</rt></ruby>`;
                    }} else {{
                        htmlOutput += char;
                    }}
                }}
                return htmlOutput;
            }}

            function renderPhraseText() {{
                textDisplayPhrase.innerHTML = ''; // Clear previous
                const phraseWordsContainer = document.createElement('div');

                wordsDataPhrase.forEach((wordObj, index) => {{
                    const wordSpan = document.createElement('span');
                    wordSpan.innerHTML = generateFuriganaHTML(wordObj.text, kanjiReadingsMap);
                    wordSpan.id = `word-phrase-{phrase_unique_id}-word-${{index}}`; // Unique ID for each word span
                    wordSpan.style.cursor = 'pointer';
                    wordSpan.style.transition = 'color 0.2s ease-in-out, font-weight 0.2s ease-in-out';
                    wordSpan.style.marginRight = '2px'; // Small spacing between words

                    wordSpan.onclick = () => {{
                        if (audioPlayerPhrase) {{ // Play only if audio element exists
                            audioPlayerPhrase.currentTime = wordObj.start;
                            audioPlayerPhrase.play().catch(e => console.warn("Phrase audio play failed:", e));
                        }}
                    }};
                    wordSpan.ondblclick = (event) => {{
                        event.preventDefault(); // Prevent text selection
                        if (audioPlayerPhrase) {{
                            audioPlayerPhrase.pause();
                        }}
                    }};
                    phraseWordsContainer.appendChild(wordSpan);
                }});
                textDisplayPhrase.appendChild(phraseWordsContainer);
            }}

            function updatePhraseWordHighlights() {{
                if (!audioPlayerPhrase || !wordsDataPhrase || wordsDataPhrase.length === 0) {{
                    return; // No audio or no words, nothing to highlight
                }}
                const currentTime = audioPlayerPhrase.currentTime;
                wordsDataPhrase.forEach((wordObj, index) => {{
                    const wordElement = document.getElementById(`word-phrase-{phrase_unique_id}-word-${{index}}`);
                    if (wordElement) {{
                        if (currentTime >= wordObj.start && currentTime < wordObj.end) {{ // Use < end
                            wordElement.style.color = '#ff4b4b';
                            wordElement.style.fontWeight = 'bold';
                        }} else {{
                            wordElement.style.color = '';
                            wordElement.style.fontWeight = 'normal';
                        }}
                    }}
                }});
            }}
            
            // Initial setup
            try {{
                renderPhraseText();
                if (audioPlayerPhrase) {{ // Add event listeners only if audio element is present
                    audioPlayerPhrase.addEventListener('timeupdate', updatePhraseWordHighlights);
                    audioPlayerPhrase.addEventListener('ended', () => {{ // Clear highlights on end
                        wordsDataPhrase.forEach((wordObj, index) => {{
                             const wordElement = document.getElementById(`word-phrase-{phrase_unique_id}-word-${{index}}`);
                             if(wordElement) {{wordElement.style.color = ''; wordElement.style.fontWeight = 'normal';}}
                        }});
                    }});
                }}
            }} catch (e) {{
                console.error("Error setting up phrase player ({phrase_unique_id}):", e);
                textDisplayPhrase.innerHTML = "<p style='color:red;font-size:14px;'>Error initializing player.</p>";
            }}
        }})();
        </script>
        """
        return html_content
    except Exception as e:
        # Python-side error during HTML string generation
        print(f"Python error during create_phrase_synchronized_player for {phrase_unique_id}: {str(e)}")
        return f"""<div class="phrase-player"><p style="color:red;text-align:center;padding:10px;">Error generating player for phrase {phrase_unique_id}.</p></div>"""

def generate_breakdown_html_from_session_state(segment_analysis_data: dict, video_data_dir_name: str, db_segment_id_for_player: int):
    gpt_json = segment_analysis_data.get("gpt_json", {})
    phrase_audio_map = segment_analysis_data.get("phrase_audio_map", {})
    if not gpt_json or "phrases" not in gpt_json: return "<p>No analysis data for this segment.</p>"
    html_parts = []
    video_specific_audio_root = AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_data_dir_name
    
    # Get raw transcript data from database
    conn = get_db_connection()
    raw_transcript_data = {}
    if conn:
        segment = conn.execute("SELECT v.raw_deepgram_response_json FROM Segments s JOIN Videos v ON s.video_id = v.id WHERE s.id = ?", (db_segment_id_for_player,)).fetchone()
        if segment:
            raw_transcript_data = json.loads(segment["raw_deepgram_response_json"])
        conn.close()

    for phrase_idx, gpt_phrase_detail in enumerate(gpt_json.get("phrases", [])):
        phrase_html = ""
        phrase_audio_filename = phrase_audio_map.get(phrase_idx)
        kanji_map = {k["kanji"]: k["reading"] for k in gpt_phrase_detail.get("kanji_explanations", []) if k.get("kanji") and k.get("reading")}
        kanji_map_js = json.dumps(kanji_map, ensure_ascii=False)
        
        phrase_audio_path = None
        if phrase_audio_filename: phrase_audio_path = video_specific_audio_root / "phrases" / phrase_audio_filename
        
        p_sync_words = extract_phrase_words_for_sync(raw_transcript_data, gpt_phrase_detail.get("original_start_time",0), gpt_phrase_detail.get("original_end_time",0))
        phrase_html += create_phrase_synchronized_player(str(phrase_audio_path) if phrase_audio_path and phrase_audio_path.exists() else None, p_sync_words, f"S{db_segment_id_for_player}_P{phrase_idx}_live", kanji_map_js)
        
        phrase_html += "<table style='width:100%;border-collapse:collapse;margin-bottom:15px;font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,sans-serif;'><tr><th style='border:1px solid #e0e0e0;padding:8px 12px;text-align:left;background-color:#f2f2f2;font-size:15px;'>일본어</th><th style='border:1px solid #e0e0e0;padding:8px 12px;text-align:left;background-color:#f2f2f2;font-size:15px;'>로마자</th><th style='border:1px solid #e0e0e0;padding:8px 12px;text-align:left;background-color:#f2f2f2;font-size:15px;'>품사/설명</th><th style='border:1px solid #e0e0e0;padding:8px 12px;text-align:left;background-color:#f2f2f2;font-size:15px;'>한자</th></tr>"
        for word in gpt_phrase_detail.get("words", []): phrase_html += f"<tr><td style='border:1px solid #e0e0e0;padding:8px 12px;text-align:left;font-size:15px;'>{word.get('japanese','')}</td><td style='border:1px solid #e0e0e0;padding:8px 12px;text-align:left;font-size:15px;'>{word.get('romaji','')}</td><td style='border:1px solid #e0e0e0;padding:8px 12px;text-align:left;font-size:15px;'>{word.get('meaning','')}</td><td style='border:1px solid #e0e0e0;padding:8px 12px;text-align:left;font-size:15px;'>{word.get('kanji','')}</td></tr>"
        phrase_html += "</table>"
        if gpt_phrase_detail.get("kanji_explanations"):
            phrase_html += (
                "<div style='margin-top:5px;margin-bottom:10px;"
                "font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,sans-serif;'>"
                "<strong class='section-header-strong'></strong><ul class='kanji-list'>"
            )

            for k in gpt_phrase_detail.get("kanji_explanations", []):
                original_meaning = k.get("meaning", "")
                formatted_meaning = original_meaning

                # If the meaning has a Korean / Hanja split, bold-highlight the Hanja part
                if " / " in original_meaning:
                    korean, hanja = original_meaning.split(" / ", 1)
                    formatted_meaning = f"{korean} <strong>{hanja}</strong>"

                phrase_html += (
                    "<li style='display:flex;align-items:baseline;margin-bottom:6px;"
                    "font-size:15px;line-height:1.6;'>"
                    f"<strong style='flex-basis:40px;flex-shrink:0;font-weight:bold;text-align:center;'>"
                    f"{k.get('kanji', '')}</strong>"
                    f"<span style='flex-basis:100px;flex-shrink:0;color:#4A4A4A;padding-left:8px;padding-right:8px;'>"
                    f"({k.get('reading', '')})</span>"
                    f"<span style='flex-grow:1;'>{formatted_meaning}</span>"
                    "</li>"
                )

            phrase_html += "</ul></div>"

        if gpt_phrase_detail.get("meaning"):
            phrase_html += f"<div class='meaning-paragraph' style='margin-top:5px;margin-bottom:15px;font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,sans-serif;'><strong class='section-header-strong'></strong><p style='font-size:20px;line-height:1.6;margin-top:0px;'>{gpt_phrase_detail.get('meaning','')}</p></div>"
        
        html_parts.append(phrase_html)
        if phrase_idx < len(gpt_json.get("phrases", [])) - 1: html_parts.append("<hr style='margin-top:15px;margin-bottom:15px;border:0;height:1px;background-color:#e0e0e0;'>")
    return "".join(html_parts)

def extract_and_store_kanji_for_video(conn, video_id):
    cursor = conn.cursor(); cursor.execute("SELECT gpa.gpt_phrase_json FROM GptPhraseAnalyses gpa JOIN Segments s ON gpa.segment_id=s.id WHERE s.video_id=?",(video_id,))
    uk = {}
    for row in cursor.fetchall():
        gd = json.loads(row["gpt_phrase_json"])
        for ke in gd.get("kanji_explanations",[]):
            char=ke.get("kanji");
            if char and char not in uk: uk[char]={"reading":ke.get("reading","N/A"),"meaning":ke.get("meaning","N/A")}
    for char,info in uk.items():
        try: cursor.execute("INSERT INTO KanjiEntries(video_id,character,reading,meaning)VALUES(?,?,?,?)",(video_id,char,info["reading"],info["meaning"]))
        except sqlite3.IntegrityError: pass
    conn.commit()

# ─────────────────────────────────────────────────────────────
#  Kanji-to-timing mapper (final version with absolute offset)
# ─────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────
#  Final timing-aware vocabulary collector
# ──────────────────────────────────────────────────────────────
# ────────────────────────────────────────────────────────────────
def collect_vocab_with_kanji(gpt_json, vocab_map, phrase_sync_words=None):
    """
    Insert / update kanji words from GPT analysis, *with real timings*.
    Works for compounds up to 8 tokens and tolerates small string noise.
    """
    if not gpt_json or "phrases" not in gpt_json:
        return

    # small util — same normaliser for BOTH sides
    _full2half = str.maketrans("０１２３４５６７８９", "0123456789")
    def _norm(txt: str) -> str:
        return normalize_japanese(txt).translate(_full2half)

    for phr in gpt_json["phrases"]:
        # ------------------------------------------------------------------
        # Build token-window lookup once per phrase
        # ------------------------------------------------------------------
        lookup = {}                              # key → (abs_start, abs_end)
        if phrase_sync_words:                    # already speed-adjusted list
            off = phr.get("original_start_time", 0) or 0        # <-- original units

            # ------------------------------------------------------------------
            # replace with slowed-audio offset (same transform you used earlier)
            # ------------------------------------------------------------------
            adj = 1 / 0.75                  # <- or pass speed_factor in
            time_off = 0.3
            off = phr.get("original_start_time", 0) * adj - time_off
            toks = phrase_sync_words
            n = len(toks)

            # single tokens first
            for t in toks:
                lookup[_norm(t["text"])] = (t["start"] + off, t["end"] + off)

            # n-grams 2-…-8  (ニュー/タ/バル/基/地  → ニュータバル基地)
            for span in range(2, min(9, n + 1)):
                for i in range(n - span + 1):
                    win = toks[i : i + span]
                    key = _norm("".join(t["text"] for t in win))
                    lookup[key] = (win[0]["start"] + off, win[-1]["end"] + off)

        lkeys = list(lookup.keys())              # cache for fuzzy

        # ------------------------------------------------------------------
        # Walk GPT words
        # ------------------------------------------------------------------
        for w in phr["words"]:
            if not w.get("kanji"):
                continue

            surf = w.get("japanese", "")
            if not surf:
                continue

            k = _norm(surf)
            start = end = None

            # 1) exact
            if k in lookup:
                start, end = lookup[k]

            # 2) fuzzy (≥90) if RapidFuzz available
            elif FUZZY_MATCHING_AVAILABLE and lkeys:
                hit, score, _ = process.extractOne(k, lkeys, scorer=fuzz.ratio)
                if score >= 90:
                    start, end = lookup[hit]

            # discard micro-windows (<150 ms) – usually wrong
            if start is not None and (end - start) < 0.15:
                start = end = None

            # write / update map
            if surf not in vocab_map or (
                start is not None and vocab_map[surf].get("start") is None
            ):
                vocab_map[surf] = {
                    "kanji": w.get("kanji", ""),
                    "romaji": w.get("romaji", ""),
                    "meaning": w.get("meaning", ""),
                    "kanji_readings": {
                        ke["kanji"]: ke["reading"]
                        for ke in phr.get("kanji_explanations", [])
                        if ke.get("kanji") and ke.get("reading")
                    },
                    "start": start,
                    "end": end,
                }





def find_audio_file_for_video(video_id, video_dir_name):
    """
    Attempts to find the audio file using multiple methods if the standard path resolution fails.
    
    Args:
        video_id: ID of the video
        video_dir_name: Name of the video directory
        
    Returns:
        Path to the audio file if found, None otherwise
    """
    # Method 1: Check database path
    try:
        conn = get_db_connection()
        if conn:
            video_info = conn.execute("SELECT full_slowed_audio_path FROM Videos WHERE id = ?", (video_id,)).fetchone()
            if video_info and video_info["full_slowed_audio_path"]:
                standard_path = AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_dir_name / video_info["full_slowed_audio_path"]
                if os.path.exists(standard_path):
                    conn.close()
                    return str(standard_path)
            conn.close()
    except Exception:
        pass
    
    # Method 2: Search directly in the video directory for MP3 files
    try:
        video_dir = AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_dir_name
        if os.path.exists(video_dir):
            mp3_files = list(video_dir.glob("*.mp3"))
            if mp3_files:
                # Prefer files with "full" or "slowed" in the name
                for keyword in ["full_slowed", "slowed", "full"]:
                    for file_path in mp3_files:
                        if keyword in file_path.name.lower():
                            return str(file_path)
                
                # If no keyword match, return the largest MP3 file (likely the full audio)
                return str(max(mp3_files, key=os.path.getsize))
    except Exception:
        pass
    
    # Method 3: Check for any MP3 file in storage root as last resort
    try:
        if os.path.exists(AUDIO_FILES_STORAGE_ROOT_ABS_PATH):
            for root, dirs, files in os.walk(AUDIO_FILES_STORAGE_ROOT_ABS_PATH):
                if video_dir_name in root:  # Only look in directories related to this video
                    mp3_files = [os.path.join(root, f) for f in files if f.endswith(".mp3")]
                    if mp3_files:
                        return max(mp3_files, key=os.path.getsize)
    except Exception:
        pass
    
    return None

def create_vocab_component(vocab_map, full_slowed_audio_path, filter_query="", sort_by="일본어순"):
    """
    Generate a complete self-contained HTML component for vocabulary with proper audio playback.
    
    Args:
        vocab_map: Dictionary of vocabulary words with their details
        full_slowed_audio_path: Path to the slowed audio file
        filter_query: Optional filter for vocabulary words
        sort_by: Sort method ("일본어순" or "한자순")
        
    Returns:
        String containing complete HTML component
    """
    # Sort and filter vocabulary items
    if sort_by == "일본어순":
        sorted_items = sorted(vocab_map.items())
    elif sort_by == "한자순":
        sorted_items = sorted(vocab_map.items(), key=lambda x: x[1]["kanji"])
    else:                             # 시간순  ← default branch
        sorted_items = sorted(
            vocab_map.items(),
            key=lambda kv: (
                float("inf") if kv[1]["start"] is None else kv[1]["start"]
            ),
        )
    
    # Filter based on search query
    filtered_items = [
        (jp, info) for jp, info in sorted_items 
        if not filter_query or (filter_query.lower() in jp.lower() or 
                               filter_query.lower() in info["meaning"].lower())
    ]
    
    # Complete HTML content with CSS, audio, cards, and JavaScript in ONE component
    html_content = """
    <style>
    /* CSS styles for vocabulary cards */
    .vocab-card {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 20px;
        margin-bottom: 12px;
        background-color: #ffffff;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        transition: box-shadow 0.2s, transform 0.2s;
        text-align: center;
        cursor: pointer;
    }
    .vocab-card:hover {
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        transform: translateY(-2px);
    }
    .vocab-card.vocab-playing {
        background-color: #f8f8ff;
        border-color: #4285f4;
        box-shadow: 0 4px 12px rgba(66, 133, 244, 0.2);
    }
    .vocab-japanese {
        font-size: 2.2rem;
        margin-bottom: 16px;
        color: #2c3e50;
        font-weight: 500;
        line-height: 1.4;
    }
    .vocab-meaning {
        font-size: 1.4rem;
        color: #16a085;
        font-weight: 500;
    }
    rt {
        font-size: 0.7em;
        color: #555;
        opacity: 0.9;
    }
    .vocab-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 15px;
        padding: 10px;
    }
    .debug-info {
        color: #999;
        font-size: 10px;
        margin-top: 5px;
    }
    .control-panel {
        text-align: center;
        margin-bottom: 15px;
        padding: 10px;
        background: #f8f8f8;
        border-radius: 8px;
    }
    .stop-button {
        display: inline-block;
        padding: 6px 12px;
        background-color: #f44336;
        color: white;
        font-size: 14px;
        border-radius: 4px;
        margin: 5px;
        cursor: pointer;
        border: none;
    }
    .play-all-button {
        display: inline-block;
        padding: 6px 12px;
        background-color: #4CAF50;
        color: white;
        font-size: 14px;
        border-radius: 4px;
        margin: 5px;
        cursor: pointer;
        border: none;
    }
    .audio-status {
        display: inline-block;
        margin-left: 10px;
        font-size: 14px;
    }
    .timing-missing {
        border: 1px dashed #ff9800 !important;
    }
    </style>
    
    <div id="debug-output" style="display:none;"></div>
    
    <!-- Control panel with status indicator -->
    <div class="control-panel">
        <button onclick="stopVocab()" class="stop-button">Stop</button>
        <span id="audio-status" class="audio-status">Initializing audio...</span>
    </div>
    """
    
    # Add the audio element with more robust error handling
    if full_slowed_audio_path and os.path.exists(full_slowed_audio_path):
        try:
            with open(full_slowed_audio_path, 'rb') as audio_file:
                audio_size = os.path.getsize(full_slowed_audio_path)
                audio_b64 = base64.b64encode(audio_file.read()).decode()
                html_content += f"""
                <audio id="vocab-player" preload="auto">
                    <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
                    Your browser does not support the audio element.
                </audio>
                <div style="color:green; padding:5px; margin:5px 0; background:#f0fff0; border-radius:4px; display:none;">
                    Audio file loaded successfully: {os.path.basename(full_slowed_audio_path)} ({audio_size/1024/1024:.2f} MB)
                </div>
                """
        except Exception as e:
            error_message = str(e)
            html_content += f"""
            <div style="color:red; padding:10px; margin-bottom:15px; background:#fff0f0; border-radius:4px;">
                Audio loading error: {error_message}
                <div style="font-size:12px; margin-top:5px;">Path: {full_slowed_audio_path}</div>
            </div>
            <audio id="vocab-player"></audio>
            """
    else:
        html_content += f"""
        <div style="color:orange; padding:10px; margin-bottom:15px; background:#fff8e1; border-radius:4px;">
            No audio file available for this video.
            <div style="font-size:12px; margin-top:5px;">
                Path checked: {full_slowed_audio_path if full_slowed_audio_path else "None"}
                <br>Path exists: {os.path.exists(full_slowed_audio_path) if full_slowed_audio_path else "False"}
            </div>
        </div>
        <audio id="vocab-player"></audio>
        """
    
    # Add vocabulary cards grid with timing data
    html_content += '<div class="vocab-grid">'
    
    for jp, info in filtered_items:
        # Create furigana HTML for display
        jp_with_furigana = jp
        kanji_readings = info.get("kanji_readings", {})
        if kanji_readings:
            for kanji, reading in kanji_readings.items():
                if kanji in jp:
                    jp_with_furigana = jp_with_furigana.replace(
                        kanji, 
                        f'<ruby>{kanji}<rt>{reading}</rt></ruby>'
                    )
        
        # IMPORTANT FIX: Always include data attributes, with defaults if actual timing is missing
        start_time = info.get("start")
        end_time = info.get("end")
        has_timing = start_time is not None and end_time is not None
        
        # Include data attributes even if the values are "null" - better for debugging
        # JavaScript can handle null values, but missing attributes cause more problems
        start_attr = f'data-start="{start_time}"'
        end_attr = f'data-end="{end_time}"'
        
        # Add a class to visually indicate cards with missing timing
        timing_class = "" if has_timing else "timing-missing"
        
        # Add debug timing display for troubleshooting
        #debug_timing = f'<div class="debug-info">{start_time}s - {end_time}s</div>' if has_timing else '<div class="debug-info">No timing data</div>'
        debug_timing = ""
        html_content += f"""
        <div class="vocab-card {timing_class}" {start_attr} {end_attr} onclick="playVocab(this)">
            <div class="vocab-japanese">{jp_with_furigana}</div>
            <div class="vocab-meaning">{info["meaning"]}</div>
            {debug_timing}
        </div>
        """
    
    html_content += '</div>'
    
    # Add improved JavaScript with better error handling and debugging
    html_content += """
    <script>
    (function() {
        // Use let/const for variables to keep them in this closure
        const player = document.getElementById('vocab-player');
        const audioStatus = document.getElementById('audio-status');
        let stopTimeout = null;
        let currentPlayingCard = null;
        
        // Log initial state to help debugging
        console.log("Audio player on initialization:", player);
        
        // Check if player has a source
        function checkAudioSource() {
            if (player) {
                const source = player.querySelector('source');
                if (source && source.src) {
                    console.log("Audio source found:", source.src.substring(0, 50) + "...");
                    return true;
                } else {
                    console.warn("Audio element exists but has no source");
                    return false;
                }
            }
            return false;
        }
        
        // Update status based on player and source
        if (player) {
            audioStatus.innerHTML = '<span style="color:green">✓ Audio player found</span>';
            
            if (checkAudioSource()) {
                audioStatus.innerHTML = '<span style="color:green">✓ Audio ready</span>';
            } else {
                audioStatus.innerHTML = '<span style="color:orange">⚠️ Audio source missing</span>';
            }
            
            // Set up error handling for the audio element
            player.addEventListener('error', function(e) {
                console.error("Audio element error:", e);
                audioStatus.innerHTML = '<span style="color:red">⚠️ Audio error: ' + 
                    (player.error ? player.error.message : 'unknown') + '</span>';
            });
        } else {
            console.error("Audio player element not found!");
            audioStatus.innerHTML = '<span style="color:red">⚠️ Audio player not found!</span>';
        }
        
        window.playVocab = function (card) {
            console.log("Card clicked:", card);
            console.log("Audio player when clicked:", player);

            if (!player) {
                audioStatus.innerHTML =
                    '<span style="color:red">⚠️ Audio player not available</span>';
                return;
            }
            if (!checkAudioSource()) {
                audioStatus.innerHTML =
                    '<span style="color:red">⚠️ No audio source available</span>';
                return;
            }

            // ─── ① read raw timings from data-attributes ────────────────────
            const rawStart = parseFloat(card.dataset.start);
            const rawEnd   = parseFloat(card.dataset.end);
            console.log("Raw Start:", rawStart, "Raw End:", rawEnd);

            if (isNaN(rawStart) || isNaN(rawEnd)) {
                card.style.border = "2px solid orange";
                audioStatus.innerHTML =
                    '<span style="color:orange">⚠️ No timing data for this word</span>';
                setTimeout(() => {
                    card.style.border = "";
                    audioStatus.innerHTML = '<span style="color:green">Ready</span>';
                }, 2000);
                return;
            }

            // ─── ② add ± padding (seconds) and clamp inside audio duration ─
            const EXTRA = 0.8;                                        // adjust here
            const startTime = rawStart + 0.3;
            const endTime   = Math.min(
                (player.duration || rawEnd + EXTRA + 1),            // if metadata not yet loaded
                rawEnd + EXTRA
            );

            // ─── ③ highlight card / reset previous ─────────────────────────
            if (currentPlayingCard) {
                currentPlayingCard.classList.remove("vocab-playing");
            }
            card.classList.add("vocab-playing");
            currentPlayingCard = card;

            clearTimeout(stopTimeout);                            // cancel old snippet

            try {
                if (Math.abs(player.currentTime - startTime) > 0.1) {
                    player.currentTime = startTime;
                }

                const playPromise = player.play();
                if (playPromise !== undefined) {
                    playPromise
                        .then(() => {
                            audioStatus.innerHTML =
                                '<span style="color:blue">▶️ Playing</span>';
                        })
                        .catch((error) => {
                            console.error("Play failed:", error);
                            audioStatus.innerHTML =
                                '<span style="color:red">⚠️ Playback failed: ' +
                                error.message +
                                "</span>";
                            card.classList.remove("vocab-playing");
                        });
                }

                // ─── ④ schedule pause after padded window finishes ──────────
                const duration = (endTime - startTime) * 1000;
                stopTimeout = setTimeout(() => {
                    player.pause();
                    if (currentPlayingCard) {
                        currentPlayingCard.classList.remove("vocab-playing");
                        currentPlayingCard = null;
                    }
                    audioStatus.innerHTML = '<span style="color:green">Ready</span>';
                }, duration + 100); // tiny buffer

            } catch (e) {
                console.error("Error playing audio:", e);
                audioStatus.innerHTML =
                    '<span style="color:red">⚠️ Error: ' + e.message + "</span>";
                if (currentPlayingCard) {
                    currentPlayingCard.classList.remove("vocab-playing");
                }
            }
        };
        
        // Stop button function
        window.stopVocab = function() {
            if (player) {
                player.pause();
            }
            clearTimeout(stopTimeout);
            
            if (currentPlayingCard) {
                currentPlayingCard.classList.remove('vocab-playing');
                currentPlayingCard = null;
            }
            
            audioStatus.innerHTML = '<span style="color:green">Ready</span>';
        };
        
        // Set audio status when page loads
        window.addEventListener('load', function() {
            if (player) {
                if (checkAudioSource()) {
                    audioStatus.innerHTML = '<span style="color:green">Ready</span>';
                }
            }
        });
    })();
    </script>
    """
    
    # Add diagnostic tools for troubleshooting
    html_content += """
    <div style="margin-top: 20px; padding: 10px; border: 1px solid #ddd; background: #f9f9f9; border-radius: 4px;">
        <label style="display: block; margin-bottom: 10px;">
            <input type="checkbox" id="toggle-debug" onclick="toggleDebug()"> 
            Show debugging information
        </label>
        <div id="debug-panel" style="display: none; margin-top: 10px;">
            <h3>Audio Element Debug:</h3>
            <pre id="audio-debug"></pre>
            <h3>Timing Data Debug:</h3>
            <pre id="timing-debug"></pre>
            <button onclick="testAudio()" style="padding: 5px 10px; background: #4285f4; color: white; border: none; border-radius: 4px; cursor: pointer;">Test Audio</button>
        </div>
    </div>

    <script>
    function toggleDebug() {
        const debugPanel = document.getElementById('debug-panel');
        debugPanel.style.display = debugPanel.style.display === 'none' ? 'block' : 'none';
        
        if (debugPanel.style.display === 'block') {
            const audioEl = document.getElementById('vocab-player');
            document.getElementById('audio-debug').textContent = 
                'Audio element exists: ' + (audioEl ? 'Yes' : 'No') + '\\n' +
                'Audio source: ' + (audioEl && audioEl.querySelector('source') ? 
                                   audioEl.querySelector('source').src.substring(0, 50) + '...' : 'None') + '\\n' +
                'Ready state: ' + (audioEl ? audioEl.readyState : 'N/A') + '\\n' +
                'Network state: ' + (audioEl ? audioEl.networkState : 'N/A') + '\\n' +
                'Paused: ' + (audioEl ? audioEl.paused : 'N/A') + '\\n' +
                'Duration: ' + (audioEl ? audioEl.duration : 'N/A') + '\\n' +
                'Error: ' + (audioEl && audioEl.error ? audioEl.error.message : 'None');
                
            // Show timing data for cards
            let timingInfo = '';
            const cards = document.querySelectorAll('.vocab-card');
            for (let i = 0; i < Math.min(5, cards.length); i++) {
                const card = cards[i];
                const jp = card.querySelector('.vocab-japanese').textContent;
                timingInfo += `Card ${i+1}: "${jp.substring(0, 10)}..." ` + 
                              `Start: ${card.dataset.start}, End: ${card.dataset.end}\\n`;
            }
            document.getElementById('timing-debug').textContent = timingInfo;
        }
    }

    function testAudio() {
        const audioEl = document.getElementById('vocab-player');
        if (!audioEl) {
            alert('Audio element not found!');
            return;
        }
        
        try {
            audioEl.currentTime = 0;
            const playPromise = audioEl.play();
            if (playPromise !== undefined) {
                playPromise.then(_ => {
                    setTimeout(() => {
                        audioEl.pause();
                        alert('Audio test successful!');
                    }, 2000);
                }).catch(e => {
                    alert('Audio play error: ' + e);
                });
            }
        } catch (e) {
            alert('Audio test error: ' + e);
        }
    }
    </script>
    """
    
    return html_content

def populate_vocab_tab(tab_word, vocab_map, video_id, video_dir_name):
    """
    Populates the vocabulary tab with an interactive word display.
    
    Args:
        tab_word: Streamlit tab object for the vocabulary tab
        vocab_map: Dictionary of vocabulary words with their details
        video_id: ID of the current video
        video_dir_name: Directory name for the current video data
    """
    
    with tab_word:
        #st.subheader("📚 단어 (Kanji Vocabulary)")
        
        if not vocab_map:
            st.info("이 영상에 한자가 포함된 단어가 없습니다.")
        else:
            # Filter and sort controls
            col1, col2 = st.columns([3, 1])
            with col1:
                filter_key = f"filter_{video_id}"
                filter_q = st.text_input("검색 / 필터 (일본어 또는 의미로 검색)", "", key=filter_key)
            with col2:
                sort_key = f"sort_{video_id}"
                sort_option = st.selectbox("정렬 기준", ["시간순", "일본어순", "한자순"], key=sort_key)
            
            # Add debug output to show path resolution
            audio_debug_expander = st.expander("", expanded=False)
            
            # Get full slowed audio path with better error handling
            full_slowed_audio_path = None
            
            try:
                conn = get_db_connection()
                if conn and video_dir_name:
                    with audio_debug_expander:
                        st.write(f"Video ID: {video_id}")
                        st.write(f"Video Directory: {video_dir_name}")
                        st.write(f"Storage Root: {AUDIO_FILES_STORAGE_ROOT_ABS_PATH}")
                    
                    video_info = conn.execute("SELECT full_slowed_audio_path FROM Videos WHERE id = ?", (video_id,)).fetchone()
                    
                    if video_info and "full_slowed_audio_path" in video_info and video_info["full_slowed_audio_path"]:
                        relative_audio_path = video_info["full_slowed_audio_path"]
                        with audio_debug_expander:
                            st.write(f"Relative Audio Path: {relative_audio_path}")
                        
                        # Construct full path
                        full_slowed_audio_path = str(AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_dir_name / relative_audio_path)
                        
                        with audio_debug_expander:
                            st.write(f"Full Audio Path: {full_slowed_audio_path}")
                            st.write(f"File exists: {os.path.exists(full_slowed_audio_path)}")
                            
                            # If file doesn't exist, check parent directory
                            if not os.path.exists(full_slowed_audio_path):
                                parent_dir = os.path.dirname(full_slowed_audio_path)
                                st.write(f"Parent directory: {parent_dir}")
                                st.write(f"Parent exists: {os.path.exists(parent_dir)}")
                                if os.path.exists(parent_dir):
                                    st.write(f"Files in parent: {os.listdir(parent_dir)}")
                    else:
                        with audio_debug_expander:
                            st.write("No audio path found in database")
                            
                if conn:
                    conn.close()
            except Exception as e:
                with audio_debug_expander:
                    st.error(f"Error retrieving audio path: {e}")
                    st.write(f"Exception type: {type(e).__name__}")
                    st.write(f"Traceback: {traceback.format_exc()}")
            
            # Use fallback if standard path failed
            if not full_slowed_audio_path or not os.path.exists(full_slowed_audio_path):
                with audio_debug_expander:
                    st.write("Primary audio path failed, attempting fallback...")
                
                # Try the fallback method
                fallback_path = find_audio_file_for_video(video_id, video_dir_name)
                
                with audio_debug_expander:
                    st.write(f"Fallback path: {fallback_path}")
                    st.write(f"Fallback exists: {os.path.exists(fallback_path) if fallback_path else False}")
                
                if fallback_path and os.path.exists(fallback_path):
                    full_slowed_audio_path = fallback_path
            
            # Create and display the unified HTML component
            html_content = create_vocab_component(
                vocab_map, 
                full_slowed_audio_path, 
                filter_q,
                sort_option
            )
            
            # All HTML, CSS, JavaScript, and audio in a SINGLE component
            height_calculation = min(800, len(vocab_map) * 150 + 200)  # Extra height for controls
            st.components.v1.html(
                html_content, 
                height=height_calculation, 
                scrolling=True
            )

def load_existing_vocab(tab_word, video_id, video_dir_name):
    """
    Loads existing vocabulary data from the database for an already analyzed video.
    
    Args:
        tab_word: Streamlit tab object for the vocabulary tab
        video_id: ID of the current video
        video_dir_name: Directory name for the current video data
    """
    # Reconstruct vocab_map from database
    vocab_map = {}
    
    try:
        conn = get_db_connection()
        if conn:
            # Get all phrase analyses for this video
            cursor = conn.execute("""
                SELECT gpa.gpt_phrase_json, gpa.phrase_words_for_sync_json 
                FROM GptPhraseAnalyses gpa 
                JOIN Segments s ON gpa.segment_id = s.id 
                WHERE s.video_id = ?
            """, (video_id,))
            
            for row in cursor.fetchall():
                phrase_data = json.loads(row["gpt_phrase_json"])
                phrase_sync_words = json.loads(row["phrase_words_for_sync_json"]) if row["phrase_words_for_sync_json"] else None
                
                # Collect vocabulary with enhanced timing data
                collect_vocab_with_kanji({"phrases": [phrase_data]}, vocab_map, phrase_sync_words)
            
            conn.close()
            
            # Populate the vocabulary tab
            populate_vocab_tab(tab_word, vocab_map, video_id, video_dir_name)
    except Exception as e:
        with tab_word:
            st.error(f"Error loading vocabulary data: {e}")

def run_full_pipeline(url: str, force: bool):
    """
    Execute the complete analysis pipeline in a single run, streaming UI updates progressively.
    
    Args:
        url: YouTube URL to analyze
        force: Whether to force reprocessing if the video already exists
    
    Returns:
        Dictionary with important results (video_id, segments data, etc.)
    """
    # Setup status placeholders
    status_placeholder = st.empty()
    #progress_bar_placeholder = st.empty()
    
    # Create tabs immediately
    tabs = st.tabs(["전체 스크립트", "구문 분석", "단어", "한자", "전체 텍스트", "JSON 데이터"])
    tab1, tab2, tab_word, tab3, tab4, tab5 = tabs
    
    status_placeholder.info("1단계: 초기화 및 다운로드 중...")
    #progress_bar_placeholder.progress(0.05)
    
    conn = get_db_connection()
    if conn is None:
        status_placeholder.error("DB 연결 실패.")
        return None
    
    # Temporary directory for download
    temp_dl_dir_obj = None
    
    try:
        # STAGE 1: Initialize and Download
        cursor = conn.cursor()
        cursor.execute("SELECT id, video_title, video_data_directory FROM Videos WHERE youtube_url = ?", (url,))
        existing_video = cursor.fetchone()

        if existing_video and force:
            status_placeholder.info(f"재처리")
            try:
                if existing_video["video_data_directory"]:
                    shutil.rmtree(AUDIO_FILES_STORAGE_ROOT_ABS_PATH / existing_video["video_data_directory"], ignore_errors=True)
                cursor.execute("DELETE FROM Videos WHERE id = ?", (existing_video["id"],)) # Relies on ON DELETE CASCADE
                conn.commit()
            except Exception as e_del:
                status_placeholder.error(f"삭제 오류: {e_del}")
                return None
            existing_video = None
        elif existing_video and not force:
            status_placeholder.success(f"'{existing_video['video_title']}' 영상은 이미 분석되었습니다. 결과를 표시합니다.")
            video_id = existing_video["id"]
            video_dir_name = existing_video["video_data_directory"]
            video_info = conn.execute("SELECT full_slowed_audio_path, full_transcript_text, raw_deepgram_response_json, full_words_for_sync_json FROM Videos WHERE id = ?", (video_id,)).fetchone()
            video_info = dict(video_info) 

            missing_words  = not video_info["full_words_for_sync_json"]
            missing_audio  = not video_info["full_slowed_audio_path"]
            missing_text   = not video_info["full_transcript_text"]

            if missing_words or missing_audio or missing_text:
                raw_json = json.loads(video_info["raw_deepgram_response_json"])

                if missing_words:
                    words = extract_words_for_sync(raw_json)
                    cursor.execute(
                        "UPDATE Videos SET full_words_for_sync_json = ? WHERE id = ?",
                        (json.dumps(words), video_id)
                    )
                    video_info["full_words_for_sync_json"] = json.dumps(words)

                if missing_audio:
                    path = find_audio_file_for_video(video_id, video_dir_name)
                    if path:
                        cursor.execute(
                            "UPDATE Videos SET full_slowed_audio_path = ? WHERE id = ?",
                            (Path(path).name, video_id)
                        )
                        video_info["full_slowed_audio_path"] = Path(path).name

                if missing_text:
                    full_text = raw_json["results"]["channels"][0]["alternatives"][0]["transcript"].replace(" ", "")
                    cursor.execute(
                        "UPDATE Videos SET full_transcript_text = ? WHERE id = ?",
                        (full_text, video_id)
                    )
                    video_info["full_transcript_text"] = full_text

                conn.commit()

            
            # Fill tab 1: Full transcript
            if video_info and "full_slowed_audio_path" in video_info and video_info["full_slowed_audio_path"] and "full_words_for_sync_json" in video_info and video_info["full_words_for_sync_json"]:
                full_words_for_sync = json.loads(video_info["full_words_for_sync_json"])
                full_audio_path = AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_dir_name / video_info["full_slowed_audio_path"]
                with tab1:
                    create_synchronized_player(str(full_audio_path), full_words_for_sync)
            
            # Use the enhanced vocabulary loading function for an existing video
            load_existing_vocab(tab_word, video_id, video_dir_name)
            
            # Fill tab 2: Analysis
            with tab2:
                seg_container = st.container()
                segments = conn.execute("SELECT id, segment_index, text, start_time, end_time, deepgram_segment_words_json FROM Segments WHERE video_id = ? ORDER BY segment_index", (video_id,)).fetchall()
                
                for segment in segments:
                    segment_id = segment["id"]
                    phrase_analyses = conn.execute("SELECT gpt_phrase_json, phrase_slowed_audio_path, phrase_words_for_sync_json FROM GptPhraseAnalyses WHERE segment_id = ? ORDER BY phrase_index_in_segment", (segment_id,)).fetchall()
                    
                    if phrase_analyses:
                        # Recreate analysis data structure
                        gpt_json = {"phrases": []}
                        phrase_audio_map = {}
                        
                        for i, phrase in enumerate(phrase_analyses):
                            gpt_phrase = json.loads(phrase["gpt_phrase_json"])
                            gpt_json["phrases"].append(gpt_phrase)
                            phrase_audio_map[i] = phrase["phrase_slowed_audio_path"]
                        
                        segment_analysis = {"gpt_json": gpt_json, "phrase_audio_map": phrase_audio_map}
                        html = generate_breakdown_html_from_session_state(segment_analysis, video_dir_name, segment_id)
                        with seg_container:
                            st.components.v1.html(html, height=max(150, len(gpt_json["phrases"]) * 400), scrolling=True)
                            st.markdown("<hr style='border-top:1.5px solid #ddd; margin-top:20px; margin-bottom:20px'>", unsafe_allow_html=True)
            
            # Fill tab 3: Kanji
            with tab3:
                kanji_entries = conn.execute("SELECT character, reading, meaning FROM KanjiEntries WHERE video_id = ?", (video_id,)).fetchall()
                if kanji_entries:
                    sorted_kanji_items = sorted(kanji_entries, key=lambda x: x['character'])
                    num_columns = 2
                    cols = st.columns(num_columns)
                    st.markdown('<div class="kanji-card-container">', unsafe_allow_html=True)
                    for idx, kanji_info in enumerate(sorted_kanji_items):
                        with cols[idx % num_columns]:
                            k_desc, h_mean = "", ""
                            original_meaning = kanji_info["meaning"]
                            parts = []
                            if " / " in original_meaning:
                                parts = original_meaning.split(" / ", 1)
                                k_desc = parts[0]
                            if len(parts) > 1 and len(parts[1]) > 0:
                                h_mean = parts[1]
                            else:
                                k_desc = original_meaning
                            html_c = f"""<div class="kanji-card"><div class="kanji-char-display">{kanji_info['character']}</div><div class="kanji-info"><div class="reading"><strong>Reading:</strong> <span class="value">{kanji_info['reading']}</span></div><div class="meaning-korean"><strong>Korean:</strong> <span class="value">{k_desc}</span></div>{'<div class="meaning-hanja"><strong>Hanja:</strong> <span class="value">' + h_mean + '</span></div>' if h_mean else ''}</div></div>"""
                            st.markdown(html_c, unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
            
            # Fill tab 4: Full text
            with tab4:
                if video_info and "full_transcript_text" in video_info and video_info["full_transcript_text"]:
                    st.text_area("전체 텍스트", video_info["full_transcript_text"], height=300)
            
            # Fill tab 5: JSON data
            with tab5:
                if video_info and "raw_deepgram_response_json" in video_info and video_info["raw_deepgram_response_json"]:
                    st.json(json.loads(video_info["raw_deepgram_response_json"]))
            
            # Save results to session state
            st.session_state["last_video_id"] = video_id
            
            return {
                "video_id": video_id,
                "video_title": existing_video["video_title"]
            }
        
        # Create a temporary directory for download
        temp_dl_dir_obj = tempfile.TemporaryDirectory(prefix="yt_dl_sess_")
        temp_dl_dir_path = Path(temp_dl_dir_obj.name)
        
        # Download audio
        downloaded_audio_path, video_title = download_audio(url, temp_dl_dir_path)
        if not downloaded_audio_path:
            status_placeholder.error("오디오 다운로드 실패.")
            return None
        
        # Insert video record
        cursor.execute("INSERT INTO Videos (youtube_url, video_title) VALUES (?, ?)", (url, video_title))
        conn.commit()
        video_id = cursor.lastrowid
        
        # Create video directory
        video_dir_name = f"video_{video_id}"
        video_dir_abs_path = AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_dir_name
        (video_dir_abs_path / "phrases").mkdir(parents=True, exist_ok=True)
        cursor.execute("UPDATE Videos SET video_data_directory = ? WHERE id = ?", (video_dir_name, video_id))
        
        # Slow down full audio
        slowed_full_audio_name = f"full_slowed_{video_id}.mp3"
        full_slowed_audio_abs_path = str(video_dir_abs_path / slowed_full_audio_name)
        slow_down_audio(downloaded_audio_path, full_slowed_audio_abs_path)
        cursor.execute("UPDATE Videos SET full_slowed_audio_path = ? WHERE id = ?", (slowed_full_audio_name, video_id))
        
        # Update progress
        #progress_bar_placeholder.progress(0.2)
        status_placeholder.info("음성 변환 완료. 스크립트 변환 중...")
        
        # Transcribe audio
        transcript_data = transcribe_audio(downloaded_audio_path)
        if not transcript_data:
            status_placeholder.error("스크립트 변환 실패.")
            return None
        
        # Process transcript data
        #progress_bar_placeholder.progress(0.3)
        status_placeholder.info("스크립트 처리 중...")
        
        full_transcript, segments_list = prepare_japanese_segments(transcript_data)
        if full_transcript is None:
            status_placeholder.error("세그먼트 준비 실패.")
            return None
        
        # Extract words for sync
        sync_words = extract_words_for_sync(transcript_data)
        
        # Update database
        cursor.execute("UPDATE Videos SET raw_deepgram_response_json = ?, full_transcript_text = ?, full_words_for_sync_json = ? WHERE id = ?",
                      (json.dumps(transcript_data), full_transcript, json.dumps(sync_words), video_id))
        
        # Create segment records
        segment_db_data = []
        for seg_idx, seg_detail in enumerate(segments_list):
            cursor.execute("""INSERT INTO Segments (video_id, segment_index, text, start_time, end_time, deepgram_segment_words_json) 
                           VALUES (?, ?, ?, ?, ?, ?)""", 
                           (video_id, seg_idx, seg_detail['text'], seg_detail['start'], seg_detail['end'], 
                            json.dumps(seg_detail['words'])))
            seg_detail['db_id'] = cursor.lastrowid
            segment_db_data.append(seg_detail)
        conn.commit()
        
        # Populate Tab 1 with full audio player
        with tab1:
            create_synchronized_player(full_slowed_audio_abs_path, sync_words)
        
        # Populate Tab 4 with full text
        with tab4:
            st.text_area("전체 텍스트", full_transcript, height=300)
        
        # Populate Tab 5 with JSON data
        with tab5:
            st.json(transcript_data)
        
        # STAGE 2: Analyze segments with GPT
        status_placeholder.info("구문 분석 시작...")
        #progress_bar_placeholder.progress(0.4)
        
        # Create a container for segments in Tab 2
        with tab2:
            segments_container = st.container()
        
        # Initialize vocabulary map
        vocab_map = {}
            
        # Process each segment
        segment_analyses = {}
        total_segments = len(segment_db_data)
        
        for i, segment in enumerate(segment_db_data):
            segment_progress = 0.4 + (0.5 * ((i+1) / total_segments))  # Fixed to reach 0.9 at the end
            status_placeholder.info(f"세그먼트 {i + 1}/{total_segments} GPT 분석 중...")
            #progress_bar_placeholder.progress(segment_progress)
            
            # Analyze segment
            db_segment_id = segment['db_id']
            gpt_analysis = analyze_japanese_segment(
                segment['text'], segment['start'], segment['end'], segment['words']
            )
            
            # Process phrases and create audio segments
            segment_analysis = {"gpt_json": gpt_analysis, "phrase_audio_map": {}}
            
            if gpt_analysis and "phrases" in gpt_analysis:
                gpt_phrases = gpt_analysis.get("phrases", [])
                phrase_timings = [
                    (p.get("original_start_time", 0), p.get("original_end_time", 0)) 
                    for p in gpt_phrases
                ]
                phrases_dir = video_dir_abs_path / "phrases"
                
                # Create phrase audio segments
                audio_map = create_phrase_audio_segments(
                    downloaded_audio_path, gpt_phrases, phrase_timings, 
                    phrases_dir, 0.75, db_segment_id
                )
                segment_analysis["phrase_audio_map"] = audio_map

                # Process each phrase
                for p_idx, p_item in enumerate(gpt_phrases):
                    # Get the audio filename for this phrase from the audio map
                    p_audio_filename = audio_map.get(p_idx)
                    
                    # Extract sync words for this phrase
                    p_sync_words = extract_phrase_words_for_sync(
                        transcript_data, 
                        p_item.get("original_start_time", 0),
                        p_item.get("original_end_time", 0)
                    )
                    
                    # Collect vocab with kanji and timing - use the enhanced function
                    collect_vocab_with_kanji({"phrases": [p_item]}, vocab_map, p_sync_words)
                    
                    # Save phrase data to database
                    cursor.execute("""
                    INSERT INTO GptPhraseAnalyses 
                    (segment_id, phrase_index_in_segment, gpt_phrase_json, phrase_slowed_audio_path, phrase_words_for_sync_json) 
                    VALUES (?, ?, ?, ?, ?)
                    """, (
                        db_segment_id, p_idx, json.dumps(p_item), 
                        p_audio_filename, json.dumps(p_sync_words)
                    ))
            
            conn.commit()
            segment_analyses[db_segment_id] = segment_analysis
            
            # Generate HTML for this segment and add to UI immediately
            with segments_container:
                html = generate_breakdown_html_from_session_state(
                    segment_analysis, video_dir_name, db_segment_id
                )
                num_phrases = len(segment_analysis.get("gpt_json", {}).get("phrases", []))
                st.components.v1.html(
                    html, height=max(150, num_phrases * 400), scrolling=True
                )
                st.markdown("<hr style='border-top:1.5px solid #ddd; margin-top:20px; margin-bottom:20px'>", 
                           unsafe_allow_html=True)
        
        # Save vocab map to session state
        st.session_state["vocab_map"] = vocab_map
        
        # Populate Tab 3 (단어 tab) with enhanced vocabulary implementation
        populate_vocab_tab(tab_word, vocab_map, video_id, video_dir_name)
        
        # STAGE 3: Extract kanji information
        status_placeholder.info("한자 정보 추출 및 저장 중...")
        #progress_bar_placeholder.progress(0.95)
        
        extract_and_store_kanji_for_video(conn, video_id)
        
        # Populate Tab 3 with kanji data
        with tab3:
            kanji_entries = conn.execute("SELECT character, reading, meaning FROM KanjiEntries WHERE video_id = ?", 
                                        (video_id,)).fetchall()
            if kanji_entries:
                sorted_kanji_items = sorted(kanji_entries, key=lambda x: x['character'])
                num_columns = 2
                cols = st.columns(num_columns)
                st.markdown('<div class="kanji-card-container">', unsafe_allow_html=True)
                for idx, kanji_info in enumerate(sorted_kanji_items):
                    with cols[idx % num_columns]:
                        k_desc, h_mean = "", ""
                        original_meaning = kanji_info["meaning"]
                        parts = []
                        if " / " in original_meaning:
                            parts = original_meaning.split(" / ", 1)
                            k_desc = parts[0]
                        if len(parts) > 1 and len(parts[1]) > 0:
                            h_mean = parts[1]
                        else:
                            k_desc = original_meaning
                        html_c = f"""<div class="kanji-card"><div class="kanji-char-display">{kanji_info['character']}</div><div class="kanji-info"><div class="reading"><strong>Reading:</strong> <span class="value">{kanji_info['reading']}</span></div><div class="meaning-korean"><strong>Korean:</strong> <span class="value">{k_desc}</span></div>{'<div class="meaning-hanja"><strong>Hanja:</strong> <span class="value">' + h_mean + '</span></div>' if h_mean else ''}</div></div>"""
                        st.markdown(html_c, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
        
        # Final status
        status_placeholder.success("모든 처리 완료!")
        #progress_bar_placeholder.progress(1.0)
        
        # Save results to session state
        st.session_state["last_video_id"] = video_id
        st.session_state["last_full_transcript"] = full_transcript
        
        return {
            "video_id": video_id,
            "video_title": video_title,
            "segment_analyses": segment_analyses
        }
    except Exception as e_main_proc:
        status_placeholder.error(f"주요 처리 오류: {e_main_proc}")
        print(traceback.format_exc())  # Log full error to console
        return None
    finally:
        if conn:
            conn.close()
        # Clean up temporary directory
        if temp_dl_dir_obj:
            try:
                temp_dl_dir_obj.cleanup()
            except Exception as e_cleanup:
                print(f"Temp directory cleanup error: {e_cleanup}")  # Log cleanup errors

# --- Main Streamlit App UI ---
st.title("🇯🇵")

if not OPENAI_API_KEY: st.sidebar.error("OpenAI API key missing.")
if not DEEPGRAM_API_KEY: st.sidebar.error("Deepgram API key missing.")
st.sidebar.header("API 상태")
st.sidebar.markdown(f"OpenAI API: {'✅' if OPENAI_API_KEY else '❌'}")
st.sidebar.markdown(f"Deepgram API: {'✅' if DEEPGRAM_API_KEY else '❌'}")

youtube_url_input = st.text_input("YouTube URL:", placeholder="여기에 URL을 입력하세요...")
force_reprocess_checkbox = st.checkbox("강제 재처리 (이미 분석된 영상일 경우)")

analyze_button = st.button("분석 시작")

if analyze_button:
    if not youtube_url_input.strip():
        st.warning("YouTube URL을 입력해주세요.")
    elif not (OPENAI_API_KEY and DEEPGRAM_API_KEY):
        st.warning("API 키가 누락되었습니다.")
    else:
        run_full_pipeline(youtube_url_input.strip(), force_reprocess_checkbox)

# If there's already analyzed video data in the session state, display it
if "last_video_id" in st.session_state:
    conn = get_db_connection()
    if conn:
        video_info = conn.execute("SELECT video_title, video_data_directory FROM Videos WHERE id = ?", (st.session_state["last_video_id"],)).fetchone()
        if video_info:
            #st.success(f"최근 분석: {video_info['video_title']}")
            pass
        conn.close()