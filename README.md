# ZynthClaw – Public Goods Evaluation Agent

ZynthClaw is an AI agent that helps you evaluate **public goods projects** in a structured, conversational way. It combines:

- community sentiment (via X handle, using the official X API v2),
- **your** direct human-impact story (Telegram),
- optional **GitHub developer activity**,
- optional **extra context** (articles/docs links you provide),

to generate an **Impact Evaluation Report** and a **mechanism design insight** for funding decisions.

> **Roadmap (beta):** we plan to pipe this collected data into a **large LLM** for richer evaluation, mechanism design, and analysis. Current behavior is heuristic/rule-based; LLM-assisted depth is coming.

## Why I exist

Digital Public Infrastructure (DPI) is only as strong as the public goods behind it — tools, protocols, libraries, and services that people depend on every day.

ZynthClaw exists with a clear objective: **collect signals**, **evaluate impact**, and **design a mechanism** that helps decision-makers determine:
- **what should be funded**
- **why it should be funded**
- **what impact it is making** in DPI

---

## Features

- **Conversational public-goods evaluation (Telegram)** – multi-stage flow:
  - X handle → fetch project bio + recent posts,
  - show an in-chat **preview** (3 posts + replies),
  - long-form user impact feedback (your story),
  - optional GitHub repo → developer activity signals,
  - optional additional info (article/docs links),
  - governance Q&A (how decisions work + links/artifacts),
  - Impact Evaluation Report + mechanism design recommendation.
  - *Planned:* feed collected signals into a **large LLM** for deeper evaluation & mechanism design (**still in beta**).
- **Raw data export (PDF)** – no email; download a **pretty PDF** via:
  - Telegram **`/export`** after a completed evaluation, or
  - **`POST /export`** (JSON body = evaluation dict) for other AI agents / automation.
  The PDF includes up to **10 original X posts**, replies under each post, Telegram feedback, optional extra info, optional GitHub summary, and classification + mechanism design.
- **Homepage** – black-themed landing page with what the agent does, why it exists, and how to talk to it (Telegram).
- **Agent skill file** – `GET /skill.md` describes the flow; **`GET /export`** describes the PDF API; **`POST /export`** returns the PDF.

---

## Getting started

### 1. Homepage (once the app is running)

When the API is running, open the **homepage** in your browser:

- **Local:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Deployed:** `https://your-deployed-host/`

There you’ll see:

- What ZynthClaw does
- Why it exists and the problem it solves
- **How to talk to ZynthClaw:**
  1. **AI agents** – Copy the `curl` command to fetch `skill.md`; your agent can read it and guide a human through Telegram.
  2. **Telegram** – Link to start a chat with the ZynthClaw bot (if `TELEGRAM_BOT_USERNAME` is set).

### 2. Run the app

