from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from .config import get_settings


settings = get_settings()


class GitHubRateLimitError(Exception):
    """Raised when the GitHub API rate limit has been exceeded."""


class GitHubService:
    def __init__(self, token: Optional[str] = None) -> None:
        self.base_url = settings.github_api_base
        self.token = token or settings.github_token

    def _client(self) -> httpx.Client:
        headers: Dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        # Simple debug aid for seeing which token/config is in use
        # (token value itself is not printed).
        print("[GitHubService] Creating client for", self.base_url)
        return httpx.Client(base_url=self.base_url, headers=headers, timeout=20.0)

    @staticmethod
    def _raise_for_rate_limit(resp: httpx.Response) -> None:
        """
        Handle GitHub API rate limits by raising a clear, structured error
        instead of a generic HTTP error.
        """
        if (
            resp.status_code == 403
            and resp.headers.get("X-RateLimit-Remaining") == "0"
        ):
            reset_ts = resp.headers.get("X-RateLimit-Reset")
            raise GitHubRateLimitError(
                f"GitHub API rate limit exceeded. X-RateLimit-Reset={reset_ts}"
            )
        resp.raise_for_status()

    def search_repositories_by_topics(self, topics: List[str]) -> List[Dict[str, Any]]:
        """
        Use the GitHub search API to find repositories matching all the given topics.
        Returns a list of repository summary dictionaries (as provided by the API).
        """
        if not topics:
            return []

        # Build query like: topic:ml topic:nlp
        topic_query = " ".join(f"topic:{t}" for t in topics)
        per_page = settings.github_search_page_size
        max_pages = settings.github_max_pages

        repos: List[Dict[str, Any]] = []
        with self._client() as client:
            for page in range(1, max_pages + 1):
                params = {
                    "q": topic_query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": per_page,
                    "page": page,
                }
                resp = client.get("/search/repositories", params=params)
                self._raise_for_rate_limit(resp)
                data = resp.json()
                items = data.get("items", [])
                repos.extend(items)
                if len(items) < per_page:
                    break

        # Return at most evaluation_max_repos
        return repos[: settings.evaluation_max_repos]

    def search_repositories_by_topic_with_min_stars(
        self, topic: str, min_stars: int
    ) -> List[Dict[str, Any]]:
        """
        Use the GitHub search API to find repositories for a single topic
        with stars >= min_stars. Results are sorted by stars (desc) and
        pagination is handled up to the configured maximum pages.
        """
        if not topic:
            return []

        # Query like: topic:ml stars:>=100
        query = f"topic:{topic} stars:>={max(min_stars, 0)}"
        per_page = settings.github_search_page_size
        max_pages = settings.github_max_pages

        repos: List[Dict[str, Any]] = []
        with self._client() as client:
            for page in range(1, max_pages + 1):
                params = {
                    "q": query,
                    "sort": "stars",
                    "order": "desc",
                    "per_page": per_page,
                    "page": page,
                }
                resp = client.get("/search/repositories", params=params)
                self._raise_for_rate_limit(resp)
                data = resp.json()
                items = data.get("items", [])
                repos.extend(items)
                if len(items) < per_page:
                    break

        return repos

    def get_repo_from_url(self, repo_url: str) -> Dict[str, Any]:
        """
        Given a standard GitHub repo URL, fetch repository details.
        Expected formats:
        - https://github.com/owner/name
        - https://github.com/owner/name/
        """
        # Extract "owner/name" from URL
        parts = repo_url.rstrip("/").split("/")
        if len(parts) < 2:
            raise ValueError("Invalid GitHub repository URL")
        owner = parts[-2]
        name = parts[-1]
        full_name = f"{owner}/{name}"
        return self.get_repository(full_name)

    def get_repository(self, full_name: str) -> Dict[str, Any]:
        with self._client() as client:
            resp = client.get(f"/repos/{full_name}")
            self._raise_for_rate_limit(resp)
            return resp.json()

    def get_repo_last_commit_date(self, full_name: str) -> Optional[datetime]:
        """
        Fetch the latest commit date on the default branch.
        """
        with self._client() as client:
            # Get default branch first
            repo_resp = client.get(f"/repos/{full_name}")
            self._raise_for_rate_limit(repo_resp)
            repo_data = repo_resp.json()
            default_branch = repo_data.get("default_branch", "main")

            # Get latest commit on default branch
            commits_resp = client.get(
                f"/repos/{full_name}/commits",
                params={"sha": default_branch, "per_page": 1},
            )
            self._raise_for_rate_limit(commits_resp)
            commits = commits_resp.json()
            if not commits:
                return None
            commit = commits[0]
            date_str = (
                commit.get("commit", {})
                .get("author", {})
                .get("date")
            )
            if not date_str:
                return None
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))

    def get_repo_contributors(self, full_name: str) -> List[Dict[str, Any]]:
        """
        Fetch contributors list for a repository.
        """
        contributors: List[Dict[str, Any]] = []
        per_page = 100
        page = 1
        with self._client() as client:
            while True:
                resp = client.get(
                    f"/repos/{full_name}/contributors",
                    params={"per_page": per_page, "page": page},
                )
                if resp.status_code == 204:
                    break
                self._raise_for_rate_limit(resp)
                batch = resp.json()
                if not batch:
                    break
                contributors.extend(batch)
                if len(batch) < per_page:
                    break
                page += 1
        return contributors

    def get_active_contributors_last_n_days(
        self, full_name: str, days: int = 90
    ) -> int:
        """
        Estimate number of active contributors over the last N days by scanning commits.
        This is a heuristic and may be truncated by API pagination.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        per_page = 100
        page = 1
        active_authors = set()

        with self._client() as client:
            while True:
                resp = client.get(
                    f"/repos/{full_name}/commits",
                    params={"per_page": per_page, "page": page, "since": cutoff.isoformat()},
                )
                if resp.status_code == 204:
                    break
                self._raise_for_rate_limit(resp)
                commits = resp.json()
                if not commits:
                    break
                for c in commits:
                    author = c.get("author") or {}
                    login = author.get("login")
                    if login:
                        active_authors.add(login)
                if len(commits) < per_page:
                    break
                page += 1

        return len(active_authors)

    # High-level, structured helpers requested in the spec -----------------

    def get_repo_metrics(self, repo_full_name: str) -> Dict[str, Any]:
        """
        Return key repository metrics as structured JSON:
        - stars, forks, open_issues
        - creation_date
        - last_commit (ISO8601, or None)
        """
        repo_data = self.get_repository(repo_full_name)
        last_commit_at = self.get_repo_last_commit_date(repo_full_name)

        return {
            "full_name": repo_data["full_name"],
            "description": repo_data.get("description"),
            "stars": repo_data.get("stargazers_count", 0),
            "forks": repo_data.get("forks_count", 0),
            "open_issues": repo_data.get("open_issues_count", 0),
            "creation_date": repo_data.get("created_at"),
            "last_commit": last_commit_at.isoformat() if last_commit_at else None,
        }

    def get_contributors(self, repo_full_name: str) -> Dict[str, Any]:
        """
        Return contributor statistics as structured JSON:
        - total_contributors
        - active_contributors_90d
        """
        contributors = self.get_repo_contributors(repo_full_name)
        active_90d = self.get_active_contributors_last_n_days(
            repo_full_name, days=90
        )

        return {
            "total_contributors": len(contributors),
            "active_contributors_90d": active_90d,
        }

    # NOTE: "dependents_count" scraping has been removed.

