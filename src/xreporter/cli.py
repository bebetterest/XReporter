from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Optional, cast

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from xreporter.config import (
    APIProvider,
    AppConfig,
    config_exists,
    default_config_path,
    default_db_path,
    default_home_dir,
    default_report_dir,
    load_config,
    save_config,
)
from xreporter.i18n import resolve_language, tr
from xreporter.logging_utils import get_logger, setup_logging
from xreporter.render import render_report
from xreporter.service import CollectorService
from xreporter.storage import SQLiteStorage
from xreporter.time_range import TimeRangeError, parse_time_range
from xreporter.x_api import (
    FixtureXApiClient,
    SocialDataApiClient,
    XApiClient,
    XApiError,
)


app = typer.Typer(help="XReporter CLI")
config_app = typer.Typer(help="Manage XReporter config")
app.add_typer(config_app, name="config")
console = Console()


def _setup_runtime_logging() -> None:
    log_path = setup_logging(default_home_dir() / "logs")
    get_logger("cli").debug("runtime logging ready log_path=%s", log_path)


def _load_config_or_exit() -> AppConfig:
    _setup_runtime_logging()
    cfg_path = default_config_path()
    try:
        return load_config()
    except Exception as exc:  # noqa: BLE001
        get_logger("cli.config").exception("failed to load config path=%s", cfg_path)
        raise typer.BadParameter(f"Failed to load config ({cfg_path}): {exc}") from exc


def _effective_lang(cfg: AppConfig) -> str:
    return resolve_language(cfg.language)


def _emit_retry_notice(message: str) -> None:
    console.print(message, markup=False)


def _build_api_client(
    cfg: AppConfig,
    *,
    retry_printer: Callable[[str], None] | None = None,
) -> tuple[str, object]:
    fixture_path = os.getenv("XREPORTER_FIXTURE_FILE")
    if fixture_path:
        return "fixture", FixtureXApiClient(Path(fixture_path))

    if cfg.api_provider == "official":
        token = os.getenv("X_BEARER_TOKEN")
        if not token:
            raise typer.BadParameter("X_BEARER_TOKEN is required for provider=official.")
        return "official", XApiClient(token=token, retry_callback=retry_printer)

    if cfg.api_provider == "socialdata":
        token = os.getenv("SOCIALDATA_API_KEY")
        if not token:
            raise typer.BadParameter("SOCIALDATA_API_KEY is required for provider=socialdata.")
        return "socialdata", SocialDataApiClient(token=token, retry_callback=retry_printer)

    raise typer.BadParameter(f"Unsupported api_provider: {cfg.api_provider}")


def _provider_credential_status(
    provider: str,
    fixture_mode: bool,
) -> tuple[bool, str]:
    if fixture_mode:
        return True, "fixture override"

    if provider == "official":
        token_ok = bool(os.getenv("X_BEARER_TOKEN"))
        return token_ok, f"X_BEARER_TOKEN: {'set' if token_ok else 'not set'}"

    if provider == "socialdata":
        token_ok = bool(os.getenv("SOCIALDATA_API_KEY"))
        return token_ok, f"SOCIALDATA_API_KEY: {'set' if token_ok else 'not set'}"

    return False, f"unknown provider: {provider}"


def _progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    )


@config_app.command("init")
def config_init(
    username: str = typer.Option(..., "--username"),
    lang: str = typer.Option("auto", "--lang"),
    api_provider: str = typer.Option("official", "--api-provider"),
    db_path: Path | None = typer.Option(None, "--db-path"),
    report_dir: Path | None = typer.Option(None, "--report-dir"),
    following_cap: int = typer.Option(200, "--following-cap"),
    include_replies: bool = typer.Option(True, "--include-replies/--no-include-replies"),
) -> None:
    _setup_runtime_logging()
    logger = get_logger("cli.config")

    if lang not in {"auto", "en", "zh"}:
        raise typer.BadParameter("--lang must be one of auto|en|zh")
    if api_provider not in {"official", "socialdata"}:
        raise typer.BadParameter("--api-provider must be one of official|socialdata")
    if following_cap <= 0:
        raise typer.BadParameter("--following-cap must be > 0")

    selected_db_path = db_path or default_db_path()
    selected_report_dir = report_dir or default_report_dir()

    cfg = AppConfig(
        username=username,
        language=lang,
        db_path=str(selected_db_path),
        report_dir=str(selected_report_dir),
        following_cap_default=following_cap,
        include_replies_default=include_replies,
        api_provider=cast(APIProvider, api_provider),
    )
    path = save_config(cfg)
    logger.info(
        "config saved path=%s username=%s lang=%s api_provider=%s db_path=%s report_dir=%s "
        "following_cap=%d include_replies=%s",
        path,
        username,
        lang,
        api_provider,
        selected_db_path,
        selected_report_dir,
        following_cap,
        include_replies,
    )
    language = resolve_language(lang)
    console.print(tr(language, "config_saved", path=path))


