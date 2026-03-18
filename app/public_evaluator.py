from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .github_service import GitHubService
from .evaluator import Evaluator
from .twitter_scraper import TwitterScraperError, fetch_user_posts_with_replies, fetch_user_tweets_and_replies


@dataclass
class XSignals:
    handle: str
    tweets: List[Dict[str, Any]]
    replies: List[Dict[str, Any]]
    threads: List[Dict[str, Any]]
    community_summary: str
    sentiment_label: str  # e.g. "positive", "mixed", "critical", "unknown"


@dataclass
class GitHubSignals:
    repo_url: str
    stars: int
    forks: int
    open_issues: int
    contributors_count: int
    recent_commit_count: int
    summary: str


def analyze_x_handle(handle: str) -> XSignals:
    """Analyze recent X activity for a handle using the official X API if configured."""
    handle = handle.lstrip("@").strip()

    try:
        print(f"[Evaluator] Analyzing X handle @{handle}")
        # Prefer grouped "post -> replies" threads for raw export and better review.
        threads = fetch_user_posts_with_replies(handle, max_posts=10, max_replies_per_post=30)
        raw_tweets = [t.post for t in threads]
        raw_replies = [r for t in threads for r in t.replies]
    except TwitterScraperError as exc:
        summary = (
            f"X analysis for @{handle} could not be completed ({exc}). "
            "This evaluation focuses on your direct feedback and optional GitHub signals."
        )
        print(f"[Evaluator] TwitterScraperError for @{handle}: {exc}")
        return XSignals(
            handle=handle,
            tweets=[],
            replies=[],
            threads=[],
            community_summary=summary,
            sentiment_label="unknown",
        )
    except Exception as exc:
        summary = (
            f"X analysis for @{handle} could not be completed (unexpected error). "
            "This evaluation focuses on your direct feedback and optional GitHub signals."
        )
        print(f"[Evaluator] Unexpected X analysis error for @{handle}: {exc}")
        return XSignals(
            handle=handle,
            tweets=[],
            replies=[],
            threads=[],
            community_summary=summary,
            sentiment_label="unknown",
        )

    # Convert Tweets to plain dicts for serialization
    tweets: List[Dict[str, Any]] = []
    for t in raw_tweets:
        tweets.append(
            {
                "id": t.id,
                "date": t.created_at.isoformat() if t.created_at else None,
                "content": t.text,
                "like_count": t.like_count,
                "retweet_count": t.retweet_count,
                "reply_count": t.reply_count,
                "author": t.author_username,
            }
        )

    replies: List[Dict[str, Any]] = []
    for r in raw_replies:
        replies.append(
            {
                "id": r.id,
                "date": r.created_at.isoformat() if r.created_at else None,
                "content": r.text,
                "like_count": r.like_count,
                "author": r.author_username,
            }
        )

    # Threaded view for raw export (post -> replies)
    threads_out: List[Dict[str, Any]] = []
    try:
        threads_out = []
        for th in threads:
            threads_out.append(
                {
                    "post": {
                        "id": th.post.id,
                        "date": th.post.created_at.isoformat() if th.post.created_at else None,
                        "content": th.post.text,
                        "like_count": th.post.like_count,
                        "retweet_count": th.post.retweet_count,
                        "reply_count": th.post.reply_count,
                        "author": th.post.author_username,
                    },
                    "replies": [
                        {
                            "id": rr.id,
                            "date": rr.created_at.isoformat() if rr.created_at else None,
                            "content": rr.text,
                            "like_count": rr.like_count,
                            "author": rr.author_username,
                        }
                        for rr in th.replies
                    ],
                }
            )
    except Exception as exc:
        print(f"[Evaluator] Failed to build threads output for @{handle}: {exc}")

    # Very light sentiment heuristic over replies
    positive_tokens = {"great", "love", "amazing", "awesome", "helpful", "useful", "thank", "thanks"}
    negative_tokens = {"bad", "broken", "bug", "hate", "terrible", "issue", "problem", "scam"}

    pos, neg = 0, 0
    for r in replies:
        text = r["content"].lower()
        if any(tok in text for tok in positive_tokens):
            pos += 1
        if any(tok in text for tok in negative_tokens):
            neg += 1

    if pos == 0 and neg == 0:
        sentiment_label = "unknown"
    elif pos >= neg * 2:
        sentiment_label = "positive"
    elif neg >= pos * 2:
        sentiment_label = "critical"
    else:
        sentiment_label = "mixed"

    summary_lines: List[str] = []
    summary_lines.append(f"Recent community sentiment for @{handle} (X):")
    summary_lines.append(f"- Original tweets analyzed: {len(tweets)}")
    summary_lines.append(f"- Filtered replies analyzed: {len(replies)}")
    summary_lines.append(f"- Heuristic sentiment label: {sentiment_label.upper()}")
    if replies:
        summary_lines.append(
            "Replies sampled appear to contain a mix of usage reports, feedback, and discussion. "
            "This is a heuristic summary; see raw data for details."
        )
    else:
        summary_lines.append(
            "No meaningful replies were found recently (or they were filtered out as noise). "
            "This evaluation will lean more heavily on your direct feedback and GitHub signals."
        )

    print(
        f"[Evaluator] X summary for @{handle}: tweets={len(tweets)}, replies={len(replies)}, "
        f"sentiment={sentiment_label}"
    )

    return XSignals(
        handle=handle,
        tweets=tweets,
        replies=replies,
        threads=threads_out,
        community_summary="\n".join(summary_lines),
        sentiment_label=sentiment_label,
    )


