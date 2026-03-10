from __future__ import annotations

import locale


MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "config_saved": "Config saved to {path}",
        "config_loaded": "Config loaded from {path}",
        "collect_start": "Starting collection",
        "collect_success": "Collection completed. run_id={run_id}, activities={activities}",
        "collect_warnings": "Collection completed with {warnings} warning(s). See report for details.",
        "render_success": "Report generated at {path}",
        "doctor_title": "Health Check",
        "doctor_ok": "OK",
        "doctor_fail": "FAIL",
        "doctor_config": "Config",
        "doctor_provider": "API Provider",
        "doctor_credentials": "Credentials",
        "doctor_db": "SQLite",
        "doctor_fixture": "Fixture Mode",
        "error": "Error: {message}",
        "progress_resolve": "Resolve target user",
        "progress_followings": "Fetch followings",
        "progress_timelines": "Fetch timelines",
        "progress_render": "Render HTML",
    },
    "zh": {
        "config_saved": "配置已保存到 {path}",
        "config_loaded": "已从 {path} 加载配置",
        "collect_start": "开始采集",
        "collect_success": "采集完成。run_id={run_id}，活动数={activities}",
        "collect_warnings": "采集完成，包含 {warnings} 条告警。详情请查看报告。",
        "render_success": "报告已生成：{path}",
        "doctor_title": "健康检查",
        "doctor_ok": "正常",
        "doctor_fail": "失败",
        "doctor_config": "配置",
        "doctor_provider": "API 来源",
        "doctor_credentials": "凭据",
        "doctor_db": "SQLite",
        "doctor_fixture": "固定数据模式",
        "error": "错误：{message}",
        "progress_resolve": "解析目标用户",
        "progress_followings": "拉取关注列表",
        "progress_timelines": "拉取时间线",
        "progress_render": "渲染 HTML",
    },
}


def resolve_language(preference: str, locale_name: str | None = None) -> str:
    if preference in {"en", "zh"}:
        return preference

    if preference != "auto":
        return "en"

    if locale_name is None:
        detected = locale.getlocale()[0] or locale.getdefaultlocale()[0]  # type: ignore[index]
    else:
        detected = locale_name

    if not detected:
        return "en"

    detected = detected.lower()
    if detected.startswith("zh"):
        return "zh"
    if detected.startswith("en"):
        return "en"
    return "en"


def tr(lang: str, key: str, **kwargs: object) -> str:
    table = MESSAGES.get(lang, MESSAGES["en"])
    template = table.get(key, MESSAGES["en"].get(key, key))
    return template.format(**kwargs)
