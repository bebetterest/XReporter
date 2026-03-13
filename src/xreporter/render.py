from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


REPORT_TEXT: dict[str, dict[str, Any]] = {
    "en": {
        "title": "XReporter Activity Report",
        "summary": "Run Summary",
        "warnings": "Collection Warnings",
        "grouped": "Grouped Posts / Retweets / Quotes / Replies",
        "user_grouped": "Grouped by User",
        "timeline": "Chronological Full Activity",
        "jump_warnings": "Jump to warnings section",
        "jump_grouped": "Jump to grouped section",
        "jump_user_grouped": "Jump to user-grouped section",
        "jump_timeline": "Jump to timeline section",
        "no_warnings": "No collection warnings recorded in this run.",
        "no_grouped": "No grouped post/retweet/quote/reply records in this run.",
        "no_user_grouped": "No user-grouped activity records in this run.",
        "generated": "Generated at",
        "actions": "actions",
        "warning_user": "User",
        "warning_resource": "Resource",
        "warning_provider_status": "Provider / Status",
        "warning_type": "Warning Type",
        "warning_api_path": "API Path",
        "warning_recorded_at": "Recorded At",
        "warning_raw_error": "Raw Error",
        "no_timeline": "No activity records in this run.",
        "by": "by",
        "at": "at",
        "unknown": "unknown",
        "open": "open",
        "open_post": "open post",
        "summary_user": "Target User",
        "summary_run_id": "Run ID",
        "summary_provider": "Provider",
        "summary_status": "Run Status",
        "summary_window": "Time Window",
        "summary_include_replies": "Include Replies",
        "summary_yes": "Yes",
        "summary_no": "No",
        "stat_followings": "Followings Scanned",
        "stat_activities": "Activities",
        "stat_grouped": "Grouped Originals",
        "stat_warnings": "Warnings",
        "original_post": "Original Post",
        "timeline_original": "Original",
        "action_text": "Action Text",
        "timeline_original_text": "Original Text",
        "no_action_text": "(empty)",
        "toggle_hint": "Click to expand/collapse",
        "latest_activity": "Latest Activity",
        "user_id": "User ID",
        "original_ref": "Original",
        "activity_labels": {
            "tweet": "Tweet",
            "retweet": "Retweet",
            "quote": "Quote",
            "reply": "Reply",
        },
    },
    "zh": {
        "title": "XReporter 活动报告",
        "summary": "运行摘要",
        "warnings": "采集告警",
        "grouped": "按原帖聚合（发帖 / 转发 / 引用 / 回复）",
        "user_grouped": "按用户聚合",
        "timeline": "完整活动时间线",
        "jump_warnings": "跳转到告警区",
        "jump_grouped": "跳转到聚合区",
        "jump_user_grouped": "跳转到按用户聚合区",
        "jump_timeline": "跳转到时间线",
        "no_warnings": "本次运行未记录采集告警。",
        "no_grouped": "本次运行没有可聚合的发帖/转发/引用/回复记录。",
        "no_user_grouped": "本次运行没有可按用户聚合的活动记录。",
        "generated": "生成时间",
        "actions": "条动作",
        "warning_user": "用户",
        "warning_resource": "资源链接",
        "warning_provider_status": "数据源 / 状态码",
        "warning_type": "告警类型",
        "warning_api_path": "API 路径",
        "warning_recorded_at": "记录时间",
        "warning_raw_error": "原始错误",
        "no_timeline": "本次运行没有活动记录。",
        "by": "来自",
        "at": "时间",
        "unknown": "未知",
        "open": "打开",
        "open_post": "打开帖子",
        "summary_user": "目标用户",
        "summary_run_id": "运行 ID",
        "summary_provider": "数据源",
        "summary_status": "运行状态",
        "summary_window": "时间窗口",
        "summary_include_replies": "包含回复",
        "summary_yes": "是",
        "summary_no": "否",
        "stat_followings": "扫描关注数",
        "stat_activities": "活动数",
        "stat_grouped": "聚合原帖数",
        "stat_warnings": "告警数",
        "original_post": "原帖",
        "timeline_original": "原帖",
        "action_text": "动作内容",
        "timeline_original_text": "原帖内容",
        "no_action_text": "（空）",
        "toggle_hint": "点击展开/收起",
        "latest_activity": "最新活动",
        "user_id": "用户 ID",
        "original_ref": "原帖",
        "activity_labels": {
            "tweet": "发帖",
            "retweet": "转发",
            "quote": "引用",
            "reply": "回复",
        },
    },
}