def analyze_github_repo(repo_url: str) -> Optional[GitHubSignals]:
    """Collect lightweight developer activity signals for a GitHub repo.

    Leverages the existing Evaluator + GitHubService so we don't duplicate
    metric collection logic.
    """
    if not repo_url:
        return None

    service = GitHubService()
    evaluator = Evaluator(github_service=service)
    try:
        print(f"[Evaluator] Analyzing GitHub repo URL: {repo_url}")
        repo = service.get_repo_from_url(repo_url)
        metrics = evaluator.collect_metrics_from_repo_obj(repo)
        full_name = metrics.full_name
    except Exception as exc:
        print(f"[Evaluator] Failed to analyze GitHub repo {repo_url}: {exc}")
        return None

    stars = metrics.stars
    forks = metrics.forks
    open_issues = metrics.open_issues
    contributors_count = metrics.contributors_count
    recent_commit_count = metrics.active_contributors_90d  # reuse existing metric as simple activity proxy

    summary_parts: List[str] = []
    summary_parts.append(f"⭐ Stars: {stars:,}, Forks: {forks:,}, Open issues: {open_issues:,}.")
    summary_parts.append(
        f"👥 Contributors: {contributors_count:,}, Active maintainers (90d): {metrics.active_contributors_90d:,}."
    )

    if stars > 1000 and contributors_count >= 5 and metrics.active_contributors_90d > 3:
        summary_parts.append(
            "This repository shows strong developer activity and ecosystem traction."
        )
    elif stars > 200 and metrics.active_contributors_90d > 1:
        summary_parts.append("Developer activity appears steady but not extreme.")
    else:
        summary_parts.append(
            "Developer activity appears relatively light; this may indicate maintainer bandwidth constraints."
        )

    print(
        f"[Evaluator] GitHub summary for {repo_url}: stars={stars}, forks={forks}, "
        f"open_issues={open_issues}, contributors={contributors_count}, "
        f"active_maintainers_90d={metrics.active_contributors_90d}"
    )

    return GitHubSignals(
        repo_url=repo_url,
        stars=stars,
        forks=forks,
        open_issues=open_issues,
        contributors_count=contributors_count,
        recent_commit_count=recent_commit_count,
        summary=" ".join(summary_parts),
    )


def classify_impact(
    sentiment_label: str,
    user_feedback: str,
    github_signals: Optional[GitHubSignals],
) -> str:
    """Coarse impact classification: High, Moderate, Emerging."""
    feedback_words = len(user_feedback.split())

    if github_signals is None:
        if feedback_words >= 80 and sentiment_label in {"positive", "mixed"}:
            return "High"
        if feedback_words >= 40:
            return "Moderate"
        return "Emerging"

    high_dev = (
        github_signals.stars > 1000
        and github_signals.contributors_count >= 5
        and github_signals.recent_commit_count >= 30
    )
    medium_dev = github_signals.stars > 200 and github_signals.recent_commit_count >= 10

    if high_dev and feedback_words >= 60 and sentiment_label in {"positive", "mixed"}:
        return "High"
    if medium_dev and feedback_words >= 30:
        return "Moderate"
    return "Emerging"


