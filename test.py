# minimal_test.py
import streamlit as st

st.title("Minimal Script Test")

SIMPLE_TEST_SCRIPT_TEMPLATE = """
<script>
    console.log("--- MINIMAL APP: SIMPLE JS TEST SCRIPT EXECUTING ---");
    alert("Minimal App: Simple JS Test Script Loaded!");
</script>
"""
if st.button("Inject Simple Script"):
    st.markdown(SIMPLE_TEST_SCRIPT_TEMPLATE, unsafe_allow_html=True)
    st.write("Simple script should have been injected above.")