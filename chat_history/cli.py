from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import shutil
import sys
import threading
import time
import webbrowser
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any

import questionary
import uvicorn
from dotenv import dotenv_values, set_key, unset_key
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from chat_history import __version__ as PACKAGE_VERSION
from chat_history.config import load_settings
from chat_history.exporter import export_conversation
from chat_history.services import ChatHistoryService

PROVIDERS = ("chatgpt", "claude")
PROVIDER_LABELS = {"chatgpt": "ChatGPT", "claude": "Claude"}
CONSOLE = Console()
ENV_RELATIVE_PATH = Path("data") / ".env"


@dataclass(frozen=True)
class ValidationSummary:
    provider: str
    conversations: int
    first_date: str | None
    last_date: str | None


def _info(message: str) -> None:
    CONSOLE.print(message, style="bold white")


def _warn(message: str) -> None:
    CONSOLE.print(message, style="bold yellow")


def _error(message: str) -> None:
    CONSOLE.print(message, style="bold red")


def _success(message: str) -> None:
    CONSOLE.print(message, style="bold green")


def _section(title: str) -> None:
    CONSOLE.print(f"\n[bold cyan]{title}[/bold cyan]")


def _provider_env_key(provider: str) -> str:
    return f"CHAT_HISTORY_{provider.upper()}_PATH"


def _as_bool(raw_value: str | None, default: bool = False) -> bool:
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_path(raw_path: str, base_dir: Path) -> Path:
    expanded = Path(raw_path).expanduser()
    if expanded.is_absolute():
        return expanded
    return (base_dir / expanded).resolve()


@contextmanager
def _chdir(path: Path):
    old_cwd = Path.cwd()
    try:
        if path != old_cwd:
            path.mkdir(parents=True, exist_ok=True)
            os.chdir(path)
        yield
    finally:
        if Path.cwd() != old_cwd:
            os.chdir(old_cwd)


def _load_service(*, build_embeddings: bool = False) -> ChatHistoryService:
    with CONSOLE.status("[bold cyan]Loading conversations...", spinner="dots"):
        settings = load_settings()
        service = ChatHistoryService(settings)
        service.load(build_embeddings=build_embeddings)
    return service


def _current_version() -> str:
    try:
        return package_version("chat-history")
    except PackageNotFoundError:
        return PACKAGE_VERSION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chat history command line tool")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_current_version()}",
    )
    subcommands = parser.add_subparsers(dest="command")

    serve_parser = subcommands.add_parser("serve", help="Start web server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8080)
    serve_parser.add_argument("--no-browser", action="store_true")
    serve_parser.set_defaults(func=_run_serve_command)

    export_parser = subcommands.add_parser(
        "export", help="Export conversations to markdown files"
    )
    export_parser.add_argument(
        "--provider",
        choices=["chatgpt", "claude", "all"],
        default="all",
        help="Provider filter for exported conversations",
    )
    export_parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: CHAT_HISTORY_DATA_DIR/export)",
    )
    export_parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing exported files before writing new output (provider-scoped when --provider is set)",
    )
    export_parser.add_argument("--exclude-system", action="store_true")
    export_parser.add_argument("--exclude-tool", action="store_true")
    export_parser.add_argument("--exclude-thinking", action="store_true")
    export_parser.add_argument("--exclude-attachments", action="store_true")
    export_parser.set_defaults(func=_run_export_command)

    inspect_parser = subcommands.add_parser("inspect", help="Print loaded provider counts")
    inspect_parser.add_argument(
        "--provider",
        choices=["chatgpt", "claude", "all"],
        default="all",
        help="Provider filter",
    )
    inspect_parser.set_defaults(func=_run_inspect_command)

    init_parser = subcommands.add_parser("init", help="Interactive setup wizard")
    init_parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Target directory for data/.env and local data (default: current directory)",
    )
    init_parser.set_defaults(func=_run_init_command)

    install_parser = subcommands.add_parser(
        "install",
        help="Reinstall chat-history via uvx",
    )
    install_parser.set_defaults(func=_run_install_command)

    return parser


def _browser_host(host: str) -> str:
    return "127.0.0.1" if host in {"0.0.0.0", "::"} else host


