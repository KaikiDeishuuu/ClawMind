from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from memory_api.models import CommitMemoryUpdateRequest, ProposeMemoryUpdateRequest
from memory_api.service import MemoryService


class MemoryServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        shutil.copytree("examples/memory", root / "memory")
        self.service = MemoryService(root / "memory")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_read_profile(self) -> None:
        response = self.service.read_profile("user_001")
        self.assertEqual(response.data["identity"][0], "Preferred name: Alex")
        self.assertEqual(response.source, "users/user_001/profile.md")

    def test_search_memory(self) -> None:
        response = self.service.search_memory("user_001", "telegram reminders", ["preferences", "logs"], top_k=5)
        self.assertTrue(any("telegram" in result.snippet.lower() for result in response.results))

    def test_propose_and_commit_high_confidence_conflict_replaces_section(self) -> None:
        proposal = self.service.propose_memory_update(
            ProposeMemoryUpdateRequest(
                user_id="user_001",
                request_id="req_high_conflict",
                proposed_by="openclaw",
                memory_type="preferences",
                operation="update",
                target_path="communication",
                evidence=["User said: use Telegram for reminders, email is too noisy."],
                candidate_value=["Prefers Telegram for reminders.", "Avoid email reminders when possible."],
                confidence="high",
                reason="Explicit user instruction",
                observed_at="2026-03-19T08:00:00Z",
            )
        )

        commit = self.service.commit_memory_update(
            CommitMemoryUpdateRequest(proposal_id=proposal.proposal_id, approved_by="test-suite", commit_mode="merge")
        )
        self.assertEqual(commit.status, "committed")

        preferences = self.service.read_preferences("user_001")
        self.assertIn("Prefers Telegram for reminders.", preferences.data["communication"])
        self.assertNotIn("Prefers email for reminders.", preferences.data["communication"])

    def test_low_confidence_conflict_goes_to_review(self) -> None:
        proposal = self.service.propose_memory_update(
            ProposeMemoryUpdateRequest(
                user_id="user_001",
                request_id="req_low_conflict",
                proposed_by="openclaw",
                memory_type="preferences",
                operation="update",
                target_path="communication",
                evidence=["Model inferred user may want Telegram reminders."],
                candidate_value="Prefers Telegram for reminders.",
                confidence="medium",
                reason="Indirect signal from logs",
                observed_at="2026-03-19T08:00:00Z",
            )
        )

        commit = self.service.commit_memory_update(
            CommitMemoryUpdateRequest(proposal_id=proposal.proposal_id, approved_by="test-suite", commit_mode="merge")
        )
        self.assertEqual(commit.status, "needs_review")
        self.assertTrue(any("rejected/" in path for path in commit.written_files))

        preferences_path = self.service.root_dir / "users" / "user_001" / "preferences.md"
        self.assertIn("Prefers email for reminders.", preferences_path.read_text(encoding="utf-8"))

    def test_proposal_file_is_real_json_on_disk(self) -> None:
        proposal = self.service.propose_memory_update(
            ProposeMemoryUpdateRequest(
                user_id="user_001",
                request_id="req_json",
                proposed_by="openclaw",
                memory_type="preferences",
                operation="update",
                target_path="communication",
                evidence=["User directly requested Telegram reminders."],
                candidate_value="Prefers Telegram for reminders.",
                confidence="high",
                reason="Direct explicit user instruction",
                observed_at="2026-03-19T08:00:00Z",
            )
        )

        proposal_path = self.service.root_dir / proposal.stored_at
        payload = json.loads(proposal_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["proposal_id"], proposal.proposal_id)


if __name__ == "__main__":
    unittest.main()
