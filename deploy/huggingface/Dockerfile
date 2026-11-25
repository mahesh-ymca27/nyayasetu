# NyayaSetu on Hugging Face Spaces (Docker SDK).
# The code, data and trained model are downloaded from the GitHub repository's main branch, so the Space
# only needs this Dockerfile and README.md. Set GROQ_API_KEY under Settings -> Variables and secrets.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Spaces run the container as user 1000.
RUN useradd -m -u 1000 user
WORKDIR /app

# Docker re-downloads this archive whenever main changes, so a "Factory rebuild" always gets the latest code.
ADD https://github.com/mahesh-ymca27/nyayasetu/archive/refs/heads/main.tar.gz /tmp/source.tar.gz
RUN tar -xzf /tmp/source.tar.gz --strip-components=1 -C /app \
    && rm /tmp/source.tar.gz \
    && pip install -r requirements.txt

# Listen on all interfaces on the Spaces port; keep the database in a writable folder.
# (Free Spaces have no persistent disk: registered users and uploads reset when the Space restarts.
#  The demo account demo@nyayasetu.in / demo1234 is recreated on every start.)
ENV HOST=0.0.0.0 \
    PORT=7860 \
    NYAYASETU_STORAGE=/tmp/nyayasetu

USER user
EXPOSE 7860
CMD ["python", "run.py"]
