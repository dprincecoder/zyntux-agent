from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .github_service import GitHubService


@dataclass
class RepositoryMetrics:
    full_name: str
    html_url: str
    description: Optional[str]
    stars: int
    forks: int
    open_issues: int
    created_at: datetime
    last_commit_at: Optional[datetime]
    contributors_count: int
    active_contributors_90d: int


class Evaluator:
    """
    Collect lightweight GitHub activity metrics for a repository.

    NOTE: Legacy "funding candidates / dependents / risk scoring" has been removed.
    This class is retained because public-goods evaluation reuses the metric collection.
    """

    def __init__(self, github_service: GitHubService | None = None) -> None:
        self.github = github_service or GitHubService()

    def collect_metrics_from_repo_obj(self, repo: Dict[str, Any]) -> RepositoryMetrics:
        full_name = repo["full_name"]
        html_url = repo["html_url"]
        description = repo.get("description")
        stars = repo.get("stargazers_count", 0)
        forks = repo.get("forks_count", 0)
        open_issues = repo.get("open_issues_count", 0)
        created_at_str = repo.get("created_at")
        created_at = (
            datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            if created_at_str
            else datetime.now(timezone.utc)
        )

        last_commit_at = self.github.get_repo_last_commit_date(full_name)
        contributors = self.github.get_repo_contributors(full_name)
        contributors_count = len(contributors)
        active_contributors_90d = self.github.get_active_contributors_last_n_days(
            full_name, days=90
        )

        return RepositoryMetrics(
            full_name=full_name,
            html_url=html_url,
            description=description,
            stars=stars,
            forks=forks,
            open_issues=open_issues,
            created_at=created_at,
            last_commit_at=last_commit_at,
            contributors_count=contributors_count,
            active_contributors_90d=active_contributors_90d,
        )

