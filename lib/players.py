# lib/players.py
"""HTML/JS player components with base64 audio."""

import json
import os
import time
import base64
import streamlit as st
from config import AUDIO_FILES_STORAGE_ROOT_ABS_PATH


@st.cache_data(ttl=3600, show_spinner=False)
def load_audio_base64(filepath: str) -> str:
    """Read file, return base64 string. Cached so it doesn't re-encode on every rerun."""
    if not filepath or not os.path.exists(filepath):
        return ""
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _full_path(video_dir_name, filename):
    return str(AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_dir_name / filename)


def _phrase_path(video_dir_name, filename):
    return str(AUDIO_FILES_STORAGE_ROOT_ABS_PATH / video_dir_name / "phrases" / filename)


# ---------------------------------------------------------------------------
# Main transcript player
# ---------------------------------------------------------------------------

def create_synchronized_player(
    video_dir_name: str,
    audio_filename: str,
    words_for_sync: list[dict],
    height: int = 700,
):
    if not audio_filename or not video_dir_name:
        st.warning("Audio file information missing.")
        return

    b64 = load_audio_base64(_full_path(video_dir_name, audio_filename))
    if not b64:
        st.warning("Audio file not found.")
        return

    words_json = json.dumps(words_for_sync or [])
    pid = f"main-{int(time.time() * 1000)}"

    html = f"""
    <div style="width:100%;font-family:sans-serif;">
        <audio id="audio-{pid}" controls style="width:100%;" preload="metadata">
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
        </audio>
        <div id="text-{pid}"
             style="margin-top:10px;font-size:18px;line-height:1.8;
                    max-height:{height-100}px;overflow-y:auto;padding:5px;">
        </div>
    </div>
    <script>
    (function(){{
        "use strict";
        const words={words_json};
        const audio=document.getElementById('audio-{pid}');
        const display=document.getElementById('text-{pid}');
        if(!audio||!display)return;
        if(!words||!words.length){{display.innerHTML='<p style="color:grey;text-align:center;">No transcript data.</p>';return;}}

        function buildPhrases(){{
            const phrases=[];let cur=[];let lastEnd=0;
            words.forEach((w,i)=>{{
                const connected=i>0&&Math.abs(w.start-lastEnd)<0.3;
                const punct=['。','、','！','？'].some(p=>w.text.includes(p));
                cur.push(w);lastEnd=w.end;
                if(punct||(!connected&&cur.length>0)){{
                    if(cur.length>0){{phrases.push([...cur]);cur=[];}}
                }}
            }});
            if(cur.length>0)phrases.push(cur);
            const merged=[];
            for(let i=0;i<phrases.length;i++){{
                const txt=phrases[i].map(w=>w.text).join('');
                if(txt.length<=3&&i<phrases.length-1){{
                    phrases[i+1]=[...phrases[i],...phrases[i+1]];
                }}else{{merged.push(phrases[i]);}}
            }}
            return merged;
        }}

        const PHRASES=buildPhrases();
        const flatWords=[];
        PHRASES.forEach(ph=>ph.forEach(w=>flatWords.push(w)));

        function render(){{
            display.innerHTML='';let idx=0;
            PHRASES.forEach(ph=>{{
                const div=document.createElement('div');
                div.style.marginBottom='10px';
                ph.forEach(w=>{{
                    const span=document.createElement('span');
                    span.textContent=w.text;
                    span.id='w-{pid}-'+idx;idx++;
                    span.style.cursor='pointer';
                    span.style.transition='color 0.2s,font-weight 0.2s';
                    span.onclick=()=>{{if(!audio.paused){{audio.pause();}}else{{audio.currentTime=w.start;audio.play().catch(()=>{{}});}}}};
                    div.appendChild(span);
                }});
                display.appendChild(div);
            }});
        }}

        function highlight(){{
            const t=audio.currentTime;let active=null;
            for(let i=0;i<flatWords.length;i++){{
                const el=document.getElementById('w-{pid}-'+i);
                if(!el)continue;
                if(t>=flatWords[i].start&&t<flatWords[i].end){{
                    el.style.color='#ff4b4b';el.style.fontWeight='bold';active=el;
                }}else{{el.style.color='';el.style.fontWeight='';}}
            }}
            if(active&&display.contains(active)){{
                const dr=display.getBoundingClientRect();
                const wr=active.getBoundingClientRect();
                if(wr.top<dr.top+30||wr.bottom>dr.bottom-30){{
                    display.scrollTop+=(wr.top-dr.top)-(dr.height/2)+(wr.height/2);
                }}
            }}
        }}

        render();
        audio.addEventListener('timeupdate',highlight);
    }})();
    </script>
    """
    st.components.v1.html(html, height=height)


