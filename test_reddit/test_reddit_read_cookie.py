from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import time

import browser_cookie3
from curl_cffi import requests as cffi_requests
from curl_cffi.requests.exceptions import RequestException


SUBREDDIT = "vozforums"
API_URL = f"https://www.reddit.com/r/{SUBREDDIT}/new.json?limit=1"
REFERER_URL = f"https://www.reddit.com/r/{SUBREDDIT}/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# File cache cookie cục bộ để tránh phải mở lại DB trình duyệt mỗi lần chạy.
# Cookie hết hạn tự nhiên (Reddit thường set session dài hạn), nhưng ta vẫn
# đặt TTL để tự làm mới định kỳ.
COOKIE_CACHE_PATH = Path(__file__).parent / ".reddit_cookies_cache.json"
COOKIE_CACHE_TTL_SECONDS = 12 * 60 * 60  # 12 giờ

BROWSER_LOADERS = [
    ("chrome", browser_cookie3.chrome),
    ("edge", browser_cookie3.edge),
    ("brave", browser_cookie3.brave),
    ("firefox", browser_cookie3.firefox),
]


def _load_cookies_from_browser() -> dict:
    """Đọc cookie domain reddit.com từ trình duyệt đã đăng nhập trên máy."""
    last_error: Exception | None = None

    for name, loader in BROWSER_LOADERS:
        try:
            cookie_jar = loader(domain_name="reddit.com")
            cookies = {c.name: c.value for c in cookie_jar}
            if cookies:
                print(f"Đã lấy được {len(cookies)} cookie reddit.com từ {name}")
                return cookies
        except Exception as exc: 
            last_error = exc
            continue

    raise RuntimeError(
        "Không tìm thấy cookie reddit.com đã đăng nhập ở bất kỳ trình duyệt nào "
        f"(Chrome/Edge/Brave/Firefox). Lỗi cuối: {last_error}. "
        "Hãy đảm bảo bạn đã đăng nhập reddit.com trên một trong các trình duyệt đó, "
        "và đóng trình duyệt lại trước khi chạy script (một số hệ điều hành khoá "
        "file cookie DB khi trình duyệt đang mở)."
    )


def _get_cookies() -> dict:
    """Lấy cookie từ cache nếu còn hạn, ngược lại đọc lại từ trình duyệt."""
    if COOKIE_CACHE_PATH.exists():
        try:
            cached = json.loads(COOKIE_CACHE_PATH.read_text(encoding="utf-8"))
            if time.time() - cached.get("saved_at", 0) < COOKIE_CACHE_TTL_SECONDS:
                return cached["cookies"]
        except (json.JSONDecodeError, KeyError):
            pass 

    cookies = _load_cookies_from_browser()
    COOKIE_CACHE_PATH.write_text(
        json.dumps({"saved_at": time.time(), "cookies": cookies}, ensure_ascii=False),
        encoding="utf-8",
    )
    return cookies


def get_posts_from_last_24_hours() -> list[dict]:
    cookies = _get_cookies()

    session = cffi_requests.Session(impersonate="chrome124")
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    session.cookies.update(cookies)

    # "Ghé" trang thread list trước để trông giống hành vi trình duyệt thật
    # (đặt referer, chạm cùng session) trước khi gọi endpoint JSON.
    session.get(REFERER_URL, timeout=30)

    response = session.get(
        API_URL,
        headers={"Referer": REFERER_URL},
        timeout=30,
    )

    if response.status_code == 403:
        COOKIE_CACHE_PATH.unlink(missing_ok=True)
        raise RuntimeError(
            "Vẫn bị 403 dù đã dùng cookie đăng nhập. Cookie có thể đã hết hạn "
            "hoặc tài khoản bị flag. Đã xoá cache cookie, hãy đăng nhập lại "
            "reddit.com trên trình duyệt rồi chạy lại script."
        )
    response.raise_for_status()

    if "application/json" not in response.headers.get("Content-Type", ""):
        raise RuntimeError("Reddit did not return JSON; the request may have been blocked.")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    posts = []

    for child in response.json()["data"]["children"]:
        post = child["data"]
        created_at = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc)

        if created_at < cutoff:
            continue

        posts.append(
            {
                "reddit_post_id": post["id"],
                "title": post["title"],
                "author": post.get("author"),
                "subreddit": post["subreddit"],
                "created_at": created_at.isoformat(),
                "score": post.get("score", 0),
                "upvote_ratio": post.get("upvote_ratio"),
                "comments_count": post.get("num_comments", 0),
                "is_self": post.get("is_self", False),
                "selftext": post.get("selftext", ""),
                "post_url": post.get("url"),
                "html_url": "https://www.reddit.com" + post["permalink"],
                "thumbnail": post.get("thumbnail"),
                "flair": post.get("link_flair_text"),
                "over_18": post.get("over_18", False),
            }
        )

    return posts


if __name__ == "__main__":
    try:
        recent_posts = get_posts_from_last_24_hours()
        print(f"Found {len(recent_posts)} posts from the last 24 hours")
        print(json.dumps(recent_posts, ensure_ascii=False, indent=2))
    except RequestException as exc:
        print(f"Reddit request failed: {exc}")
    except (KeyError, ValueError, RuntimeError) as exc:
        print(f"Could not process Reddit response: {exc}")
