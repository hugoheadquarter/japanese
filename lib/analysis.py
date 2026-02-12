# lib/analysis.py
"""Claude Opus 4.6 analysis, Deepgram transcription, alignment, segmentation."""

import json
import os
import re
import time
import requests
import traceback
import anthropic
from lib.utils import normalize_japanese, norm_for_alignment

# Try to import fuzzy matching
try:
    from rapidfuzz import process, fuzz

    FUZZY_MATCHING_AVAILABLE = True
except ImportError:
    FUZZY_MATCHING_AVAILABLE = False


# ---------------------------------------------------------------------------
# Claude client (lazy init)
# ---------------------------------------------------------------------------
_claude_client: anthropic.Anthropic | None = None


def get_claude_client() -> anthropic.Anthropic | None:
    global _claude_client
    if _claude_client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            _claude_client = anthropic.Anthropic(api_key=api_key)
    return _claude_client


# ---------------------------------------------------------------------------
# Deepgram transcription
# ---------------------------------------------------------------------------

def transcribe_audio(audio_path: str) -> dict | None:
    """Transcribe audio using Deepgram API."""
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        print("Deepgram API key missing.")
        return None

    headers = {"Authorization": f"Token {api_key}", "Content-Type": "audio/mp3"}
    url = (
        "https://api.deepgram.com/v1/listen?"
        "model=nova-2&language=ja&smart_format=true&punctuation=true&utterances=true"
    )
    try:
        with open(audio_path, "rb") as f:
            response = requests.post(url, headers=headers, data=f)
        if response.status_code == 200:
            return response.json()

        print(f"Deepgram error: {response.status_code} - {response.text[:200]}")

        # Fallback model
        if "No such model" in response.text or response.status_code == 400:
            alt_url = (
                "https://api.deepgram.com/v1/listen?"
                "model=general&tier=enhanced&language=ja&"
                "smart_format=true&punctuation=true&utterances=true"
            )
            with open(audio_path, "rb") as f:
                alt_resp = requests.post(alt_url, headers=headers, data=f)
            if alt_resp.status_code == 200:
                return alt_resp.json()
            print(f"Deepgram fallback error: {alt_resp.status_code}")

        return None
    except Exception as e:
        print(f"Transcription exception: {e}")
        return None


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------

def prepare_japanese_segments(
    transcript_data: dict,
) -> tuple[str | None, list[dict]]:
    """Split transcript into segments using Deepgram utterances.

    Strategy:
    1. Use utterances (natural speech pauses) as primary boundaries
    2. Merge tiny utterances (≤3 words) into the next one
    3. Split long utterances (>15 words) at nearest 、or 。
    4. Hard cap at 20 words
    Fallback: if no utterances, use word-level splitting.
    """
    try:
        alt = (
            transcript_data.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
        )
        all_words = alt.get("words", [])
        if not all_words:
            return "", []

        full_transcript = alt.get("transcript", "").replace(" ", "")
        utterances = transcript_data.get("results", {}).get("utterances", [])

        # --- Build word groups from utterances or fallback ---
        if utterances:
            word_groups = _groups_from_utterances(utterances, all_words)
        else:
            word_groups = _groups_from_words_fallback(all_words)

        # --- Merge tiny groups (≤3 words) into next ---
        merged = []
        carry = []
        for grp in word_groups:
            combined = carry + grp
            if len(combined) <= 3 and len(merged) == 0:
                # Nothing to merge into yet, carry forward
                carry = combined
            elif len(combined) <= 3:
                # Attach to previous
                merged[-1].extend(combined)
                carry = []
            else:
                merged.append(combined)
                carry = []
        if carry:
            if merged:
                merged[-1].extend(carry)
            else:
                merged.append(carry)

        # --- Split long groups at 、 or hard cap at 20 ---
        MAX_WORDS = 20
        final_groups = []
        for grp in merged:
            if len(grp) <= MAX_WORDS:
                final_groups.append(grp)
            else:
                final_groups.extend(_split_long_group(grp, MAX_WORDS))

        # --- Build segment dicts ---
        segments = []
        for grp in final_groups:
            if not grp:
                continue
            seg_text = "".join(
                w.get("punctuated_word", w.get("word", "")).strip().replace(" ", "")
                for w in grp
            )
            segments.append({
                "start": grp[0]["start"],
                "end": grp[-1]["end"],
                "text": seg_text,
                "words": [dict(w) for w in grp],
            })

        return full_transcript, segments
    except Exception as e:
        print(f"Segment prep error: {e}")
        traceback.print_exc()
        return None, []


