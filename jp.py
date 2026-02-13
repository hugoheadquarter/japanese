# pages/test_rapidapi.py
"""
🔧 RapidAPI YouTube MP3 — Diagnostic Test Page

This page tests your RapidAPI key against multiple YouTube-to-MP3 APIs
to find which ones actually work.

SETUP:
  1. Go to rapidapi.com and subscribe (free plan) to ONE OR MORE of these APIs:
     - https://rapidapi.com/ytjar/api/youtube-mp36
     - https://rapidapi.com/mahmudulhasandev/api/youtube-to-mp3-api
     - https://rapidapi.com/elisbushaj2/api/youtube-mp310
  2. Add your key to Streamlit secrets: RAPIDAPI_KEY = "your-key"
  3. Run this test page
"""

import streamlit as st
import requests
import json
import time
import re

st.set_page_config(page_title="RapidAPI Test", page_icon="🔧")
st.title("🔧 RapidAPI YouTube MP3 — Diagnostic Test")

# --- Check for API key ---
api_key = ""
try:
    api_key = st.secrets["RAPIDAPI_KEY"]
except Exception:
    pass

if not api_key:
    st.error("❌ No `RAPIDAPI_KEY` found in Streamlit secrets!")
    st.markdown("""
    **How to fix:**
    1. Go to [rapidapi.com](https://rapidapi.com) → Sign up
    2. Go to **Developer Dashboard** → **Apps** → Copy your API key
    3. In Streamlit Cloud: **Settings** → **Secrets** → Add:
    ```
    RAPIDAPI_KEY = "your-key-here"
    ```
    """)
    st.stop()

st.success(f"✅ API key found: `{api_key[:8]}...{api_key[-4:]}`")

# --- Video ID input ---
test_url = st.text_input(
    "YouTube URL to test",
    value="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    help="Use a short video for faster testing"
)

def extract_video_id(url):
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:embed/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

video_id = extract_video_id(test_url)
if video_id:
    st.info(f"📹 Video ID: `{video_id}`")
else:
    st.error("Could not extract video ID from URL")
    st.stop()

# --- Define APIs to test ---
APIS = [
    {
        "name": "YouTube MP3 (youtube-mp36)",
        "subscribe_url": "https://rapidapi.com/ytjar/api/youtube-mp36",
        "host": "youtube-mp36.p.rapidapi.com",
        "method": "GET",
        "url": f"https://youtube-mp36.p.rapidapi.com/dl?id={video_id}",
        "response_type": "json",
        "notes": "Most popular. Returns {status, link, title}",
    },
    {
        "name": "YouTube to MP3 API (mahmudulhasandev)",
        "subscribe_url": "https://rapidapi.com/mahmudulhasandev/api/youtube-to-mp3-api",
        "host": "youtube-to-mp3-api.p.rapidapi.com",
        "method": "GET",
        "url": f"https://youtube-to-mp3-api.p.rapidapi.com/mp3?url=https://www.youtube.com/watch?v={video_id}",
        "response_type": "json",
        "notes": "Takes full URL. Returns audio URLs + metadata",
    },
    {
        "name": "YouTube MP3 Downloader (elisbushaj2)",
        "subscribe_url": "https://rapidapi.com/elisbushaj2/api/youtube-mp310",
        "host": "youtube-mp310.p.rapidapi.com",
        "method": "GET",
        "url": f"https://youtube-mp310.p.rapidapi.com/download/mp3?url=https://www.youtube.com/watch?v={video_id}",
        "response_type": "text",
        "notes": "Returns plain-text MP3 download link",
    },
    {
        "name": "YouTube to MP3 Converter (cybernetwebdesign)",
        "subscribe_url": "https://rapidapi.com/cybernetwebdesign/api/youtube-to-mp3-converter2",
        "host": "youtube-to-mp3-converter2.p.rapidapi.com",
        "method": "GET",
        "url": f"https://youtube-to-mp3-converter2.p.rapidapi.com/getMP3?url=https://www.youtube.com/watch?v={video_id}",
        "response_type": "json",
        "notes": "Returns {status, data: {link, title}}",
    },
]