@config_app.command("show")
def config_show() -> None:
    _setup_runtime_logging()
    logger = get_logger("cli.config")
    cfg = _load_config_or_exit()
    language = _effective_lang(cfg)
    logger.info("config show path=%s", default_config_path())
    console.print(tr(language, "config_loaded", path=default_config_path()))
    console.print_json(json.dumps(cfg.__dict__, ensure_ascii=False, indent=2))


@app.command("collect")
def collect(
    username: Optional[str] = typer.Option(None, "--username"),
    last: Optional[str] = typer.Option(None, "--last"),
    since: Optional[str] = typer.Option(None, "--since"),
    until: Optional[str] = typer.Option(None, "--until"),
    following_cap: Optional[int] = typer.Option(None, "--following-cap"),
    include_replies: Optional[bool] = typer.Option(None, "--include-replies/--no-include-replies"),
    api_concurrency: int = typer.Option(4, "--api-concurrency"),
    resume_run_id: Optional[int] = typer.Option(None, "--resume-run-id"),
) -> None:
    _setup_runtime_logging()
    logger = get_logger("cli.collect")
    cfg = _load_config_or_exit()
    language = _effective_lang(cfg)

    selected_username = username or cfg.username
    selected_following_cap = following_cap if following_cap is not None else cfg.following_cap_default
    if selected_following_cap <= 0:
        raise typer.BadParameter("--following-cap must be > 0")
    if api_concurrency <= 0:
        raise typer.BadParameter("--api-concurrency must be > 0")

    selected_include_replies = include_replies if include_replies is not None else cfg.include_replies_default

    try:
        time_range = parse_time_range(last=last, since=since, until=until)
    except TimeRangeError as exc:
        logger.exception(
            "collect invalid time range username=%s last=%s since=%s until=%s",
            selected_username,
            last,
            since,
            until,
        )
        raise typer.BadParameter(str(exc)) from exc

    logger.info(
        "collect start username=%s api_provider=%s since=%s until=%s following_cap=%d include_replies=%s "
        "api_concurrency=%d resume_run_id=%s",
        selected_username,
        cfg.api_provider,
        time_range.since.isoformat(),
        time_range.until.isoformat(),
        selected_following_cap,
        selected_include_replies,
        api_concurrency,
        resume_run_id,
    )
    console.print(tr(language, "collect_start"))

    with SQLiteStorage(Path(cfg.db_path)) as storage:
        storage.init_schema()

        effective_provider, api_client = _build_api_client(cfg, retry_printer=_emit_retry_notice)
        labels = {
            "resolve": tr(language, "progress_resolve"),
            "followings": tr(language, "progress_followings"),
            "timelines": tr(language, "progress_timelines"),
        }

        try:
            service = CollectorService(storage=storage, api_client=api_client)
            with _progress() as progress:
                result = service.collect_with_error_handling(
                    username=selected_username,
                    api_provider=effective_provider,
                    time_range=time_range,
                    following_cap=selected_following_cap,
                    include_replies=selected_include_replies,
                    api_concurrency=api_concurrency,
                    resume_run_id=resume_run_id,
                    progress=progress,
                    labels=labels,
                )
        except KeyboardInterrupt as exc:
            logger.warning("collect interrupted username=%s api_provider=%s", selected_username, effective_provider)
            console.print(tr(language, "error", message="Collection interrupted by user."))
            raise typer.Exit(code=130) from exc
        except (XApiError, Exception) as exc:  # noqa: BLE001
            logger.exception("collect failed username=%s api_provider=%s", selected_username, effective_provider)
            console.print(tr(language, "error", message=str(exc)))
            raise typer.Exit(code=1) from exc
        finally:
            close = getattr(api_client, "close", None)
            if callable(close):
                close()

    logger.info(
        "collect success run_id=%d activities=%d warnings=%d username=%s provider=%s",
        result.run_id,
        result.total_activities,
        result.total_warnings,
        selected_username,
        effective_provider,
    )
    console.print(tr(language, "collect_success", run_id=result.run_id, activities=result.total_activities))
    if result.total_warnings > 0:
        logger.warning("collect finished with warnings run_id=%d warning_count=%d", result.run_id, result.total_warnings)
        console.print(tr(language, "collect_warnings", warnings=result.total_warnings))


