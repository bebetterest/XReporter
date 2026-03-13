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


def test_render_report_zh_localized_content(tmp_path: Path) -> None:
    output = tmp_path / "run_2.html"
    run = {
        "id": 2,
        "username": "target_zh",
        "since_utc": "2026-03-10T00:00:00+00:00",
        "until_utc": "2026-03-10T02:00:00+00:00",
        "api_provider": "official",
        "status": "success",
        "include_replies": 1,
        "total_followings": 5,
        "total_activities": 1,
    }
    activities = [
        {
            "id": "act_1",
            "activity_type": "retweet",
            "actor_username": "alice",
            "event_created_at": "2026-03-10T01:10:00Z",
            "event_text": "转发示例",
            "event_url": "https://x.com/alice/status/501",
            "original_tweet_id": "700",
            "original_url": "https://x.com/origin/status/700",
            "original_text": "原帖内容示例",
            "original_author_username": "origin",
        }
    ]

    render_report(run=run, activities=activities, warnings=[], output_path=output, lang="zh")
    content = output.read_text(encoding="utf-8")

    assert '<html lang="zh">' in content
    assert "XReporter 活动报告" in content
    assert "按原帖聚合（发帖 / 转发 / 引用 / 回复）" in content
    assert "按用户聚合" in content
    assert "完整活动时间线" in content
    assert "目标用户" in content
    assert "转发" in content
    assert "动作内容" in content
    assert "打开帖子" in content
    assert '<details id="grouped" class="card collapsible">' in content
    assert '<details id="user-grouped" class="card collapsible">' in content
    assert '<details id="timeline" class="card collapsible">' in content
    assert '<details class="group-card item-collapsible">' in content
    assert '<details class="user-card item-collapsible">' in content
    assert '<details class="group-card item-collapsible" open>' not in content
    assert '<details class="user-card item-collapsible" open>' not in content
    assert 'id="grouped" class="card collapsible" open' not in content
    assert 'id="user-grouped" class="card collapsible" open' not in content
    assert 'id="timeline" class="card collapsible" open' not in content
    assert content.count("转发示例") >= 2
    assert content.count("原帖内容示例") >= 2
    assert "summary-grid" in content


def test_render_grouped_includes_tweet_activity(tmp_path: Path) -> None:
    output = tmp_path / "run_3.html"
    run = {
        "id": 3,
        "username": "target",
        "since_utc": "2026-03-10T00:00:00+00:00",
        "until_utc": "2026-03-10T02:00:00+00:00",
    }
    activities = [
        {
            "id": "tweet_act_1",
            "activity_type": "tweet",
            "event_tweet_id": "900",
            "actor_username": "alice",
            "event_created_at": "2026-03-10T01:20:00Z",
            "event_text": "My own tweet",
            "event_url": "https://x.com/alice/status/900",
            "original_tweet_id": None,
            "original_url": None,
            "original_text": None,
            "original_author_username": None,
        }
    ]

    render_report(run=run, activities=activities, warnings=[], output_path=output, lang="en")
    content = output.read_text(encoding="utf-8")

    assert "Grouped Posts / Retweets / Quotes / Replies" in content
    assert "Original Post #900" in content
    assert "My own tweet" in content
    assert content.count("My own tweet") >= 2


def test_render_timeline_sorted_newest_first(tmp_path: Path) -> None:
    output = tmp_path / "run_4.html"
    run = {
        "id": 4,
        "username": "target",
        "since_utc": "2026-03-10T00:00:00+00:00",
        "until_utc": "2026-03-10T03:00:00+00:00",
    }
    activities = [
        {
            "id": "a_old",
            "activity_type": "tweet",
            "event_tweet_id": "901",
            "actor_username": "alice",
            "event_created_at": "2026-03-10T01:00:00Z",
            "event_text": "timeline_old",
            "event_url": "https://x.com/alice/status/901",
        },
        {
            "id": "a_new",
            "activity_type": "tweet",
            "event_tweet_id": "902",
            "actor_username": "alice",
            "event_created_at": "2026-03-10T02:00:00Z",
            "event_text": "timeline_new",
            "event_url": "https://x.com/alice/status/902",
        },
        {
            "id": "a_mid",
            "activity_type": "tweet",
            "event_tweet_id": "903",
            "actor_username": "alice",
            "event_created_at": "2026-03-10T01:30:00Z",
            "event_text": "timeline_mid",
            "event_url": "https://x.com/alice/status/903",
        },
    ]

    render_report(run=run, activities=activities, warnings=[], output_path=output, lang="en")
    content = output.read_text(encoding="utf-8")

    timeline_start = content.index('<details id="timeline"')
    timeline_content = content[timeline_start:]
    assert timeline_content.index("timeline_new") < timeline_content.index("timeline_mid")
    assert timeline_content.index("timeline_mid") < timeline_content.index("timeline_old")


