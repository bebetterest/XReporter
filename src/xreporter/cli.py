from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, cast

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
    default_report_dir,
    default_twscrape_accounts_db_path,
    load_config,
    save_config,
)
from xreporter.i18n import resolve_language, tr
from xreporter.render import render_report
from xreporter.service import CollectorService
from xreporter.storage import SQLiteStorage
from xreporter.time_range import TimeRangeError, parse_time_range
from xreporter.x_api import (
    FixtureXApiClient,
    SocialDataApiClient,
    TwscrapeApiClient,
    XApiClient,
    XApiError,
    twscrape_accounts_db_has_account,
)


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


def _build_api_client(cfg: AppConfig) -> tuple[str, object]:
    fixture_path = os.getenv("XREPORTER_FIXTURE_FILE")
    if fixture_path:
        return "fixture", FixtureXApiClient(Path(fixture_path))

    if cfg.api_provider == "official":
        token = os.getenv("X_BEARER_TOKEN")
        if not token:
            raise typer.BadParameter("X_BEARER_TOKEN is required for provider=official.")
        return "official", XApiClient(token=token)

    if cfg.api_provider == "socialdata":
        token = os.getenv("SOCIALDATA_API_KEY")
        if not token:
            raise typer.BadParameter("SOCIALDATA_API_KEY is required for provider=socialdata.")
        return "socialdata", SocialDataApiClient(token=token)

    if cfg.api_provider == "twscrape":
        try:
            return "twscrape", TwscrapeApiClient(accounts_db_path=Path(cfg.twscrape_accounts_db_path))
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc

    raise typer.BadParameter(f"Unsupported api_provider: {cfg.api_provider}")


def _provider_credential_status(
    provider: str,
    fixture_mode: bool,
    *,
    twscrape_accounts_db_path: Path | None = None,
) -> tuple[bool, str]:
    if fixture_mode:
        return True, "fixture override"

    if provider == "official":
        token_ok = bool(os.getenv("X_BEARER_TOKEN"))
        return token_ok, f"X_BEARER_TOKEN: {'set' if token_ok else 'not set'}"

    if provider == "socialdata":
        token_ok = bool(os.getenv("SOCIALDATA_API_KEY"))
        return token_ok, f"SOCIALDATA_API_KEY: {'set' if token_ok else 'not set'}"

    if provider == "twscrape":
        required = {
            "XREPORTER_TWS_USERNAME": os.getenv("XREPORTER_TWS_USERNAME"),
            "XREPORTER_TWS_PASSWORD": os.getenv("XREPORTER_TWS_PASSWORD"),
            "XREPORTER_TWS_EMAIL": os.getenv("XREPORTER_TWS_EMAIL"),
            "XREPORTER_TWS_EMAIL_PASSWORD": os.getenv("XREPORTER_TWS_EMAIL_PASSWORD"),
        }
        missing = [name for name, value in required.items() if not value]
        if not missing:
            return True, "all twscrape credentials set"

        if twscrape_accounts_db_path and twscrape_accounts_db_has_account(twscrape_accounts_db_path):
            return True, f"existing account pool: {twscrape_accounts_db_path}"

        if missing:
            return False, f"missing: {', '.join(missing)}"

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
    api_provider: str = typer.Option("twscrape", "--api-provider"),
    db_path: Path | None = typer.Option(None, "--db-path"),
    report_dir: Path | None = typer.Option(None, "--report-dir"),
    twscrape_accounts_db_path: Path | None = typer.Option(None, "--twscrape-accounts-db-path"),
    following_cap: int = typer.Option(200, "--following-cap"),
    include_replies: bool = typer.Option(True, "--include-replies/--no-include-replies"),
) -> None:
    if lang not in {"auto", "en", "zh"}:
        raise typer.BadParameter("--lang must be one of auto|en|zh")
    if api_provider not in {"official", "twscrape", "socialdata"}:
        raise typer.BadParameter("--api-provider must be one of official|twscrape|socialdata")
    if following_cap <= 0:
        raise typer.BadParameter("--following-cap must be > 0")

    selected_db_path = db_path or default_db_path()
    selected_report_dir = report_dir or default_report_dir()
    selected_tws_accounts_db_path = twscrape_accounts_db_path or default_twscrape_accounts_db_path()

    cfg = AppConfig(
        username=username,
        language=lang,
        db_path=str(selected_db_path),
        report_dir=str(selected_report_dir),
        following_cap_default=following_cap,
        include_replies_default=include_replies,
        api_provider=cast(APIProvider, api_provider),
        twscrape_accounts_db_path=str(selected_tws_accounts_db_path),
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

        effective_provider, api_client = _build_api_client(cfg)
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
    if result.total_warnings > 0:
        console.print(tr(language, "collect_warnings", warnings=result.total_warnings))


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

    fixture_mode = bool(os.getenv("XREPORTER_FIXTURE_FILE"))
    provider = cfg.api_provider if cfg else "official"
    credential_ok, credential_detail = _provider_credential_status(
        provider,
        fixture_mode,
        twscrape_accounts_db_path=Path(cfg.twscrape_accounts_db_path) if cfg else None,
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

    if not cfg_ok or not credential_ok or not db_ok:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