def mechanism_design_recommendation(
    impact_classification: str,
    x_signals: XSignals,
    user_feedback: str,
    github_signals: Optional[GitHubSignals],
) -> str:
    """Suggest how funding/incentives could be structured for this public good."""
    parts: List[str] = []
    parts.append(
        f"Overall impact classification for @{x_signals.handle}: {impact_classification.upper()}."
    )

    if github_signals is None:
        parts.append(
            "No GitHub repository was provided, so the recommendation leans heavily on "
            "community sentiment and your direct experience."
        )
    else:
        parts.append(
            "Both community/user signals and developer signals were considered "
            "to shape this recommendation."
        )

    if github_signals is not None:
        high_dev = (
            github_signals.stars > 1000
            and github_signals.contributors_count >= 5
            and github_signals.recent_commit_count >= 30
        )
        if high_dev:
            parts.append(
                "The project already has strong developer throughput. Funding could focus on "
                "expanding contributor onboarding, governance, and long-term maintainer sustainability, "
                "rather than purely bootstrapping development."
            )
        else:
            parts.append(
                "Developer activity looks relatively constrained. Mechanisms like retroactive public-goods "
                "rewards, targeted grants for maintainers, or matching pools for contributors could help "
                "stabilize and grow the development side."
            )

    if impact_classification == "High":
        parts.append(
            "Given the strong impact signals, this project is a good candidate for priority public-goods "
            "funding. Consider multi-epoch support rather than one-off grants."
        )
    elif impact_classification == "Moderate":
        parts.append(
            "Impact signals are meaningful but not maximal. It may fit well into mid-tier funding bands, "
            "with follow-up evaluations to track whether impact is growing."
        )
    else:
        parts.append(
            "Signals suggest an emerging public good. Smaller, exploratory grants or matching-based "
            "mechanisms could help test and amplify its trajectory without overcommitting capital early."
        )

    return " ".join(parts)


def build_public_goods_evaluation(
    x_handle: str,
    user_feedback: str,
    repo_url: Optional[str] = None,
    optional_user_info: Optional[str] = None,
) -> Dict[str, Any]:
    """End-to-end evaluation for a single project as a public good."""
    print(f"[Evaluator] Starting public goods evaluation for @{x_handle}")
    x_signals = analyze_x_handle(x_handle)
    github_signals = analyze_github_repo(repo_url) if repo_url else None

    impact_class = classify_impact(
        sentiment_label=x_signals.sentiment_label,
        user_feedback=user_feedback,
        github_signals=github_signals,
    )

    mech_rec = mechanism_design_recommendation(
        impact_classification=impact_class,
        x_signals=x_signals,
        user_feedback=user_feedback,
        github_signals=github_signals,
    )

    created_at = datetime.now(timezone.utc).isoformat()

    github_repo_url: Optional[str]
    github_summary: Optional[str]
    github_error: Optional[str] = None
    if repo_url and github_signals is None:
        # User provided a URL but we couldn't analyze it (e.g. org URL, private repo, or invalid).
        github_repo_url = repo_url
        github_summary = None
        github_error = (
            "GitHub repository could not be analyzed. Make sure the URL points to a public repository "
            "(for example https://github.com/owner/repo, not just an organization page)."
        )
    else:
        github_repo_url = github_signals.repo_url if github_signals else None
        github_summary = github_signals.summary if github_signals else None

    result = {
        "x_handle": x_signals.handle,
        "community_sentiment_summary": x_signals.community_summary,
        "user_feedback": user_feedback,
        "optional_user_info": optional_user_info,
        "github_repo_url": github_repo_url,
        "github_summary": github_summary,
        "github_error": github_error,
        "impact_classification": impact_class,
        "mechanism_design_recommendation": mech_rec,
        "created_at": created_at,
        "x_raw_tweets": x_signals.tweets,
        "x_raw_replies": x_signals.replies,
        "x_threads": x_signals.threads,
    }
    print(
        f"[Evaluator] Completed public goods evaluation for @{x_signals.handle}: "
        f"impact={impact_class}, github_repo_url={github_repo_url}"
    )
    return result

