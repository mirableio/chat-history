from __future__ import annotations

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
