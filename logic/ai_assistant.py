"""
Two Groq-backed features, same API key, two different jobs:

- ask(): the "ask a question" box on Insights. The model is never given
  database access and never asked to calculate anything on its own --
  it only ever sees the exact same JSON snapshot the Insights page
  already renders (see db.manager_queries.insights_summary) and is told
  to answer from that data alone or say the data doesn't cover it. This
  app's whole pitch is "don't trust a number you can't verify" -- an
  assistant that could invent a number would break that on the first
  question asked of it.

- transcribe(): speech-to-text for the "record instead of typing" note
  on Counter Conversation -- a BDM speaks what was agreed instead of
  typing it one-handed on the road. The transcript always lands in an
  editable text field, never submitted directly, so a mis-heard word
  is a two-second fix, not a silent wrong record.
"""
import json
import os

from groq import Groq

MODEL = "llama-3.3-70b-versatile"
TRANSCRIBE_MODEL = "whisper-large-v3-turbo"

_SYSTEM_PROMPT = (
    "You are a data assistant for a field-sales manager using an internal tool. "
    "Below is a JSON snapshot of real numbers from their team's database. "
    "Answer the manager's question using ONLY the numbers in that JSON -- never "
    "invent, estimate, or recall a figure that isn't present in it. Simple "
    "arithmetic on the given numbers (differences, sums, ranking, comparisons) "
    "is fine. If the answer isn't in the data, say plainly that the data doesn't "
    "cover it instead of guessing. Keep answers short: two or three sentences, "
    "plain prose, no JSON or markdown formatting."
)


def get_api_key():
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return None


def ask(question: str, context: dict) -> str:
    """Returns a plain-English answer, or a clear message if the key is
    missing or the API call fails -- never raises, since one bad question
    shouldn't take down the rest of the Insights page."""
    api_key = get_api_key()
    if not api_key:
        return ("This isn't set up yet -- add GROQ_API_KEY (in .env locally, or "
                "Streamlit Cloud's Secrets in production) to turn it on.")

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.1,
            max_tokens=300,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "system", "content": f"DATA:\n{json.dumps(context, default=str)}"},
                {"role": "user", "content": question},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Couldn't get an answer right now ({e}). The rest of the page is unaffected."


def transcribe(audio_bytes: bytes, filename: str = "note.wav") -> str:
    """Returns the spoken text, or "" if the key is missing or the call
    fails -- a broken recording should never block filling in the field
    by hand instead."""
    api_key = get_api_key()
    if not api_key:
        return ""

    try:
        client = Groq(api_key=api_key)
        result = client.audio.transcriptions.create(
            file=(filename, audio_bytes),
            model=TRANSCRIBE_MODEL,
            response_format="text",
        )
        return result.strip() if isinstance(result, str) else ""
    except Exception:
        return ""
