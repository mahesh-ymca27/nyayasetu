# Deploying NyayaSetu to Hugging Face Spaces (free)

The free CPU Space (2 vCPU, 16 GB RAM) runs the whole app, including the trained model. The Space contains only
two small files; its Dockerfile downloads the code, data and model from this GitHub repository's `main` branch.

## One-time setup (in the browser, no git needed)
1. Sign in at https://huggingface.co and open https://huggingface.co/new-space
2. **Space name:** `nyayasetu` · **SDK:** Docker · **Template:** Blank · **Hardware:** CPU basic (free) ·
   **Visibility:** Public. Click **Create Space**.
3. Open the Space's **Files** tab → **Add file** → **Upload files**, and upload these two files from this
   repository's `deploy/huggingface/` folder: `Dockerfile` and `README.md` (replace the README the Space created).
   Click **Commit changes to main**.
4. Open **Settings** → **Variables and secrets** → **New secret**. Name: `GROQ_API_KEY`, value: your Groq key.
   Save. (A *secret*, not a variable, so the key is never shown publicly.)
5. The Space builds automatically (about 3–6 minutes; watch the **Logs** tab). When it says **Running**, open
   `https://<your-username>-nyayasetu.hf.space` and sign in with **demo@nyayasetu.in / demo1234**.

## Updating after a new change is merged on GitHub
Space **Settings** → **Factory rebuild**. The Dockerfile downloads the latest `main` again.

## Good to know
- **Data resets on restart.** Free Spaces have no permanent disk, so registered users, questions and uploaded
  documents are cleared when the Space restarts. The demo account is recreated every time.
- **Sleep.** A free Space sleeps after a period without visitors and wakes on the next visit (about a minute).
  Open it a few minutes before a demo.
- **Groq usage.** The Space is public and uses your Groq key; anyone using it uses your free-tier quota.
- The `docker` job in GitHub Actions builds the same image for every pull request and checks that it starts,
  the demo login works and the trained model loads.
