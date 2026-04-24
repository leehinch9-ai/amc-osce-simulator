import streamlit as st
from groq import Groq
from supabase import create_client, Client

# --- CLOUD CONFIGURATION (Using Streamlit Secrets) ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
# -----------------------------

# Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
groq_client = Groq(api_key=GROQ_API_KEY)

st.set_page_config(page_title="AMC Clinical AI Simulator", page_icon="??")

# --- AUTHENTICATION SYSTEM (The Paywall) ---
def check_subscription(email):
    # Queries Supabase to see if the email exists and is active
    response = supabase.table("active_subscribers").select("*").eq("email", email).execute()
    if len(response.data) > 0 and response.data[0]['status'] == 'active':
        return True
    return False

# Login UI
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("?? Login Required")
    st.write("Enter the email address you used to purchase via Gumroad.")
    
    user_email = st.text_input("Email Address")
    if st.button("Access Simulator"):
        if check_subscription(user_email.strip()):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Email not found or subscription inactive. Please purchase access.")
    st.stop() # Stops the rest of the app from loading until logged in

# --- THE SIMULATOR (Only runs if authenticated) ---
st.title("AMC Clinical OSCE Simulator")
st.success("Authentication successful. Welcome.")

# Define the Master Prompt
SYSTEM_PROMPT = """Act as a strict, standard-adherent examiner for the Australian Medical Council (AMC) Clinical Examination. I am the candidate. 
Provide a 3-minute reading scenario. Include patient age, setting, presenting complaint, and tasks. Do not provide the diagnosis. 
Act as the patient. Grade me strictly out of 7 at the end, focusing heavily on pharmacological safety and clinical reasoning."""

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

for msg in st.session_state.messages:
    if msg["role"] != "system":
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

if prompt := st.chat_input("Type 'Begin' to start your station, or talk to the patient..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        
        # Calling the upgraded Groq API (Llama 3.3 70B)
        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=st.session_state.messages,
            temperature=0.5,
            max_tokens=500,
        )
        
        ai_response = completion.choices[0].message.content
        response_placeholder.markdown(ai_response)
        
    st.session_state.messages.append({"role": "assistant", "content": ai_response})