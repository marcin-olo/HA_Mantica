"""Failure thresholds and flood protection."""
from fixtures import policy as pol


def test_auth_needs_three_in_a_row():
    p = pol.FailurePolicy()
    assert [p.record("auth") for _ in range(3)] == ["retry", "retry", "reauth"]


def test_other_failure_resets_auth_count():
    p = pol.FailurePolicy()
    p.record("auth"), p.record("auth"), p.record("conn")
    assert p.record("auth") == "retry"


def test_success_resets():
    p = pol.FailurePolicy()
    p.record("auth"), p.record("auth"), p.success()
    assert p.record("auth") == "retry"


def test_layout_issue_after_two():
    p = pol.FailurePolicy()
    assert [p.record("layout") for _ in range(2)] == ["retry", "issue"]


def test_connection_issue_after_four():
    p = pol.FailurePolicy()
    assert [p.record("conn") for _ in range(4)] == ["retry"] * 3 + ["issue"]


def test_first_run_reports_nothing():
    assert pol.find_new([{"id": "a"}], None) == ([], False)


def test_few_new_items_are_individual():
    new, bulk = pol.find_new([{"id": str(i)} for i in range(5)], {"x"})
    assert len(new) == 5 and not bulk


def test_many_new_items_are_bulk():
    new, bulk = pol.find_new([{"id": str(i)} for i in range(30)], {"x"})
    assert len(new) == 30 and bulk


def test_recently_added_events_only():
    events = [
        {"id": "a", "added": "2026-11-06"},  # 2 days ago -> new
        {"id": "b", "added": "2026-10-01"},  # old entry, month just came into view
        {"id": "c", "added": ""},  # no date -> treated as new
    ]
    assert [e["id"] for e in pol.recently_added(events, "2026-11-08")] == ["a", "c"]


def test_poll_schedule_active_hours():
    from datetime import datetime, timedelta, timezone

    tz = timezone(timedelta(hours=1))

    def delay(h, m=0, interval=60, start=6, end=22):
        now = datetime(2026, 11, 9, h, m, tzinfo=tz)
        return pol.next_poll_delay(now, interval, start, end)

    assert delay(12) == timedelta(minutes=60)  # daytime: every hour
    assert delay(21) == timedelta(minutes=60)  # 22:00 is still read
    assert delay(21, 30) == timedelta(hours=8, minutes=30)  # -> 06:00 tomorrow
    assert delay(23, 30) == timedelta(hours=6, minutes=30)
    assert delay(1) == timedelta(hours=5)  # after midnight -> 06:00 today
    assert delay(5, 30) == timedelta(minutes=60)  # 06:30 is inside the window
    assert delay(3, interval=15, start=0, end=24) == timedelta(minutes=15)  # always on
