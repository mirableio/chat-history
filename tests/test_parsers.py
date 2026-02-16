from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from parsers import (
    load_provider_conversations,
    parse_chatgpt_export,
    parse_claude_export,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class ParserTests(unittest.TestCase):
    def test_chatgpt_active_branch_is_selected(self) -> None:
        conversations = parse_chatgpt_export(FIXTURES_DIR / "chatgpt_2026_sample.json")
        main = next(conversation for conversation in conversations if conversation.id == "chatgpt-conv-1")

        message_ids = [message.id for message in main.messages]
        self.assertIn("msg-user-1", message_ids)
        self.assertIn("msg-assistant-main", message_ids)
        self.assertNotIn("msg-assistant-alt", message_ids)

    def test_chatgpt_unknown_content_type_does_not_crash(self) -> None:
        conversations = parse_chatgpt_export(FIXTURES_DIR / "chatgpt_2026_sample.json")
        target = next(conversation for conversation in conversations if conversation.id == "chatgpt-conv-2")
        self.assertGreaterEqual(len(target.messages), 1)
        all_text = "\n".join(message.text() for message in target.messages)
        self.assertTrue(all_text.strip())

    def test_chatgpt_code_falls_back_to_metadata_text(self) -> None:
        conversations = parse_chatgpt_export(FIXTURES_DIR / "chatgpt_2026_sample.json")
        target = next(conversation for conversation in conversations if conversation.id == "chatgpt-conv-3")
        self.assertEqual(len(target.messages), 1)
        self.assertIn("from metadata", target.messages[0].text())

    def test_chatgpt_ignores_hidden_and_empty_text_messages(self) -> None:
        payload = [
            {
                "id": "chatgpt-conv-empty-text-filter",
                "title": "Empty text filter",
                "create_time": 1733000000.0,
                "update_time": 1733000005.0,
                "current_node": "assistant-final",
                "mapping": {
                    "root": {
                        "id": "root",
                        "parent": None,
                        "children": ["system-hidden"],
                        "message": None,
                    },
                    "system-hidden": {
                        "id": "system-hidden",
                        "parent": "root",
                        "children": ["user-1"],
                        "message": {
                            "id": "msg-system-hidden",
                            "author": {"role": "system"},
                            "create_time": 1733000001.0,
                            "update_time": 1733000001.0,
                            "content": {"content_type": "text", "parts": [""]},
                            "metadata": {"is_visually_hidden_from_conversation": True},
                        },
                    },
                    "user-1": {
                        "id": "user-1",
                        "parent": "system-hidden",
                        "children": ["assistant-empty"],
                        "message": {
                            "id": "msg-user-1",
                            "author": {"role": "user"},
                            "create_time": 1733000002.0,
                            "update_time": 1733000002.0,
                            "content": {"content_type": "text", "parts": ["real user text"]},
                            "metadata": {},
                        },
                    },
                    "assistant-empty": {
                        "id": "assistant-empty",
                        "parent": "user-1",
                        "children": ["assistant-final"],
                        "message": {
                            "id": "msg-assistant-empty",
                            "author": {"role": "assistant"},
                            "create_time": 1733000003.0,
                            "update_time": 1733000003.0,
                            "content": {"content_type": "text", "parts": [""]},
                            "metadata": {},
                        },
                    },
                    "assistant-final": {
                        "id": "assistant-final",
                        "parent": "assistant-empty",
                        "children": [],
                        "message": {
                            "id": "msg-assistant-final",
                            "author": {"role": "assistant"},
                            "create_time": 1733000004.0,
                            "update_time": 1733000004.0,
                            "content": {"content_type": "text", "parts": ["real assistant text"]},
                            "metadata": {},
                        },
                    },
                },
            }
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as temp_file:
            json.dump(payload, temp_file)
            temp_path = Path(temp_file.name)
        try:
            conversations = parse_chatgpt_export(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        self.assertEqual(len(conversations), 1)
        message_ids = [message.id for message in conversations[0].messages]
        self.assertEqual(message_ids, ["msg-user-1", "msg-assistant-final"])
        self.assertEqual(conversations[0].messages[0].text(), "real user text")
        self.assertEqual(conversations[0].messages[1].text(), "real assistant text")

    def test_chatgpt_content_references_replace_citation_markers(self) -> None:
        payload = [
            {
                "id": "chatgpt-conv-content-ref",
                "title": "Content references",
                "create_time": 1734000000.0,
                "update_time": 1734000005.0,
                "current_node": "assistant-1",
                "mapping": {
                    "root": {
                        "id": "root",
                        "parent": None,
                        "children": ["assistant-1"],
                        "message": None,
                    },
                    "assistant-1": {
                        "id": "assistant-1",
                        "parent": "root",
                        "children": [],
                        "message": {
                            "id": "msg-assistant-1",
                            "author": {"role": "assistant"},
                            "create_time": 1734000002.0,
                            "update_time": 1734000002.0,
                            "content": {
                                "content_type": "text",
                                "parts": [
                                    "Use the docker client with no extra setup. citeturn4view0"
                                ],
                            },
                            "metadata": {
                                "content_references": [
                                    {
                                        "matched_text": "citeturn4view0",
                                        "alt": "([GitHub](https://github.com/abiosoft/colima))",
                                        "safe_urls": ["https://github.com/abiosoft/colima"],
                                    }
                                ]
                            },
                        },
                    },
                },
            }
        ]

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as temp_file:
            json.dump(payload, temp_file)
            temp_path = Path(temp_file.name)
        try:
            conversations = parse_chatgpt_export(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        self.assertEqual(len(conversations), 1)
        self.assertEqual(len(conversations[0].messages), 1)
        text = conversations[0].messages[0].text()
        self.assertIn("https://github.com/abiosoft/colima", text)
        self.assertNotIn("citeturn4view0", text)

    def test_chatgpt_content_references_include_all_safe_urls(self) -> None:
        payload = [
            {
                "id": "chatgpt-conv-content-ref-multi",
                "title": "Content references multiple urls",
                "create_time": 1735000000.0,
                "update_time": 1735000005.0,
                "current_node": "assistant-1",
                "mapping": {
                    "root": {
                        "id": "root",
                        "parent": None,
                        "children": ["assistant-1"],
                        "message": None,
                    },
                    "assistant-1": {
                        "id": "assistant-1",
                        "parent": "root",
                        "children": [],
                        "message": {
                            "id": "msg-assistant-1",
                            "author": {"role": "assistant"},
                            "create_time": 1735000002.0,
                            "update_time": 1735000002.0,
                            "content": {
                                "content_type": "text",
                                "parts": [
                                    "Dockerd mode gives Docker API + Docker CLI. citeturn1search2turn1search6"
                                ],
                            },
                            "metadata": {
                                "content_references": [
                                    {
                                        "matched_text": "citeturn1search2turn1search6",
                                        "alt": "([docs.rancherdesktop.io](https://docs.rancherdesktop.io/1.7/ui/preferences/container-engine/?utm_source=chatgpt.com))",
                                        "safe_urls": [
                                            "https://docs.rancherdesktop.io/",
                                            "https://docs.rancherdesktop.io/?utm_source=chatgpt.com",
                                            "https://docs.rancherdesktop.io/1.7/ui/preferences/container-engine/",
                                            "https://docs.rancherdesktop.io/1.7/ui/preferences/container-engine/?utm_source=chatgpt.com",
                                        ],
                                    }
                                ]
                            },
                        },
                    },
                },
            }
        ]

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as temp_file:
            json.dump(payload, temp_file)
            temp_path = Path(temp_file.name)
        try:
            conversations = parse_chatgpt_export(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        self.assertEqual(len(conversations), 1)
        self.assertEqual(len(conversations[0].messages), 1)
        text = conversations[0].messages[0].text()
        self.assertIn("https://docs.rancherdesktop.io/", text)
        self.assertIn(
            "https://docs.rancherdesktop.io/1.7/ui/preferences/container-engine/",
            text,
        )
        self.assertNotIn("utm_source=chatgpt.com", text)
        self.assertNotIn("citeturn1search2turn1search6", text)

    def test_claude_block_list_and_attachment_blocks(self) -> None:
        conversations = parse_claude_export(FIXTURES_DIR / "claude_2026_sample.json")
        self.assertEqual(len(conversations), 1)
        conversation = conversations[0]

        assistant = next(message for message in conversation.messages if message.role == "assistant")
        block_types = [block.type for block in assistant.content]
        self.assertIn("thinking", block_types)
        self.assertIn("tool_use", block_types)
        self.assertIn("tool_result", block_types)
        self.assertIn("attachment", block_types)
        self.assertIn("file", block_types)

    def test_provider_merge_and_utc_datetimes(self) -> None:
        conversations = load_provider_conversations(
            chatgpt_path=FIXTURES_DIR / "chatgpt_2026_sample.json",
            claude_path=FIXTURES_DIR / "claude_2026_sample.json",
        )
        providers = {conversation.provider for conversation in conversations}
        self.assertEqual(providers, {"chatgpt", "claude"})
        for conversation in conversations:
            self.assertIsNotNone(conversation.created.tzinfo)
            for message in conversation.messages:
                self.assertIsNotNone(message.created.tzinfo)


if __name__ == "__main__":
    unittest.main()
