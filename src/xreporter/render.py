from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


REPORT_TEXT = {
    "en": {
        "title": "XReporter Activity Report",
        "summary": "Run Summary",
        "grouped": "Grouped Retweets / Quotes / Replies",
        "timeline": "Chronological Full Activity",
        "jump_grouped": "Jump to grouped section",
        "jump_timeline": "Jump to timeline section",
        "no_grouped": "No grouped retweet/quote/reply records in this run.",
        "generated": "Generated at",
        "actions": "actions",
    },
    "zh": {
        "title": "XReporter 活动报告",
        "summary": "运行摘要",
        "grouped": "按原帖聚合（转发 / 引用 / 回复）",
        "timeline": "完整活动时间线",
        "jump_grouped": "跳转到聚合区",
        "jump_timeline": "跳转到时间线",
        "no_grouped": "本次运行没有可聚合的转发/引用/回复记录。",
        "generated": "生成时间",
        "actions": "条动作",
    },
}


@dataclass
class GroupedOriginal:
    original_tweet_id: str
    original_url: str
    original_text: str
    original_author_username: str | None
    actions: list[dict[str, Any]]


def _fmt_dt(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S UTC")
    except ValueError:
        return value


def _render_grouped(groups: list[GroupedOriginal], lang: str) -> str:
    text = REPORT_TEXT.get(lang, REPORT_TEXT["en"])
    if not groups:
        return f"<p>{escape(text['no_grouped'])}</p>"

    blocks: list[str] = []
    for group in groups:
        author = group.original_author_username or "unknown"
        blocks.append(
            """
            <section class="group-card">
              <h3><a href="{url}" target="_blank" rel="noopener">{tweet_id}</a></h3>
              <p class="meta">@{author} · {count} {actions}</p>
              <p>{text}</p>
              <ul>
                {actions_html}
              </ul>
            </section>
            """.format(
                url=escape(group.original_url),
                tweet_id=escape(group.original_tweet_id),
                author=escape(author),
                count=len(group.actions),
                actions=escape(text["actions"]),
                text=escape(group.original_text or ""),
                actions_html="\n".join(
                    (
                        "<li>"
                        f"<strong>{escape(action.get('activity_type', ''))}</strong> "
                        f"by @{escape(action.get('actor_username') or '')} "
                        f"at {escape(_fmt_dt(action.get('event_created_at')))} "
                        f"<a href='{escape(action.get('event_url') or '#')}' target='_blank' rel='noopener'>open</a>"
                        "</li>"
                    )
                    for action in group.actions
                ),
            )
        )

    return "\n".join(blocks)


def _render_timeline(activities: list[dict[str, Any]]) -> str:
    lines: list[str] = ["<ul class='timeline'>"]
    for item in activities:
        lines.append(
            "<li>"
            f"<div><strong>{escape(item.get('activity_type', ''))}</strong> "
            f"@{escape(item.get('actor_username') or '')} · {escape(_fmt_dt(item.get('event_created_at')))}</div>"
            f"<div>{escape(item.get('event_text') or '')}</div>"
            f"<div><a href='{escape(item.get('event_url') or '#')}' target='_blank' rel='noopener'>"
            "open post</a></div>"
            "</li>"
        )
    lines.append("</ul>")
    return "\n".join(lines)


def render_report(
    *,
    run: dict[str, Any],
    activities: list[dict[str, Any]],
    output_path: Path,
    lang: str,
) -> Path:
    text = REPORT_TEXT.get(lang, REPORT_TEXT["en"])

    grouped_map: dict[str, GroupedOriginal] = {}
    for item in activities:
        activity_type = item.get("activity_type")
        original_id = item.get("original_tweet_id")
        if activity_type not in {"retweet", "quote", "reply"} or not original_id:
            continue

        if original_id not in grouped_map:
            grouped_map[original_id] = GroupedOriginal(
                original_tweet_id=original_id,
                original_url=item.get("original_url") or f"https://x.com/i/web/status/{original_id}",
                original_text=item.get("original_text") or "",
                original_author_username=item.get("original_author_username"),
                actions=[],
            )
        grouped_map[original_id].actions.append(item)

    grouped = sorted(
        grouped_map.values(),
        key=lambda g: max((a.get("event_created_at") or "" for a in g.actions), default=""),
        reverse=True,
    )

    grouped_html = _render_grouped(grouped, lang)
    timeline_html = _render_timeline(activities)

    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    html = f"""<!doctype html>
<html lang=\"{escape(lang)}\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{escape(text['title'])}</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --paper: #ffffff;
      --ink: #14213d;
      --muted: #5c677d;
      --line: #dbe3f0;
      --accent: #ff7f11;
    }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Noto Sans", "PingFang SC", sans-serif;
      background: radial-gradient(circle at 20% 10%, #d6e4ff 0%, #f5f7fb 55%);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 28px 16px 40px;
    }}
    .card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 16px;
      box-shadow: 0 6px 20px rgba(20, 33, 61, 0.08);
    }}
    h1, h2, h3 {{ margin-top: 0; }}
    .meta {{ color: var(--muted); }}
    .group-card {{
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 12px;
      background: #fffdfa;
    }}
    .timeline {{ list-style: none; padding: 0; margin: 0; }}
    .timeline li {{
      border-bottom: 1px dashed var(--line);
      padding: 12px 0;
    }}
    a {{ color: #0d5bd1; }}
    .jump a {{ margin-right: 14px; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <section class=\"card\">
      <h1>{escape(text['title'])}</h1>
      <p class=\"meta\">{escape(text['generated'])}: {escape(generated_at)}</p>
      <h2>{escape(text['summary'])}</h2>
      <p>@{escape(run.get('username', ''))} | run_id={escape(str(run.get('id', '')))}</p>
      <p>{escape(run.get('since_utc', ''))} ~ {escape(run.get('until_utc', ''))}</p>
      <p class=\"jump\">
        <a href=\"#grouped\">{escape(text['jump_grouped'])}</a>
        <a href=\"#timeline\">{escape(text['jump_timeline'])}</a>
      </p>
    </section>

    <section id=\"grouped\" class=\"card\">
      <h2>{escape(text['grouped'])}</h2>
      {grouped_html}
    </section>

    <section id=\"timeline\" class=\"card\">
      <h2>{escape(text['timeline'])}</h2>
      {timeline_html}
    </section>
  </div>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path