def _groups_from_utterances(utterances: list[dict], all_words: list[dict]) -> list[list[dict]]:
    """Map utterances to word lists by matching timestamps."""
    groups = []
    word_idx = 0
    for utt in utterances:
        utt_start = utt.get("start", 0)
        utt_end = utt.get("end", 0)
        grp = []
        while word_idx < len(all_words):
            w = all_words[word_idx]
            ws = w.get("start", 0)
            # Word belongs to this utterance if it starts within its time range
            # (small tolerance for floating point)
            if ws >= utt_start - 0.05 and ws <= utt_end + 0.05:
                grp.append(w)
                word_idx += 1
            elif ws > utt_end + 0.05:
                break
            else:
                word_idx += 1
        if grp:
            groups.append(grp)

    # Catch any leftover words not covered by utterances
    if word_idx < len(all_words):
        groups.append(all_words[word_idx:])

    return groups


def _groups_from_words_fallback(all_words: list[dict]) -> list[list[dict]]:
    """Fallback: split on 。？！ or every 20 words."""
    groups = []
    current = []
    for i, w in enumerate(all_words):
        current.append(w)
        text = w.get("punctuated_word", w.get("word", "")).strip()
        is_punct = any(p in text for p in "。？！")
        if is_punct or len(current) >= 20 or i == len(all_words) - 1:
            if current:
                groups.append(current)
                current = []
    if current:
        groups.append(current)
    return groups


def _split_long_group(words: list[dict], max_words: int) -> list[list[dict]]:
    """Split a word group that exceeds max_words at nearest comma/period."""
    result = []
    current = []
    for i, w in enumerate(words):
        current.append(w)
        text = w.get("punctuated_word", w.get("word", "")).strip()
        has_comma = "、" in text or "。" in text or "？" in text or "！" in text

        # Split at comma if we're past the halfway point, or hard cap
        if (has_comma and len(current) >= 8) or len(current) >= max_words:
            result.append(current)
            current = []

    if current:
        if result and len(current) <= 3:
            # Don't leave a tiny trailing fragment
            result[-1].extend(current)
        else:
            result.append(current)
    return result


# ---------------------------------------------------------------------------
# Word sync extraction
# ---------------------------------------------------------------------------

def extract_words_for_sync(
    transcript_data: dict, speed_factor: float = 0.75, time_offset: float = 0.3
) -> list[dict]:
    """Extract word timing data adjusted for slowed audio."""
    try:
        alt = (
            transcript_data.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
        )
        raw_words = alt.get("words", [])
        if not raw_words:
            return []

        adj = 1.0 / speed_factor
        result = []
        for w in raw_words:
            s = w.get("start", 0) * adj
            e = w.get("end", 0) * adj
            result.append(
                {
                    "text": w.get("punctuated_word", w.get("word", "")),
                    "start": max(0, s - time_offset),
                    "end": max(0.01, e - time_offset),
                }
            )
        return result
    except Exception as e:
        print(f"Word sync error: {e}")
        return []


def extract_phrase_words_for_sync(
    transcript_data: dict,
    phrase_start_orig: float,
    phrase_end_orig: float,
    speed_factor: float = 0.75,
    time_offset: float = 0.3,
) -> list[dict]:
    """Extract word timings for a specific phrase, relative to phrase start."""
    try:
        alt = (
            transcript_data.get("results", {})
            .get("channels", [{}])[0]
            .get("alternatives", [{}])[0]
        )
        raw_words = alt.get("words", [])
        if not raw_words:
            return []

        adj = 1.0 / speed_factor
        result = []
        for w in raw_words:
            ws = w.get("start", 0)
            we = w.get("end", 0)
            # STRICT containment: word must be fully within phrase bounds
            if ws >= phrase_start_orig and we <= phrase_end_orig:
                rs = (ws - phrase_start_orig) * adj
                re_ = (we - phrase_start_orig) * adj
                result.append(
                    {
                        "text": w.get("punctuated_word", w.get("word", "")),
                        "start": max(0, rs - time_offset),
                        "end": max(0.01, re_ - time_offset),
                    }
                )
        return result
    except Exception as e:
        print(f"Phrase sync error: {e}")
        return []


# ---------------------------------------------------------------------------
# Alignment (FIXED: sequential, no overlap)
# ---------------------------------------------------------------------------

def align_gpt_phrase_to_deepgram_words(
    gpt_phrase_text: str,
    deepgram_words: list[dict],
    search_start_index: int = 0,
    min_match_score: float = 70,
) -> tuple[float, float, float, int]:
    """Align a GPT phrase to Deepgram word timings.

    FIXED: Accepts search_start_index to prevent overlap with previous phrases.

    Returns: (start_time, end_time, match_score, end_word_index)
    """
    if not gpt_phrase_text or not deepgram_words:
        return 0, 0, 0, search_start_index

    norm_phrase = normalize_japanese(gpt_phrase_text)
    if not norm_phrase:
        return 0, 0, 0, search_start_index

    # Only search from search_start_index onwards
    search_words = deepgram_words[search_start_index:]

    if not search_words:
        # Fallback to last word
        last = deepgram_words[-1]
        return last["start"], last["end"], 0, len(deepgram_words)

    if FUZZY_MATCHING_AVAILABLE:
        return _align_fuzzy(
            norm_phrase, deepgram_words, search_start_index, min_match_score
        )
    else:
        return _align_fallback(norm_phrase, deepgram_words, search_start_index)


