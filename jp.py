# pages/test_edge_fn.py
"""
🧪 Test: Supabase Edge Function YouTube MP3 Proxy

This tests the full pipeline:
  Streamlit → Edge Function → RapidAPI → CDN download (from edge IP) → Supabase Storage → back to Streamlit

The Edge Function runs on Deno Deploy (different IP from Streamlit Cloud),
so it can download from CDNs that block datacenter IPs.
"""

import streamlit as st
import requests
import json
import re
import time

st.set_page_config(page_title="Edge Function Test", page_icon="🧪")
st.title("🧪 Edge Function YouTube MP3 Test")

# --- Gather config ---
supabase_url = ""
supabase_anon_key = ""

try:
    supabase_url = st.secrets["SUPABASE_URL"]
    supabase_anon_key = st.secrets["SUPABASE_KEY"]  # anon key
except Exception:
    pass

if not supabase_url or not supabase_anon_key:
    st.error("❌ Missing `SUPABASE_URL` or `SUPABASE_KEY` in Streamlit secrets!")
    st.info("""
    Add these to your Streamlit secrets:
    ```
    SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
    SUPABASE_KEY = "your-anon-key"
    ```
    """)
    st.stop()

edge_fn_url = f"{supabase_url}/functions/v1/youtube-mp3"
st.success(f"✅ Supabase URL: `{supabase_url}`")
st.info(f"🔗 Edge Function URL: `{edge_fn_url}`")

# =====================================================================
# TEST 1: Connectivity test
# =====================================================================
st.markdown("---")
st.markdown("## 1️⃣ Edge Function Connectivity Test")

