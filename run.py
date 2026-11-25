"""Start NyayaSetu:  python run.py   then open http://localhost:8000"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"\n  NyayaSetu is running at  http://localhost:{port}\n  API docs:               http://localhost:{port}/docs\n")
    uvicorn.run("backend.main:app", host=os.environ.get("HOST", "127.0.0.1"), port=port,
                reload=os.environ.get("RELOAD") == "1")
