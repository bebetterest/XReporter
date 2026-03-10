from __future__ import annotations

from pathlib import Path

from xreporter.render import render_report


def test_render_report_includes_red_warning_block(tmp_path: Path) -> None:
    output = tmp_path / "run_1.html"
    run = {
        "id": 1,
        "username": "target",
        "since_utc": "2026-03-10T00:00:00+00:00",
        "until_utc": "2026-03-10T02:00:00+00:00",
    }
    warnings = [
        {
            "provider": "socialdata",
            "warning_type": "private_content_403",
            "status_code": 403,
            "user_id": "200",
            "username": "locked_user",
            "resource_url": "https://x.com/i/web/status/123",
            "api_path": "/twitter/tweets/123",
            "message": "Skipped private content due to SocialData privacy restriction.",
            "raw_error": '{"status":"error","message":"Forbidden: privacy settings"}',
        }
    ]

    render_report(run=run, activities=[], warnings=warnings, output_path=output, lang="en")
    content = output.read_text(encoding="utf-8")

    assert "Collection Warnings" in content
    assert "warning-card" in content
    assert "--danger: #b42318;" in content
    assert "locked_user" in content
    assert "https://x.com/i/web/status/123" in content
    assert "/twitter/tweets/123" in content