@dataclass
class GroupedOriginal:
    original_tweet_id: str
    original_url: str
    original_text: str
    original_author_username: str | None
    actions: list[dict[str, Any]]


@dataclass
class UserGrouped:
    actor_id: str | None
    actor_username: str | None
    actions: list[dict[str, Any]]


def _text_table(lang: str) -> dict[str, Any]:
    return REPORT_TEXT.get(lang, REPORT_TEXT["en"])


def _class_safe(value: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "-" for ch in value.lower())
    normalized = normalized.strip("-")
    return normalized or "unknown"


def _activity_label(activity_type: str | None, text: dict[str, Any]) -> str:
    labels = text.get("activity_labels", {})
    if isinstance(labels, dict) and activity_type:
        mapped = labels.get(activity_type)
        if isinstance(mapped, str):
            return mapped
    return activity_type or "-"


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _fmt_dt(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return value


def _event_sort_ts(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return float("-inf")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).timestamp()
    except ValueError:
        return float("-inf")


def _activity_sort_key(item: dict[str, Any]) -> tuple[float, str]:
    return (
        _event_sort_ts(item.get("event_created_at")),
        str(item.get("id") or item.get("event_tweet_id") or ""),
    )


def _render_summary(
    *,
    run: dict[str, Any],
    activities: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    grouped_count: int,
    lang: str,
) -> str:
    text = _text_table(lang)

    username = run.get("username") or text["unknown"]
    run_id = run.get("id")
    provider = run.get("api_provider") or "-"
    status = run.get("status") or "-"
    since = _fmt_dt(str(run.get("since_utc") or "")) or "-"
    until = _fmt_dt(str(run.get("until_utc") or "")) or "-"
    include_replies = text["summary_yes"] if _to_bool(run.get("include_replies")) else text["summary_no"]

    total_followings = _to_int(run.get("total_followings"), 0)
    total_activities = _to_int(run.get("total_activities"), len(activities))

    meta_rows = [
        (text["summary_user"], f"@{username}"),
        (text["summary_run_id"], str(run_id) if run_id is not None else "-"),
        (text["summary_provider"], str(provider)),
        (text["summary_status"], str(status)),
        (text["summary_window"], f"{since} ~ {until}"),
        (text["summary_include_replies"], include_replies),
    ]
    meta_html = "\n".join(
        (
            "<div class='kv-row'>"
            f"<span class='kv-key'>{escape(str(key))}</span>"
            f"<span class='kv-value'>{escape(str(value))}</span>"
            "</div>"
        )
        for key, value in meta_rows
    )

    stat_rows = [
        (text["stat_followings"], total_followings),
        (text["stat_activities"], total_activities),
        (text["stat_grouped"], grouped_count),
        (text["stat_warnings"], len(warnings)),
    ]
    stat_html = "\n".join(
        (
            "<div class='stat-card'>"
            f"<p class='stat-label'>{escape(str(label))}</p>"
            f"<p class='stat-value'>{escape(str(value))}</p>"
            "</div>"
        )
        for label, value in stat_rows
    )

    return f"""
    <div class="summary-grid">
      <section class="summary-meta">
        <h2>{escape(text['summary'])}</h2>
        <div class="kv-grid">
          {meta_html}
        </div>
      </section>
      <section class="summary-stats">
        <div class="stat-grid">
          {stat_html}
        </div>
      </section>
    </div>
    """


def _render_grouped(groups: list[GroupedOriginal], lang: str) -> str:
    text = _text_table(lang)
    if not groups:
        return f"<p class='empty'>{escape(text['no_grouped'])}</p>"

    blocks: list[str] = []
    for group in groups:
        author = group.original_author_username or text["unknown"]
        blocks.append(
            """
            <details class="group-card item-collapsible">
              <summary class="item-summary">
                <div class="item-summary-left">
                  <h3><a href="{url}" target="_blank" rel="noopener">{original_post} #{tweet_id}</a></h3>
                  <p class="meta">@{author} · {count} {actions}</p>
                </div>
                <span class="section-right">
                  <span class="toggle-hint"><span class="toggle-icon">▸</span>{toggle_hint}</span>
                </span>
              </summary>
              <div class="item-content">
                <p class="group-original"><span class="inline-label">{timeline_original_text}:</span>{text}</p>
                <ul class="action-list">
                  {actions_html}
                </ul>
              </div>
            </details>
            """.format(
                url=escape(group.original_url),
                original_post=escape(text["original_post"]),
                tweet_id=escape(group.original_tweet_id),
                author=escape(author),
                count=len(group.actions),
                actions=escape(text["actions"]),
                toggle_hint=escape(text["toggle_hint"]),
                text=escape(group.original_text or "-"),
                timeline_original_text=escape(text["timeline_original_text"]),
                actions_html="\n".join(
                    (
                        "<li class='action-item'>"
                        "<div class='action-head'>"
                        f"<span class='activity-tag activity-{_class_safe(str(action.get('activity_type') or 'unknown'))}'>"
                        f"{escape(_activity_label(action.get('activity_type'), text))}</span>"
                        f"<span class='action-meta'>{escape(text['by'])} @{escape(action.get('actor_username') or text['unknown'])}"
                        f" · {escape(text['at'])} {escape(_fmt_dt(action.get('event_created_at')) or '-')}</span>"
                        f"<a href='{escape(action.get('event_url') or '#')}' target='_blank' rel='noopener'>{escape(text['open'])}</a>"
                        "</div>"
                        f"<p class='action-text'><span class='inline-label'>{escape(text['action_text'])}:</span>"
                        f"{escape(str(action.get('event_text') or text['no_action_text']))}</p>"
                        "</li>"
                    )
                    for action in group.actions
                ),
            )
        )

    return "\n".join(blocks)


def _render_user_grouped(groups: list[UserGrouped], lang: str) -> str:
    text = _text_table(lang)
    if not groups:
        return f"<p class='empty'>{escape(text['no_user_grouped'])}</p>"

    blocks: list[str] = []
    for group in groups:
        username = group.actor_username or text["unknown"]
        user_id = group.actor_id or "-"
        latest_ts = _fmt_dt(group.actions[0].get("event_created_at")) if group.actions else "-"

        action_rows: list[str] = []
        for action in group.actions:
            original_line = ""
            original_id = action.get("original_tweet_id")
            if original_id:
                original_url = action.get("original_url") or f"https://x.com/i/web/status/{original_id}"
                original_line = (
                    "<p class='action-extra'>"
                    f"<span class='inline-label'>{escape(text['original_ref'])}:</span>"
                    f"<a href='{escape(original_url)}' target='_blank' rel='noopener'>{escape(str(original_id))}</a>"
                    "</p>"
                )

            action_rows.append(
                "<li class='action-item'>"
                "<div class='action-head'>"
                f"<span class='activity-tag activity-{_class_safe(str(action.get('activity_type') or 'unknown'))}'>"
                f"{escape(_activity_label(action.get('activity_type'), text))}</span>"
                f"<span class='action-meta'>{escape(text['at'])} {escape(_fmt_dt(action.get('event_created_at')) or '-')}</span>"
                f"<a href='{escape(action.get('event_url') or '#')}' target='_blank' rel='noopener'>{escape(text['open'])}</a>"
                "</div>"
                f"<p class='action-text'><span class='inline-label'>{escape(text['action_text'])}:</span>"
                f"{escape(str(action.get('event_text') or text['no_action_text']))}</p>"
                f"{original_line}"
                "</li>"
            )

        blocks.append(
            """
            <details class="user-card item-collapsible">
              <summary class="item-summary">
                <div class="item-summary-left">
                  <h3>@{username}</h3>
                  <p class="meta"><span class="inline-label">{user_id_label}:</span>{user_id} · {count} {actions}</p>
                  <p class="meta"><span class="inline-label">{latest_activity}:</span>{latest_ts}</p>
                </div>
                <span class="section-right">
                  <span class="toggle-hint"><span class="toggle-icon">▸</span>{toggle_hint}</span>
                </span>
              </summary>
              <div class="item-content">
                <ul class="action-list">
                  {actions_html}
                </ul>
              </div>
            </details>
            """.format(
                username=escape(username),
                user_id_label=escape(text["user_id"]),
                user_id=escape(user_id),
                count=len(group.actions),
                actions=escape(text["actions"]),
                latest_activity=escape(text["latest_activity"]),
                latest_ts=escape(latest_ts or "-"),
                toggle_hint=escape(text["toggle_hint"]),
                actions_html="\n".join(action_rows),
            )
        )

    return "\n".join(blocks)


def _render_timeline(activities: list[dict[str, Any]], lang: str) -> str:
    text = _text_table(lang)
    if not activities:
        return f"<p class='empty'>{escape(text['no_timeline'])}</p>"

    ordered_activities = sorted(
        activities,
        key=_activity_sort_key,
        reverse=True,
    )

    lines: list[str] = ["<ul class='timeline'>"]
    for item in ordered_activities:
        activity_type = str(item.get("activity_type") or "unknown")
        original_tweet_id = item.get("original_tweet_id")
        original_line = ""
        original_text_line = ""
        if original_tweet_id:
            original_url = item.get("original_url") or f"https://x.com/i/web/status/{original_tweet_id}"
            original_line = (
                "<p class='timeline-extra'>"
                f"{escape(text['timeline_original'])}: "
                f"<a href='{escape(original_url)}' target='_blank' rel='noopener'>"
                f"{escape(str(original_tweet_id))}</a>"
                "</p>"
            )
            original_text = str(item.get("original_text") or "").strip()
            if original_text:
                original_text_line = (
                    "<p class='timeline-original-text'>"
                    f"<span class='inline-label'>{escape(text['timeline_original_text'])}:</span>"
                    f"{escape(original_text)}"
                    "</p>"
                )

        lines.append(
            "<li class='timeline-item'>"
            "<article class='timeline-card'>"
            "<p class='timeline-head'>"
            f"<span class='activity-tag activity-{_class_safe(activity_type)}'>{escape(_activity_label(item.get('activity_type'), text))}</span>"
            f"<span class='timeline-meta'>@{escape(item.get('actor_username') or text['unknown'])} · {escape(_fmt_dt(item.get('event_created_at')) or '-')}</span>"
            "</p>"
            f"<p class='timeline-text'><span class='inline-label'>{escape(text['action_text'])}:</span>"
            f"{escape(str(item.get('event_text') or text['no_action_text']))}</p>"
            f"{original_line}"
            f"{original_text_line}"
            f"<p class='timeline-link'><a href='{escape(item.get('event_url') or '#')}' target='_blank' rel='noopener'>{escape(text['open_post'])}</a></p>"
            "</article>"
            "</li>"
        )
    lines.append("</ul>")
    return "\n".join(lines)


def _render_warnings(warnings: list[dict[str, Any]], lang: str) -> str:
    text = _text_table(lang)
    if not warnings:
        return f"<p class='empty'>{escape(text['no_warnings'])}</p>"

    blocks: list[str] = []
    for warning in warnings:
        username = warning.get("username") or text["unknown"]
        user_id = warning.get("user_id") or "-"
        status_code = warning.get("status_code")
        status = str(status_code) if status_code is not None else "-"
        warning_type = warning.get("warning_type") or "-"
        resource_url = str(warning.get("resource_url") or "").strip()
        api_path = warning.get("api_path") or "-"
        raw_error = warning.get("raw_error") or "-"
        message = warning.get("message") or ""
        provider = warning.get("provider") or "-"
        recorded_at = _fmt_dt(str(warning.get("created_at") or "")) or "-"

        resource_html = "-"
        if resource_url:
            resource_html = (
                f"<a href='{escape(resource_url)}' target='_blank' rel='noopener'>{escape(resource_url)}</a>"
            )

        blocks.append(
            """
            <section class="warning-card">
              <h3 class="warning-title">{message}</h3>
              <p class="warning-line"><strong>{warning_user}:</strong> @{username} (id={user_id})</p>
              <p class="warning-line"><strong>{warning_resource}:</strong> {resource}</p>
              <p class="warning-line"><strong>{warning_provider_status}:</strong> {provider} / {status}</p>
              <p class="warning-line"><strong>{warning_type}:</strong> {warning_type_value}</p>
              <p class="warning-line"><strong>{warning_api_path}:</strong> {api_path}</p>
              <p class="warning-line"><strong>{warning_recorded_at}:</strong> {recorded_at}</p>
              <p class="warning-line"><strong>{warning_raw_error}:</strong></p>
              <pre class="warning-raw">{raw_error}</pre>
            </section>
            """.format(
                message=escape(message),
                warning_user=escape(text["warning_user"]),
                username=escape(username),
                user_id=escape(user_id),
                warning_resource=escape(text["warning_resource"]),
                resource=resource_html,
                warning_provider_status=escape(text["warning_provider_status"]),
                provider=escape(provider),
                status=escape(status),
                warning_type=escape(text["warning_type"]),
                warning_type_value=escape(warning_type),
                warning_api_path=escape(text["warning_api_path"]),
                api_path=escape(api_path),
                warning_recorded_at=escape(text["warning_recorded_at"]),
                recorded_at=escape(recorded_at),
                warning_raw_error=escape(text["warning_raw_error"]),
                raw_error=escape(raw_error),
            )
        )

    return "\n".join(blocks)


def render_report(
    *,
    run: dict[str, Any],
    activities: list[dict[str, Any]],
    warnings: list[dict[str, Any]] | None = None,
    output_path: Path,
    lang: str,
) -> Path:
    text = _text_table(lang)
    warning_rows = warnings or []
    user_group_map: dict[str, UserGrouped] = {}

    grouped_map: dict[str, GroupedOriginal] = {}
    for item in activities:
        activity_type = str(item.get("activity_type") or "")
        if activity_type not in {"tweet", "retweet", "quote", "reply"}:
            continue

        actor_id = str(item.get("actor_id") or "").strip() or None
        actor_username = str(item.get("actor_username") or "").strip() or None
        user_key = actor_id or (f"username:{actor_username.lower()}" if actor_username else "unknown")
        if user_key not in user_group_map:
            user_group_map[user_key] = UserGrouped(
                actor_id=actor_id,
                actor_username=actor_username,
                actions=[],
            )
        user_group = user_group_map[user_key]
        if not user_group.actor_id and actor_id:
            user_group.actor_id = actor_id
        if not user_group.actor_username and actor_username:
            user_group.actor_username = actor_username
        user_group.actions.append(item)

        if activity_type == "tweet":
            original_id = str(item.get("event_tweet_id") or "")
            if not original_id:
                continue
            original_url = item.get("event_url") or f"https://x.com/i/web/status/{original_id}"
            original_text = item.get("event_text") or ""
            original_author_username = item.get("actor_username")
        else:
            original_id = str(item.get("original_tweet_id") or "")
            if not original_id:
                continue
            original_url = item.get("original_url") or f"https://x.com/i/web/status/{original_id}"
            original_text = item.get("original_text") or ""
            original_author_username = item.get("original_author_username")

        default_original_url = f"https://x.com/i/web/status/{original_id}"
        if original_id not in grouped_map:
            grouped_map[original_id] = GroupedOriginal(
                original_tweet_id=original_id,
                original_url=original_url,
                original_text=original_text,
                original_author_username=original_author_username,
                actions=[],
            )
        group = grouped_map[original_id]
        if not group.original_text and original_text:
            group.original_text = original_text
        if not group.original_author_username and original_author_username:
            group.original_author_username = original_author_username
        if group.original_url == default_original_url and original_url != default_original_url:
            group.original_url = original_url
        group.actions.append(item)

    for group in grouped_map.values():
        group.actions.sort(key=_activity_sort_key, reverse=True)

    grouped = sorted(
        grouped_map.values(),
        key=lambda group: (
            len(group.actions),
            max((_event_sort_ts(action.get("event_created_at")) for action in group.actions), default=float("-inf")),
        ),
        reverse=True,
    )
    for user_group in user_group_map.values():
        user_group.actions.sort(key=_activity_sort_key, reverse=True)

    user_grouped = sorted(
        user_group_map.values(),
        key=lambda group: (
            len(group.actions),
            _event_sort_ts(group.actions[0].get("event_created_at")) if group.actions else float("-inf"),
        ),
        reverse=True,
    )

    summary_html = _render_summary(
        run=run,
        activities=activities,
        warnings=warning_rows,
        grouped_count=len(grouped),
        lang=lang,
    )
    grouped_html = _render_grouped(grouped, lang)
    user_grouped_html = _render_user_grouped(user_grouped, lang)
    timeline_html = _render_timeline(activities, lang)
    warnings_html = _render_warnings(warning_rows, lang)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    html = f"""<!doctype html>
<html lang=\"{escape(lang)}\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{escape(text['title'])}</title>
  <style>
    :root {{
      --bg-top: #dce8ff;
      --bg: #f5f7fb;
      --paper: #ffffff;
      --ink: #14213d;
      --muted: #5c677d;
      --line: #dbe3f0;
      --accent: #0d5bd1;
      --accent-soft: #ebf3ff;
      --danger: #b42318;
      --danger-line: #fecaca;
      --danger-bg: #fff1f2;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Noto Sans", "PingFang SC", sans-serif;
      line-height: 1.5;
      background: radial-gradient(circle at 16% 10%, var(--bg-top) 0%, var(--bg) 58%);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 16px 96px;
    }}
    .card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px;
      margin-bottom: 16px;
      box-shadow: 0 6px 20px rgba(20, 33, 61, 0.08);
    }}
    h1, h2, h3 {{
      margin-top: 0;
      margin-bottom: 10px;
      line-height: 1.25;
    }}
    .meta {{ color: var(--muted); }}
    .summary-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
      gap: 14px;
      margin-top: 14px;
    }}
    .summary-meta {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      background: #ffffff;
    }}
    .summary-stats {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      background: var(--accent-soft);
    }}
    .kv-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 14px;
    }}
    .kv-row {{
      border-bottom: 1px dashed var(--line);
      padding-bottom: 6px;
    }}
    .kv-key {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 2px;
    }}
    .kv-value {{
      display: block;
      font-weight: 600;
      word-break: break-word;
    }}
    .stat-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      height: 100%;
    }}
    .stat-card {{
      background: #ffffff;
      border: 1px solid #cfe0ff;
      border-radius: 10px;
      padding: 10px;
      min-height: 82px;
    }}
    .stat-label {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .stat-value {{
      margin: 4px 0 0;
      font-size: 24px;
      font-weight: 700;
      color: var(--accent);
    }}
    .section-head {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }}
    .section-right {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }}
    .collapsible {{
      overflow: hidden;
    }}
    .collapsible > summary {{
      cursor: pointer;
      list-style: none;
    }}
    .collapsible > summary::-webkit-details-marker {{
      display: none;
    }}
    .collapsible > summary h2 {{
      margin: 0;
    }}
    .collapsible-content {{
      margin-top: 10px;
    }}
    .toggle-hint {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .toggle-icon {{
      display: inline-block;
      transition: transform 0.15s ease;
    }}
    details[open] > summary .toggle-icon {{
      transform: rotate(90deg);
    }}
    .item-collapsible {{
      overflow: hidden;
    }}
    .item-collapsible > summary {{
      cursor: pointer;
      list-style: none;
    }}
    .item-collapsible > summary::-webkit-details-marker {{
      display: none;
    }}
    .item-summary {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
    }}
    .item-summary-left {{
      min-width: 0;
      flex: 1;
    }}
    .item-summary-left h3 {{
      margin: 0;
      word-break: break-word;
    }}
    .item-summary-left .meta {{
      margin: 6px 0 0;
      word-break: break-word;
    }}
    .item-content {{
      margin-top: 10px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      border: 1px solid #c9d8f6;
      padding: 2px 10px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .empty {{
      color: var(--muted);
      margin: 8px 0 2px;
    }}
    .group-card {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 12px;
      background: #fffdfa;
    }}
    .user-card {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 12px;
      background: #f7fbff;
    }}
    .group-original {{
      margin: 0 0 12px;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .inline-label {{
      color: var(--muted);
      font-size: 12px;
      margin-right: 6px;
    }}
    .action-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 8px;
    }}
    .action-item {{
      display: block;
      border: 1px dashed var(--line);
      border-radius: 10px;
      padding: 8px;
      background: #ffffff;
    }}
    .action-head {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px 10px;
    }}
    .action-meta {{
      color: var(--muted);
      flex: 1;
      min-width: 220px;
      word-break: break-word;
    }}
    .action-head a {{
      margin-left: auto;
    }}
    .action-text {{
      margin: 6px 0 0;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .action-extra {{
      margin: 6px 0 0;
      color: var(--muted);
      word-break: break-word;
    }}
    .activity-tag {{
      display: inline-flex;
      align-items: center;
      font-size: 12px;
      border-radius: 999px;
      padding: 2px 8px;
      border: 1px solid var(--line);
      background: #ffffff;
      color: var(--ink);
      font-weight: 600;
      text-transform: capitalize;
    }}
    .activity-retweet {{
      border-color: #cbe9d4;
      background: #f0fbf3;
      color: #166534;
    }}
    .activity-quote {{
      border-color: #cde2ff;
      background: #f1f6ff;
      color: #1e40af;
    }}
    .activity-reply {{
      border-color: #ffe0b2;
      background: #fff7ed;
      color: #9a3412;
    }}
    .activity-tweet {{
      border-color: #d8d8df;
      background: #f8f9fc;
      color: #374151;
    }}
    .timeline {{
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 10px;
    }}
    .timeline-item {{
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #ffffff;
    }}
    .timeline-card {{
      padding: 12px;
    }}
    .timeline-head {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin: 0;
    }}
    .timeline-meta {{
      color: var(--muted);
      word-break: break-word;
    }}
    .timeline-text {{
      margin: 8px 0 8px;
      word-break: break-word;
      white-space: pre-wrap;
    }}
    .timeline-extra {{
      margin: 0 0 8px;
      color: var(--muted);
    }}
    .timeline-original-text {{
      margin: 0 0 8px;
      color: var(--muted);
      word-break: break-word;
      white-space: pre-wrap;
    }}
    .timeline-link {{
      margin: 0;
    }}
    .warning-card {{
      border: 1px solid var(--danger-line);
      background: var(--danger-bg);
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 12px;
    }}
    .warning-title {{
      color: var(--danger);
      margin-bottom: 8px;
    }}
    .warning-line {{
      color: var(--danger);
      margin: 6px 0;
    }}
    .warning-raw {{
      color: var(--danger);
      white-space: pre-wrap;
      background: #ffffff;
      border: 1px dashed var(--danger-line);
      border-radius: 8px;
      padding: 8px;
      margin: 6px 0 0;
      word-break: break-word;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    .jump {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }}
    .jump a {{
      display: inline-flex;
      border-radius: 999px;
      border: 1px solid #c9d8f6;
      background: #ffffff;
      padding: 5px 12px;
      font-size: 13px;
      color: var(--accent);
    }}
    @media (max-width: 900px) {{
      .summary-grid {{
        grid-template-columns: 1fr;
      }}
    }}
    @media (max-width: 720px) {{
      .kv-grid {{
        grid-template-columns: 1fr;
      }}
      .stat-grid {{
        grid-template-columns: 1fr 1fr;
      }}
      .stat-value {{
        font-size: 22px;
      }}
    }}
    @media (max-width: 520px) {{
      .wrap {{
        padding: 18px 12px 72px;
      }}
      .card {{
        padding: 14px;
      }}
      .stat-grid {{
        grid-template-columns: 1fr;
      }}
      .jump a {{
        width: 100%;
        justify-content: center;
      }}
    }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <section class=\"card\">
      <h1>{escape(text['title'])}</h1>
      <p class=\"meta\">{escape(text['generated'])}: {escape(generated_at)}</p>
      {summary_html}
      <p class=\"jump\">
        <a href=\"#warnings\">{escape(text['jump_warnings'])}</a>
        <a href=\"#grouped\">{escape(text['jump_grouped'])}</a>
        <a href=\"#user-grouped\">{escape(text['jump_user_grouped'])}</a>
        <a href=\"#timeline\">{escape(text['jump_timeline'])}</a>
      </p>
    </section>

    <details id=\"warnings\" class=\"card collapsible\">
      <summary class=\"section-head\">
        <h2>{escape(text['warnings'])}</h2>
        <span class=\"section-right\">
          <span class=\"pill\">{escape(str(len(warning_rows)))}</span>
          <span class=\"toggle-hint\"><span class=\"toggle-icon\">▸</span>{escape(text['toggle_hint'])}</span>
        </span>
      </summary>
      <div class=\"collapsible-content\">
        {warnings_html}
      </div>
    </details>

    <details id=\"grouped\" class=\"card collapsible\">
      <summary class=\"section-head\">
        <h2>{escape(text['grouped'])}</h2>
        <span class=\"section-right\">
          <span class=\"pill\">{escape(str(len(grouped)))}</span>
          <span class=\"toggle-hint\"><span class=\"toggle-icon\">▸</span>{escape(text['toggle_hint'])}</span>
        </span>
      </summary>
      <div class=\"collapsible-content\">
        {grouped_html}
      </div>
    </details>

    <details id=\"user-grouped\" class=\"card collapsible\">
      <summary class=\"section-head\">
        <h2>{escape(text['user_grouped'])}</h2>
        <span class=\"section-right\">
          <span class=\"pill\">{escape(str(len(user_grouped)))}</span>
          <span class=\"toggle-hint\"><span class=\"toggle-icon\">▸</span>{escape(text['toggle_hint'])}</span>
        </span>
      </summary>
      <div class=\"collapsible-content\">
        {user_grouped_html}
      </div>
    </details>

    <details id=\"timeline\" class=\"card collapsible\">
      <summary class=\"section-head\">
        <h2>{escape(text['timeline'])}</h2>
        <span class=\"section-right\">
          <span class=\"pill\">{escape(str(len(activities)))}</span>
          <span class=\"toggle-hint\"><span class=\"toggle-icon\">▸</span>{escape(text['toggle_hint'])}</span>
        </span>
      </summary>
      <div class=\"collapsible-content\">
        {timeline_html}
      </div>
    </details>
  </div>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