# ---------------------------------------------------------------------------
# Phrase player
# ---------------------------------------------------------------------------

def create_phrase_player_html(
    video_dir_name: str,
    phrase_audio_filename: str | None,
    phrase_words: list[dict],
    phrase_unique_id: str,
    kanji_map: dict,
) -> str:
    words_json = json.dumps(phrase_words or [])
    kanji_json = json.dumps(kanji_map, ensure_ascii=False)

    aid = f"audio-phr-{phrase_unique_id}"
    tid = f"text-phr-{phrase_unique_id}"

    audio_tag = ""
    if phrase_audio_filename and video_dir_name:
        b64 = load_audio_base64(_phrase_path(video_dir_name, phrase_audio_filename))
        if b64:
            audio_tag = f'<audio id="{aid}" loop preload="none"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>'

    return f"""
    <div class="phrase-player">
        {audio_tag}
        <div id="{tid}"
             style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
                    font-size:30px;line-height:1.8;padding:5px 10px;cursor:pointer;">
        </div>
    </div>
    <script>
    (function(){{
        "use strict";
        if(!window.parent.__pam){{window.parent.__pam={{cur:null,clearFn:null,stopCur(){{
            if(this.cur)try{{this.cur.pause();}}catch(_){{}}
            if(this.clearFn)this.clearFn();this.cur=null;this.clearFn=null;
        }}}};}}

        const W={words_json};
        const KM=JSON.parse('{kanji_json.replace(chr(39), chr(92)+chr(39))}');
        const aud=document.getElementById('{aid}');
        const txt=document.getElementById('{tid}');
        if(!txt)return;
        if(!W||!W.length)return;

        function clearHL(){{
            W.forEach((_,i)=>{{
                const el=document.getElementById('wp-{phrase_unique_id}-'+i);
                if(el){{el.style.color='';el.style.fontWeight='';}}
            }});
        }}

        function furigana(text,map){{
            let h='';
            for(let i=0;i<text.length;i++){{
                const c=text[i];const cc=c.charCodeAt(0);
                const isK=(cc>=0x4E00&&cc<=0x9FFF)||(cc>=0x3400&&cc<=0x4DBF)||(cc>=0xF900&&cc<=0xFAFF);
                if(isK&&map&&map[c])h+='<ruby><rb>'+c+'</rb><rt>'+map[c]+'</rt></ruby>';
                else h+=c;
            }}
            return h;
        }}

        function render(){{
            txt.innerHTML='';const div=document.createElement('div');
            W.forEach((w,i)=>{{
                const span=document.createElement('span');
                span.innerHTML=furigana(w.text,KM);
                span.id='wp-{phrase_unique_id}-'+i;
                span.style.cursor='pointer';span.style.transition='color 0.2s,font-weight 0.2s';
                span.style.marginRight='2px';
                span.onclick=()=>{{
                    if(!aud)return;
                    if(!aud.paused&&window.parent.__pam.cur===aud){{aud.pause();}}
                    else{{
                        window.parent.__pam.stopCur();
                        window.parent.__pam.cur=aud;window.parent.__pam.clearFn=clearHL;
                        aud.currentTime=w.start;aud.play().catch(()=>{{}});
                    }}
                }};
                div.appendChild(span);
            }});
            txt.appendChild(div);
        }}

        function highlight(){{
            if(!aud)return;const t=aud.currentTime;
            W.forEach((w,i)=>{{
                const el=document.getElementById('wp-{phrase_unique_id}-'+i);
                if(!el)return;
                if(t>=w.start&&t<w.end){{el.style.color='#ff4b4b';el.style.fontWeight='bold';}}
                else{{el.style.color='';el.style.fontWeight='';}}
            }});
        }}

        render();
        if(aud)aud.addEventListener('timeupdate',highlight);
    }})();
    </script>
    """


# ---------------------------------------------------------------------------
# Breakdown HTML for a segment
# ---------------------------------------------------------------------------