def _align_fuzzy(
    normalized_phrase: str,
    all_words: list[dict],
    start_idx: int,
    min_score: float,
) -> tuple[float, float, float, int]:
    """Fuzzy alignment searching only from start_idx onwards."""
    best_score = 0
    best_si = start_idx
    best_ei = start_idx
    n = len(all_words)

    for window_size in range(1, n - start_idx + 1):
        for si in range(start_idx, n - window_size + 1):
            ei = si + window_size
            window_words = all_words[si:ei]
            window_text = "".join(
                normalize_japanese(w.get("punctuated_word", w.get("word", "")))
                for w in window_words
            )
            if not window_text:
                continue

            score = fuzz.ratio(normalized_phrase, window_text)
            # Slight bonus for longer matches
            adj_score = score * (1 + 0.01 * len(window_text))

            if adj_score > best_score:
                best_score = adj_score
                best_si = si
                best_ei = ei - 1  # inclusive end index

    if best_score >= min_score and best_ei < n:
        return (
            all_words[best_si]["start"],
            all_words[best_ei]["end"],
            best_score,
            best_ei + 1,  # next phrase starts after this
        )

    # Fallback: use remaining words
    return (
        all_words[start_idx]["start"],
        all_words[-1]["end"],
        0,
        len(all_words),
    )


def _align_fallback(
    normalized_phrase: str,
    all_words: list[dict],
    start_idx: int,
) -> tuple[float, float, float, int]:
    """Simple string-search alignment from start_idx."""
    search_words = all_words[start_idx:]
    full_text = "".join(
        normalize_japanese(w.get("punctuated_word", w.get("word", "")))
        for w in search_words
    )
    if not full_text:
        return 0, 0, 0, start_idx

    pos = full_text.find(normalized_phrase)
    if pos >= 0:
        char_start = pos
        char_end = pos + len(normalized_phrase) - 1
        start_wi = None
        end_wi = None
        cp = 0
        for i, w in enumerate(search_words):
            wt = normalize_japanese(w.get("punctuated_word", w.get("word", "")))
            ncp = cp + len(wt)
            if start_wi is None and cp <= char_start < ncp:
                start_wi = i
            if cp <= char_end < ncp:
                end_wi = i
                break
            cp = ncp
        if start_wi is not None and end_wi is not None:
            abs_si = start_idx + start_wi
            abs_ei = start_idx + end_wi
            return (
                all_words[abs_si]["start"],
                all_words[abs_ei]["end"],
                100,
                abs_ei + 1,
            )

    return (
        all_words[start_idx]["start"],
        all_words[-1]["end"],
        0,
        len(all_words),
    )


# ---------------------------------------------------------------------------
# GPT / Claude analysis
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT = """You are an expert Japanese language analyst and tutor for Korean learners. Take a Japanese sentence, break it into smaller grammatically logical phrases/clauses, and provide detailed analysis for EACH phrase.

Return ONLY a valid JSON object (no markdown fences, no extra text) with this structure:
{
  "phrases": [
    {
      "number": 1,
      "text": "phrase text",
      "words": [
        {"japanese": "word", "kanji": "kanji or empty string", "romaji": "romaji", "meaning": "Korean meaning"}
      ],
      "kanji_explanations": [
        {"kanji": "大", "reading": "だい", "meaning": "클 / 대"}
      ],
      "meaning": "Korean translation of phrase"
    }
  ]
}

Guidelines:
1. Break into natural grammatical phrases/clauses. Keep phrases under 15 characters if possible.
2. Number each phrase sequentially (1, 2, 3...).
3. For each word: japanese, kanji (empty string if none), romaji (Hepburn), meaning (Korean, concise).
4. kanji_explanations: ONLY kanji in the current phrase. Include character, contextual reading, Korean meaning (e.g. "클 / 대" = Korean description + Hanja sound).
5. Provide natural Korean translation of each phrase.

Example for "ロシア大統領府によりますと":
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
    }
  ]
}

Return ONLY the JSON object."""


def create_fallback_json(segment_text: str) -> dict:
    """Create fallback analysis when Claude fails."""
    kanji_chars = [c for c in segment_text if 0x4E00 <= ord(c) <= 0x9FFF]
    ke = [{"kanji": c, "reading": "", "meaning": "분석 실패"} for c in kanji_chars]
    return {
        "phrases": [
            {
                "number": 1,
                "text": segment_text,
                "words": [
                    {
                        "japanese": segment_text,
                        "kanji": "".join(kanji_chars),
                        "romaji": "",
                        "meaning": "분석 실패",
                    }
                ],
                "kanji_explanations": ke,
                "meaning": segment_text,
            }
        ]
    }


