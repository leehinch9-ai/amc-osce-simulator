import streamlit as st
from groq import Groq, AuthenticationError as GroqAuthenticationError
from postgrest.exceptions import APIError
from supabase import create_client, Client
from audio_recorder_streamlit import audio_recorder
import openai
from openai import AuthenticationError, OpenAIError
import io

# --- 1. SECURE CONFIGURATION ---
SUPABASE_URL = "https://rmvabqsxupkaglxperuj.supabase.co"

def _get_secret(key: str):
    try:
        return st.secrets[key]
    except Exception:
        return None

SUPABASE_KEY = _get_secret("SUPABASE_KEY")
GROQ_API_KEY = _get_secret("GROQ_API_KEY")
OPENAI_API_KEY = _get_secret("OPENAI_API_KEY")

if not (SUPABASE_KEY and GROQ_API_KEY and OPENAI_API_KEY):
    st.error("Missing Streamlit secrets: SUPABASE_KEY, GROQ_API_KEY, and OPENAI_API_KEY are required.")
    st.stop()
    raise RuntimeError("Missing Streamlit secrets")

# Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

st.set_page_config(page_title="AMC Clinical AI", page_icon="🩺", layout="wide")

# --- 2. WHISPER TRANSCRIPTION ENGINE (Hardened) ---
def transcribe_audio(audio_bytes):
    if not audio_bytes or len(audio_bytes) < 5000: # Ignore tiny files (noise)
        return None
    
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "temp.webm"
    try:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            prompt="Doctor-patient clinical interview. Medical OSCE. Phrases: Hello, examination, symptoms.",
            response_format="text",
            temperature=0.0 # Force accuracy over creativity
        )
        
        clean_text = transcript.strip()
        
        # Aggressive Hallucination Filter
        forbidden = ["un.org", "un videos", "watching", "social media", "subscribe", "please like", "share this video"]
        if any(phrase in clean_text.lower() for phrase in forbidden):
            return None
            
        if len(clean_text) < 2 or clean_text in [".", "..", "..."]:
            return None
            
        return clean_text
    except AuthenticationError:
        st.error("OpenAI API error: invalid or missing OPENAI_API_KEY. Please update `.streamlit/secrets.toml` with your real OpenAI key.")
        return None
    except OpenAIError as e:
        st.error(f"Whisper Error: {e}")
        return None
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
        try:
            res = supabase.table("active_subscribers").select("*").eq("email", user_email.lower()).execute()
            if res.data and res.data[0]['status'] == 'active':
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Access Denied.")
        except APIError as e:
            st.error("Supabase API error: invalid or missing `SUPABASE_KEY`. Please update `.streamlit/secrets.toml` with a valid Supabase key.")
            st.stop()
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
    
    if st.button("🗑️ Reset Current Chat"):
        st.session_state.messages = []
        st.rerun()

if "current_station" not in st.session_state:
    st.info("👈 Please load a station from the sidebar to begin.")
    st.stop()

station = st.session_state.current_station

# --- 5. MAIN INTERFACE ---
st.title("🩺 AMC Clinical OSCE Simulator")

# --- STABLE MIC PLACEMENT ---
# Moving the recorder to a dedicated, stable top-level row to prevent 'Container not found' errors
st.write("### 🎙️ Voice Interaction")
with st.container():
    try:
        audio_bytes = audio_recorder(
            text="START RECORDING",
            key='stable_clinical_mic'
        )
    except Exception as e:
        audio_bytes = None
        st.error("Audio recorder failed to initialize. Please refresh the page and try again.")

if audio_bytes:
    with st.spinner("Whisper is listening..."):
        user_speech = transcribe_audio(audio_bytes)
    if user_speech:
        st.success(f"**Heard:** {user_speech}")
        if "messages" not in st.session_state:
            st.session_state.messages = []
        st.session_state.messages.append({"role": "user", "content": user_speech})
        st.rerun()

st.divider()

col1, col2 = st.columns([1, 1.2])

with col1:
    st.subheader("📋 Candidate Instructions")
    with st.container(border=True, height=500):
        st.markdown(station['content'])

with col2:
    st.subheader("💬 Patient Interaction")
    
    # CHAT BOX DISPLAY
    chat_container = st.container(height=450, border=True)
    with chat_container:
        if not st.session_state.get("messages"):
            sys_msg = f"Act as the patient. Scenario: {station['content']}. Criteria: {station['marking_criteria']}. BE BRIEF."
            st.session_state.messages = [{"role": "system", "content": sys_msg}]

        for msg in st.session_state.messages:
            if msg["role"] != "system":
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

    # TEXT INPUT OVERRIDE
    text_input = st.chat_input("Or type your clinical question here...")
    if text_input:
        st.session_state.messages.append({"role": "user", "content": text_input})
        st.rerun()

    # TRIGGER AI RESPONSE
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
        with chat_container:
            with st.chat_message("assistant"):
                try:
                    completion = groq_client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=st.session_state.messages,
                        temperature=0.5
                    )
                    ai_response = completion.choices[0].message.content
                    st.write(ai_response)
                    st.session_state.messages.append({"role": "assistant", "content": ai_response})
                    st.rerun()
                except GroqAuthenticationError:
                    st.error("Groq API error: invalid or missing GROQ_API_KEY. Please update `.streamlit/secrets.toml` with a valid key.")
                except Exception as e:
                    st.error(f"Groq Error: {e}")

# --- 6. VETTING & MARKING ---
st.divider()
with st.expander("🔍 Examiner's Marking Criteria"):
    st.markdown("### 📋 Marking Criteria")
    st.write(station.get('marking_criteria', 'No criteria available.'))
    
    source_url = station.get('clinical_guideline_source')
    if source_url and isinstance(source_url, str) and source_url.startswith("http"):
        st.link_button("View Evidence Source", source_url)
    
    if st.button("✅ Approve Station"):
        supabase.table("exam_recalls").update({"vetted": True}).eq("id", station['id']).execute()
        st.success("Station vetted.")