def generate_breakdown_html(
    phrases_data: list[dict],
    phrase_audio_map: dict[int, str | None],
    phrase_sync_words_map: dict[int, list[dict]],
    video_dir_name: str,
    segment_id: int,
) -> str:
    parts = []
    for i, phrase in enumerate(phrases_data):
        kanji_map = {
            k["kanji"]: k["reading"]
            for k in phrase.get("kanji_explanations", [])
            if k.get("kanji") and k.get("reading")
        }
        uid = f"S{segment_id}_P{i}"

        parts.append(create_phrase_player_html(
            video_dir_name, phrase_audio_map.get(i), phrase_sync_words_map.get(i, []), uid, kanji_map
        ))

        font = '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif'

        # Korean meaning right below the Japanese phrase
        if phrase.get("meaning"):
            parts.append(
                f"<div style='margin-top:0;margin-bottom:12px;font-family:{font};'>"
                f"<p style='font-size:20px;line-height:1.6;margin:0;color:#555;'>{phrase['meaning']}</p></div>"
            )

        # Build a lookup: for each word, find its kanji explanations (meaning only, no reading)
        kanji_explanations = phrase.get("kanji_explanations", [])
        ke_lookup = {}
        for ke in kanji_explanations:
            ch = ke.get("kanji", "")
            meaning = ke.get("meaning", "")
            if ch:
                ke_lookup[ch] = meaning

        # Check if ANY word in the phrase has kanji
        has_any_kanji = any(w.get("kanji") for w in phrase.get("words", []))

        th_style = "border:1px solid #e0e0e0;padding:8px 12px;text-align:left;background-color:#f2f2f2;font-size:15px;"
        td_style = "border:1px solid #e0e0e0;padding:8px 12px;text-align:left;font-size:15px;"

        table = f"<table style='width:100%;border-collapse:collapse;margin-bottom:15px;font-family:{font};'>"
        table += "<tr>"
        table += f"<th style='{th_style}'>일본어</th>"
        table += f"<th style='{th_style}'>로마자</th>"
        table += f"<th style='{th_style}'>품사/설명</th>"
        if has_any_kanji:
            table += f"<th style='{th_style}'>한자</th>"
        table += "</tr>"

        for w in phrase.get("words", []):
            table += "<tr>"
            table += f"<td style='{td_style}'>{w.get('japanese', '')}</td>"
            table += f"<td style='{td_style}'>{w.get('romaji', '')}</td>"
            table += f"<td style='{td_style}'>{w.get('meaning', '')}</td>"
            if has_any_kanji:
                # Build kanji cell: only actual kanji characters (filter out hiragana/katakana)
                kanji_str = w.get("kanji", "")
                if kanji_str:
                    kanji_parts = []
                    for ch in kanji_str:
                        cp = ord(ch)
                        is_kanji = (0x4E00 <= cp <= 0x9FFF) or (0x3400 <= cp <= 0x4DBF) or (0xF900 <= cp <= 0xFAFF)
                        if not is_kanji:
                            continue
                        m = ke_lookup.get(ch, "")
                        if m:
                            kanji_parts.append(f"<strong>{ch}</strong> <span style='color:#666;font-size:13px;'>{m}</span>")
                        else:
                            kanji_parts.append(f"<strong>{ch}</strong>")
                    if kanji_parts:
                        table += f"<td style='{td_style}'>{'<br>'.join(kanji_parts)}</td>"
                    else:
                        table += f"<td style='{td_style}'></td>"
                else:
                    table += f"<td style='{td_style}'></td>"
            table += "</tr>"

        table += "</table>"
        parts.append(table)

        if i < len(phrases_data) - 1:
            parts.append("<hr style='margin-top:15px;margin-bottom:15px;border:0;height:1px;background-color:#e0e0e0;'>")

    # Auto-resize via Streamlit's postMessage API
    parts.append("""
    <script>
    (function(){
        function sendHeight(){
            var h=document.documentElement.scrollHeight;
            if(h>10){
                window.parent.postMessage({type:"streamlit:setFrameHeight",height:h},"*");
            }
        }
        sendHeight();
        setTimeout(sendHeight,100);
        setTimeout(sendHeight,300);
    })();
    </script>
    """)

    return "".join(parts)


def estimate_segment_height(phrases: list[dict]) -> int:
    """Height estimate per segment - slightly generous to avoid clipping."""
    total = 30
    for p in phrases:
        # phrase text ~60px + meaning ~40px + table header ~42px + margin/padding ~30px
        total += 60 + 40 + 42 + 30
        word_rows = max(1, len(p.get("words", [])))
        total += word_rows * 40
        # hr between phrases
        total += 20
    return max(200, total)


# ---------------------------------------------------------------------------
# Vocabulary component
# ---------------------------------------------------------------------------