def test_render_grouped_sorted_by_count_then_latest(tmp_path: Path) -> None:
    output = tmp_path / "run_5.html"
    run = {
        "id": 5,
        "username": "target",
        "since_utc": "2026-03-10T00:00:00+00:00",
        "until_utc": "2026-03-10T03:00:00+00:00",
    }
    activities = [
        {
            "id": "g1_a",
            "activity_type": "reply",
            "event_tweet_id": "911",
            "actor_username": "u1",
            "event_created_at": "2026-03-10T01:10:00Z",
            "event_text": "g1_a",
            "event_url": "https://x.com/u1/status/911",
            "original_tweet_id": "g1",
            "original_url": "https://x.com/i/web/status/g1",
            "original_text": "orig_g1",
            "original_author_username": "o1",
        },
        {
            "id": "g1_b",
            "activity_type": "quote",
            "event_tweet_id": "912",
            "actor_username": "u2",
            "event_created_at": "2026-03-10T01:20:00Z",
            "event_text": "g1_b",
            "event_url": "https://x.com/u2/status/912",
            "original_tweet_id": "g1",
            "original_url": "https://x.com/i/web/status/g1",
            "original_text": "orig_g1",
            "original_author_username": "o1",
        },
        {
            "id": "g2_a",
            "activity_type": "retweet",
            "event_tweet_id": "921",
            "actor_username": "u3",
            "event_created_at": "2026-03-10T02:50:00Z",
            "event_text": "g2_a",
            "event_url": "https://x.com/u3/status/921",
            "original_tweet_id": "g2",
            "original_url": "https://x.com/i/web/status/g2",
            "original_text": "orig_g2",
            "original_author_username": "o2",
        },
        {
            "id": "g3_a",
            "activity_type": "reply",
            "event_tweet_id": "931",
            "actor_username": "u4",
            "event_created_at": "2026-03-10T02:00:00Z",
            "event_text": "g3_a",
            "event_url": "https://x.com/u4/status/931",
            "original_tweet_id": "g3",
            "original_url": "https://x.com/i/web/status/g3",
            "original_text": "orig_g3",
            "original_author_username": "o3",
        },
        {
            "id": "g3_b",
            "activity_type": "quote",
            "event_tweet_id": "932",
            "actor_username": "u5",
            "event_created_at": "2026-03-10T02:40:00Z",
            "event_text": "g3_b",
            "event_url": "https://x.com/u5/status/932",
            "original_tweet_id": "g3",
            "original_url": "https://x.com/i/web/status/g3",
            "original_text": "orig_g3",
            "original_author_username": "o3",
        },
    ]

    render_report(run=run, activities=activities, warnings=[], output_path=output, lang="en")
    content = output.read_text(encoding="utf-8")

    grouped_start = content.index('<details id="grouped"')
    user_grouped_start = content.index('<details id="user-grouped"')
    grouped_content = content[grouped_start:user_grouped_start]

    # g3 (2 actions, latest 02:40) should be before g1 (2 actions, latest 01:20),
    # and both should be before g2 (1 action).
    assert grouped_content.index("Original Post #g3") < grouped_content.index("Original Post #g1")
    assert grouped_content.index("Original Post #g1") < grouped_content.index("Original Post #g2")


def test_render_user_grouped_sorted_by_count_then_latest(tmp_path: Path) -> None:
    output = tmp_path / "run_6.html"
    run = {
        "id": 6,
        "username": "target",
        "since_utc": "2026-03-10T00:00:00+00:00",
        "until_utc": "2026-03-10T03:00:00+00:00",
    }
    activities = [
        {
            "id": "u1_a",
            "activity_type": "tweet",
            "event_tweet_id": "1001",
            "actor_id": "u1",
            "actor_username": "alice",
            "event_created_at": "2026-03-10T01:10:00Z",
            "event_text": "alice_1",
            "event_url": "https://x.com/alice/status/1001",
        },
        {
            "id": "u1_b",
            "activity_type": "reply",
            "event_tweet_id": "1002",
            "actor_id": "u1",
            "actor_username": "alice",
            "event_created_at": "2026-03-10T01:20:00Z",
            "event_text": "alice_2",
            "event_url": "https://x.com/alice/status/1002",
            "original_tweet_id": "5001",
            "original_url": "https://x.com/i/web/status/5001",
            "original_text": "orig_5001",
            "original_author_username": "orig",
        },
        {
            "id": "u2_a",
            "activity_type": "quote",
            "event_tweet_id": "1101",
            "actor_id": "u2",
            "actor_username": "bob",
            "event_created_at": "2026-03-10T02:55:00Z",
            "event_text": "bob_1",
            "event_url": "https://x.com/bob/status/1101",
            "original_tweet_id": "5002",
            "original_url": "https://x.com/i/web/status/5002",
            "original_text": "orig_5002",
            "original_author_username": "orig",
        },
        {
            "id": "u3_a",
            "activity_type": "tweet",
            "event_tweet_id": "1201",
            "actor_id": "u3",
            "actor_username": "carol",
            "event_created_at": "2026-03-10T02:00:00Z",
            "event_text": "carol_1",
            "event_url": "https://x.com/carol/status/1201",
        },
        {
            "id": "u3_b",
            "activity_type": "retweet",
            "event_tweet_id": "1202",
            "actor_id": "u3",
            "actor_username": "carol",
            "event_created_at": "2026-03-10T02:40:00Z",
            "event_text": "carol_2",
            "event_url": "https://x.com/carol/status/1202",
            "original_tweet_id": "5003",
            "original_url": "https://x.com/i/web/status/5003",
            "original_text": "orig_5003",
            "original_author_username": "orig",
        },
    ]

    render_report(run=run, activities=activities, warnings=[], output_path=output, lang="en")
    content = output.read_text(encoding="utf-8")

    user_grouped_start = content.index('<details id="user-grouped"')
    timeline_start = content.index('<details id="timeline"')
    user_grouped_content = content[user_grouped_start:timeline_start]

    # carol and alice both have 2 activities; carol latest (02:40) is newer than alice (01:20).
    # bob has 1 activity and should come after both.
    assert user_grouped_content.index("@carol") < user_grouped_content.index("@alice")
    assert user_grouped_content.index("@alice") < user_grouped_content.index("@bob")
