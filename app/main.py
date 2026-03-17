from __future__ import annotations

from typing import List, Optional
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, HttpUrl, field_validator

from .config import get_settings
from .crawler import TopicCrawler
from .evaluator import Evaluator, RepositoryEvaluation
from .github_service import GitHubService


settings = get_settings()
app = FastAPI(title=settings.app_name)


class TopicsEvaluateRequest(BaseModel):
    topics: List[str]
    min_stars: int = 0

    @field_validator("topics", mode="after")
    @classmethod
    def _normalize_topics(cls, value: List[str]) -> List[str]:
        normalized = [t.strip() for t in value if t and t.strip()]
        if not normalized:
            raise ValueError("At least one non-empty topic is required.")
        return normalized

    @field_validator("min_stars", mode="after")
    @classmethod
    def _validate_min_stars(cls, value: int) -> int:
        if value < 0:
            raise ValueError("min_stars must be >= 0.")
        return value


class RepoEvaluateRequest(BaseModel):
    repo_url: HttpUrl


class RepositoryMetricsResponse(BaseModel):
    full_name: str
    html_url: str
    description: Optional[str]
    stars: int
    forks: int
    open_issues: int
    created_at: str
    last_commit_at: Optional[str]
    contributors_count: int
    active_contributors_90d: int
    dependents_count: Optional[int]


class RepositoryEvaluationResponse(BaseModel):
    full_name: str
    html_url: str
    impact_score: float
    maintainer_sustainability_score: float
    ecosystem_dependency_score: float
    criticality_score: float
    risk_flag: str
    analysis: Optional[str] = None
    metrics: RepositoryMetricsResponse


class FundingCandidateResponse(BaseModel):
    full_name: str
    html_url: str
    description: Optional[str]
    total_contributors: int
    open_issues: int
    impact_score: float
    maintainer_sustainability_score: float
    ecosystem_dependency_score: float
    criticality_score: float
    dependents_count: int
    active_contributors_90d: int
    risk_flag: str
    analysis: Optional[str] = None


class FundingCandidatesEnvelope(BaseModel):
    count: int
    funding_candidates: List[FundingCandidateResponse]


class EvaluationsEnvelope(BaseModel):
    # Number of funding candidates
    count: int
    funding_candidates: List[FundingCandidateResponse]
    # All evaluated projects from the last request (for manual review)
    evaluations_count: int
    evaluations: List[RepositoryEvaluationResponse]


def get_github_service() -> GitHubService:
    return GitHubService()


def get_evaluator(github_service: GitHubService = Depends(get_github_service)) -> Evaluator:
    return Evaluator(github_service=github_service)


def get_crawler(github_service: GitHubService = Depends(get_github_service)) -> TopicCrawler:
    return TopicCrawler(github_service=github_service)


_last_funding_candidates: List[FundingCandidateResponse] = []
_last_all_evaluations: List[RepositoryEvaluation] = []


def _to_funding_candidate(e: RepositoryEvaluation) -> Optional[FundingCandidateResponse]:
    """
    Map a RepositoryEvaluation into a funding candidate if it meets
    the infrastructure-under-maintained criteria.
    """
    m = e.metrics
    dep = m.dependents_count or 0
    active = m.active_contributors_90d

    if dep >= 500 and active < 20:
        print(f"[FUNDING TARGET] {m.full_name}")
        print(f"dependents={dep}")
        print(f"active_contributors={active}")
        return FundingCandidateResponse(
            full_name=e.full_name,
            html_url=e.html_url,
            description=m.description,
            open_issues=m.open_issues,
            impact_score=e.impact_score,
            maintainer_sustainability_score=e.maintainer_sustainability_score,
            ecosystem_dependency_score=e.ecosystem_dependency_score,
            criticality_score=e.criticality_score,
            dependents_count=dep,
            total_contributors=m.contributors_count,
            active_contributors_90d=active,
            risk_flag=e.risk_flag,
            analysis=e.analysis,
        )
    return None


def get_last_funding_targets() -> FundingCandidatesEnvelope:
    """
    Return the funding candidates from the most recent evaluation.
    """
    funding = _last_funding_candidates or []
    return FundingCandidatesEnvelope(count=len(funding), funding_candidates=funding)


