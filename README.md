# AMC OSCE Simulator

This is a Streamlit-based clinical OSCE simulator.

## Setup

1. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Add required secrets in `.streamlit/secrets.toml`:
   ```toml
   SUPABASE_KEY = "your-supabase-key"
   GROQ_API_KEY = "your-groq-api-key"
   OPENAI_API_KEY = "your-openai-api-key"
   ```

## Run

```bash
streamlit run app.py
```

## Notes

- `.streamlit/secrets.toml` is ignored by `.gitignore` to keep credentials local.
- The app requires valid `SUPABASE_KEY`, `GROQ_API_KEY`, and `OPENAI_API_KEY` to run.
