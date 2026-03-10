from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from xreporter.config import (
    AppConfig,
    config_exists,
    default_config_path,
    default_db_path,
    default_report_dir,
    load_config,
    save_config,
)
from xreporter.i18n import resolve_language, tr
from xreporter.render import render_report
from xreporter.service import CollectorService
from xreporter.storage import SQLiteStorage
from xreporter.time_range import TimeRangeError, parse_time_range
from xreporter.x_api import FixtureXApiClient, XApiClient, XApiError


app = typer.Typer(help="XReporter CLI")
config_app = typer.Typer(help="Manage XReporter config")
app.add_typer(config_app, name="config")
console = Console()


def _load_config_or_exit() -> AppConfig:
    cfg_path = default_config_path()
    try:
        return load_config()
    except Exception as exc:  # noqa: BLE001
        raise typer.BadParameter(f"Failed to load config ({cfg_path}): {exc}") from exc


def _effective_lang(cfg: AppConfig) -> str:
    return resolve_language(cfg.language)


def _build_api_client() -> object:
    fixture_path = os.getenv("XREPORTER_FIXTURE_FILE")
    if fixture_path:
        return FixtureXApiClient(Path(fixture_path))

    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        raise typer.BadParameter("X_BEARER_TOKEN is required. Set env var or XREPORTER_FIXTURE_FILE.")
    return XApiClient(token=token)


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
    db_path: Path | None = typer.Option(None, "--db-path"),
    report_dir: Path | None = typer.Option(None, "--report-dir"),
    following_cap: int = typer.Option(200, "--following-cap"),
    include_replies: bool = typer.Option(True, "--include-replies/--no-include-replies"),
) -> None:
    if lang not in {"auto", "en", "zh"}:
        raise typer.BadParameter("--lang must be one of auto|en|zh")
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
    )
    path = save_config(cfg)
    language = resolve_language(lang)
    console.print(tr(language, "config_saved", path=path))


@config_app.command("show")
def config_show() -> None:
    cfg = _load_config_or_exit()
    language = _effective_lang(cfg)
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
) -> None:
    cfg = _load_config_or_exit()
    language = _effective_lang(cfg)

    selected_username = username or cfg.username
    selected_following_cap = following_cap if following_cap is not None else cfg.following_cap_default
    if selected_following_cap <= 0:
        raise typer.BadParameter("--following-cap must be > 0")

    selected_include_replies = include_replies if include_replies is not None else cfg.include_replies_default

    try:
        time_range = parse_time_range(last=last, since=since, until=until)
    except TimeRangeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    console.print(tr(language, "collect_start"))

    with SQLiteStorage(Path(cfg.db_path)) as storage:
        storage.init_schema()

        api_client = _build_api_client()
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
                    time_range=time_range,
                    following_cap=selected_following_cap,
                    include_replies=selected_include_replies,
                    progress=progress,
                    labels=labels,
                )
        except (XApiError, Exception) as exc:  # noqa: BLE001
            console.print(tr(language, "error", message=str(exc)))
            raise typer.Exit(code=1) from exc
        finally:
            close = getattr(api_client, "close", None)
            if callable(close):
                close()

    console.print(tr(language, "collect_success", run_id=result.run_id, activities=result.total_activities))


@app.command("render")
def render(
    run_id: Optional[int] = typer.Option(None, "--run-id"),
    latest: bool = typer.Option(False, "--latest"),
    output: Optional[Path] = typer.Option(None, "--output"),
) -> None:
    cfg = _load_config_or_exit()
    language = _effective_lang(cfg)

    with SQLiteStorage(Path(cfg.db_path)) as storage:
        storage.init_schema()

        selected_run_id = run_id
        if selected_run_id is None:
            if latest or run_id is None:
                selected_run_id = storage.get_latest_run_id()
        if selected_run_id is None:
            console.print(tr(language, "error", message="No available run to render."))
            raise typer.Exit(code=1)

        run = storage.get_run(selected_run_id)
        if not run:
            console.print(tr(language, "error", message=f"Run not found: {selected_run_id}"))
            raise typer.Exit(code=1)

        activities = storage.get_activities_for_run(selected_run_id)
        default_output = Path(cfg.report_dir) / f"run_{selected_run_id}.html"
        output_path = output or default_output

        with _progress() as progress:
            task = progress.add_task(tr(language, "progress_render"), total=1)
            result_path = render_report(run=run, activities=activities, output_path=output_path, lang=language)
            progress.advance(task)

    console.print(tr(language, "render_success", path=result_path))


@app.command("doctor")
def doctor() -> None:
    cfg_ok = config_exists()
    cfg = None
    lang = "en"

    if cfg_ok:
        try:
            cfg = load_config()
            lang = _effective_lang(cfg)
        except Exception:
            cfg_ok = False

    token_ok = bool(os.getenv("X_BEARER_TOKEN"))
    fixture_mode = bool(os.getenv("XREPORTER_FIXTURE_FILE"))

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
        tr(lang, "doctor_token"),
        tr(lang, "doctor_ok") if token_ok or fixture_mode else tr(lang, "doctor_fail"),
        "set" if token_ok else "not set",
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

    if not cfg_ok or (not token_ok and not fixture_mode) or not db_ok:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