def _to_evaluation_response(e: RepositoryEvaluation) -> RepositoryEvaluationResponse:
    m = e.metrics
    return RepositoryEvaluationResponse(
        full_name=e.full_name,
        html_url=e.html_url,
        impact_score=e.impact_score,
        maintainer_sustainability_score=e.maintainer_sustainability_score,
        ecosystem_dependency_score=e.ecosystem_dependency_score,
        criticality_score=e.criticality_score,
        risk_flag=e.risk_flag,
        analysis=e.analysis,
        metrics=RepositoryMetricsResponse(
            full_name=m.full_name,
            html_url=m.html_url,
            description=m.description,
            stars=m.stars,
            forks=m.forks,
            open_issues=m.open_issues,
            created_at=m.created_at.isoformat(),
            last_commit_at=m.last_commit_at.isoformat() if m.last_commit_at else None,
            contributors_count=m.contributors_count,
            active_contributors_90d=m.active_contributors_90d,
            dependents_count=m.dependents_count,
        ),
    )


@app.post("/evaluate/topics", response_model=FundingCandidatesEnvelope)
def evaluate_topics(
    request: TopicsEvaluateRequest,
    evaluator: Evaluator = Depends(get_evaluator),
    crawler: TopicCrawler = Depends(get_crawler),
):
    """
    Evaluate repositories based on topics, then surface only funding
    candidate projects that are highly depended on but under-maintained.
    """
    global _last_funding_candidates, _last_all_evaluations

    repos = crawler.crawl_by_topics(request.topics, request.min_stars)
    if not repos:
        raise HTTPException(status_code=404, detail="No repositories found for given topics")

    evaluations = evaluator.evaluate_repositories(repos)
    _last_all_evaluations = evaluations

    # Funding candidate filter
    candidates: List[FundingCandidateResponse] = []
    for e in evaluations:
        candidate = _to_funding_candidate(e)
        if candidate:
            candidates.append(candidate)

    # Sort by ecosystem risk: dependents DESC, active_contributors ASC
    candidates.sort(
        key=lambda c: (-c.dependents_count, c.active_contributors_90d),
    )

    # Limit to top 20
    candidates = candidates[:50]

    _last_funding_candidates = candidates
    return FundingCandidatesEnvelope(count=len(candidates), funding_candidates=candidates)


@app.post("/evaluate/repo", response_model=FundingCandidatesEnvelope)
def evaluate_repo(
    request: RepoEvaluateRequest,
    evaluator: Evaluator = Depends(get_evaluator),
):
    """
    Evaluate a single repository provided by repo_url and surface it as a
    funding candidate only if it matches the funding criteria.
    """
    global _last_funding_candidates, _last_all_evaluations

    github_service = evaluator.github  # reuse same underlying service
    repo = github_service.get_repo_from_url(str(request.repo_url))
    evaluations = evaluator.evaluate_repositories([repo])
    _last_all_evaluations = evaluations

    candidates: List[FundingCandidateResponse] = []
    for e in evaluations:
        candidate = _to_funding_candidate(e)
        if candidate:
            candidates.append(candidate)

    # Sort and limit even for single repo for consistency
    candidates.sort(
        key=lambda c: (-c.dependents_count, c.active_contributors_90d),
    )
    candidates = candidates[:20]

    _last_funding_candidates = candidates
    return FundingCandidatesEnvelope(count=len(candidates), funding_candidates=candidates)


@app.get("/evaluations", response_model=EvaluationsEnvelope)
def get_evaluations():
    """
    Return the results of the most recent evaluation, including both
    prioritized funding candidates and all evaluated projects for
    manual review.
    """
    funding = _last_funding_candidates or []
    evals = _last_all_evaluations or []
    return EvaluationsEnvelope(
        count=len(funding),
        funding_candidates=funding,
        evaluations_count=len(evals),
        evaluations=[_to_evaluation_response(e) for e in evals],
    )


