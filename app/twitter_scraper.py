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
    author_username: Optional[str] = None


@dataclass
class Thread:
    post: Tweet
    replies: List[Tweet]


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
        print(f"[X] Reply search returned {len(raw_replies)} raw items for @{handle} (before filtering)")

        for t in raw_replies:
            refs = t.get("referenced_tweets") or []
            in_reply_to_ids = [ref.get("id") for ref in refs if ref.get("type") == "replied_to"]
            if not any(rid in tweet_ids for rid in in_reply_to_ids):
                continue

            text = t.get("text", "")
            lowered = text.lower()
            # Filter out only link-containing replies (keep everything else).
            if "http://" in lowered or "https://" in lowered or "www." in lowered:
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


def fetch_user_posts_with_replies(
    handle: str,
    max_posts: int = 10,
    max_replies_per_post: int = 30,
) -> List[Thread]:
    """Fetch posts first, then fetch replies by conversation_id, then map replies onto posts."""
    handle = handle.lstrip("@").strip()
    print(f"[X] Starting fetch_user_posts_with_replies for @{handle}")

    posts = fetch_user_posts(handle, max_posts=max_posts)
    post_ids = [p.id for p in posts]
    replies_by_cid = fetch_replies_by_conversation_ids(
        post_ids,
        max_results_per_conversation=max_replies_per_post,
    )

    threads: List[Thread] = []
    for post in posts:
        replies = replies_by_cid.get(post.id) or []
        # Skip replies authored by the project itself (focus on community responses).
        replies = [r for r in replies if (r.author_username or "").lower() != handle.lower()]
        threads.append(Thread(post=post, replies=replies))

    print(
        f"[X] Completed fetch_user_posts_with_replies for @{handle}: posts={len(threads)} "
        f"replies_total={sum(len(t.replies) for t in threads)}"
    )
    return threads


def fetch_user_posts(handle: str, max_posts: int = 10) -> List[Tweet]:
    """Fetch recent original posts for a handle (no retweets, no replies)."""
    handle = handle.lstrip("@").strip()
    print(f"[X] Starting fetch_user_posts for @{handle}")
    user_id = _get_user_id(handle)

    tweets_url = f"https://api.x.com/2/users/{user_id}/tweets"
    params = {
        "max_results": min(max_posts * 2, 100),
        "expansions": "referenced_tweets.id",
        "tweet.fields": "created_at,public_metrics,referenced_tweets",
    }
    print(f"[X] Fetching posts for @{handle} from {tweets_url} with params={params}")
    resp = requests.get(tweets_url, headers=_get_headers(), params=params, timeout=20)
    if resp.status_code != 200:
        print(f"[X] Post fetch failed for @{handle}: {resp.status_code} {resp.text}")
        raise TwitterScraperError(f"Failed to fetch tweets for @{handle}: {resp.status_code}")

    data = resp.json()
    raw = data.get("data") or []
    posts: List[Tweet] = []
    for t in raw:
        refs = t.get("referenced_tweets") or []
        if any(ref.get("type") == "retweeted" for ref in refs):
            continue
        if any(ref.get("type") == "replied_to" for ref in refs):
            continue

        metrics = t.get("public_metrics") or {}
        posts.append(
            Tweet(
                id=t["id"],
                text=t.get("text", ""),
                created_at=_parse_datetime(t.get("created_at")),
                like_count=metrics.get("like_count", 0),
                reply_count=metrics.get("reply_count", 0),
                retweet_count=metrics.get("retweet_count", 0),
                author_username=handle,
            )
        )
        if len(posts) >= max_posts:
            break

    print(f"[X] Completed fetch_user_posts for @{handle}: posts={len(posts)}")
    return posts


def fetch_replies_by_conversation_ids(
    conversation_ids: List[str],
    max_results_per_conversation: int = 100,
) -> Dict[str, List[Tweet]]:
    """Fetch replies grouped by conversation_id for each provided id.

    This follows the X recent search approach:
      /2/tweets/search/recent?query=conversation_id:<ID>&tweet.fields=author_id,created_at,in_reply_to_user_id,referenced_tweets&expansions=author_id&max_results=100
    """
    search_url = "https://api.x.com/2/tweets/search/recent"
    out: Dict[str, List[Tweet]] = {}

    for cid in conversation_ids:
        query = f"conversation_id:{cid}"
        params = {
            "query": query,
            "max_results": min(max_results_per_conversation, 100),
            "tweet.fields": "author_id,created_at,in_reply_to_user_id,referenced_tweets,public_metrics",
            "expansions": "author_id",
            "user.fields": "username",
        }
        print(f"[X] Fetching conversation replies for cid={cid} via {search_url} query={query!r}")
        resp = requests.get(search_url, headers=_get_headers(), params=params, timeout=20)
        if resp.status_code != 200:
            print(f"[X] Conversation fetch failed cid={cid}: {resp.status_code} {resp.text}")
            out[cid] = []
            continue

        payload = resp.json()
        raw_items = payload.get("data") or []
        users = payload.get("includes", {}).get("users") or []
        user_map = {u.get("id"): u.get("username") for u in users if u.get("id")}

        print(f"[X] cid={cid} returned {len(raw_items)} items (before filtering to replies)")
        replies: List[Tweet] = []
        for item in raw_items:
            refs = item.get("referenced_tweets") or []
            # Only keep actual replies (avoid the root post if it shows up).
            if not any(ref.get("type") == "replied_to" for ref in refs):
                continue

            text = (item.get("text") or "").strip()
            lowered = text.lower()
            if not text:
                continue

            author_username = user_map.get(item.get("author_id"))
            print(f"[X] cid={cid} raw_reply id={item.get('id')} author=@{author_username or 'unknown'}")

            # Filter only link-containing replies.
            if "http://" in lowered or "https://" in lowered or "www." in lowered:
                continue

            metrics = item.get("public_metrics") or {}
            replies.append(
                Tweet(
                    id=item["id"],
                    text=text,
                    created_at=_parse_datetime(item.get("created_at")),
                    like_count=metrics.get("like_count", 0),
                    reply_count=metrics.get("reply_count", 0),
                    retweet_count=metrics.get("retweet_count", 0),
                    author_username=author_username,
                )
            )

        print(f"[X] cid={cid} kept {len(replies)} replies after filtering")
        out[cid] = replies

    return out

