# ZynthClaw – Public Goods Evaluation Agent

ZynthClaw is an AI agent that helps you evaluate **public goods projects** in a structured, conversational way. It combines:

- community sentiment (via X handle, placeholder-ready for live X integration),
- **your** direct human-impact story (Telegram),
- optional **GitHub developer activity**,

to generate an **Impact Evaluation Report** and a **mechanism design insight** for funding decisions.

## Why it exists

Many essential libraries and tools power huge ecosystems but are maintained by very few people. When those maintainers burn out or move on, **whole dependency trees are at risk**. ZynthClaw helps find and prioritize these projects so funders and communities can support them before it’s too late.

---

## Features

- **Conversational public-goods evaluation (Telegram)** – multi-stage flow:
  - X handle → initial community sentiment (placeholder, ready for live X integration),
  - long-form user impact feedback (your story),
  - optional GitHub repo → developer activity signals,
  - Impact Evaluation Report + mechanism design recommendation.
- **Raw data export** – email the raw collated evaluation (sentiment summary, your feedback, GitHub summary, classification, mechanism design) as a **PDF**.
- **REST API (infrastructure risk, legacy)** – `POST /evaluate/topics`, `POST /evaluate/repo`, `GET /evaluations`, `GET /skill.md` for classic “high dependents, low maintainers” infrastructure risk analysis.
- **Homepage** – black-themed landing page with what the agent does, why it exists, and how to talk to it (API + Telegram).
- **Agent skill file** – `GET /skill.md` describes both the public-goods evaluation flow and the HTTP infrastructure-risk API.

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
  1. **AI agents** – Copy the `curl` command to fetch `skill.md`; your agent will know what to do from there.
  2. **Telegram** – Link to start a chat with the ZynthClaw bot (if `TELEGRAM_BOT_USERNAME` is set).

### 2. Run the app

See [Installation](#installation) and [Running](#running) below. Use `run_agent.py` to start both the **API** and the **Telegram bot** together.

---

## Project structure

```text
Zynthclaw/
  app/
    config.py          # Settings (GitHub, SMTP, Telegram)
    main.py            # FastAPI app: homepage, API routes, skill.md
    crawler.py         # GitHub topic crawling (legacy infra-risk API)
    evaluator.py       # Repo metrics and scoring (legacy infra-risk API)
    github_service.py  # GitHub API client
    email_service.py   # Email delivery (funding candidates + raw evaluation PDF)
    public_evaluator.py # Public-goods evaluation and mechanism design engine
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
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` | Email delivery for `/email_targets` |

Example `.env`:

```env
GITHUB_TOKEN=ghp_your_token_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_BOT_USERNAME=YourBotUsername
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_username
SMTP_PASSWORD=your_password
SMTP_FROM_EMAIL=bot@example.com
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
  - **curl to skill file** – e.g. `curl -s "https://your-host/skill.md"` so another AI agent can read the skill and call the API.
  - **Telegram** – link to open a chat with the bot (if `TELEGRAM_BOT_USERNAME` is set).

### 2. Telegram integration (Public Goods Evaluation Agent)

In Telegram, send:

| Command | Description |
|--------|-------------|
| `/start` | Intro and description of the public-goods evaluation flow |
| `/evaluate_project` | Start a new evaluation: X handle → user impact → optional GitHub → report |
| `/request_raw_data` | Email the raw collated data (PDF) from your last evaluation |

**Evaluation stages:**

1. **X handle** – you send an X (Twitter) handle (e.g. `@project`).  
2. **User impact** – you answer:  
   “How has this project impacted your workflow, business, or people around you?”  
   - If you try to skip (short reply, “skip”, “no”, “next”, “i don’t have anything to say”), the agent replies:  
     “I need to understand how this project has impacted you to be able to proceed.” and waits for a better answer.  
3. **Optional GitHub repo** – you may send a repo URL or “skip”.  
4. **Impact Evaluation Report** – bot responds with:
   - community sentiment summary (from X, placeholder until live X integration),
   - your real user impact summary,
   - developer activity summary (if GitHub provided),
   - overall impact classification (`High`, `Moderate`, `Emerging`),
   - mechanism design recommendation for public-goods funding.  
5. **Raw data offer** – ~1 minute later, the bot asks:  
   “If you want, I can email you the raw collated data for manual review, Yes?”  
   - If you say **Yes**, it asks for your email and sends the raw data as a PDF.  
   - If you say **No**, it ends the flow.

### 3. REST API (legacy infrastructure-risk scoring)

- **Evaluate by topics:** `POST /evaluate/topics` with `{"topics": ["topic1", "topic2"], "min_stars": 100}`  
- **Evaluate one repo:** `POST /evaluate/repo` with `{"repo_url": "https://github.com/owner/repo"}`  
- **Last evaluation results:** `GET /evaluations`  
- **Agent skill (for other AI agents):** `GET /skill.md`

---

## REST API quick reference

### Evaluate by topics

`POST /evaluate/topics` – discover infrastructure-ish repos for given topics and return funding candidates.

### Evaluate a single repository

`POST /evaluate/repo` – evaluate one repo as a potential funding candidate.

### Get last evaluation results

`GET /evaluations` – returns the most recent funding candidates and full evaluations from the last topic or repo run.

### Get agent skill (for AI agents)

`GET /skill.md` – Markdown description of what ZynthClaw does and how to call it (endpoints, request/response shapes). Use this so other agents can integrate via the API.

---

## Email report (PDF)

There are two email flows:

- **Raw public-goods evaluation data (Telegram)** – after `/evaluate_project`, the bot can email you:
  - community sentiment summary,
  - your impact feedback,
  - optional GitHub summary,
  - classification + mechanism design,
  as a **PDF** for manual review. This uses `send_raw_evaluation_email` under the hood.

- **Legacy funding-candidates report** – the HTTP-facing logic (`send_funding_targets_email`) can still be used to send funding-candidate lists as a PDF, if you call it from other tooling.

Both flows require SMTP env vars; see [Configuration](#configuration).

---

## License and credits

See the **footer on the homepage** for credits. ZynthClaw was made for the **Octant hackathon** in partnership with **Synthesis**.
