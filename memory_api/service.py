from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import (
    CommitMemoryUpdateRequest,
    CommitMemoryUpdateResponse,
    MemoryType,
    ProposeMemoryUpdateRequest,
    ProposeMemoryUpdateResponse,
    ProposalStatus,
    ReadResponse,
    SearchResponse,
    SearchResult,
)


FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
SECTION_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
BULLET_RE = re.compile(r"^-\s+(.*)$")


@dataclass
class MarkdownDocument:
    metadata: dict[str, Any]
    body: str


class MemoryService:
    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)

    def read_profile(self, user_id: str) -> ReadResponse:
        path = self._user_dir(user_id) / "profile.md"
        document = self._read_markdown_document(path)
        data = self._parse_sections(document.body)
        return ReadResponse(user_id=user_id, source=self._relative(path), updated_at=document.metadata.get("updated_at"), data=data)

    def read_preferences(self, user_id: str) -> ReadResponse:
        path = self._user_dir(user_id) / "preferences.md"
        document = self._read_markdown_document(path)
        data = self._parse_sections(document.body)
        return ReadResponse(user_id=user_id, source=self._relative(path), updated_at=document.metadata.get("updated_at"), data=data)

    def search_memory(self, user_id: str, query: str, scopes: list[str] | None = None, top_k: int = 8) -> SearchResponse:
        scopes = scopes or ["profile", "preferences", "logs"]
        query_terms = self._tokenize(query)
        results: list[SearchResult] = []

        for path in self._iter_scope_files(user_id, scopes):
            document = self._read_markdown_document(path)
            sections = self._parse_sections(document.body)
            for section_name, values in sections.items():
                snippets = values if isinstance(values, list) else [str(values)]
                for snippet in snippets:
                    score = self._score_text(snippet, query_terms)
                    if score <= 0:
                        continue
                    memory_type = "short-term" if "/logs/" in self._relative(path) else path.stem
                    results.append(
                        SearchResult(
                            memory_type=memory_type,
                            source=self._relative(path),
                            snippet=f"[{section_name}] {snippet}",
                            score=round(score, 4),
                            updated_at=document.metadata.get("updated_at"),
                        )
                    )

        results.sort(key=lambda item: item.score, reverse=True)
        return SearchResponse(user_id=user_id, query=query, results=results[:top_k])

    def propose_memory_update(self, payload: ProposeMemoryUpdateRequest) -> ProposeMemoryUpdateResponse:
        user_dir = self._user_dir(payload.user_id)
        proposal_id = f"mp_{uuid4().hex[:12]}"
        now = self._now_iso()
        proposal_record = payload.model_dump()
        proposal_record.update({
            "proposal_id": proposal_id,
            "status": ProposalStatus.queued.value,
            "created_at": now,
        })

        target_dir = user_dir / "inbox" / "proposals"
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self._filename_timestamp()}_{payload.request_id}_{proposal_id}.json"
        stored_path = target_dir / filename
        stored_path.write_text(json.dumps(proposal_record, indent=2), encoding="utf-8")
        return ProposeMemoryUpdateResponse(
            proposal_id=proposal_id,
            status=ProposalStatus.queued,
            stored_at=self._relative(stored_path),
        )

    def commit_memory_update(self, payload: CommitMemoryUpdateRequest) -> CommitMemoryUpdateResponse:
        proposal_path = self._find_proposal_path(payload.proposal_id)
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        user_id = proposal["user_id"]
        memory_type = MemoryType(proposal["memory_type"])
        canonical_path = self._canonical_path(user_id, memory_type)
        document = self._read_markdown_document(canonical_path)
        sections = self._parse_sections(document.body)
        target_section = self._slugify(proposal["target_path"])
        existing_values = list(sections.get(target_section, []))
        candidate_values = proposal["candidate_value"]
        if isinstance(candidate_values, str):
            candidate_values = [candidate_values]

        conflicts = self._detect_conflicts(existing_values, candidate_values)
        status = ProposalStatus.committed
        if conflicts and proposal["confidence"] != "high" and payload.commit_mode != "replace":
            status = ProposalStatus.needs_review
            rejected_path = self._move_proposal(proposal_path, "rejected", payload.approved_by, status, conflicts)
            return CommitMemoryUpdateResponse(
                proposal_id=payload.proposal_id,
                status=status,
                written_files=[self._relative(rejected_path)],
                conflicts=conflicts,
            )

        if payload.commit_mode == "replace" or conflicts:
            sections[target_section] = candidate_values
        else:
            merged = existing_values[:]
            normalized_existing = {self._normalize_entry(value) for value in existing_values}
            for value in candidate_values:
                if self._normalize_entry(value) not in normalized_existing:
                    merged.append(value)
            sections[target_section] = merged

        document.metadata["updated_at"] = self._now_iso()
        document.metadata["last_committed_proposal"] = payload.proposal_id
        canonical_path.write_text(self._serialize_markdown_document(document.metadata, sections), encoding="utf-8")

        history_path = self._append_history_entry(user_id, proposal, existing_values, sections[target_section], conflicts, payload.approved_by, status)
        committed_path = self._move_proposal(proposal_path, "committed", payload.approved_by, status, conflicts)
        return CommitMemoryUpdateResponse(
            proposal_id=payload.proposal_id,
            status=status,
            written_files=[self._relative(canonical_path), self._relative(history_path), self._relative(committed_path)],
            conflicts=conflicts,
        )

    def _append_history_entry(
        self,
        user_id: str,
        proposal: dict[str, Any],
        previous_values: list[str],
        new_values: list[str],
        conflicts: list[str],
        approved_by: str,
        status: ProposalStatus,
    ) -> Path:
        history_dir = self._user_dir(user_id) / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        history_path = history_dir / f"{self._today()}-memory-changelog.md"
        lines = [
            f"## {self._now_iso()} {proposal['proposal_id']}",
            f"- status: {status.value}",
            f"- memory_type: {proposal['memory_type']}",
            f"- target_path: {proposal['target_path']}",
            f"- approved_by: {approved_by}",
            f"- previous_values: {json.dumps(previous_values)}",
            f"- new_values: {json.dumps(new_values)}",
            f"- conflicts: {json.dumps(conflicts)}",
            "",
        ]
        if history_path.exists():
            history_path.write_text(history_path.read_text(encoding="utf-8") + "\n" + "\n".join(lines), encoding="utf-8")
        else:
            history_path.write_text("# Memory Changelog\n\n" + "\n".join(lines), encoding="utf-8")
        return history_path

    def _move_proposal(self, proposal_path: Path, target_bucket: str, approved_by: str, status: ProposalStatus, conflicts: list[str]) -> Path:
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        proposal["status"] = status.value
        proposal["approved_by"] = approved_by
        proposal["conflicts"] = conflicts
        target_dir = proposal_path.parents[1] / target_bucket
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / proposal_path.name
        target_path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
        proposal_path.unlink()
        return target_path

    def _find_proposal_path(self, proposal_id: str) -> Path:
        for path in self.root_dir.glob(f"users/*/inbox/proposals/*{proposal_id}.json"):
            return path
        raise FileNotFoundError(f"Proposal {proposal_id} was not found in queued proposals")

    def _canonical_path(self, user_id: str, memory_type: MemoryType) -> Path:
        mapping = {
            MemoryType.profile: "profile.md",
            MemoryType.preferences: "preferences.md",
            MemoryType.active_projects: "active_projects.md",
            MemoryType.routines: "routines.md",
            MemoryType.short_term: f"logs/{self._today_path()}.md",
        }
        return self._user_dir(user_id) / mapping[memory_type]

    def _iter_scope_files(self, user_id: str, scopes: list[str]) -> list[Path]:
        user_dir = self._user_dir(user_id)
        files: list[Path] = []
        if "profile" in scopes:
            files.append(user_dir / "profile.md")
        if "preferences" in scopes:
            files.append(user_dir / "preferences.md")
        if "active_projects" in scopes:
            files.append(user_dir / "active_projects.md")
        if "routines" in scopes:
            files.append(user_dir / "routines.md")
        if "logs" in scopes:
            files.extend(sorted((user_dir / "logs").glob("**/*.md")))
        return [path for path in files if path.exists()]

    def _parse_sections(self, body: str) -> dict[str, list[str]]:
        section_matches = list(SECTION_RE.finditer(body))
        if not section_matches:
            return {}

        sections: dict[str, list[str]] = {}
        for index, match in enumerate(section_matches):
            title = self._slugify(match.group("title"))
            start = match.end()
            end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(body)
            block = body[start:end].strip()
            values = []
            for line in block.splitlines():
                line = line.strip()
                bullet = BULLET_RE.match(line)
                if bullet:
                    values.append(bullet.group(1).strip())
            sections[title] = values
        return sections

    def _serialize_markdown_document(self, metadata: dict[str, Any], sections: dict[str, list[str]]) -> str:
        front_matter = self._dump_front_matter(metadata).strip()
        section_chunks = []
        for title, values in sections.items():
            header = self._heading_from_slug(title)
            bullets = "\n".join(f"- {value}" for value in values)
            section_chunks.append(f"## {header}\n{bullets}".rstrip())
        body = "# Memory\n\n" + "\n\n".join(section_chunks).strip() + "\n"
        return f"---\n{front_matter}\n---\n\n{body}"


    def _load_front_matter(self, raw: str) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if ':' not in stripped:
                raise ValueError(f"Invalid front matter line: {line}")
            key, value = stripped.split(':', 1)
            metadata[key.strip()] = value.strip()
        return metadata

    def _dump_front_matter(self, metadata: dict[str, Any]) -> str:
        lines = []
        for key, value in metadata.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    def _read_markdown_document(self, path: Path) -> MarkdownDocument:
        raw = path.read_text(encoding="utf-8")
        match = FRONT_MATTER_RE.match(raw)
        if not match:
            raise ValueError(f"{path} is missing YAML front matter")
        metadata = self._load_front_matter(match.group(1))
        body = match.group(2).strip() + "\n"
        return MarkdownDocument(metadata=metadata, body=body)

    def _detect_conflicts(self, existing_values: list[str], candidate_values: list[str]) -> list[str]:
        if not existing_values:
            return []
        normalized_existing = {self._normalize_entry(item) for item in existing_values}
        normalized_candidates = {self._normalize_entry(item) for item in candidate_values}
        if normalized_existing & normalized_candidates:
            return []
        return [
            f"Existing values {existing_values} differ from candidate values {candidate_values}"
        ]

    def _score_text(self, text: str, query_terms: set[str]) -> float:
        text_terms = self._tokenize(text)
        if not query_terms or not text_terms:
            return 0
        overlap = query_terms & text_terms
        return len(overlap) / len(query_terms)

    def _tokenize(self, text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9_]+", text.lower()) if len(token) > 1}

    def _normalize_entry(self, value: str) -> str:
        return " ".join(self._tokenize(value))

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.root_dir).as_posix()

    def _user_dir(self, user_id: str) -> Path:
        return self.root_dir / "users" / user_id

    def _slugify(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")

    def _heading_from_slug(self, slug: str) -> str:
        return slug.replace("_", " ").title()

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _today(self) -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _today_path(self) -> str:
        today = datetime.now(timezone.utc).date()
        return f"{today.year:04d}/{today.month:02d}/{today.isoformat()}"

    def _filename_timestamp(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
