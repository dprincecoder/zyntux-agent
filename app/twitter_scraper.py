from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests


X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN")


class TwitterScraperError(RuntimeError):
    pass


@dataclass
class Tweet:
    id: str
    text: str
    created_at: Optional[datetime]
    like_count: int
    reply_count: int
    retweet_count: int


def _get_headers() -> Dict[str, str]:
    if not X_BEARER_TOKEN:
        raise TwitterScraperError("X_BEARER_TOKEN is not configured in the environment.")
    return {
        "Authorization": f"Bearer {X_BEARER_TOKEN}",
        "User-Agent": "ZynthClaw-PublicGoods-Evaluator/1.0",
    }


def _get_user_id(handle: str) -> str:
    url = f"https://api.x.com/2/users/by/username/{handle}"
    print(f"[X] Looking up user id for @{handle} via {url}")
    resp = requests.get(url, headers=_get_headers(), timeout=20)
    if resp.status_code != 200:
        print(f"[X] User lookup failed for @{handle}: {resp.status_code} {resp.text}")
        raise TwitterScraperError(f"Failed to look up X user @{handle}: {resp.status_code}")
    data = resp.json()
    user = data.get("data") or {}
    user_id = user.get("id")
    if not user_id:
        raise TwitterScraperError(f"X user @{handle} not found.")
    return user_id


def fetch_user_bio(handle: str) -> Optional[str]:
    """Fetch the profile bio/description for a given X handle."""
    handle = handle.lstrip("@").strip()
    url = f"https://api.x.com/2/users/by/username/{handle}?user.fields=description"
    print(f"[X] Fetching bio for @{handle} via {url}")
    resp = requests.get(url, headers=_get_headers(), timeout=20)
    if resp.status_code != 200:
        print(f"[X] Bio fetch failed for @{handle}: {resp.status_code} {resp.text}")
        return None
    data = resp.json()
    user = data.get("data") or {}
    bio = user.get("description")
    print(f"[X] Bio for @{handle}: {bio!r}")
    return bio or None


def _parse_datetime(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def fetch_user_tweets_and_replies(handle: str, max_tweets: int = 20, max_replies: int = 200) -> Tuple[List[Tweet], List[Tweet]]:
    """Fetch recent original tweets and replies using the official X API v2.

    - Only returns original tweets (no retweets).
    - Replies are tweets replying to those originals.
    """
    handle = handle.lstrip("@").strip()
    print(f"[X] Starting fetch_user_tweets_and_replies for @{handle}")
    user_id = _get_user_id(handle)

    # Fetch recent tweets with expansions
    tweets_url = f"https://api.x.com/2/users/{user_id}/tweets"
    params = {
        "max_results": min(max_tweets, 100),
        "expansions": "referenced_tweets.id",
        "tweet.fields": "created_at,public_metrics,referenced_tweets",
    }
    print(f"[X] Fetching tweets for @{handle} from {tweets_url} with params={params}")
    resp = requests.get(tweets_url, headers=_get_headers(), params=params, timeout=20)
    if resp.status_code != 200:
        print(f"[X] Tweet fetch failed for @{handle}: {resp.status_code} {resp.text}")
        raise TwitterScraperError(f"Failed to fetch tweets for @{handle}: {resp.status_code}")

    data = resp.json()
    raw_tweets = data.get("data") or []

    tweets: List[Tweet] = []
    tweet_ids: List[str] = []

    for t in raw_tweets:
        # Skip retweets
        refs = t.get("referenced_tweets") or []
        if any(ref.get("type") == "retweeted" for ref in refs):
            continue
        tweet_ids.append(t["id"])
        metrics = t.get("public_metrics") or {}
        tweets.append(
            Tweet(
                id=t["id"],
                text=t.get("text", ""),
                created_at=_parse_datetime(t.get("created_at")),
                like_count=metrics.get("like_count", 0),
                reply_count=metrics.get("reply_count", 0),
                retweet_count=metrics.get("retweet_count", 0),
            )
        )
        if len(tweets) >= max_tweets:
            break

    replies: List[Tweet] = []
    if tweet_ids:
        # Search for replies to these tweet IDs
        # Use a "to:handle" query and then filter by referenced_tweets
        search_url = "https://api.x.com/2/tweets/search/recent"
        params = {
            "query": f"to:{handle}",
            "max_results": min(max_replies, 100),
            "tweet.fields": "created_at,public_metrics,referenced_tweets",
        }
        print(f"[X] Fetching replies to @{handle} from {search_url} with params={params}")
        resp = requests.get(search_url, headers=_get_headers(), params=params, timeout=20)
        if resp.status_code != 200:
            print(f"[X] Reply search failed for @{handle}: {resp.status_code} {resp.text}")
            # We treat this as non-fatal and just return tweets without replies
            return tweets, []

        search_data = resp.json()
        raw_replies = search_data.get("data") or []

        for t in raw_replies:
            refs = t.get("referenced_tweets") or []
            in_reply_to_ids = [ref.get("id") for ref in refs if ref.get("type") == "replied_to"]
            if not any(rid in tweet_ids for rid in in_reply_to_ids):
                continue

            text = t.get("text", "")
            lowered = text.lower()
            # Filter out obvious noise: links / very short content
            if "http://" in lowered or "https://" in lowered or "www." in lowered:
                continue
            if len(lowered.split()) < 3:
                continue

            metrics = t.get("public_metrics") or {}
            replies.append(
                Tweet(
                    id=t["id"],
                    text=text,
                    created_at=_parse_datetime(t.get("created_at")),
                    like_count=metrics.get("like_count", 0),
                    reply_count=metrics.get("reply_count", 0),
                    retweet_count=metrics.get("retweet_count", 0),
                )
            )
            if len(replies) >= max_replies:
                break

    print(f"[X] Completed fetch_user_tweets_and_replies for @{handle}: tweets={len(tweets)}, replies={len(replies)}")
    return tweets, replies

