# Deploying NyayaSetu (free, on Render)

Render's free web service (512 MB RAM, no credit card) runs the whole app, including the trained model, straight
from this GitHub repository. The settings are in [`render.yaml`](render.yaml).

The live deployment is at **https://nyayasetu-doeu.onrender.com**.

## One-time setup (in the browser)
1. Open https://render.com and choose **Get Started** → **GitHub**. Sign in with the GitHub account that owns
   this repository and allow Render to access it.
2. In the Render dashboard: **New** → **Blueprint**.
3. Choose the repository **nyayasetu** and click **Connect**. Render reads `render.yaml` and shows one free web
   service called `nyayasetu`.
4. It asks for **GROQ_API_KEY**: paste your Groq key (it is stored as a secret on Render, not in the repository).
   Click **Apply** / **Deploy Blueprint**.
5. The first build takes about 5–10 minutes (watch **Logs**). When the service shows **Live**, open the URL at
   the top of its page (for example `https://nyayasetu.onrender.com`; Render adds letters if the name is taken)
   and sign in with **demo@nyayasetu.in / demo1234**.

## Updating
`autoDeploy` is on: every change merged into `main` on GitHub is deployed automatically. To redeploy by hand:
service page → **Manual Deploy** → **Deploy latest commit**.

## Good to know about the free plan
- **It sleeps.** After 15 minutes without visitors the service stops; the next visit wakes it in about a minute.
  Open the site a few minutes before a demo.
- **It is slow to start and to think.** The free plan has a small share of a CPU, so the first page and the
  first search after waking take longer. Groq answers are not affected (they run on Groq's servers).
- **Data resets.** There is no permanent disk, so registered users, questions and uploaded documents are cleared
  whenever the service restarts or redeploys. The demo account is recreated every time.
- **Groq usage.** The site is public and uses your Groq key; anyone using it uses your free-tier quota.

## Other hosts
`deploy/huggingface/` contains a Docker setup for Hugging Face Spaces. Hugging Face now requires a paid plan
(PRO) for Docker Spaces, so it is kept for that case only. The same image is built and tested in GitHub Actions
(the `docker` job), which also reports how much memory the running app uses.
