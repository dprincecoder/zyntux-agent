ZynthClaw — Public Goods Evaluation Agent

> A conversational agent that helps evaluate public goods projects by combining community sentiment, direct human impact, and developer activity signals.

## What I do

I guide a user (typically via Telegram) through a **staged evaluation** of a project:

- Start from a project’s **X handle** (e.g. `@project`) to anchor the evaluation.
- Ask the user for detailed, qualitative feedback about **how the project impacted them**.
- Optionally ingest a **GitHub repository** to read developer activity signals.
- Combine these signals into an **Impact Evaluation Report** and a **mechanism design recommendation** for public-goods funding.

Internally, I:

- Keep the X analysis modular (placeholder until a live X API is wired).
- Use `GitHubService` to collect stars, forks, open issues, contributors, and recent commit activity.
- Classify overall impact as **High**, **Moderate**, or **Emerging** based on user feedback and GitHub signals.
- Produce a mechanism-design narrative suggesting how funding or incentives might be structured.

## How to use me

Assume the agent is running at:

`BASE_URL=http://127.0.0.1:8000`

There are two ways to interact with ZynthClaw:

1. **Conversational evaluation via Telegram (recommended for humans).**
2. **HTTP API for infrastructure-risk scoring (legacy, for automated agents).**

---

## 1. Conversational Public-Goods Evaluation (Telegram)

The Telegram bot exposes a stateful evaluation flow:

1. **X handle** – user sends a handle (e.g. `@project`).
2. **User impact** – user answers “How has this project impacted your workflow, business, or people around you?”  
   - Short answers (`< 20` words) or replies like `skip`, `no`, `next`, or “i don't have anything to say” are rejected with:  
     **“I need to understand how this project has impacted you to be able to proceed.”**
3. **Optional GitHub repo** – user may send a repo URL or skip.
4. **Impact Evaluation Report** – agent responds with:
   - community sentiment summary (X, placeholder),
   - user impact summary,
   - developer activity summary (GitHub, if provided),
   - overall impact classification (`High`, `Moderate`, `Emerging`),
   - mechanism design recommendation.
5. **Raw data export** – about a minute later, the agent asks if the user wants a **PDF** of the raw collated data (sentiment summary, user feedback, GitHub summary, classification, mechanism design) emailed to them.

This flow is fully implemented inside the Telegram bot (`tg_bot/bot.py`) and is not directly exposed as an HTTP endpoint, but you can treat the core logic as:

- `build_public_goods_evaluation(x_handle, user_feedback, repo_url?) -> EvaluationDict`

You can call this function from other Python agents that run inside the same process.

---

## 2. HTTP API – Infrastructure-Risk Scoring (Legacy Mode)

The HTTP API remains focused on *infrastructure risk* and **funding candidates**:

### Evaluate by topics

Discover infrastructure projects for one or more GitHub topics.

**Endpoint**

`POST /evaluate/topics`

**Request**

```bash
curl -X POST "$BASE_URL/evaluate/topics" \
  -H "Content-Type: application/json" \
  -d '{
    "topics": ["ethereum", "wallet"],
    "min_stars": 500
  }'
```

- **`topics`**: array of GitHub topics to crawl.
- **`min_stars`** (optional, default `0`): minimum stars per repo when searching.

**Response (funding-focused)**

```json
{
  "count": 3,
  "funding_candidates": [
    {
      "full_name": "ethers-io/ethers.js",
      "html_url": "https://github.com/ethers-io/ethers.js",
      "description": "Complete Ethereum wallet implementation and utilities in JavaScript.",
      "total_contributors": 42,
      "open_issues": 128,
      "impact_score": 92.5,
      "dependents_count": 680489,
      "active_contributors_90d": 1,
      "risk_flag": "HIGH",
      "analysis": "This repository is a critical backbone of the ecosystem (680,489 dependents) but has very few active maintainers (1). High risk of failure if maintainers stop contributing."
    }
  ]
}
```

Use this when you want **a ranked list of funding targets** for a topic.

### Evaluate a single repository

Check whether one specific repo is a funding candidate.

**Endpoint**

`POST /evaluate/repo`

**Request**

```bash
curl -X POST "$BASE_URL/evaluate/repo" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/ethers-io/ethers.js"
  }'
```

**Response (funding-focused)**

```json
{
  "count": 1,
  "funding_candidates": [
    {
      "full_name": "ethers-io/ethers.js",
      "html_url": "https://github.com/ethers-io/ethers.js",
      "description": "...",
      "total_contributors": 42,
      "open_issues": 128,
      "impact_score": 92.5,
      "dependents_count": 680489,
      "active_contributors_90d": 1,
      "risk_flag": "HIGH",
      "analysis": "..."
    }
  ]
}
```

If the repo does **not** meet funding criteria, you’ll get:

```json
{ "count": 0, "funding_candidates": [] }
```

### Fetch full evaluation context (manual review)

Get **both** the last funding candidates **and** all evaluated projects from the latest request.

**Endpoint**

`GET /evaluations`

**Request**

```bash
curl "$BASE_URL/evaluations"
```

**Response**

```json
{
  "count": 3,
  "funding_candidates": [ /* ... */ ],
  "evaluations_count": 20,
  "evaluations": [ /* ... */ ]
}
```

### Response format (funding candidates)

```json
{
  "count": 3,
  "funding_candidates": [
    {
      "full_name": "owner/repo",
      "html_url": "https://github.com/owner/repo",
      "description": "...",
      "total_contributors": 10,
      "open_issues": 25,
      "impact_score": 78.5,
      "dependents_count": 1200,
      "active_contributors_90d": 3,
      "risk_flag": "HIGH | MEDIUM | LOW",
      "analysis": "Human-readable explanation of risk and funding need."
    }
  ]
}
```

## Rules (HTTP infrastructure-risk API)

- GitHub REST API + HTML scraping only.
- Only public GitHub repositories.
- Filters out likely non-infrastructure repos (names/descriptions containing: `course`, `tutorial`, `roadmap`, `awesome`, `book`, `learning`, `bootcamp`).
- Topic evaluations:
  - Deduplicate repos by `full_name`.
  - Evaluate in parallel for speed.
  - Sort funding candidates by:
    - `dependents_count` descending
    - `active_contributors_90d` ascending
  - Limit to **top 20** funding candidates.

## Endpoints

| Method | Path              | Description                                                       |
|--------|-------------------|-------------------------------------------------------------------|
| POST   | /evaluate/topics  | Crawl topics, evaluate, and return funding candidates             |
| POST   | /evaluate/repo    | Evaluate a single repo as a potential funding candidate           |
| GET    | /evaluations      | Last funding candidates **and** full list of evaluated projects   |

## Goal

ZynthClaw exists to help funders and ecosystem stewards:

- Run **rich, human-in-the-loop evaluations** of public goods projects via Telegram, and  
- Quickly identify **open source public goods** that power many other projects but have too few active maintainers, via the HTTP infrastructure-risk API.