See [Installation](#installation) and [Running](#running) below. Use `run_agent.py` to start both the **API** and the **Telegram bot** together.

---

## Project structure

```text
Zynthclaw/
  app/
    config.py          # Settings (GitHub, Telegram)
    main.py            # FastAPI app: homepage, skill.md, POST /export (PDF)
    github_service.py  # GitHub API client
    email_service.py   # Raw evaluation PDF generation (Telegram /export + POST /export)
    public_evaluator.py # Public-goods evaluation and mechanism design engine
    twitter_scraper.py # Official X API v2 collector (posts, replies, bio)
  tg_bot/
    bot.py            # Telegram handlers and commands (public goods evaluation flow)
  run_agent.py        # Entrypoint: starts API + Telegram bot
  skill.md            # Agent skill description (also served at GET /skill.md)
  requirements.txt
  .env                # Secrets (not committed; see .gitignore)
```

---

## Configuration

Create a `.env` file in the project root (see `.env.example` or below). Required for full functionality:

| Variable | Purpose |
|----------|---------|
| `GITHUB_TOKEN` | GitHub API (higher rate limits; recommended) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token (required if you run the bot) |
| `TELEGRAM_BOT_USERNAME` | Bot username for homepage link (e.g. `MyBot` → t.me/MyBot) |
| `X_BEARER_TOKEN` | X API v2 bearer token (required for X bio/posts/replies collection) |

Email delivery is **disabled**; raw data is exported as PDF via Telegram **`/export`** or **`POST /export`**. (Optional SendGrid/SMTP settings in `app/config.py` are commented out.)

Example `.env`:

```env
GITHUB_TOKEN=ghp_your_token_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_BOT_USERNAME=YourBotUsername
X_BEARER_TOKEN=your_x_bearer_token
```

---

## Installation

```bash
cd /path/to/Zynthclaw
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

---

## Running

**API + Telegram bot together (recommended):**

```bash
python run_agent.py
```

- API: [http://127.0.0.1:8000/](http://127.0.0.1:8000/) (homepage, docs, and routes).
- Telegram bot starts polling; use your bot in Telegram as configured.

**API only (e.g. for development):**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open [http://127.0.0.1:8000/](http://127.0.0.1:8000/) for the homepage and [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for Swagger.

---

## How to talk to ZynthClaw

### 1. Homepage and AI agents

- Open the **homepage** (`/`) for a short description and two options:
  - **curl to skill file** – e.g. `curl -s "https://your-host/skill.md"` so another AI agent can read the skill and guide the Telegram flow.
  - **Telegram** – link to open a chat with the bot (if `TELEGRAM_BOT_USERNAME` is set).

### 2. Telegram integration (Public Goods Evaluation Agent)

In Telegram, send:

| Command | Description |
|--------|-------------|
| `/start` | Intro and description of the public-goods evaluation flow |
| `/evaluate_project` | Start a new collection & evaluation flow |
| `/export` | Send the raw collated data as a **PDF file** in Telegram (after a completed evaluation) |

**Evaluation stages:**

1. **X handle** – you send an X handle (e.g. `@project`).
   - Bot confirms it’s checking X, then returns “project found” and shows the project bio.
   - Bot shows a **preview**: 3 posts (max) with replies visually nested under each post.
   - Bot reminds you that you can get the full raw data as a PDF with **`/export`** after the evaluation.
2. **User impact** – you answer:
   “How has this project impacted your workflow, business, or people around you?”  
   - If you try to skip (short reply, “skip”, “no”, “next”, “i don’t have anything to say”), the agent replies:  
     “I need to understand how this project has impacted you to be able to proceed.” and waits for a better answer.  
3. **Optional GitHub repo** – you may send a repo URL or “skip”.
4. **Optional additional info** – bot asks if you want to add extra context (articles/docs links).  
5. **Governance** – bot sends “Analysing social activity” and “Analysing developer activity”, then asks how governance works (decisions, participation, voting, cadence) and for links/artifacts (Snapshot, forum, proposals, etc.).
6. **Impact Evaluation Report** – bot sends “Analysing social activity”, “Analysing developer activity”, and “Analysing governance activity”, then responds with:
   - community sentiment summary (from X),
   - your real user impact feedback,
   - developer activity summary (if GitHub provided),
   - governance (your answers),
   - overall impact classification (`High`, `Moderate`, `Emerging`),
   - mechanism design recommendation for public-goods funding.
7. **Raw data reminder** – ~1 minute later, the bot reminds you that you can **`/export`** the raw collated data (including governance) as a PDF in Telegram when you want it.

---

## Raw data PDF export

- **Telegram** – after a completed `/evaluate_project` flow, send **`/export`**. The bot uploads `zynthclaw_public_goods_raw_evaluation.pdf` with the full threaded X data (up to 10 posts), feedback, optional info, governance text, GitHub summary (if any), and mechanism design text.
- **HTTP (other AI agents)** – `GET /export` returns JSON API help. **`POST /export`** with a JSON body equal to the evaluation dict (same shape as `build_public_goods_evaluation()` output) returns `application/pdf`.

```bash
curl -sS -X POST "https://your-host/export" \
  -H "Content-Type: application/json" \
  -d @evaluation.json \
  -o raw.pdf
```

Implementation: `generate_raw_evaluation_pdf()` in `app/email_service.py`.

---

## License and credits

See the **footer on the homepage** for credits. ZynthClaw was made for the **Octant hackathon** in partnership with **Synthesis**.
