import streamlit as st
from groq import Groq
from supabase import create_client, Client
from streamlit_mic_recorder import mic_recorder
import openai
import io
import json

# --- 1. CONFIGURATION ---
SUPABASE_URL = "https://rmvabqsxupkaglxperuj.supabase.co"
SUPABASE_KEY = st.secrets["sb_secret__nOuXZlGSf40iM1n9BaI1A_57Fj9PWJ"] 
GROQ_API_KEY = "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"
OPENAI_API_KEY = "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"

# Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="AMC Clinical AI Simulator", page_icon="🩺", layout="wide")

# --- 2. AUTHENTICATION ---
def check_subscription(email):
    try:
        response = supabase.table("active_subscribers").select("*").eq("email", email.lower()).execute()
        return len(response.data) > 0 and response.data[0]['status'] == 'active'
    except: return False

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Subscriber Access")
    user_email = st.text_input("Enter Gumroad Email")
    if st.button("Access Simulator"):
        if check_subscription(user_email.strip()):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Access Denied.")
    st.stop()

# --- 3. WHISPER HELPER ---
def transcribe_audio(audio_bytes):
    if not audio_bytes: return None
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "temp.wav"
    try:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text"
        )
        return transcript
    except Exception as e:
        st.error(f"Whisper Error: {e}")
        return None

# --- 4. STATION SELECTION ---
with st.sidebar:
    st.header("🗄️ Station Library")
    if st.button("🔄 Load New Random Recall"):
        res = supabase.table("exam_recalls").select("*").limit(1).execute()
        if res.data:
            st.session_state.current_station = res.data[0]
            st.session_state.messages = [] 
            st.rerun()

if "current_station" not in st.session_state:
    st.info("👈 Please load a station from the sidebar.")
    st.stop()

station = st.session_state.current_station

# --- 5. MAIN INTERFACE (Optimized for Mic Visibility) ---
st.title("🩺 AMC Clinical Simulator")

# Two-column layout
col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("📋 Candidate Instructions")
    with st.container(border=True, height=400):
        st.markdown(station['content'])
    
    # Optional: Display marking criteria here ONLY if you want to see them while practicing
    with st.expander("Show Marking Criteria (Examiner Only)"):
        st.markdown(station['marking_criteria'])

with col2:
    st.subheader("💬 Patient Interaction")
    
    # --- 🎙️ THE MISSING BUTTON: Placing it at the top of the chat for easy access ---
    st.write("Click and speak to the patient:")
    audio_data = mic_recorder(
        start_prompt="🎙️ START SPEAKING", 
        stop_prompt="🛑 SEND TO PATIENT", 
        key='mic_button'
    )

    # Transcription Logic
    if audio_data:
        with st.spinner("Whisper is listening..."):
            user_speech = transcribe_audio(audio_data['bytes'])
        if user_speech:
            if "messages" not in st.session_state: st.session_state.messages = []
            st.session_state.messages.append({"role": "user", "content": user_speech})

    # Container for the Chat History
    chat_container = st.container(height=500)
    
    with chat_container:
        if not st.session_state.get("messages"):
            # Same system prompt logic as before
            system_content = f"Act as the patient. Scenario: {station['content']}. Marking Criteria: {station['marking_criteria']}."
            st.session_state.messages = [{"role": "system", "content": system_content}]

        for msg in st.session_state.messages:
            if msg["role"] != "system":
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

    # Handle AI Response Trigger
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        with chat_container:
            with st.chat_message("assistant"):
                completion = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=st.session_state.messages,
                    temperature=0.6
                )
                ai_response = completion.choices[0].message.content
                st.markdown(ai_response)
                st.session_state.messages.append({"role": "assistant", "content": ai_response})
                st.rerun()
# --- 6. VETTING PANEL ---
st.divider()
with st.expander("🔍 Examiner's Marking Criteria & Source"):
    st.markdown(station['marking_criteria'])
    st.link_button("View Evidence Source", station['clinical_guideline_source'])
    
    st.write("---")
    st.write("### 🩺 Vetting Audit")
    if st.button("✅ Approve Logic"):
        supabase.table("exam_recalls").update({"vetted": True}).eq("id", station['id']).execute()
        st.success("Station Approved.")