def create_vocab_component(
    vocab_map: dict,
    video_dir_name: str,
    audio_filename: str | None,
    filter_query: str = "",
    sort_by: str = "일본어순",
) -> str:
    if sort_by == "한자순":
        sorted_items = sorted(vocab_map.items(), key=lambda x: x[1]["kanji"])
    elif sort_by == "시간순":
        sorted_items = sorted(vocab_map.items(), key=lambda kv: float("inf") if kv[1]["start"] is None else kv[1]["start"])
    else:
        sorted_items = sorted(vocab_map.items())

    fq = filter_query.lower()
    filtered = [(jp, info) for jp, info in sorted_items if not fq or fq in jp.lower() or fq in info["meaning"].lower()]

    # Same file as transcript player → cache hit, no re-encode
    audio_b64 = ""
    if audio_filename and video_dir_name:
        audio_b64 = load_audio_base64(_full_path(video_dir_name, audio_filename))

    html = """
    <style>
    .vocab-card{border:1px solid #e0e0e0;border-radius:8px;padding:20px;margin-bottom:12px;
        background:#fff;box-shadow:0 2px 4px rgba(0,0,0,0.05);
        transition:box-shadow 0.2s,transform 0.2s;text-align:center;cursor:pointer;position:relative;}
    .vocab-card:hover{box-shadow:0 4px 8px rgba(0,0,0,0.1);transform:translateY(-2px);}
    .vocab-card.playing{background:#f8f8ff;border-color:#4285f4;box-shadow:0 4px 12px rgba(66,133,244,0.2);}
    .vocab-jp{font-size:2.2rem;margin-bottom:16px;color:#2c3e50;font-weight:500;line-height:1.4;}
    .vocab-mean{font-size:1.4rem;color:#16a085;font-weight:500;}
    .vocab-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:15px;padding:10px;}
    rt{font-size:0.7em;color:#555;opacity:0.9;}
    .no-timing{border:1px dashed #ff9800!important;}
    .ctrl-panel{text-align:center;margin-bottom:15px;padding:10px;background:#f8f8f8;border-radius:8px;}
    .stop-btn{padding:6px 12px;background:#f44336;color:#fff;font-size:14px;border-radius:4px;margin:5px;cursor:pointer;border:none;}
    </style>
    """

    if audio_b64:
        html += f'<audio id="vocab-aud" preload="metadata"><source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3"></audio>'
    else:
        html += '<audio id="vocab-aud"></audio>'

    html += """
    <div class="ctrl-panel">
        <button onclick="stopVocab()" class="stop-btn">Stop All Audio</button>
        <div id="vocab-status" style="margin-top:8px;font-size:14px;color:green;">Ready</div>
    </div>
    <div class="vocab-grid">
    """

    for jp, info in filtered:
        jp_display = jp
        for kanji, reading in info.get("kanji_readings", {}).items():
            if kanji in jp_display:
                jp_display = jp_display.replace(kanji, f"<ruby>{kanji}<rt>{reading}</rt></ruby>")

        start, end = info.get("start"), info.get("end")
        has_timing = start is not None and end is not None
        s_attr = f'data-start="{start}"' if has_timing else ""
        e_attr = f'data-end="{end}"' if has_timing else ""
        cls = "" if has_timing else "no-timing"

        html += f"""
        <div class="vocab-card {cls}" {s_attr} {e_attr} onclick="playVocab(this)">
            <div class="vocab-jp">{jp_display}</div>
            <div class="vocab-mean">{info['meaning']}</div>
        </div>
        """

    html += "</div>"

    html += """
    <script>
    (function(){
        const player=document.getElementById('vocab-aud');
        const status=document.getElementById('vocab-status');
        let curCard=null;let endBound=null;

        if(player){
            player.addEventListener('timeupdate',function(){
                if(endBound!==null&&player.currentTime>=endBound){
                    player.pause();
                    if(curCard){curCard.classList.remove('playing');curCard=null;}
                    endBound=null;
                    status.innerHTML='<span style="color:green;">Ready</span>';
                }
            });
        }

        window.playVocab=function(card){
            if(!player){status.innerHTML='<span style="color:red;">No audio</span>';return;}
            const s=parseFloat(card.dataset.start);
            const e=parseFloat(card.dataset.end);
            if(isNaN(s)||isNaN(e)){card.style.border='2px solid orange';setTimeout(()=>{card.style.border='';},2000);return;}
            if(curCard){curCard.classList.remove('playing');}
            card.classList.add('playing');curCard=card;
            const EXTRA=0.8;
            endBound=Math.min(player.duration||e+EXTRA+1,e+EXTRA);
            player.currentTime=s+0.3;
            player.play().then(()=>{status.innerHTML='<span style="color:blue;">▶ Playing</span>';})
            .catch(()=>{status.innerHTML='<span style="color:orange;">Play failed</span>';card.classList.remove('playing');});
        };

        window.stopVocab=function(){
            if(player)player.pause();endBound=null;
            if(curCard){curCard.classList.remove('playing');curCard=null;}
            status.innerHTML='<span style="color:green;">Ready</span>';
        };
    })();
    </script>
    """

    return html