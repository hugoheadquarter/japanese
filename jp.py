# pages/test_rapidapi.py
"""
🔧 YouTube MP3 API — Full End-to-End Diagnostic

Tests the ENTIRE chain: API call → get link → actually download the file.
This will reveal if the CDN blocks datacenter IPs (which is the likely issue).
"""

import streamlit as st
import requests
import json
import time
import re

st.set_page_config(page_title="API Diagnostic", page_icon="🔧")
st.title("🔧 YouTube MP3 — Full Download Diagnostic")

# --- Check for API key ---
api_key = ""
try:
    api_key = st.secrets["RAPIDAPI_KEY"]
except Exception:
    pass

if not api_key:
    st.error("❌ No `RAPIDAPI_KEY` found in Streamlit secrets!")
    st.stop()

st.success(f"✅ API key found: `{api_key[:8]}...{api_key[-4:]}`")

# --- Video ID input ---
test_url = st.text_input(
    "YouTube URL to test",
    value="https://www.youtube.com/watch?v=zm-G5MqBAns",
)

def extract_video_id(url):
    for p in [r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})", r"(?:shorts/)([a-zA-Z0-9_-]{11})"]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

video_id = extract_video_id(test_url)
if video_id:
    st.info(f"📹 Video ID: `{video_id}`")
else:
    st.error("Could not extract video ID")
    st.stop()


