import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from xreporter.cli import app


runner = CliRunner()


def _write_fixture(path: Path) -> None:
    fixture = {
        "users_by_username": {
            "target": {"id": "100", "username": "target", "name": "Target"},
        },
        "followings_by_user_id": {
            "100": [
                {"id": "200", "username": "alice", "name": "Alice"},
            ]
        },
        "timelines_by_user_id": {
            "200": {
                "data": [
                    {
                        "id": "501",
                        "author_id": "200",
                        "text": "RT original",
                        "created_at": "2026-03-10T01:10:00Z",
                        "referenced_tweets": [{"type": "retweeted", "id": "700"}],
                        "public_metrics": {"like_count": 1, "retweet_count": 0, "reply_count": 0, "quote_count": 0},
                    },
                    {
                        "id": "502",
                        "author_id": "200",
                        "text": "My own tweet",
                        "created_at": "2026-03-10T01:20:00Z",
                        "public_metrics": {"like_count": 2, "retweet_count": 1, "reply_count": 0, "quote_count": 0},
                    },
                ],
                "includes": {
                    "users": [
                        {"id": "200", "username": "alice", "name": "Alice"},
                        {"id": "300", "username": "origin", "name": "Origin"},
                    ],
                    "tweets": [
                        {
                            "id": "700",
                            "author_id": "300",
                            "text": "Original content",
                            "created_at": "2026-03-10T00:50:00Z",
                            "public_metrics": {"like_count": 12, "retweet_count": 5, "reply_count": 1, "quote_count": 1},
                        }
                    ],
                },
            }
        },
        "users_by_id": {
            "300": {"id": "300", "username": "origin", "name": "Origin"},
        },
        "tweets_by_id": {
            "700": {
                "id": "700",
                "author_id": "300",
                "text": "Original content",
                "created_at": "2026-03-10T00:50:00Z",
                "public_metrics": {"like_count": 12, "retweet_count": 5, "reply_count": 1, "quote_count": 1},
            }
        },
    }
    path.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")


def test_collect_render_and_idempotency(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)

    db_path = tmp_path / "xreporter.db"
    report_dir = tmp_path / "reports"

    env = {
        "HOME": str(tmp_path),
        "XREPORTER_FIXTURE_FILE": str(fixture_path),
    }

    result = runner.invoke(
        app,
        [
            "config",
            "init",
            "--username",
            "target",
            "--lang",
            "en",
            "--db-path",
            str(db_path),
            "--report-dir",
            str(report_dir),
            "--following-cap",
            "200",
            "--include-replies",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    show_result = runner.invoke(app, ["config", "show"], env=env)
    assert show_result.exit_code == 0, show_result.output
    assert '"api_provider": "official"' in show_result.output

    collect_args = [
        "collect",
        "--since",
        "2026-03-10T00:00:00Z",
        "--until",
        "2026-03-10T02:00:00Z",
    ]

    result_collect_1 = runner.invoke(app, collect_args, env=env)
    assert result_collect_1.exit_code == 0, result_collect_1.output

    result_collect_2 = runner.invoke(app, collect_args, env=env)
    assert result_collect_2.exit_code == 0, result_collect_2.output

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM activities")
    activity_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM run_activities")
    run_activity_count = cur.fetchone()[0]
    cur.execute("SELECT MAX(id) FROM runs")
    latest_run_id = cur.fetchone()[0]
    conn.close()

    assert activity_count == 2
    assert run_activity_count == 4

    output_html = tmp_path / "report.html"
    result_render = runner.invoke(
        app,
        ["render", "--run-id", str(latest_run_id), "--output", str(output_html)],
        env=env,
    )
    assert result_render.exit_code == 0, result_render.output
    content = output_html.read_text(encoding="utf-8")
    assert "Grouped Retweets / Quotes / Replies" in content
    assert "Original content" in content
    assert "My own tweet" in content


def test_bilingual_cli_switch(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixture.json"
    _write_fixture(fixture_path)

    db_path = tmp_path / "xreporter.db"
    report_dir = tmp_path / "reports"

    env = {
        "HOME": str(tmp_path),
        "XREPORTER_FIXTURE_FILE": str(fixture_path),
    }

    init_zh = runner.invoke(
        app,
        [
            "config",
            "init",
            "--username",
            "target",
            "--lang",
            "zh",
            "--db-path",
            str(db_path),
            "--report-dir",
            str(report_dir),
        ],
        env=env,
    )
    assert init_zh.exit_code == 0

    doctor_zh = runner.invoke(app, ["doctor"], env=env)
    assert doctor_zh.exit_code == 0
    assert "健康检查" in doctor_zh.output

    init_en = runner.invoke(
        app,
        [
            "config",
            "init",
            "--username",
            "target",
            "--lang",
            "en",
            "--db-path",
            str(db_path),
            "--report-dir",
            str(report_dir),
        ],
        env=env,
    )
    assert init_en.exit_code == 0

    doctor_en = runner.invoke(app, ["doctor"], env=env)
    assert doctor_en.exit_code == 0
    assert "Health Check" in doctor_en.output
