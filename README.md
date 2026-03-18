# ZynthClaw – Public Goods Evaluation Agent

ZynthClaw is an AI agent that helps you evaluate **public goods projects** in a structured, conversational way. It combines:

- community sentiment (via X handle, using the official X API v2),
- **your** direct human-impact story (Telegram),
- optional **GitHub developer activity**,
- optional **extra context** (articles/docs links you provide),

to generate an **Impact Evaluation Report** and a **mechanism design insight** for funding decisions.

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
  - Impact Evaluation Report + mechanism design recommendation.
- **Raw data export** – email a **pretty PDF** containing:
  - up to **10 original X posts** (skipping reposts/retweets),
  - replies under each post (grouped by `conversation_id`, link-only replies filtered out),
  - your Telegram feedback + optional extra info,
  - optional GitHub summary,
  - classification + mechanism design recommendation.
- **Homepage** – black-themed landing page with what the agent does, why it exists, and how to talk to it (Telegram).
- **Agent skill file** – `GET /skill.md` describes the public-goods evaluation flow so other agents can understand how to interact with it.

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
    config.py          # Settings (GitHub, SMTP, Telegram)
    main.py            # FastAPI app: homepage + skill.md
    github_service.py  # GitHub API client
    email_service.py   # Email delivery (raw evaluation PDF)
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
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` | Email delivery for raw-data PDF export |
| `SMTP_USE_TLS`, `SMTP_USE_SSL` | Transport settings (TLS vs SSL) |

Example `.env`:

```env
GITHUB_TOKEN=ghp_your_token_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_BOT_USERNAME=YourBotUsername
X_BEARER_TOKEN=your_x_bearer_token
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_username
SMTP_PASSWORD=your_password
SMTP_FROM_EMAIL=bot@example.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false
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
| `/request_raw_data` | Email the raw collated data (PDF) from your last completed flow |

**Evaluation stages:**

1. **X handle** – you send an X handle (e.g. `@project`).
   - Bot confirms it’s checking X, then returns “project found” and shows the project bio.
   - Bot shows a **preview**: 3 posts (max) with replies visually nested under each post.
   - Bot reminds you to request full raw data via email for manual review.
2. **User impact** – you answer:
   “How has this project impacted your workflow, business, or people around you?”  
   - If you try to skip (short reply, “skip”, “no”, “next”, “i don’t have anything to say”), the agent replies:  
     “I need to understand how this project has impacted you to be able to proceed.” and waits for a better answer.  
3. **Optional GitHub repo** – you may send a repo URL or “skip”.
4. **Optional additional info** – bot asks if you want to add extra context (articles/docs links).  
5. **Impact Evaluation Report** – bot responds with:
   - community sentiment summary (from X),
   - your real user impact feedback,
   - developer activity summary (if GitHub provided),
   - overall impact classification (`High`, `Moderate`, `Emerging`),
   - mechanism design recommendation for public-goods funding.
6. **Raw data offer** – ~1 minute later, the bot asks:
   “If you want, I can email you the raw collated data for manual review, Yes?”  
   - If you say **Yes**, it asks for your email and sends the raw data as a PDF.  
   - If you say **No**, it ends the flow.

---

## Email report (PDF)

- **Raw public-goods evaluation data (Telegram)** – after `/evaluate_project`, the agent can email you a PDF containing:
  - up to **10 original X posts** for the handle,
  - replies grouped under each post by conversation (link-only replies filtered out),
  - your Telegram feedback + optional additional info,
  - optional GitHub developer-activity summary,
  - classification + mechanism design,
  for manual review. This uses `send_raw_evaluation_email` under the hood.

This flow requires SMTP env vars; see [Configuration](#configuration).

---

## License and credits

See the **footer on the homepage** for credits. ZynthClaw was made for the **Octant hackathon** in partnership with **Synthesis**.
