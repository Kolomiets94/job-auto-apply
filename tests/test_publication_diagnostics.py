from datetime import datetime, timezone

from publication_diagnostics import build_freshness_report


def test_freshness_report_counts_age_buckets_and_unknown_without_guessing():
    now = datetime(2026, 11, 28, 12, tzinfo=timezone.utc)
    leads = [
        {"published": "2026-11-27T12:00:00Z"},
        {"published": "2026-11-23T12:00:00+00:00"},
        {"published": "2026-11-10T12:00:00Z"},
        {"published": "2026-10-01T12:00:00Z"},
        {"published": ""},
        {"published": "not-a-date"},
        {"published": "2026-11-29T12:00:00Z"},
    ]

    report = build_freshness_report(leads, now=now)

    assert "Проверено: 7" in report
    assert "- до 3 дней: 1" in report
    assert "- 4–7 дней: 1" in report
    assert "- 8–30 дней: 1" in report
    assert "- старше 30 дней: 1" in report
    assert "- дата неизвестна: 3" in report
    assert "возраст не меняет фильтры допуска" in report


def test_freshness_report_handles_empty_batch():
    report = build_freshness_report([])
    assert "Проверено: 0" in report
    assert "- дата неизвестна: 0" in report
