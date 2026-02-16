from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import load_settings
from exporter import export_conversation
from services import ChatHistoryService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chat history management commands")
    subcommands = parser.add_subparsers(dest="command", required=True)

    export_parser = subcommands.add_parser(
        "export", help="Export conversations to markdown or plain text files"
    )
    export_parser.add_argument(
        "--provider",
        choices=["chatgpt", "claude", "all"],
        default="all",
        help="Provider filter for exported conversations",
    )
    export_parser.add_argument(
        "--format",
        choices=["markdown", "text"],
        default="markdown",
        help="Output format",
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

    inspect_parser = subcommands.add_parser("inspect", help="Print loaded provider counts")
    inspect_parser.add_argument(
        "--provider",
        choices=["chatgpt", "claude", "all"],
        default="all",
        help="Provider filter",
    )

    return parser


def run_export(service: ChatHistoryService, args: argparse.Namespace) -> int:
    output_dir = args.out or service.settings.export_dir
    provider_filter = args.provider

    if args.clean:
        removed_count = 0
        if output_dir.exists():
            for path in output_dir.iterdir():
                if not path.is_file():
                    continue
                if path.suffix not in {".md", ".txt"}:
                    continue
                if provider_filter == "all" or path.name.startswith(f"{provider_filter}--"):
                    path.unlink()
                    removed_count += 1
        print(f"Removed {removed_count} existing export files from {output_dir}")

    conversations = service.conversations
    if provider_filter != "all":
        conversations = [
            conversation
            for conversation in conversations
            if conversation.provider == provider_filter
        ]

    if not conversations:
        print("No conversations matched the requested provider filter.")
        return 1

    exported_paths: list[Path] = []
    for conversation in conversations:
        exported_paths.append(
            export_conversation(
                conversation=conversation,
                output_dir=output_dir,
                output_format=args.format,
                include_system=not args.exclude_system,
                include_tool=not args.exclude_tool,
                include_thinking=not args.exclude_thinking,
                include_attachments=not args.exclude_attachments,
            )
        )

    print(f"Exported {len(exported_paths)} conversations to {output_dir}")
    return 0


def run_inspect(service: ChatHistoryService, args: argparse.Namespace) -> int:
    provider_filter = args.provider
    counts = {"chatgpt": 0, "claude": 0}
    message_count = 0

    for conversation in service.conversations:
        if provider_filter != "all" and conversation.provider != provider_filter:
            continue
        counts[conversation.provider] += 1
        message_count += len(conversation.messages)

    print(f"Conversations: {sum(counts.values())}")
    print(f"Messages: {message_count}")
    for provider, count in counts.items():
        if provider_filter in {"all", provider}:
            print(f"- {provider}: {count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = load_settings()
    service = ChatHistoryService(settings)
    service.load(build_embeddings=False)

    if args.command == "export":
        return run_export(service, args)
    if args.command == "inspect":
        return run_inspect(service, args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
