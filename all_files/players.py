# lib/players.py
"""HTML/JS player components using static file URLs instead of base64.

All audio is served via Streamlit's static file serving:
  /_app/static/<video_dir>/<filename>

This eliminates base64 encoding, reducing page payloads from 50-200MB to <1MB.
"""

import json
import time
import streamlit as st


def _audio_url(video_dir_name: str, filename: str) -> str:
    """Build the static file URL for an audio file."""
    return f"/_app/static/{video_dir_name}/{filename}"


def _phrase_audio_url(video_dir_name: str, filename: str) -> str:
    """Build the static file URL for a phrase audio file."""
    return f"/_app/static/{video_dir_name}/phrases/{filename}"


# ---------------------------------------------------------------------------
# Main transcript player
# ---------------------------------------------------------------------------

def create_synchronized_player(
    video_dir_name: str,
    audio_filename: str,
    words_for_sync: list[dict],
    height: int = 700,
):
    """Full transcript player with word-level highlighting.

    Uses static URL for audio instead of base64.
    JS optimization: phrase groupings computed once, not on every timeupdate.
    """
    if not audio_filename or not video_dir_name:
        st.warning("Audio file information missing.")
        return

    audio_src = _audio_url(video_dir_name, audio_filename)
    words_json = json.dumps(words_for_sync or [])

    pid = f"main-{int(time.time() * 1000)}"
    audio_id = f"audio-{pid}"
    text_id = f"text-{pid}"

    html = f"""
    <div id="container-{pid}" style="width:100%;font-family:sans-serif;">
        <audio id="{audio_id}" controls style="width:100%;" preload="metadata">
            <source src="{audio_src}" type="audio/mp3">
        </audio>
        <div id="{text_id}"
             style="margin-top:10px;font-size:18px;line-height:1.8;
                    max-height:{height-100}px;overflow-y:auto;padding:5px;">
        </div>
    </div>
    <script>
    (function(){{
        "use strict";
        const words={words_json};
        const audio=document.getElementById('{audio_id}');
        const display=document.getElementById('{text_id}');
        if(!audio||!display)return;
        if(!words||!words.length){{display.innerHTML='<p style="color:grey;text-align:center;">No transcript data.</p>';return;}}

        // OPTIMIZED: compute phrase groupings ONCE
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
            // merge short phrases
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

        // Build a flat index: wordIndex -> word object
        const flatWords=[];
        PHRASES.forEach(ph=>ph.forEach(w=>flatWords.push(w)));

        function render(){{
            display.innerHTML='';
            let idx=0;
            PHRASES.forEach(ph=>{{
                const div=document.createElement('div');
                div.style.marginBottom='10px';
                ph.forEach(w=>{{
                    const span=document.createElement('span');
                    span.textContent=w.text;
                    span.id='w-{pid}-'+idx;
                    idx++;
                    span.style.cursor='pointer';
                    span.style.transition='color 0.2s,font-weight 0.2s';
                    span.onclick=()=>{{audio.currentTime=w.start;audio.play().catch(()=>{{}});}};
                    span.ondblclick=(e)=>{{e.preventDefault();audio.pause();}};
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
                }}else{{
                    el.style.color='';el.style.fontWeight='';
                }}
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
    """Generate HTML/JS for a single phrase player.

    Uses static URL for audio. Returns HTML string (not rendered directly).
    """
    words_json = json.dumps(phrase_words or [])
    kanji_json = json.dumps(kanji_map, ensure_ascii=False)

    audio_el_id = f"audio-phr-{phrase_unique_id}"
    text_el_id = f"text-phr-{phrase_unique_id}"
    status_id = f"status-phr-{phrase_unique_id}"

    audio_tag = ""
    if phrase_audio_filename and video_dir_name:
        src = _phrase_audio_url(video_dir_name, phrase_audio_filename)
        audio_tag = f'<audio id="{audio_el_id}" loop preload="none"><source src="{src}" type="audio/mp3"></audio>'

    return f"""
    <div class="phrase-player">
        <div id="{status_id}" style="font-size:12px;color:#666;margin-bottom:5px;text-align:center;"></div>
        {audio_tag}
        <div id="{text_el_id}"
             style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
                    font-size:30px;line-height:1.8;padding:5px 10px;cursor:pointer;">
        </div>
    </div>
    <script>
    (function(){{
        "use strict";
        if(!window.__pam){{window.__pam={{cur:null,clearFn:null,stopCur(){{
            if(this.cur)try{{this.cur.pause();}}catch(_){{}}
            if(this.clearFn)this.clearFn();this.cur=null;this.clearFn=null;
        }}}};}}

        const W={words_json};
        const KM=JSON.parse('{kanji_json.replace(chr(39), chr(92)+chr(39))}');
        const aud=document.getElementById('{audio_el_id}');
        const txt=document.getElementById('{text_el_id}');
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
                    window.__pam.stopCur();
                    window.__pam.cur=aud;window.__pam.clearFn=clearHL;
                    aud.currentTime=w.start;aud.play().catch(()=>{{}});
                }};
                span.ondblclick=(e)=>{{e.preventDefault();if(aud)aud.pause();}};
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
    """Generate the full breakdown HTML for one segment's phrases.

    Args:
        phrases_data: List of GPT phrase dicts
        phrase_audio_map: {phrase_idx: audio_filename}
        phrase_sync_words_map: {phrase_idx: sync_words_list}
        video_dir_name: For building audio URLs
        segment_id: For unique IDs
    """
    parts = []
    for i, phrase in enumerate(phrases_data):
        kanji_map = {
            k["kanji"]: k["reading"]
            for k in phrase.get("kanji_explanations", [])
            if k.get("kanji") and k.get("reading")
        }
        audio_fn = phrase_audio_map.get(i)
        sync_words = phrase_sync_words_map.get(i, [])
        uid = f"S{segment_id}_P{i}"

        # Phrase player
        player_html = create_phrase_player_html(
            video_dir_name, audio_fn, sync_words, uid, kanji_map
        )
        parts.append(player_html)

        # Word table
        font = '-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif'
        table = f"<table style='width:100%;border-collapse:collapse;margin-bottom:15px;font-family:{font};'>"
        table += "<tr>"
        for h in ["일본어", "로마자", "품사/설명", "한자"]:
            table += f"<th style='border:1px solid #e0e0e0;padding:8px 12px;text-align:left;background-color:#f2f2f2;font-size:15px;'>{h}</th>"
        table += "</tr>"
        for w in phrase.get("words", []):
            table += "<tr>"
            for k in ["japanese", "romaji", "meaning", "kanji"]:
                table += f"<td style='border:1px solid #e0e0e0;padding:8px 12px;text-align:left;font-size:15px;'>{w.get(k, '')}</td>"
            table += "</tr>"
        table += "</table>"
        parts.append(table)

        # Kanji explanations
        if phrase.get("kanji_explanations"):
            kanji_html = f"<div style='margin-top:5px;margin-bottom:10px;font-family:{font};'><ul class='kanji-list'>"
            for k in phrase["kanji_explanations"]:
                meaning = k.get("meaning", "")
                fmt = meaning
                if " / " in meaning:
                    korean, hanja = meaning.split(" / ", 1)
                    fmt = f"{korean} <strong>{hanja}</strong>"
                kanji_html += (
                    f"<li style='display:flex;align-items:baseline;margin-bottom:6px;font-size:15px;line-height:1.6;'>"
                    f"<strong style='flex-basis:40px;flex-shrink:0;font-weight:bold;text-align:center;'>{k.get('kanji','')}</strong>"
                    f"<span style='flex-basis:100px;flex-shrink:0;color:#4A4A4A;padding-left:8px;padding-right:8px;'>({k.get('reading','')})</span>"
                    f"<span style='flex-grow:1;'>{fmt}</span></li>"
                )
            kanji_html += "</ul></div>"
            parts.append(kanji_html)

        # Meaning
        if phrase.get("meaning"):
            parts.append(
                f"<div style='margin-top:5px;margin-bottom:15px;font-family:{font};'>"
                f"<p style='font-size:20px;line-height:1.6;margin-top:0;'>{phrase['meaning']}</p></div>"
            )

        # Separator between phrases
        if i < len(phrases_data) - 1:
            parts.append(
                "<hr style='margin-top:15px;margin-bottom:15px;border:0;height:1px;background-color:#e0e0e0;'>"
            )

    return "".join(parts)


def estimate_segment_height(phrases: list[dict]) -> int:
    """Estimate pixel height needed for a segment's breakdown HTML."""
    total = 40  # buffer
    for p in phrases:
        base = 110 + 38 + 40  # player + header + meaning
        word_rows = max(1, len(p.get("words", [])))
        kanji_block = 20 if p.get("kanji_explanations") else 0
        total += base + (word_rows * 30) + kanji_block
    return max(200, min(total, 2000))


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
    """Generate vocabulary card grid with audio playback.

    Uses static URL for audio instead of base64.
    JS optimization: single timeupdate listener instead of setTimeout.
    """
    # Sort
    if sort_by == "한자순":
        sorted_items = sorted(vocab_map.items(), key=lambda x: x[1]["kanji"])
    elif sort_by == "시간순":
        sorted_items = sorted(
            vocab_map.items(),
            key=lambda kv: float("inf") if kv[1]["start"] is None else kv[1]["start"],
        )
    else:
        sorted_items = sorted(vocab_map.items())

    # Filter
    fq = filter_query.lower()
    filtered = [
        (jp, info)
        for jp, info in sorted_items
        if not fq or fq in jp.lower() or fq in info["meaning"].lower()
    ]

    # Audio source
    audio_src = ""
    if audio_filename and video_dir_name:
        audio_src = _audio_url(video_dir_name, audio_filename)

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
    .stop-btn{padding:6px 12px;background:#f44336;color:#fff;font-size:14px;border-radius:4px;
        margin:5px;cursor:pointer;border:none;}
    </style>
    """

    if audio_src:
        html += f'<audio id="vocab-aud" preload="metadata"><source src="{audio_src}" type="audio/mp3"></audio>'
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
                jp_display = jp_display.replace(
                    kanji, f"<ruby>{kanji}<rt>{reading}</rt></ruby>"
                )

        start = info.get("start")
        end = info.get("end")
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

    # OPTIMIZED: single timeupdate listener for bound checking instead of setTimeout
    html += """
    <script>
    (function(){
        const player=document.getElementById('vocab-aud');
        const status=document.getElementById('vocab-status');
        let curCard=null;
        let endBound=null;

        // Use timeupdate to check bounds instead of setTimeout (no drift)
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
            if(isNaN(s)||isNaN(e)){
                card.style.border='2px solid orange';
                setTimeout(()=>{card.style.border='';},2000);
                return;
            }
            if(curCard){curCard.classList.remove('playing');}
            card.classList.add('playing');curCard=card;

            const EXTRA=0.8;
            const startT=s+0.3;
            endBound=Math.min(player.duration||e+EXTRA+1,e+EXTRA);

            player.currentTime=startT;
            player.play().then(()=>{
                status.innerHTML='<span style="color:blue;">▶ Playing</span>';
            }).catch(()=>{
                status.innerHTML='<span style="color:orange;">Play failed</span>';
                card.classList.remove('playing');
            });
        };

        window.stopVocab=function(){
            if(player)player.pause();
            endBound=null;
            if(curCard){curCard.classList.remove('playing');curCard=null;}
            status.innerHTML='<span style="color:green;">Ready</span>';
        };
    })();
    </script>
    """

    return html
