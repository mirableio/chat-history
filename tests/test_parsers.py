from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from chat_history.parsers import (
    load_provider_conversations,
    parse_chatgpt_export,
    parse_claude_export,
    parse_gemini_export,
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

    def test_chatgpt_image_asset_part_has_structured_metadata(self) -> None:
        conversations = parse_chatgpt_export(FIXTURES_DIR / "chatgpt_2026_sample.json")
        target = next(conversation for conversation in conversations if conversation.id == "chatgpt-conv-1")
        assistant = next(message for message in target.messages if message.id == "msg-assistant-main")
        image_block = next(block for block in assistant.content if block.type == "image_asset_pointer")
        asset = image_block.data.get("asset")

        self.assertEqual(image_block.text, "[Image]")
        self.assertIsInstance(asset, dict)
        self.assertEqual(asset.get("kind"), "image")
        self.assertEqual(asset.get("source_pointer"), "file-service://image-1")
        self.assertEqual(asset.get("width"), None)
        self.assertEqual(asset.get("height"), None)
        self.assertEqual(asset.get("is_resolved"), False)

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

    def test_claude_attachment_uses_full_extracted_content_text(self) -> None:
        conversations = parse_claude_export(FIXTURES_DIR / "claude_2026_sample.json")
        conversation = conversations[0]
        assistant = next(message for message in conversation.messages if message.role == "assistant")

        attachment_block = next(block for block in assistant.content if block.type == "attachment")
        file_block = next(block for block in assistant.content if block.type == "file")

        self.assertEqual(attachment_block.text, "sample notes")
        self.assertEqual(attachment_block.data.get("file_name"), "notes.txt")
        self.assertEqual(attachment_block.data.get("file_type"), "text/plain")
        self.assertTrue(attachment_block.data.get("has_extracted_content"))
        self.assertEqual(file_block.data.get("file_name"), "draft.md")

    def test_claude_attachment_and_file_fallback_names(self) -> None:
        payload = [
            {
                "uuid": "claude-conv-fallbacks",
                "name": "Fallback names",
                "created_at": "2025-01-01T00:00:00.000000Z",
                "updated_at": "2025-01-01T00:01:00.000000Z",
                "chat_messages": [
                    {
                        "uuid": "claude-msg-fallbacks",
                        "sender": "assistant",
                        "created_at": "2025-01-01T00:00:30.000000Z",
                        "updated_at": "2025-01-01T00:00:30.000000Z",
                        "content": [{"type": "text", "text": "ok"}],
                        "attachments": [
                            {
                                "file_name": "",
                                "file_size": 10,
                                "file_type": "txt",
                                "extracted_content": "Attachment body",
                            }
                        ],
                        "files": [{"file_name": ""}],
                    }
                ],
            }
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as temp_file:
            json.dump(payload, temp_file)
            temp_path = Path(temp_file.name)
        try:
            conversations = parse_claude_export(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        assistant = conversations[0].messages[0]
        attachment_block = next(block for block in assistant.content if block.type == "attachment")
        file_block = next(block for block in assistant.content if block.type == "file")
        self.assertEqual(attachment_block.data.get("file_name"), "attachment-1")
        self.assertEqual(file_block.data.get("file_name"), "file-1")
        self.assertEqual(file_block.text, "[File] file-1")

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


class GeminiParserTests(unittest.TestCase):
    def test_gemini_basic_conversation_count(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        self.assertEqual(len(conversations), 2)

    def test_gemini_user_and_assistant_roles(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        conv = next(c for c in conversations if c.id == "gemini-conv-basic")
        roles = [m.role for m in conv.messages]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)

    def test_gemini_thinking_blocks(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        conv = next(c for c in conversations if c.id == "gemini-conv-basic")
        assistant_msgs = [m for m in conv.messages if m.role == "assistant"]
        self.assertGreater(len(assistant_msgs), 0)
        block_types = [b.type for b in assistant_msgs[0].content]
        self.assertIn("thinking", block_types)
        self.assertIn("text", block_types)

    def test_gemini_system_prompt(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        conv = next(c for c in conversations if c.id == "gemini-conv-basic")
        system_msgs = [m for m in conv.messages if m.role == "system"]
        self.assertEqual(len(system_msgs), 1)
        self.assertIn("helpful and concise", system_msgs[0].text())

    def test_gemini_inline_image(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        conv = next(c for c in conversations if c.id == "gemini-conv-multimodal")
        all_blocks = [b for m in conv.messages for b in m.content]
        image_blocks = [b for b in all_blocks if b.type == "inline_image"]
        self.assertGreater(len(image_blocks), 0)
        self.assertTrue(image_blocks[0].data.get("data_uri", "").startswith("data:"))

    def test_gemini_inline_audio(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        conv = next(c for c in conversations if c.id == "gemini-conv-multimodal")
        all_blocks = [b for m in conv.messages for b in m.content]
        audio_blocks = [b for b in all_blocks if b.type == "inline_audio"]
        self.assertGreater(len(audio_blocks), 0)
        self.assertTrue(audio_blocks[0].data.get("data_uri", "").startswith("data:"))

    def test_gemini_grounding(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        conv = next(c for c in conversations if c.id == "gemini-conv-multimodal")
        all_blocks = [b for m in conv.messages for b in m.content]
        grounding_blocks = [b for b in all_blocks if b.type == "grounding"]
        self.assertGreater(len(grounding_blocks), 0)
        self.assertIn("example.com", grounding_blocks[0].text)

    def test_gemini_drive_reference(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        conv = next(c for c in conversations if c.id == "gemini-conv-multimodal")
        all_blocks = [b for m in conv.messages for b in m.content]
        drive_blocks = [b for b in all_blocks if b.type == "drive_document"]
        self.assertGreater(len(drive_blocks), 0)
        self.assertIn("id", drive_blocks[0].data)

    def test_gemini_model_extracted(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        conv = next(c for c in conversations if c.id == "gemini-conv-basic")
        models = {m.model for m in conv.messages if m.model}
        self.assertIn("gemini-2.5-pro", models)

    def test_gemini_message_timestamps_increment(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        conv = next(c for c in conversations if c.id == "gemini-conv-basic")
        non_system = [m for m in conv.messages if m.role != "system"]
        for i in range(1, len(non_system)):
            self.assertGreater(non_system[i].created, non_system[i - 1].created)

    def test_gemini_provider_merge(self) -> None:
        conversations = load_provider_conversations(
            chatgpt_path=FIXTURES_DIR / "chatgpt_2026_sample.json",
            claude_path=FIXTURES_DIR / "claude_2026_sample.json",
            gemini_path=FIXTURES_DIR / "gemini_2026_sample.json",
        )
        providers = {c.provider for c in conversations}
        self.assertEqual(providers, {"chatgpt", "claude", "gemini"})

    def test_gemini_provider_is_gemini(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        for conv in conversations:
            self.assertEqual(conv.provider, "gemini")
            for msg in conv.messages:
                self.assertEqual(msg.provider, "gemini")

    def test_gemini_utc_datetimes(self) -> None:
        conversations = parse_gemini_export(FIXTURES_DIR / "gemini_2026_sample.json")
        for conv in conversations:
            self.assertIsNotNone(conv.created.tzinfo)
            for msg in conv.messages:
                self.assertIsNotNone(msg.created.tzinfo)


if __name__ == "__main__":
    unittest.main()
