from datetime import timedelta

from app.core.constants import metric_tier_for, next_metric_update_for, schedule_tier_for, utc_now


def test_metric_tiers():
    assert metric_tier_for(50, 0) == "hot"
    assert metric_tier_for(0, 10) == "high"
    assert metric_tier_for(0, 4) == "medium"
    assert metric_tier_for(0, 1) == "low"
    assert metric_tier_for(0, 0) == "very_low"


def test_schedule_tiers():
    assert schedule_tier_for(100, 200, 200) == 5
    assert schedule_tier_for(20, 50, 100) == 3
    assert schedule_tier_for(0, 0, 0) == 1


def test_next_metric_update_is_capped_by_tracking_until():
    now = utc_now()
    tracking_until = now + timedelta(minutes=10)
    assert next_metric_update_for(now, "very_low", tracking_until) == tracking_until
    assert next_metric_update_for(tracking_until, "hot", tracking_until) is None
