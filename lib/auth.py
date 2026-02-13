import streamlit as st

def check_auth():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.markdown("<style>[data-testid='stSidebar']{display:none;}</style>", unsafe_allow_html=True)
        st.title("🔒")
        key = st.text_input("Access key:", type="password")
        if st.button("Submit"):
            if key == st.secrets.get("AUTH_KEY", ""):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid key.")
        st.stop()