@app.command("render")
def render(
    run_id: Optional[int] = typer.Option(None, "--run-id"),
    latest: bool = typer.Option(False, "--latest"),
    output: Optional[Path] = typer.Option(None, "--output"),
) -> None:
    _setup_runtime_logging()
    logger = get_logger("cli.render")
    cfg = _load_config_or_exit()
    language = _effective_lang(cfg)

    with SQLiteStorage(Path(cfg.db_path)) as storage:
        storage.init_schema()

        selected_run_id = run_id
        if selected_run_id is None:
            if latest or run_id is None:
                selected_run_id = storage.get_latest_run_id()
        if selected_run_id is None:
            logger.error("render failed: no run available latest=%s requested_run_id=%s", latest, run_id)
            console.print(tr(language, "error", message="No available run to render."))
            raise typer.Exit(code=1)

        run = storage.get_run(selected_run_id)
        if not run:
            logger.error("render failed: run not found run_id=%s", selected_run_id)
            console.print(tr(language, "error", message=f"Run not found: {selected_run_id}"))
            raise typer.Exit(code=1)

        activities = storage.get_activities_for_run(selected_run_id)
        warnings = storage.get_warnings_for_run(selected_run_id)
        default_output = Path(cfg.report_dir) / f"run_{selected_run_id}.html"
        output_path = output or default_output

        with _progress() as progress:
            task = progress.add_task(tr(language, "progress_render"), total=1)
            result_path = render_report(
                run=run,
                activities=activities,
                warnings=warnings,
                output_path=output_path,
                lang=language,
            )
            progress.advance(task)

    logger.info(
        "render success run_id=%d output=%s activities=%d warnings=%d",
        selected_run_id,
        result_path,
        len(activities),
        len(warnings),
    )
    console.print(tr(language, "render_success", path=result_path))


@app.command("doctor")
def doctor() -> None:
    _setup_runtime_logging()
    logger = get_logger("cli.doctor")
    cfg_ok = config_exists()
    cfg = None
    lang = "en"

    if cfg_ok:
        try:
            cfg = load_config()
            lang = _effective_lang(cfg)
        except Exception:
            cfg_ok = False

    fixture_mode = bool(os.getenv("XREPORTER_FIXTURE_FILE"))
    provider = cfg.api_provider if cfg else "official"
    credential_ok, credential_detail = _provider_credential_status(
        provider,
        fixture_mode,
    )

    db_ok = False
    db_message = ""
    if cfg:
        try:
            with SQLiteStorage(Path(cfg.db_path)) as storage:
                storage.init_schema()
            db_ok = True
        except Exception as exc:  # noqa: BLE001
            db_message = str(exc)

    table = Table(title=tr(lang, "doctor_title"))
    table.add_column("Item")
    table.add_column("Status")
    table.add_column("Details")

    table.add_row(
        tr(lang, "doctor_config"),
        tr(lang, "doctor_ok") if cfg_ok else tr(lang, "doctor_fail"),
        str(default_config_path()),
    )

    table.add_row(
        tr(lang, "doctor_provider"),
        tr(lang, "doctor_ok") if cfg_ok else tr(lang, "doctor_fail"),
        provider if cfg_ok else "unknown",
    )

    table.add_row(
        tr(lang, "doctor_credentials"),
        tr(lang, "doctor_ok") if credential_ok else tr(lang, "doctor_fail"),
        credential_detail,
    )

    table.add_row(
        tr(lang, "doctor_fixture"),
        tr(lang, "doctor_ok") if fixture_mode else tr(lang, "doctor_fail"),
        os.getenv("XREPORTER_FIXTURE_FILE", "disabled"),
    )

    table.add_row(
        tr(lang, "doctor_db"),
        tr(lang, "doctor_ok") if db_ok else tr(lang, "doctor_fail"),
        cfg.db_path if cfg else db_message,
    )

    console.print(table)
    logger.info(
        "doctor result config_ok=%s provider=%s credential_ok=%s fixture_mode=%s db_ok=%s",
        cfg_ok,
        provider if cfg_ok else "unknown",
        credential_ok,
        fixture_mode,
        db_ok,
    )

    if not cfg_ok or not credential_ok or not db_ok:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
