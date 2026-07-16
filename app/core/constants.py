from datetime import datetime, timedelta, timezone

METRIC_MINUTES_BY_TIER = {
    "hot": 30,
    "high": 90,
    "medium": 240,
    "low": 360,
    "very_low": 720,
}

SCHEDULE_MINUTES_BY_TIER = {
    1: 30,
    2: 60,
    3: 120,
    4: 240,
    5: 360,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def metric_tier_for(score: int | None, comments_count: int | None) -> str:
    engagement = (comments_count or 0) * 5 + max(score or 0, 0) * 2
    if engagement >= 100:
        return "hot"
    if engagement >= 50:
        return "high"
    if engagement >= 20:
        return "medium"
    if engagement >= 5:
        return "low"
    return "very_low"


def schedule_tier_for(total_posts: int, total_comments: int, total_score: int) -> int:
    activity_score = total_posts * 5 + total_comments * 2 + max(total_score, 0)
    if activity_score >= 1000:
        return 1
    if activity_score >= 500:
        return 2
    if activity_score >= 200:
        return 3
    if activity_score >= 50:
        return 4
    return 5


def next_metric_update_for(now: datetime, tier: str, tracking_until: datetime) -> datetime | None:
    if now >= tracking_until:
        return None
    candidate = now + timedelta(minutes=METRIC_MINUTES_BY_TIER[tier])
    return min(candidate, tracking_until)


def next_scrape_for(now: datetime, schedule_tier: int | None, override_minutes: int | None) -> datetime:
    minutes = override_minutes or SCHEDULE_MINUTES_BY_TIER.get(schedule_tier or 5, 360)
    return now + timedelta(minutes=minutes)