# --- Test button ---
if st.button("🧪 Run Diagnostic Tests", type="primary"):
    st.markdown("---")
    
    results = []
    
    for api in APIS:
        st.markdown(f"### {api['name']}")
        st.caption(f"Host: `{api['host']}`")
        
        headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": api["host"],
        }
        
        with st.spinner(f"Testing {api['name']}..."):
            try:
                start = time.time()
                resp = requests.get(api["url"], headers=headers, timeout=30)
                elapsed = time.time() - start
                
                st.write(f"**Status Code:** `{resp.status_code}` | **Time:** `{elapsed:.1f}s`")
                
                if resp.status_code == 403:
                    st.error("❌ **403 Forbidden — You are NOT subscribed to this API!**")
                    st.markdown(f"👉 [Subscribe here (free)]({api['subscribe_url']})")
                    st.markdown("Click **Subscribe to Test** or **Subscribe** on the free/basic plan, then re-run this test.")
                    results.append({"api": api["name"], "status": "NOT SUBSCRIBED"})
                    
                elif resp.status_code == 401:
                    st.error("❌ **401 Unauthorized — Invalid API key**")
                    results.append({"api": api["name"], "status": "BAD KEY"})
                    
                elif resp.status_code == 429:
                    st.warning("⚠️ **429 Too Many Requests — Rate limit hit**")
                    results.append({"api": api["name"], "status": "RATE LIMITED"})
                    
                elif resp.status_code == 200:
                    st.success(f"✅ **200 OK** — API is responding!")
                    
                    # Show response
                    if api["response_type"] == "json":
                        try:
                            data = resp.json()
                            st.json(data)
                            
                            # Check for download link
                            link = None
                            if isinstance(data, dict):
                                link = data.get("link") or data.get("url")
                                if not link and data.get("data"):
                                    link = data["data"].get("link") or data["data"].get("url")
                            
                            if link:
                                st.success(f"🎵 **Download link found!** This API works!")
                                st.code(link[:120] + "..." if len(str(link)) > 120 else link)
                                results.append({"api": api["name"], "status": "✅ WORKING", "link": link})
                            else:
                                st.warning("⚠️ Got 200 but no download link found in response")
                                results.append({"api": api["name"], "status": "NO LINK"})
                        except Exception as e:
                            st.warning(f"Response is not JSON: {resp.text[:300]}")
                            results.append({"api": api["name"], "status": "BAD RESPONSE"})
                    else:
                        # Text response
                        text = resp.text.strip()
                        st.code(text[:500])
                        if text.startswith("http"):
                            st.success("🎵 **Download link found!** This API works!")
                            results.append({"api": api["name"], "status": "✅ WORKING", "link": text})
                        else:
                            results.append({"api": api["name"], "status": "UNKNOWN RESPONSE"})
                else:
                    st.warning(f"⚠️ Unexpected status: {resp.status_code}")
                    st.code(resp.text[:500])
                    results.append({"api": api["name"], "status": f"HTTP {resp.status_code}"})
                    
            except requests.exceptions.Timeout:
                st.error("❌ **Timeout** — API did not respond within 30s")
                results.append({"api": api["name"], "status": "TIMEOUT"})
            except Exception as e:
                st.error(f"❌ **Error:** {e}")
                results.append({"api": api["name"], "status": f"ERROR: {e}"})
        
        st.markdown("---")
    
    # --- Summary ---
    st.markdown("## 📊 Summary")
    
    working = [r for r in results if "WORKING" in r.get("status", "")]
    not_subscribed = [r for r in results if "NOT SUBSCRIBED" in r.get("status", "")]
    
    if working:
        st.success(f"🎉 **{len(working)} API(s) working!**")
        for r in working:
            st.write(f"  ✅ {r['api']}")
        st.markdown("### Next step: Update `lib/audio.py` to use the working API")
    elif not_subscribed:
        st.error(f"❌ **No APIs working.** {len(not_subscribed)} API(s) need subscription.")
        st.markdown("""
        ### 🔑 How to fix:
        1. Click the subscribe links above for at least ONE API
        2. Choose the **Free** or **Basic** plan
        3. Come back here and re-run the test
        
        **The most reliable option is usually:**
        - [YouTube MP3 (youtube-mp36)](https://rapidapi.com/ytjar/api/youtube-mp36)
        """)
    else:
        st.error("❌ All APIs failed for other reasons. Check the details above.")