def _homepage_html(base_url: str, telegram_link: str | None) -> str:
    telegram_html = (
        f'<a href="{telegram_link}" target="_blank" rel="noopener noreferrer" '
        'style="color: #60a5fa; font-weight: bold;">ZynthClaw</a>'
        if telegram_link
        else '<strong style="color: #94a3b8;">Configure TELEGRAM_BOT_USERNAME to show the Telegram link.</strong>'
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ZynthClaw – Open Source Funding Radar</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ background: #0a0a0a; color: #f4f4f5; font-family: system-ui, -apple-system, sans-serif; line-height: 1.6; margin: 0; padding: 2rem; }}
    .container {{ max-width: 720px; margin: 0 auto; }}
    h1 {{ color: #fff; font-size: 2.25rem; margin-bottom: 0.5rem; }}
    h3 {{ color: #60a5fa; font-size: 1.25rem; margin-top: 2rem; margin-bottom: 0.75rem; }}
    p {{ color: #d4d4d8; margin: 0.75rem 0; }}
    section {{ margin: 2.5rem 0; }}
    .code {{ background: #18181b; border: 1px solid #27272a; border-radius: 6px; padding: 1rem 1.25rem; font-family: ui-monospace, monospace; font-size: 0.9rem; color: #e4e4e7; overflow-x: auto; }}
    .code code {{ user-select: all; }}
    a {{ color: #60a5fa; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    footer {{ margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid #27272a; color: #71717a; font-size: 0.9rem; }}
    footer a {{ color: #60a5fa; }}
  </style>
</head>
<body>
  <div class="container">
  <h1>ZynthClaw</h1>
    <h3>What I do</h3>
    <p>I detect <strong style="color: #fff;">critical open-source infrastructure</strong> that may need funding or community support. I crawl GitHub by topic or repo, collect maintenance and ecosystem metrics, and surface <strong style="color: #60a5fa;">funding candidates</strong>—projects with high dependents but few active maintainers.</p>

    <section>
      <h3>Why I exist – the problem I solve</h3>
      <p>Many essential libraries and tools power huge ecosystems but are maintained by very few people. When those maintainers burn out or move on, <strong style="color: #fff;">whole dependency trees are at risk</strong>. I help find and prioritize these projects so funders and communities can support them before it’s too late.</p>
    </section>

    <section>
    <h3>How to talk to ZynthClaw</h3>
      <p>You can talk to me in two ways:</p>
      <ol style="color: #d4d4d8;">
        <li style="margin-bottom: 1rem;">
          <strong style="color: #fff;">Have your AI agent interact with me</strong> via a curl command. Fetch my skill file and your agent will know what to do from there:
          <div class="code" style="margin-top: 0.75rem;"><code>curl -s "{base_url}/skill.md"</code></div>
        </li>
        <li>
          <strong style="color: #fff;">Use my dedicated Telegram handler:</strong> {telegram_html}
        </li>
      </ol>
    </section>

    <footer>
      Made with &hearts; by <a href="https://x.com/eversmanxbt" target="_blank" rel="noopener noreferrer">@eversmanxbt</a> at <strong>
      <a href="https://x.com/octantapp" target="_blank" rel="noopener noreferrer">@octantapp</a></strong> hackathon in partnership with <strong><a href="https://x.com/synthesis_md" target="_blank" rel="noopener noreferrer">@synthesis_md</a></strong>
      <br>
      powered by <strong><a href="https://x.com/@cursor_ai" target="_blank" rel="noopener noreferrer">@cursor_ai Sonnet 4.5</a></strong>
    </footer>
  </div>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def homepage(request: Request):
    """Homepage: agent name, description, why it exists, how to interact."""
    base_url = str(request.base_url).rstrip("/")
    telegram_username = settings.telegram_bot_username
    telegram_link = f"https://t.me/{telegram_username}" if telegram_username else None
    return _homepage_html(base_url, telegram_link)


@app.get("/skill.md")
def get_skill_md():
    """
    Serve the ZynthClaw skill description markdown file for other agents or browsers.
    """
    root_dir = Path(__file__).resolve().parent.parent
    skill_path = root_dir / "skill.md"
    if not skill_path.exists():
        raise HTTPException(status_code=404, detail="skill.md not found")
    return FileResponse(path=skill_path, media_type="text/markdown", filename="skill.md")

