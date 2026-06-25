"""Standalone Gemini key check. Run: uv run check_gemini.py"""
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
key = os.environ.get("GEMINI_API_KEY")
print("Key loaded:", bool(key), f"(...{key[-4:]})" if key else "")

client = genai.Client(api_key=key)

print("\nModels your key can call:")
for m in client.models.list():
    if "generateContent" in (m.supported_actions or []):
        print(" -", m.name)

print("\nTrying a 1-token request on gemini-2.5-flash ...")
resp = client.models.generate_content(model="gemini-2.5-flash", contents="say hi")
print("OK:", resp.text)
