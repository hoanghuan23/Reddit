from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse

import requests

from app.core.config import get_settings
from app.services.cookie_service import CookieService


class RedditClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        permanent: bool = False,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.permanent = permanent
        self.retry_after = retry_after


@dataclass(frozen=True)
class RedditPostData:
    raw: dict[str, Any]


class RedditClient:
    def __init__(self, cookie_service: CookieService | None = None) -> None:
        self.settings = get_settings()
        self.cookie_service = cookie_service or CookieService()

    def build_listing_urls(self, source_type: str, identifier: str) -> tuple[str, str]:
        if source_type == "subreddit":
            safe = quote(identifier.strip(), safe="")
            return (
                f"https://www.reddit.com/r/{safe}/new.json",
                f"https://www.reddit.com/r/{safe}/new/",
            )
        if source_type == "keyword":
            safe = quote(identifier.strip())
            return (
                f"https://www.reddit.com/search.json?q={safe}&sort=new",
                f"https://www.reddit.com/search/?q={safe}&sort=new",
            )
        if source_type == "user":
            safe = quote(identifier.strip(), safe="")
            return (
                f"https://www.reddit.com/user/{safe}/submitted.json?sort=new",
                f"https://www.reddit.com/user/{safe}/submitted/",
            )
        if source_type == "latest":
            return ("https://www.reddit.com/r/all/new.json", "https://www.reddit.com/r/all/new/")
        raise ValueError(f"Unsupported source_type: {source_type}")

    def fetch_listing(self, source_type: str, identifier: str, limit: int | None = None) -> list[dict[str, Any]]:
        api_url, referer = self.build_listing_urls(source_type, identifier)
        payload = self._get_json(api_url, referer=referer, params={"limit": limit or self.settings.max_posts_per_source})
        try:
            children = payload["data"]["children"]
        except (KeyError, TypeError) as exc:
            raise RedditClientError("Reddit listing response không đúng cấu trúc JSON.") from exc
        return [child["data"] for child in children if child.get("kind") == "t3" and isinstance(child.get("data"), dict)]

    def fetch_post_metric(self, permalink: str) -> dict[str, Any]:
        post_url = self.normalise_post_url(permalink)
        api_url = f"{post_url.rstrip('/')}.json"
        payload = self._get_json(api_url, referer=post_url, params={"limit": 1})
        if not isinstance(payload, list) or not payload:
            raise RedditClientError("Reddit post response không đúng cấu trúc JSON.")
        try:
            return payload[0]["data"]["children"][0]["data"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RedditClientError("Không đọc được dữ liệu post từ response Reddit.") from exc

    def fetch_comments(self, permalink: str) -> list[dict[str, Any]]:
        post_url = self.normalise_post_url(permalink)
        payload = self._get_json(f"{post_url.rstrip('/')}.json", referer=post_url, params={"limit": 500})
        if not isinstance(payload, list) or len(payload) < 2:
            return []
        comments_root = payload[1].get("data", {}).get("children", [])
        comments: list[dict[str, Any]] = []
        self._flatten_comments(comments_root, comments)
        return comments

    def normalise_post_url(self, permalink: str) -> str:
        value = permalink.strip()
        if value.startswith("/"):
            return f"https://www.reddit.com{value.rstrip('/')}/"
        parsed = urlparse(value)
        if parsed.netloc.lower() in {"reddit.com", "www.reddit.com"} or parsed.netloc.lower().endswith(".reddit.com"):
            return f"https://www.reddit.com{parsed.path.rstrip('/')}/"
        raise RedditClientError("Permalink không phải URL/path Reddit hợp lệ.", permanent=True)

    def _get_json(self, url: str, referer: str, params: dict[str, Any] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.settings.reddit_max_retries + 1):
            try:
                return self._get_json_once(url, referer, params)
            except RedditClientError as exc:
                last_error = exc
                if exc.permanent or exc.status_code in {401, 403, 404}:
                    raise
                delay = self._retry_delay(exc, attempt)
            except requests.RequestException as exc:
                last_error = exc
                delay = self.settings.reddit_retry_backoff_seconds * (2**attempt)
            if attempt >= self.settings.reddit_max_retries:
                break
            time.sleep(delay)
        raise RedditClientError(f"Reddit request failed: {last_error}") from last_error

    def _get_json_once(self, url: str, referer: str, params: dict[str, Any] | None) -> Any:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": self.settings.reddit_user_agent,
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        session.cookies.update(self.cookie_service.get_cookies())
        session.get(referer, timeout=self.settings.request_timeout_seconds)
        response = session.get(url, params=params, headers={"Referer": referer}, timeout=self.settings.request_timeout_seconds)
        if response.status_code in {401, 403}:
            self.cookie_service.clear_cache()
            raise RedditClientError("Reddit từ chối request hoặc session không hợp lệ.", response.status_code, permanent=True)
        if response.status_code == 404:
            raise RedditClientError("Reddit source/post không tồn tại hoặc không truy cập được.", 404, permanent=True)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else None
            raise RedditClientError("Reddit rate limited request.", 429, retry_after=delay)
        if response.status_code >= 400:
            raise RedditClientError(f"Reddit HTTP error {response.status_code}.", response.status_code)
        content_type = response.headers.get("Content-Type", "")
        prefix = response.text[:200].lower()
        if "application/json" not in content_type and ("<html" in prefix or "login" in prefix or "blocked" in prefix):
            raise RedditClientError("Reddit trả HTML login/block page thay vì JSON.", permanent=True)
        try:
            return response.json()
        except ValueError as exc:
            raise RedditClientError("Reddit response không phải JSON hợp lệ.") from exc

    def _retry_delay(self, exc: RedditClientError, attempt: int) -> float:
        if exc.retry_after is not None:
            return exc.retry_after
        return self.settings.reddit_retry_backoff_seconds * (2**attempt)

    def _flatten_comments(self, nodes: list[dict[str, Any]], output: list[dict[str, Any]]) -> None:
        for node in nodes:
            if node.get("kind") != "t1":
                continue
            data = node.get("data") or {}
            output.append(data)
            replies = data.get("replies")
            if isinstance(replies, dict):
                children = replies.get("data", {}).get("children", [])
                self._flatten_comments(children, output)


def reddit_datetime(value: int | float | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)