def analyze_japanese_segment(
    segment_text: str,
    segment_start: float,
    segment_end: float,
    deepgram_words: list[dict],
    previous_context: str = "",
) -> dict:
    """Analyze a Japanese segment using Claude Opus 4.6.

    Args:
        previous_context: Text of previous 1-2 segments for disambiguation.

    Returns GPT-compatible JSON with phrases, words, kanji, meanings.
    Phrases are aligned sequentially to Deepgram words (no overlap).
    """
    client = get_claude_client()
    if not client:
        print("Claude client not available.")
        return create_fallback_json(segment_text)

    # Scale max_tokens to segment length
    max_tokens = min(4096, max(1024, len(segment_text) * 50))

    max_retries = 2
    retry_delay = 3

    # Build user message with optional context
    user_msg = ANALYSIS_PROMPT + "\n\n"
    if previous_context:
        user_msg += f"Previous context (for reference only, do NOT analyze this): {previous_context}\n\n"
    user_msg += f"Analyze this Japanese segment: {segment_text}"

    for attempt in range(max_retries):
        try:
            message = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": user_msg,
                    }
                ],
            )

            response_text = message.content[0].text

            # Strip any markdown fences just in case
            response_text = response_text.strip()
            if response_text.startswith("```"):
                response_text = re.sub(
                    r"^```(?:json)?\s*", "", response_text
                )
                response_text = re.sub(r"\s*```$", "", response_text)

            analysis = json.loads(response_text)

            # FIXED: Sequential alignment - no overlap between phrases
            if "phrases" in analysis and deepgram_words:
                last_word_index = 0
                for p in analysis["phrases"]:
                    s, e, score, new_idx = align_gpt_phrase_to_deepgram_words(
                        p.get("text", ""),
                        deepgram_words,
                        search_start_index=last_word_index,
                    )
                    p["original_start_time"] = s
                    p["original_end_time"] = e
                    p["match_score"] = score
                    last_word_index = new_idx
            elif "phrases" in analysis:
                # No deepgram words - distribute evenly
                n = len(analysis["phrases"])
                duration = segment_end - segment_start
                for i, p in enumerate(analysis["phrases"]):
                    p["original_start_time"] = segment_start + duration * (i / n)
                    p["original_end_time"] = segment_start + duration * ((i + 1) / n)
                    p["match_score"] = 0

            return analysis

        except json.JSONDecodeError as e:
            print(f"Claude JSON parse error (attempt {attempt + 1}): {e}")
            time.sleep(retry_delay * (attempt + 1))
        except Exception as e:
            print(f"Claude analysis error (attempt {attempt + 1}): {e}")
            time.sleep(retry_delay * (attempt + 1))

    return create_fallback_json(segment_text)


# ---------------------------------------------------------------------------
# Vocabulary collection
# ---------------------------------------------------------------------------

def collect_vocab_with_kanji(
    gpt_json: dict,
    vocab_map: dict,
    phrase_sync_words: list[dict] | None = None,
    speed_factor: float = 0.75,
    time_offset: float = 0.3,
):
    """Collect kanji words from GPT analysis with real timings."""
    if not gpt_json or "phrases" not in gpt_json:
        return

    for phr in gpt_json["phrases"]:
        # Build token-window lookup
        lookup = {}
        if phrase_sync_words:
            adj = 1.0 / speed_factor
            off = (phr.get("original_start_time", 0) or 0) * adj - time_offset
            toks = phrase_sync_words
            n = len(toks)

            # Single tokens
            for t in toks:
                lookup[norm_for_alignment(t["text"])] = (
                    t["start"] + off,
                    t["end"] + off,
                )

            # N-grams 2..8
            for span in range(2, min(9, n + 1)):
                for i in range(n - span + 1):
                    win = toks[i : i + span]
                    key = norm_for_alignment("".join(t["text"] for t in win))
                    lookup[key] = (win[0]["start"] + off, win[-1]["end"] + off)

        lkeys = list(lookup.keys())

        for w in phr["words"]:
            if not w.get("kanji"):
                continue
            surf = w.get("japanese", "")
            if not surf:
                continue

            k = norm_for_alignment(surf)
            start = end = None

            # Exact match
            if k in lookup:
                start, end = lookup[k]
            # Fuzzy match
            elif FUZZY_MATCHING_AVAILABLE and lkeys:
                hit, score, _ = process.extractOne(k, lkeys, scorer=fuzz.ratio)
                if score >= 90:
                    start, end = lookup[hit]

            # Discard micro-windows
            if start is not None and (end - start) < 0.15:
                start = end = None

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