if st.button("🧪 Run Full End-to-End Test", type="primary"):
    st.markdown("---")

    # =====================================================================
    # TEST 1: youtube-mp36 API call
    # =====================================================================
    st.markdown("## 1️⃣ API Call: youtube-mp36")
    
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "youtube-mp36.p.rapidapi.com",
    }
    api_url = f"https://youtube-mp36.p.rapidapi.com/dl?id={video_id}"
    
    with st.spinner("Calling API..."):
        # Poll until ready
        download_link = None
        title = None
        for attempt in range(8):
            resp = requests.get(api_url, headers=headers, timeout=30)
            data = resp.json()
            st.write(f"Attempt {attempt+1}: status=`{data.get('status')}` progress=`{data.get('progress')}` msg=`{data.get('msg')}`")
            
            if data.get("status") == "ok" and data.get("link"):
                download_link = data["link"]
                title = data.get("title", "unknown")
                st.success(f"✅ Got link for: **{title}**")
                break
            elif data.get("status") in ("processing", "fail"):
                if data.get("status") == "fail":
                    st.error(f"❌ API returned fail: {data.get('msg')}")
                    break
                time.sleep(5)
            else:
                time.sleep(3)
    
    if not download_link:
        st.error("❌ Could not get download link from API")
        st.stop()
    
    st.code(download_link, language=None)
    
    # =====================================================================
    # TEST 2: Try downloading the CDN link (THE CRITICAL TEST)
    # =====================================================================
    st.markdown("## 2️⃣ CDN Download Test")
    st.markdown("This tests whether the MP3 CDN link can actually be downloaded from this server (Streamlit Cloud datacenter IP).")
    
    # Test with different header combos
    header_configs = [
        {
            "name": "Browser-like headers",
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": "https://www.youtube.com/",
            }
        },
        {
            "name": "Minimal headers",
            "headers": {
                "User-Agent": "Mozilla/5.0",
            }
        },
        {
            "name": "No headers (raw request)",
            "headers": {}
        },
    ]
    
    cdn_works = False
    for config in header_configs:
        st.markdown(f"### Trying: {config['name']}")
        try:
            r = requests.get(download_link, headers=config["headers"], timeout=30, stream=True, allow_redirects=True)
            
            st.write(f"**Status:** `{r.status_code}`")
            st.write(f"**Content-Type:** `{r.headers.get('Content-Type', 'N/A')}`")
            st.write(f"**Content-Length:** `{r.headers.get('Content-Length', 'N/A')}`")
            st.write(f"**Final URL:** `{r.url[:100]}...`")
            
            # Show if Cloudflare is involved
            cf_ray = r.headers.get("cf-ray", "")
            server = r.headers.get("server", "")
            if cf_ray or "cloudflare" in server.lower():
                st.warning(f"☁️ **Cloudflare detected!** cf-ray: `{cf_ray}` server: `{server}`")
            
            if r.status_code == 200:
                content_type = r.headers.get("Content-Type", "")
                content_length = int(r.headers.get("Content-Length", 0))
                
                if "audio" in content_type or "octet-stream" in content_type or content_length > 100000:
                    st.success(f"✅ **CDN download WORKS!** File size: {content_length / 1024 / 1024:.1f} MB")
                    cdn_works = True
                    r.close()
                    break
                elif "text/html" in content_type:
                    body = r.content[:500].decode("utf-8", errors="replace")
                    st.error("❌ Got HTML instead of audio — likely Cloudflare challenge page")
                    st.code(body[:300])
                else:
                    # Try reading some bytes
                    chunk = next(r.iter_content(chunk_size=1024), b"")
                    if len(chunk) > 100:
                        st.success(f"✅ Getting data! Content-Type: {content_type}")
                        cdn_works = True
                        r.close()
                        break
                    else:
                        st.warning(f"⚠️ Got 200 but suspicious response. Content-Type: {content_type}")
            elif r.status_code == 404:
                st.error("❌ **404 Not Found** — CDN file doesn't exist or link expired")
            elif r.status_code == 403:
                st.error("❌ **403 Forbidden** — CDN is blocking this IP (datacenter block)")
            else:
                st.warning(f"⚠️ Unexpected status {r.status_code}")
            
            r.close()
        except Exception as e:
            st.error(f"❌ Error: {e}")
    
    # =====================================================================
    # TEST 3: Check what IP Streamlit sees
    # =====================================================================
    st.markdown("## 3️⃣ Server IP Check")
    try:
        ip_resp = requests.get("https://api.ipify.org?format=json", timeout=10)
        ip_data = ip_resp.json()
        st.write(f"**This server's public IP:** `{ip_data.get('ip', 'unknown')}`")
    except:
        st.write("Could not determine server IP")
    
    # =====================================================================
    # TEST 4: Alternative API — youtube-to-mp3-api  
    # =====================================================================
    st.markdown("## 4️⃣ Alternative: youtube-to-mp3-api (mahmudulhasandev)")
    st.caption("Subscribe free: https://rapidapi.com/mahmudulhasandev/api/youtube-to-mp3-api")
    
    alt_headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "youtube-to-mp3-api.p.rapidapi.com",
    }
    alt_url = f"https://youtube-to-mp3-api.p.rapidapi.com/mp3?url=https://www.youtube.com/watch?v={video_id}"
    
    try:
        r = requests.get(alt_url, headers=alt_headers, timeout=30)
        st.write(f"**Status:** `{r.status_code}`")
        if r.status_code == 403:
            st.warning("Not subscribed — subscribe to test this API")
        elif r.status_code == 200:
            data = r.json()
            st.json(data)
            # Try to find and test download link
            audio_url = None
            if isinstance(data, dict):
                for key in ["url", "link", "audio_url", "download"]:
                    if data.get(key):
                        audio_url = data[key]
                        break
                # Check nested
                if not audio_url and data.get("audios"):
                    audios = data["audios"]
                    if isinstance(audios, list) and len(audios) > 0:
                        audio_url = audios[0].get("url") or audios[0].get("link")
                if not audio_url and data.get("data"):
                    audio_url = data["data"].get("url") or data["data"].get("link")
            
            if audio_url:
                st.write(f"Found audio URL: `{str(audio_url)[:100]}...`")
                try:
                    dr = requests.get(audio_url, stream=True, timeout=15, headers={
                        "User-Agent": "Mozilla/5.0"
                    })
                    st.write(f"Download status: `{dr.status_code}` Content-Type: `{dr.headers.get('Content-Type')}`")
                    if dr.status_code == 200:
                        st.success("✅ This API's download link WORKS!")
                    dr.close()
                except Exception as e:
                    st.error(f"Download test failed: {e}")
    except Exception as e:
        st.error(f"Error: {e}")

    # =====================================================================
    # TEST 5: Alternative — YouTube Downloader with MP3 (proxified links)
    # =====================================================================
    st.markdown("## 5️⃣ Alternative: YouTube Downloader With MP3 (lifehacker-rayhan)")
    st.caption("Subscribe free: https://rapidapi.com/lifehacker-rayhan/api/youtube-downloader-with-mp3")
    
    alt2_headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "youtube-downloader-with-mp3.p.rapidapi.com",
    }
    alt2_url = f"https://youtube-downloader-with-mp3.p.rapidapi.com/v2/video/info?id={video_id}"
    
    try:
        r = requests.get(alt2_url, headers=alt2_headers, timeout=30)
        st.write(f"**Status:** `{r.status_code}`")
        if r.status_code == 403:
            st.warning("Not subscribed — subscribe to test this API")
        elif r.status_code == 200:
            data = r.json()
            # Don't dump the whole thing, it's huge
            st.write(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'not dict'}")
            
            # Look for audio download links
            if isinstance(data, dict):
                audios = data.get("audios") or data.get("audio") or []
                if audios and isinstance(audios, list):
                    st.write(f"Found {len(audios)} audio formats")
                    best = audios[0]
                    st.json(best)
                    audio_url = best.get("url") or best.get("link")
                    if audio_url:
                        try:
                            dr = requests.get(audio_url, stream=True, timeout=15, headers={
                                "User-Agent": "Mozilla/5.0"
                            })
                            cl = dr.headers.get("Content-Length", "0")
                            st.write(f"Download: status=`{dr.status_code}` size=`{cl}` type=`{dr.headers.get('Content-Type')}`")
                            if dr.status_code == 200 and int(cl or 0) > 10000:
                                st.success("✅ This API's proxied download link WORKS!")
                            dr.close()
                        except Exception as e:
                            st.error(f"Download test failed: {e}")
    except Exception as e:
        st.error(f"Error: {e}")

    # =====================================================================
    # SUMMARY
    # =====================================================================
    st.markdown("---")
    st.markdown("## 📊 Summary")
    if cdn_works:
        st.success("🎉 youtube-mp36 CDN download works! The main app should work too.")
    else:
        st.error("""
        ❌ **youtube-mp36 API works but CDN blocks this server's IP.**
        
        The CDN (123tokyo.xyz) is behind Cloudflare and blocks datacenter IPs.
        
        **Solutions:**
        1. Subscribe to an alternative API above that returns proxied/direct download links
        2. Use the file upload approach (download locally, upload to app)
        """)