if st.button("🔍 Test Edge Function", type="secondary"):
    with st.spinner("Calling edge function..."):
        try:
            resp = requests.post(
                edge_fn_url,
                json={"action": "test"},
                headers={
                    "Authorization": f"Bearer {supabase_anon_key}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            st.write(f"**HTTP Status:** `{resp.status_code}`")

            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", {})
                
                st.write(f"**Edge Function IP:** `{results.get('edge_ip', 'unknown')}`")
                st.write(f"**RapidAPI Key:** `{results.get('rapidapi_key_preview', 'not set')}`")
                st.write(f"**Supabase URL configured:** `{results.get('has_supabase_url', False)}`")
                st.write(f"**Supabase Service Key configured:** `{results.get('has_supabase_key', False)}`")

                # Compare IPs
                try:
                    my_ip = requests.get("https://api.ipify.org?format=json", timeout=5).json().get("ip")
                    edge_ip = results.get("edge_ip", "")
                    st.write(f"**Streamlit Cloud IP:** `{my_ip}`")
                    if my_ip != edge_ip and edge_ip and "error" not in str(edge_ip):
                        st.success(f"✅ **Different IPs!** Edge={edge_ip} vs Streamlit={my_ip} — proxy should work!")
                    elif my_ip == edge_ip:
                        st.warning("⚠️ Same IP — edge function may not help with CDN blocks")
                except:
                    pass

                if not results.get("has_rapidapi_key"):
                    st.error("❌ RAPIDAPI_KEY not set in Edge Function secrets!")
                    st.info("Go to Supabase Dashboard → Edge Functions → youtube-mp3 → Secrets → Add RAPIDAPI_KEY")
                if not results.get("has_supabase_key"):
                    st.error("❌ SUPABASE_SERVICE_ROLE_KEY not available — check Edge Function deployment")

            elif resp.status_code == 404:
                st.error("❌ Edge Function not found! Deploy it first.")
                st.info("""
                **How to deploy:**
                1. Supabase Dashboard → Edge Functions
                2. "Deploy a new function" → "Via Editor"
                3. Name: `youtube-mp3`
                4. Paste the edge function code
                5. Add secret: `RAPIDAPI_KEY`
                6. Create Storage bucket: `audio` (set to **public**)
                """)
            elif resp.status_code == 401:
                st.error("❌ Unauthorized — check your SUPABASE_KEY (anon key)")
            else:
                st.error(f"❌ Unexpected response: {resp.status_code}")
                st.code(resp.text[:500])
        except requests.exceptions.ConnectionError:
            st.error("❌ Cannot connect to Edge Function")
        except Exception as e:
            st.error(f"❌ Error: {e}")

# =====================================================================
# TEST 2: Full download test
# =====================================================================
st.markdown("---")
st.markdown("## 2️⃣ Full Download Test")

test_url = st.text_input(
    "YouTube URL",
    value="https://www.youtube.com/watch?v=zm-G5MqBAns",
)


def extract_video_id(url):
    for p in [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
    ]:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


video_id = extract_video_id(test_url)
if video_id:
    st.info(f"📹 Video ID: `{video_id}`")

if st.button("🚀 Download via Edge Function", type="primary"):
    if not video_id:
        st.error("Invalid YouTube URL")
        st.stop()

    progress = st.empty()
    log_area = st.empty()

    progress.info("⏳ Calling Edge Function... (this may take 15-30 seconds)")

    start = time.time()
    try:
        resp = requests.post(
            edge_fn_url,
            json={"video_id": video_id, "action": "download"},
            headers={
                "Authorization": f"Bearer {supabase_anon_key}",
                "Content-Type": "application/json",
            },
            timeout=120,  # Edge function can take a while
        )

        elapsed = time.time() - start
        st.write(f"**Response time:** {elapsed:.1f}s")
        st.write(f"**HTTP Status:** `{resp.status_code}`")

        data = resp.json()

        # Show logs
        logs = data.get("log", [])
        if logs:
            with st.expander("📋 Edge Function Logs", expanded=True):
                for line in logs:
                    st.text(line)

        if data.get("status") == "ok":
            url = data.get("url", "")
            title = data.get("title", "unknown")
            size = data.get("size_mb", "?")

            st.success(f"🎉 **SUCCESS!** Downloaded: {title} ({size} MB)")
            st.write(f"**Storage URL:** `{url}`")

            # Test that we can actually download from storage
            progress.info("⏳ Verifying download from Supabase Storage...")
            try:
                dl_resp = requests.get(url, stream=True, timeout=15)
                cl = dl_resp.headers.get("Content-Length", "0")
                ct = dl_resp.headers.get("Content-Type", "")
                st.write(
                    f"**Storage download:** status=`{dl_resp.status_code}` size=`{cl}` type=`{ct}`"
                )
                if dl_resp.status_code == 200 and int(cl or 0) > 10000:
                    st.success("✅ **Full pipeline verified!** Streamlit can download from Supabase Storage.")
                    st.balloons()
                    
                    # Provide audio player
                    st.audio(url, format="audio/mpeg")
                else:
                    st.warning(
                        f"⚠️ Storage returned {dl_resp.status_code} with {cl} bytes"
                    )
                dl_resp.close()
            except Exception as e:
                st.error(f"Storage download test failed: {e}")

            progress.empty()
        else:
            error = data.get("error", "Unknown error")
            progress.error(f"❌ {error}")

    except requests.exceptions.Timeout:
        st.error("❌ Edge Function timed out (>120s)")
    except requests.exceptions.ConnectionError:
        st.error("❌ Cannot connect to Edge Function")
    except Exception as e:
        st.error(f"❌ Error: {e}")
        try:
            st.code(resp.text[:500])
        except:
            pass

# =====================================================================
# Setup instructions
# =====================================================================
st.markdown("---")
st.markdown("## 📖 Setup Instructions")
st.markdown("""
### Step 1: Create Supabase Storage Bucket
1. Go to **Supabase Dashboard → Storage**
2. Click **"New bucket"**
3. Name: `audio`
4. ✅ Check **"Public bucket"**
5. Click Create

### Step 2: Deploy Edge Function
1. Go to **Supabase Dashboard → Edge Functions**
2. Click **"Deploy a new function"** → **"Via Editor"**
3. Function name: `youtube-mp3`
4. Paste the edge function code (provided separately)
5. Click **Deploy**

### Step 3: Add Edge Function Secrets
1. In the Edge Function page, go to **Secrets**
2. Add: `RAPIDAPI_KEY` = your RapidAPI key

### Step 4: Add Streamlit Secrets
Make sure your Streamlit secrets have:
```toml
SUPABASE_URL = "https://YOUR-PROJECT.supabase.co"
SUPABASE_KEY = "your-anon-key"
RAPIDAPI_KEY = "your-rapidapi-key"
```

### Step 5: Test!
1. Click "Test Edge Function" above to verify connectivity
2. Click "Download via Edge Function" to test full pipeline
""")