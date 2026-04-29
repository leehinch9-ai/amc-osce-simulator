import streamlit as st
from groq import Groq
from supabase import create_client, Client
from streamlit_mic_recorder import mic_recorder
import openai
import io

# --- 1. SECURE CONFIGURATION ---
SUPABASE_URL = "https://rmvabqsxupkaglxperuj.supabase.co"
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

# Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="AMC Clinical AI", page_icon="🩺", layout="wide")

# --- 2. WHISPER TRANSCRIPTION ENGINE (Anti-Hallucination V2) ---
def transcribe_audio(audio_bytes):
    if not audio_bytes: return None
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "temp.wav"
    try:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            prompt="Doctor-patient clinical interview. Medical OSCE. Terms: Hello, History, Examination.",
            response_format="text"
        )
        
        # --- THE HALLUCINATION HAMMER ---
        clean_text = transcript.strip()
        
        # Expanded list of forbidden 'YouTube-ism' phrases
        forbidden = [
            "thank you for watching", "thanks for watching", "un videos", 
            "un.org", "social media", "subscribe", "please like", "share this video"
        ]
        
        # Check if the transcript contains any forbidden phrases
        if any(phrase in clean_text.lower() for phrase in forbidden):
            # If it's a hallucination, we'll try to see if 'Hello' was buried in there
            # otherwise, we ignore it.
            if "hello" in clean_text.lower():
                return "Hello."
            return None
        
        # Ignore very short, low-energy audio that Whisper turns into dots or noise
        if len(clean_text) <= 1 or clean_text in [".", "..", "..."]:
            return None
            
        return clean_text
    except Exception as e:
        st.error(f"Whisper Error: {e}")
        return None

# --- 3. AUTHENTICATION ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔐 Registrar Login")
    user_email = st.text_input("Enter Whitelisted Email")
    if st.button("Access Simulator"):
        res = supabase.table("active_subscribers").select("*").eq("email", user_email.lower()).execute()
        if res.data and res.data[0]['status'] == 'active':
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Access Denied.")
    st.stop()

# --- 4. STATION SELECTOR ---
with st.sidebar:
    st.header("🗄️ Station Library")
    if st.button("🔄 Load New Random Recall"):
        res = supabase.table("exam_recalls").select("*").limit(1).execute()
        if res.data:
            st.session_state.current_station = res.data[0]
            st.session_state.messages = [] 
            st.rerun()

if "current_station" not in st.session_state:
    st.info("👈 Please load a station from the sidebar to begin.")
    st.stop()

station = st.session_state.current_station

# --- 5. MAIN INTERFACE ---
st.title("🩺 AMC Clinical OSCE Simulator")

col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("📋 Candidate Instructions")
    with st.container(border=True, height=500):
        st.markdown(station['content'])
    st.caption(f"Source: {station.get('source_group', 'Telegram Recalls')}")

with col2:
    st.subheader("💬 Patient Interaction")
    
    st.write("Click and speak to the patient:")
    audio_data = mic_recorder(
        start_prompt="🎙️ START SPEAKING", 
        stop_prompt="🛑 STOP & SEND", 
        key='clinical_mic'
    )

    if audio_data:
        with st.spinner("Transcribing..."):
            user_speech = transcribe_audio(audio_data['bytes'])
        
        if user_speech:
            # SUCCESS PREVIEW
            st.success(f"**You said:** {user_speech}")
            
            if "messages" not in st.session_state: st.session_state.messages = []
            st.session_state.messages.append({"role": "user", "content": user_speech})
        else:
            # If hallucination was caught, we show a tip instead of junk
            st.warning("Speech too short or unclear. Please try speaking a full sentence.")

    # CHAT BOX
    chat_container = st.container(height=450, border=True)
    with chat_container:
        if not st.session_state.get("messages"):
            sys_msg = f"Act as the patient. Scenario: {station['content']}. Criteria: {station['marking_criteria']}. BE BRIEF."
            st.session_state.messages = [{"role": "system", "content": sys_msg}]

        for msg in st.session_state.messages:
            if msg["role"] != "system":
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

    # TRIGGER AI RESPONSE
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        with chat_container:
            with st.chat_message("assistant"):
                completion = groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=st.session_state.messages,
                    temperature=0.5
                )
                ai_response = completion.choices[0].message.content
                st.write(ai_response)
                st.session_state.messages.append({"role": "assistant", "content": ai_response})
                st.rerun()

# --- 6. VETTING & MARKING ---
st.divider()
with st.expander("🔍 Examiner's Marking Criteria & Evidence"):
    st.markdown("### 📋 Marking Criteria")
    st.write(station.get('marking_criteria', 'No criteria available.'))
    
    source_url = station.get('clinical_guideline_source')
    if source_url and isinstance(source_url, str) and source_url.startswith("http"):
        st.link_button("View Evidence Source", source_url)
    
    st.write("---")
    st.write("### 🩺 Vetting Audit")
    v_col1, v_col2 = st.columns(2)
    with v_col1:
        if st.button("✅ Approve Station"):
            supabase.table("exam_recalls").update({"vetted": True}).eq("id", station['id']).execute()
            st.success("Station vetted.")
    with v_col2:
        if st.button("🚩 Flag Inaccurate"):
            st.warning("Flagged.")
