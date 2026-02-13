# config.py
"""Cloud-aware configuration. All secrets from st.secrets, all storage via Supabase."""

import streamlit as st

# ---------------------------------------------------------------------------
# Secrets — set these in Streamlit Cloud dashboard or .streamlit/secrets.toml
# ---------------------------------------------------------------------------

SUPABASE_URL: str = st.secrets["SUPABASE_URL"]
SUPABASE_KEY: str = st.secrets["SUPABASE_KEY"]          # service_role key
DEEPGRAM_API_KEY: str = st.secrets["DEEPGRAM_API_KEY"]
ANTHROPIC_API_KEY: str = st.secrets["ANTHROPIC_API_KEY"]

# ---------------------------------------------------------------------------
# Supabase Storage
# ---------------------------------------------------------------------------

STORAGE_BUCKET = "audio"