def _wait_for_server(host: str, port: int, *, timeout_seconds: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _open_browser_when_ready(host: str, port: int) -> None:
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{browser_host}:{port}"

    def _worker() -> None:
        if _wait_for_server(browser_host, port):
            webbrowser.open(url)
        else:
            _warn(f"Server did not become ready in time, open manually: {url}")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _run_serve(*, host: str, port: int, no_browser: bool, cwd: Path) -> int:
    browser_host = _browser_host(host)
    if not no_browser:
        _info(f"Browser will open when ready at http://{browser_host}:{port}")
    with _chdir(cwd):
        if not no_browser:
            _open_browser_when_ready(host, port)
        _info(f"Starting server on http://{host}:{port}")
        uvicorn.run("chat_history.app:app", host=host, port=port)
    return 0


def _run_serve_command(args: argparse.Namespace) -> int:
    return _run_serve(
        host=args.host,
        port=args.port,
        no_browser=args.no_browser,
        cwd=Path.cwd(),
    )


def _cmd_export(service: ChatHistoryService, args: argparse.Namespace) -> int:
    output_dir = args.out or service.settings.export_dir
    provider_filter = args.provider

    if args.clean:
        removed_count = 0
        if output_dir.exists():
            for path in output_dir.rglob("*"):
                if not path.is_file():
                    continue
                if path.suffix not in {".md", ".txt"}:
                    continue
                if provider_filter == "all":
                    path.unlink()
                    removed_count += 1
                    continue

                provider_dir = output_dir / provider_filter
                is_provider_file = False
                if path.name.startswith(f"{provider_filter}--"):
                    is_provider_file = True
                elif provider_dir.exists() and path.is_relative_to(provider_dir):
                    is_provider_file = True
                if is_provider_file:
                    path.unlink()
                    removed_count += 1
            for dir_path in sorted(
                [path for path in output_dir.rglob("*") if path.is_dir()],
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
        _success(f"Removed {removed_count} existing export files from {output_dir}")

    conversations = service.conversations
    if provider_filter != "all":
        conversations = [
            conversation
            for conversation in conversations
            if conversation.provider == provider_filter
        ]

    if not conversations:
        _warn("No conversations matched the requested provider filter.")
        return 1

    exported_paths: list[Path] = []
    for conversation in conversations:
        exported_paths.append(
            export_conversation(
                conversation=conversation,
                output_dir=output_dir,
                include_system=not args.exclude_system,
                include_tool=not args.exclude_tool,
                include_thinking=not args.exclude_thinking,
                include_attachments=not args.exclude_attachments,
            )
        )

    _success(f"Exported {len(exported_paths)} conversations to {output_dir}")
    return 0


def _run_export_command(args: argparse.Namespace) -> int:
    service = _load_service(build_embeddings=False)
    return _cmd_export(service, args)


def _cmd_inspect(service: ChatHistoryService, args: argparse.Namespace) -> int:
    provider_filter = args.provider
    counts = {"chatgpt": 0, "claude": 0}
    message_count = 0

    for conversation in service.conversations:
        if provider_filter != "all" and conversation.provider != provider_filter:
            continue
        counts[conversation.provider] += 1
        message_count += len(conversation.messages)

    table = Table(title="Conversation Summary", box=box.SIMPLE_HEAVY)
    table.add_column("Metric", style="bold cyan")
    table.add_column("Value", justify="right")
    table.add_row("Conversations", str(sum(counts.values())))
    table.add_row("Messages", str(message_count))
    for provider, count in counts.items():
        if provider_filter in {"all", provider}:
            table.add_row(f"{provider} conversations", str(count))
    CONSOLE.print(table)
    return 0


def _run_inspect_command(args: argparse.Namespace) -> int:
    service = _load_service(build_embeddings=False)
    return _cmd_inspect(service, args)


def _run_install_command(args: argparse.Namespace) -> int:
    del args
    command = ["uvx", "--reinstall", "chat-history", "--version"]
    _info(f"Running {' '.join(command)}")
    try:
        result = subprocess.run(command, check=False)
    except FileNotFoundError:
        _error("uvx is not installed or not in PATH.")
        return 1
    return int(result.returncode)


def _read_env_values(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    raw_values = dotenv_values(env_path)
    result: dict[str, str] = {}
    for key, value in raw_values.items():
        if isinstance(value, str):
            result[key] = value
    return result


def _write_env_updates(env_path: Path, updates: dict[str, str | None]) -> None:
    with CONSOLE.status("[bold cyan]Writing data/.env configuration...", spinner="dots"):
        env_path.parent.mkdir(parents=True, exist_ok=True)
        if not env_path.exists():
            env_path.write_text("", encoding="utf-8")

        for key, value in updates.items():
            if value is None:
                unset_key(str(env_path), key, encoding="utf-8")
                continue
            set_key(
                str(env_path),
                key,
                value,
                quote_mode="auto",
                encoding="utf-8",
            )


def _resolve_data_dir(existing_env: dict[str, str], target_dir: Path) -> Path:
    raw_data_dir = existing_env.get("CHAT_HISTORY_DATA_DIR") or "data"
    return _resolve_path(raw_data_dir, target_dir).resolve()


def _prompt_yes_no(prompt: str, *, default: bool) -> bool:
    return Confirm.ask(f"[bold]{prompt}[/]", default=default, console=CONSOLE)


def _select_option(
    *,
    prompt: str,
    options: list[tuple[str, Any]],
) -> Any:
    if not options:
        raise ValueError("Selector options cannot be empty")
    labels = [label for label, _ in options]
    selected_label = questionary.select(
        prompt,
        choices=labels,
        qmark="",
        pointer="❯",
    ).ask()
    if selected_label is None:
        return options[-1][1]
    for label, value in options:
        if label == selected_label:
            return value
    return options[-1][1]


def _format_file_size(bytes_count: int) -> str:
    size = float(bytes_count)
    units = ["B", "KB", "MB", "GB"]
    unit = units[0]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            break
        size /= 1024
    if unit == "B":
        return f"{int(size)} {unit}"
    return f"{size:.1f} {unit}"


def _format_file_age(path: Path) -> str:
    now = datetime.now(timezone.utc)
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    days = int((now - modified).total_seconds() // 86400)
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def _provider_name_tokens(provider: str) -> tuple[str, ...]:
    if provider == "chatgpt":
        return ("chatgpt", "openai", "gpt")
    if provider == "claude":
        return ("claude", "anthropic")
    return (provider.lower(),)


def _is_provider_name_match(name: str, provider: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in _provider_name_tokens(provider))


def _is_claude_default_export_zip_name(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith(".zip") and lowered.startswith("data-") and "-batch-" in lowered


def _scan_local_candidates(search_dir: Path, provider: str) -> list[Path]:
    if not search_dir.exists() or not search_dir.is_dir():
        return []

    candidates: list[Path] = []
    for path in search_dir.iterdir():
        if path.name.startswith("."):
            continue

        name_matches = _is_provider_name_match(path.name, provider)
        if path.is_file():
            lower_name = path.name.lower()
            if path.suffix.lower() == ".zip" and (
                name_matches
                or (provider == "claude" and _is_claude_default_export_zip_name(lower_name))
            ):
                candidates.append(path)
            elif lower_name == "conversations.json":
                candidates.append(path)
            elif path.suffix.lower() == ".json" and name_matches:
                candidates.append(path)
            continue

        if not path.is_dir():
            continue
        if name_matches or (path / "conversations.json").exists():
            candidates.append(path)

    deduped = sorted(
        set(candidates),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    return deduped[:12]


def _scan_download_candidates(provider: str) -> list[Path]:
    downloads_dir = Path.home() / "Downloads"
    if not downloads_dir.exists():
        return []

    candidates: list[Path] = []
    provider_token = provider.lower()
    for path in downloads_dir.iterdir():
        if not path.is_file():
            continue
        name = path.name.lower()
        if path.suffix.lower() != ".zip":
            continue
        if provider_token in name or (
            provider == "claude" and _is_claude_default_export_zip_name(name)
        ):
            candidates.append(path)

    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[:12]


def _find_conversations_json(root: Path) -> Path | None:
    if root.is_file():
        return root if root.name == "conversations.json" else None

    candidates = [path for path in root.rglob("conversations.json") if path.is_file()]
    if not candidates:
        return None

    def _sort_key(path: Path) -> tuple[int, int]:
        rel_parts = path.relative_to(root).parts
        return (len(rel_parts), len(str(path)))

    return sorted(candidates, key=_sort_key)[0]


def _parse_iso_date(raw_value: Any) -> datetime | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_unix_date(raw_value: Any) -> datetime | None:
    if isinstance(raw_value, (int, float)):
        return datetime.fromtimestamp(float(raw_value), tz=timezone.utc)
    if isinstance(raw_value, str):
        try:
            return datetime.fromtimestamp(float(raw_value), tz=timezone.utc)
        except ValueError:
            return None
    return None


def _detect_provider(first_item: dict[str, Any]) -> str | None:
    if "mapping" in first_item and "current_node" in first_item:
        return "chatgpt"
    if "uuid" in first_item and "chat_messages" in first_item:
        return "claude"
    return None


def _build_validation_summary(raw_data: list[Any], provider: str) -> ValidationSummary:
    conversation_count = sum(1 for item in raw_data if isinstance(item, dict))
    timestamps: list[datetime] = []

    for item in raw_data:
        if not isinstance(item, dict):
            continue
        if provider == "chatgpt":
            parsed = _parse_unix_date(item.get("create_time"))
        else:
            parsed = _parse_iso_date(item.get("created_at"))
        if parsed is not None:
            timestamps.append(parsed)

    first_date = min(timestamps).strftime("%Y-%m-%d") if timestamps else None
    last_date = max(timestamps).strftime("%Y-%m-%d") if timestamps else None

    return ValidationSummary(
        provider=provider,
        conversations=conversation_count,
        first_date=first_date,
        last_date=last_date,
    )


def _validate_provider_file(
    *,
    file_path: Path,
    expected_provider: str,
) -> ValidationSummary:
    with file_path.open("r", encoding="utf-8") as file_handle:
        raw_data = json.load(file_handle)

    if not isinstance(raw_data, list) or not raw_data:
        raise ValueError("Expected a non-empty JSON array in conversations export")

    first_item = raw_data[0]
    if not isinstance(first_item, dict):
        raise ValueError("Expected first JSON array item to be an object")

    detected_provider = _detect_provider(first_item)
    if detected_provider is None:
        raise ValueError("Unrecognized export format (cannot determine provider)")

    if detected_provider != expected_provider:
        label = PROVIDER_LABELS[expected_provider]
        detected_label = PROVIDER_LABELS.get(detected_provider, detected_provider)
        _warn(
            f"Warning: selected {label} but detected {detected_label} format in {file_path}."
        )
        if not _prompt_yes_no("Continue with this file anyway?", default=False):
            raise ValueError("Provider mismatch; choose a different file")

    return _build_validation_summary(raw_data, detected_provider)


def _extract_provider_zip(zip_path: Path, *, provider: str, data_dir: Path) -> Path:
    extract_dir = data_dir / provider
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(extract_dir)

    conversations_json = _find_conversations_json(extract_dir)
    if conversations_json is None:
        raise FileNotFoundError("No conversations.json found in ZIP")
    return conversations_json


def _prepare_provider_source(
    *,
    provider: str,
    source_path: Path,
    data_dir: Path,
) -> tuple[Path, ValidationSummary]:
    resolved = source_path.expanduser()
    if not resolved.is_absolute():
        resolved = (Path.cwd() / resolved).resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"Path not found: {resolved}")

    if resolved.is_file() and resolved.suffix.lower() == ".zip":
        with CONSOLE.status(
            f"[bold cyan]Extracting {resolved.name}...",
            spinner="dots",
        ):
            conversations_json = _extract_provider_zip(
                resolved,
                provider=provider,
                data_dir=data_dir,
            )
        with CONSOLE.status(
            f"[bold cyan]Validating {conversations_json.name}...",
            spinner="dots",
        ):
            summary = _validate_provider_file(
                file_path=conversations_json,
                expected_provider=provider,
            )
        return conversations_json.resolve(), summary

    if resolved.is_dir():
        conversations_json = _find_conversations_json(resolved)
        if conversations_json is None:
            raise FileNotFoundError(
                f"No conversations.json found under directory: {resolved}"
            )
        with CONSOLE.status(
            f"[bold cyan]Validating {conversations_json.name}...",
            spinner="dots",
        ):
            summary = _validate_provider_file(
                file_path=conversations_json,
                expected_provider=provider,
            )
        return conversations_json.resolve(), summary

    with CONSOLE.status(
        f"[bold cyan]Validating {resolved.name}...",
        spinner="dots",
    ):
        summary = _validate_provider_file(
            file_path=resolved,
            expected_provider=provider,
        )
    return resolved.resolve(), summary


def _print_provider_summary(
    *,
    provider: str,
    source_path: Path,
    summary: ValidationSummary,
) -> None:
    label = PROVIDER_LABELS[provider]
    range_text = "date range unavailable"
    if summary.first_date and summary.last_date:
        range_text = f"{summary.first_date} – {summary.last_date}"
    _success(
        f"  {label}: {summary.conversations} conversations ({range_text}) from {source_path}"
    )


def _prompt_manual_path() -> Path | None:
    raw_path = Prompt.ask(
        "[bold]Enter path to ZIP, directory, or conversations.json[/]",
        default="",
        console=CONSOLE,
    ).strip()
    if not raw_path:
        return None
    return Path(raw_path)


def _choose_provider_source(provider: str, *, search_dir: Path) -> Path | None:
    label = PROVIDER_LABELS[provider]

    with CONSOLE.status(
        f"[bold cyan]Scanning {search_dir} for {label} exports...",
        spinner="dots",
    ):
        local_candidates = _scan_local_candidates(search_dir, provider)
    if local_candidates:
        _section(f"{label} Sources: Current Folder")
        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column("Candidate", style="bold cyan")
        table.add_column("Type")
        table.add_column("Size", justify="right")
        table.add_column("Age", justify="right")
        for path in local_candidates:
            if path.is_file():
                size = _format_file_size(path.stat().st_size)
                kind = path.suffix.lower().lstrip(".") or "file"
                name = path.name
            else:
                size = "-"
                kind = "folder"
                name = f"{path.name}/"
            table.add_row(name, kind, size, _format_file_age(path))
        CONSOLE.print(table)
        selected = _select_option(
            prompt=f"Select {label} source",
            options=[
                *[
                    (
                        f"Use local: {path.name}{'/' if path.is_dir() else ''}",
                        path,
                    )
                    for path in local_candidates
                ],
                ("Search ~/Downloads", "__downloads__"),
                (f"Skip {label}", None),
            ],
        )
        if isinstance(selected, Path):
            return selected
        if selected is None:
            return None
    else:
        _warn(f"No {label} matches found in {search_dir}.")

    with CONSOLE.status(
        f"[bold cyan]Scanning ~/Downloads for {label} exports...",
        spinner="dots",
    ):
        download_candidates = _scan_download_candidates(provider)
    if download_candidates:
        _section(f"{label} Sources: Downloads")
        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column("Candidate", style="bold cyan")
        table.add_column("Type")
        table.add_column("Size", justify="right")
        table.add_column("Age", justify="right")
        for path in download_candidates:
            kind = path.suffix.lower().lstrip(".") or "file"
            table.add_row(
                path.name,
                kind,
                _format_file_size(path.stat().st_size),
                _format_file_age(path),
            )
        CONSOLE.print(table)
        selected = _select_option(
            prompt=f"Select {label} source",
            options=[
                *[(f"Use download: {path.name}", path) for path in download_candidates],
                ("Enter path manually", "__manual__"),
                (f"Skip {label}", None),
            ],
        )
        if isinstance(selected, Path):
            return selected
        if selected == "__manual__":
            return _prompt_manual_path()
        return None

    _warn(f"No {label} ZIP exports detected in ~/Downloads.")
    if _prompt_yes_no(f"Enter a {label} path manually?", default=True):
        return _prompt_manual_path()
    return None


def _configure_provider(
    *,
    provider: str,
    data_dir: Path,
    search_dir: Path,
) -> Path | None:
    while True:
        selected_source = _choose_provider_source(provider, search_dir=search_dir)
        if selected_source is None:
            return None
        try:
            provider_path, summary = _prepare_provider_source(
                provider=provider,
                source_path=selected_source,
                data_dir=data_dir,
            )
        except Exception as error:  # noqa: BLE001
            _error(f"Could not use selected source: {error}")
            if _prompt_yes_no("Try again?", default=True):
                continue
            return None
        _print_provider_summary(
            provider=provider,
            source_path=provider_path,
            summary=summary,
        )
        return provider_path


def _print_config_summary(env_values: dict[str, str], *, base_dir: Path, heading: str) -> None:
    data_dir = _resolve_data_dir(env_values, base_dir)
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Setting", style="bold cyan")
    table.add_column("Value", style="white")
    table.add_row("Data dir", str(data_dir))
    for provider in PROVIDERS:
        key = _provider_env_key(provider)
        raw_value = env_values.get(key)
        label = PROVIDER_LABELS[provider]
        table.add_row(label, raw_value or "[dim]not configured[/dim]")
    CONSOLE.print(Panel(table, title=heading, border_style="cyan"))


def _recover_broken_paths(cwd: Path) -> None:
    env_path = cwd / ENV_RELATIVE_PATH
    if not env_path.exists():
        return

    env_values = _read_env_values(env_path)
    data_dir = _resolve_data_dir(env_values, cwd)
    updates: dict[str, str | None] = {}

    for provider in PROVIDERS:
        key = _provider_env_key(provider)
        raw_path = env_values.get(key)
        if not raw_path:
            continue

        resolved = _resolve_path(raw_path, cwd)
        exists = resolved.exists() and (
            resolved.is_file() or (resolved.is_dir() and _find_conversations_json(resolved) is not None)
        )
        if exists:
            continue

        label = PROVIDER_LABELS[provider]
        _warn(f"{label} path not found: {raw_path}")
        action = _select_option(
            prompt=f"How should {label} be handled?",
            options=[
                ("Provide a new path", "replace"),
                ("Remove this provider from config", "remove"),
                ("Continue anyway", "skip"),
            ],
        )

        if action == "replace":
            replacement = _configure_provider(
                provider=provider,
                data_dir=data_dir,
                search_dir=cwd,
            )
            if replacement is not None:
                updates[key] = str(replacement)
        elif action == "remove":
            updates[key] = None

    if updates:
        _write_env_updates(env_path, updates)
        _success("Updated data/.env after recovery.")


def _run_init(*, target_dir: Path) -> int:
    target_dir = target_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    env_path = target_dir / ENV_RELATIVE_PATH
    existing_env = _read_env_values(env_path)
    data_dir = _resolve_data_dir(existing_env, target_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    if existing_env:
        _print_config_summary(existing_env, base_dir=target_dir, heading="Current config:")
    else:
        _section("Setup Wizard")
        _info(f"Creating new config in {target_dir}")

    updates: dict[str, str | None] = {
        "CHAT_HISTORY_DATA_DIR": str(data_dir),
    }

    for provider in PROVIDERS:
        _section(f"Configure {PROVIDER_LABELS[provider]}")
        key = _provider_env_key(provider)

        configured_path = _configure_provider(
            provider=provider,
            data_dir=data_dir,
            search_dir=target_dir,
        )
        if configured_path is not None:
            updates[key] = str(configured_path)

    currently_enabled = _as_bool(existing_env.get("CHAT_HISTORY_OPENAI_ENABLED"), default=False)
    enable_semantic = _prompt_yes_no(
        "Enable semantic search? (requires OpenAI API key)",
        default=currently_enabled,
    )
    if enable_semantic:
        existing_key = existing_env.get("OPENAI_API_KEY", "")
        prompt = "OpenAI API key (sk-...)"
        if existing_key:
            prompt += " [leave blank to keep current]"
        raw_key = Prompt.ask(
            f"[bold]{prompt}[/]",
            default="",
            password=True,
            console=CONSOLE,
        ).strip()
        if raw_key:
            updates["OPENAI_API_KEY"] = raw_key
        elif not existing_key:
            _warn("No API key provided, semantic search remains disabled.")
            enable_semantic = False
    updates["CHAT_HISTORY_OPENAI_ENABLED"] = "true" if enable_semantic else "false"

    _write_env_updates(env_path, updates)
    final_env = _read_env_values(env_path)
    _print_config_summary(final_env, base_dir=target_dir, heading="Saved config:")
    _success("Setup complete. Starting browser...")
    return _run_serve(
        host="127.0.0.1",
        port=8080,
        no_browser=False,
        cwd=target_dir,
    )


def _run_init_command(args: argparse.Namespace) -> int:
    target_dir = args.path if args.path is not None else Path.cwd()
    return _run_init(target_dir=target_dir)


def _run_auto_mode() -> int:
    cwd = Path.cwd()
    env_path = cwd / ENV_RELATIVE_PATH
    if env_path.exists():
        _recover_broken_paths(cwd)
        return _run_serve(host="127.0.0.1", port=8080, no_browser=False, cwd=cwd)
    return _run_init(target_dir=cwd)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        return _run_auto_mode()

    handler = getattr(args, "func", None)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
