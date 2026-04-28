import streamlit as st
from groq import Groq
from supabase import create_client, Client
from streamlit_mic_recorder import mic_recorder
import openai
import io

# --- 1. SECURE CONFIGURATION ---
SUPABASE_URL = "https://rmvabqsxupkaglxperuj.supabase.co"
# These pull from your Streamlit Dashboard Secrets
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

# Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="AMC Clinical Simulator", page_icon="🩺", layout="wide")

# --- 2. WHISPER TRANSCRIPTION ENGINE ---
def transcribe_audio(audio_bytes):
    if not audio_bytes: return None
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "temp.wav"
    try:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            # PROMPT helps filter out common hallucinations like "Share this video"
            prompt="A medical doctor performing a clinical OSCE examination in Australia.",
            response_format="text"
        )
        # Filter out known hallucination phrases
        hallucinations = ["share this video", "thanks for watching", "social media"]
        if any(h in transcript.lower() for h in hallucinations) and len(transcript) < 60:
            return None
        return transcript
    except Exception as e:
        st.error(f"Whisper Error: {e}")
        return None

# --- 3. AUTHENTICATION ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Registrar Access")
    user_email = st.text_input("Enter Whitelisted Email")
    if st.button("Log In"):
        res = supabase.table("active_subscribers").select("*").eq("email", user_email.lower()).execute()
        if res.data and res.data[0]['status'] == 'active':
            st.session_state.authenticated = True
            st.rerun()
        else: st.error("Access Denied.")
    st.stop()

# --- 4. STATION SELECTOR ---
with st.sidebar:
    st.header("🗄️ Station Library")
    if st.button("🔄 Shuffle New Station"):
        res = supabase.table("exam_recalls").select("*").limit(1).execute()
        if res.data:
            st.session_state.current_station = res.data[0]
            st.session_state.messages = [] 
            st.rerun()

if "current_station" not in st.session_state:
    st.info("👈 Please load a station from the sidebar.")
    st.stop()

station = st.session_state.current_station

# --- 5. MAIN UI LAYOUT ---
st.title("🩺 AMC Clinical Simulator")
col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("📋 Candidate Instructions")
    st.markdown(f"**ID:** {station['id']} | **Source:** {station.get('source_group', 'Telegram')}")
    with st.container(border=True, height=500):
        st.markdown(station['content'])

with col2:
    st.subheader("🎙️ Clinical Practice")
    
    # MIC BUTTON
    audio_data = mic_recorder(start_prompt="🎙️ START SPEAKING", stop_prompt="🛑 STOP & SEND", key='mic')
    
    if audio_data:
        with st.spinner("Transcribing..."):
            user_speech = transcribe_audio(audio_data['bytes'])
        if user_speech:
            if "messages" not in st.session_state: st.session_state.messages = []
            st.session_state.messages.append({"role": "user", "content": user_speech})

    # CHAT BOX
    chat_container = st.container(height=500, border=True)
    with chat_container:
        if not st.session_state.get("messages"):
            # SYSTEM PROMPT: Forces AI to be a realistic, "stubborn" patient
            sys_msg = f"Act as the patient. Scenario: {station['content']}. Criteria: {station['marking_criteria']}. BE BRIEF. Do not offer info unless asked specifically."
            st.session_state.messages = [{"role": "system", "content": sys_msg}]
        
        for msg in st.session_state.messages:
            if msg["role"] != "system":
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

    # AI TRIGGER
    if st.session_state.messages[-1]["role"] == "user":
        with chat_container:
            with st.chat_message("assistant"):
                comp = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=st.session_state.messages,
                    temperature=0.5
                )
                ai_reply = comp.choices[0].message.content
                st.write(ai_reply)
                st.session_state.messages.append({"role": "assistant", "content": ai_reply})
                st.rerun()

# --- 6. VETTING PANEL ---
st.divider()
with st.expander("🔍 Examiner's View & Vetting"):
    st.markdown("### Marking Criteria")
    st.write(station['marking_criteria'])
    if st.button("✅ Mark as Scientifically Vetted"):
        supabase.table("exam_recalls").update({"vetted": True}).eq("id", station['id']).execute()
        st.success("Station approved.")
