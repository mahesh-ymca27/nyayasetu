"""Start NyayaSetu:  python run.py   then open http://localhost:8000"""
import os

import uvicorn

from backend.config import ENV_FILE, ROOT, settings


def describe_key() -> None:
    key = settings.groq_api_key
    if key:
        print(f"  Groq API key loaded from {ENV_FILE.name}: {key[:4]}...{key[-4:]}  (model: {settings.groq_model})")
        if not key.startswith("gsk_"):
            print("  WARNING: Groq keys normally start with 'gsk_'. Check that you pasted the whole key.")
        return
    print("  Groq API key NOT found, so the app runs in offline mode.")
    if ENV_FILE is None:
        print(f"  No .env file was found in {ROOT}")
        print("  Create a file named .env in that folder (next to run.py) containing:")
    else:
        print(f"  {ENV_FILE} was found, but it has no GROQ_API_KEY value. It should contain:")
    print("      GROQ_API_KEY=gsk_your_key_here")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(line_buffering=True)
    port = int(os.environ.get("PORT", "8000"))
    print()
    describe_key()
    print(f"\n  NyayaSetu is running at  http://localhost:{port}\n  API docs:               http://localhost:{port}/docs\n")
    uvicorn.run("backend.main:app", host=os.environ.get("HOST", "127.0.0.1"), port=port,
                reload=os.environ.get("RELOAD") == "1")
