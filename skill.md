ZynthClaw — Public Goods Evaluation Agent

> A conversational agent that helps evaluate public goods projects by combining community sentiment, direct human impact, and developer activity signals.

**Roadmap (beta):** the maintainer plans to plug this collected data into a **large LLM** for stronger evaluation, mechanism design, and analysis. Today’s outputs use structured heuristics; LLM-backed synthesis is not live yet.

## What I do

I guide a user (typically via Telegram) through a **staged evaluation** of a project:

- Start from a project’s **X handle** (e.g. `@project`) to anchor the evaluation.
- Fetch and show the project **bio** and a **preview** of recent posts + replies (3 posts max) in Telegram.
- Ask the user for detailed, qualitative feedback about **how the project impacted them**.
- Optionally ingest a **GitHub repository** to read developer activity signals.
- Optionally collect **additional info** (links to articles/docs/notes) to include in the raw export.
- Combine these signals into an **Impact Evaluation Report** and a **mechanism design recommendation** for public-goods funding.

Internally, I:

- Use the official **X API v2** to collect:
  - the account bio/description,
  - up to 10 original posts,
  - replies grouped under each post using `conversation_id:<post_id>` search.
- Use `GitHubService` to collect stars, forks, open issues, contributors, and recent commit activity.
- Classify overall impact as **High**, **Moderate**, or **Emerging** based on user feedback and GitHub signals.
- Produce a mechanism-design narrative suggesting how funding or incentives might be structured.

**Future (beta):** the same collected signals are intended to be passed to a **large LLM** for deeper evaluation and mechanism design—see the Telegram `/start` message for the current disclaimer.

## How to use me

Assume the agent is running at:

`BASE_URL=http://127.0.0.1:8000`

There are two ways to interact with ZynthClaw:

1. **Conversational evaluation via Telegram (recommended for humans).**
2. **Read the skill via HTTP (for automated agents).**

---

## 1. Conversational Public-Goods Evaluation (Telegram)

The Telegram bot exposes a stateful evaluation flow:

1. **X handle** – user sends a handle (e.g. `@project`).
   - Bot shows “checking X…”, confirms the project is found, and displays the X bio.
   - Bot shows a preview of **3 posts max**, with replies visually nested under each post.
2. **User impact** – user answers “How has this project impacted your workflow, business, or people around you?”  
   - Short answers (`< 20` words) or replies like `skip`, `no`, `next`, or “i don't have anything to say” are rejected with:  
     **“I need to understand how this project has impacted you to be able to proceed.”**
3. **Optional GitHub repo** – user may send a repo URL or skip.
4. **Optional additional info** – agent asks if the user wants to add extra context (articles/docs links).
5. **Governance** – after optional info, status lines (“Analysing social activity”, “Analysing developer activity”), then two questions: how governance works (decisions, participation, voting, frequency), and links/artifacts (Snapshot, forum, proposals).
6. **Impact Evaluation Report** – after “Analysing social / developer / governance activity”, the agent responds with:
  - community sentiment summary (X),
  - user feedback (Telegram),
  - developer activity summary (GitHub, if provided),
  - governance (user-provided),
  - overall impact classification (`High`, `Moderate`, `Emerging`),
  - mechanism design recommendation.
7. **Raw data export** – about a minute later, the agent reminds the user they can export a **PDF** of the raw collated data. Use **`/export`** in Telegram to receive the PDF file in chat.

The PDF includes up to **10 original posts** and their replies (grouped by conversation id), plus your feedback, optional extra info, governance answers, and GitHub summary (if any).

This flow is implemented in `tg_bot/bot.py`. Core logic:

- `build_public_goods_evaluation(x_handle, user_feedback, repo_url?, optional_user_info?, governance_description?, governance_artifacts?) -> EvaluationDict`

Other Python agents in the same process can call that function, then either:

- **`POST /export`** with the evaluation JSON to receive `application/pdf`, or
- mirror the Telegram **`/export`** behavior by calling `generate_raw_evaluation_pdf(evaluation)`.

---

## For other AI agents: fetch this skill first

If you are an AI agent integrating with ZynthClaw, your first step should be to fetch this file:

```bash
curl -s "$BASE_URL/skill.md"
```

Then:

- Instruct the human user to open Telegram and run **`/evaluate_project`**.
- After the report, remind them they can run **`/export`** to download the raw-data PDF in Telegram.

### Programmatic PDF export (HTTP)

- **`GET /export`** – returns JSON describing how to download the PDF.
- **`POST /export`** – send the **evaluation object** (same shape as `build_public_goods_evaluation` output) as JSON; response is **`application/pdf`**.

Example:

```bash
curl -sS -X POST "$BASE_URL/export" \
  -H "Content-Type: application/json" \
  -d @evaluation.json \
  -o zynthclaw_raw.pdf
```

Email is **not** used; raw data is delivered as PDF via Telegram or `POST /export`.
