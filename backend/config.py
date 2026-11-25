"""Application settings, read from environment variables or a local .env file."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STORAGE_DIR = ROOT / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
FRONTEND_DIR = ROOT / "frontend"


def _read_text(path: Path) -> str:
    """Reads a text file saved by any Windows editor (UTF-8, UTF-8 with BOM, or UTF-16)."""
    data = path.read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    return data.decode("utf-8-sig", errors="ignore")


def _find_env_file() -> Path | None:
    # Windows hides extensions, so ".env" created in Notepad is often really ".env.txt".
    for name in (".env", ".env.txt", "env", "env.txt"):
        p = ROOT / name
        if p.is_file():
            return p
    return None


def _load_dotenv(path: Path | None) -> None:
    if not path:
        return
    for raw in _read_text(path).splitlines():
        line = raw.strip().lstrip("\ufeff")
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.split(" #", 1)[0].strip().strip('"').strip("'").strip()
        # An empty variable already set in Windows must not block the value from .env.
        if value and not os.environ.get(key, "").strip():
            os.environ[key] = value


ENV_FILE = _find_env_file()
_load_dotenv(ENV_FILE)

# NYAYASETU_STORAGE moves the database and uploads elsewhere (the test suite uses a temp folder).
if os.environ.get("NYAYASETU_STORAGE"):
    STORAGE_DIR = Path(os.environ["NYAYASETU_STORAGE"])
    UPLOAD_DIR = STORAGE_DIR / "uploads"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

# NYAYASETU_OFFLINE=1 ignores any Groq key, so tests never call the real API.
OFFLINE = os.environ.get("NYAYASETU_OFFLINE") == "1"


def _secret_key() -> str:
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    key_file = STORAGE_DIR / "secret.key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
    return key_file.read_text().strip()


class Settings:
    groq_api_key: str = "" if OFFLINE else os.environ.get("GROQ_API_KEY", "").strip().strip('"').strip("'")
    groq_model: str = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
    groq_base_url: str = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    secret_key: str = _secret_key()
    token_ttl_hours: int = int(os.environ.get("TOKEN_TTL_HOURS", "24"))
    max_upload_mb: int = int(os.environ.get("MAX_UPLOAD_MB", "20"))
    db_path: Path = STORAGE_DIR / "nyayasetu.db"


settings = Settings()
