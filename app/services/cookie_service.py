import json
import time
from pathlib import Path

import browser_cookie3

from app.core.config import get_settings


BROWSER_LOADERS = [
    ("chrome", browser_cookie3.chrome),
    ("edge", browser_cookie3.edge),
    ("brave", browser_cookie3.brave),
    ("firefox", browser_cookie3.firefox),
]


class CookieService:
    def __init__(self, cache_path: Path | None = None) -> None:
        self.settings = get_settings()
        self.cache_path = cache_path or Path(".reddit_cookies_cache.json")

    def get_cookies(self, force_refresh: bool = False) -> dict[str, str]:
        if not force_refresh:
            cached = self._read_cache()
            if cached is not None:
                return cached
        cookies = self._load_from_browser()
        self._write_cache(cookies)
        return cookies

    def clear_cache(self) -> None:
        self.cache_path.unlink(missing_ok=True)

    def _read_cache(self) -> dict[str, str] | None:
        if not self.cache_path.exists():
            return None
        try:
            cached = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        saved_at = float(cached.get("saved_at", 0))
        if time.time() - saved_at >= self.settings.cookie_cache_ttl_seconds:
            return None
        cookies = cached.get("cookies")
        return cookies if isinstance(cookies, dict) else None

    def _write_cache(self, cookies: dict[str, str]) -> None:
        payload = {"saved_at": time.time(), "cookies": cookies}
        self.cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _load_from_browser(self) -> dict[str, str]:
        last_error: Exception | None = None
        for _, loader in BROWSER_LOADERS:
            try:
                jar = loader(domain_name="reddit.com")
                cookies = {cookie.name: cookie.value for cookie in jar}
                if cookies:
                    return cookies
            except Exception as exc:  # pragma: no cover - browser-specific failures
                last_error = exc
        raise RuntimeError(
            "Không tìm thấy cookie reddit.com từ Chrome/Edge/Brave/Firefox. "
            f"Lỗi cuối: {type(last_error).__name__ if last_error else 'unknown'}."
        )
