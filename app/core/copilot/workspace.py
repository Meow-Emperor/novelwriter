# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Workspace state and evidence-pack helpers for copilot."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.core.ai_client import ToolCall
from app.core.copilot.messages import CopilotTextKey, get_copilot_text
from app.core.copilot.scope import EvidenceItem, MAX_EVIDENCE_ITEMS


@dataclass
class EvidencePack:
    pack_id: str
    source_refs: list[dict[str, Any]]
    preview_excerpt: str
    anchor_terms: list[str]
    support_count: int
    related_targets: list[dict[str, Any]]
    conflict_group: str | None = None
    expanded_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "source_refs": self.source_refs,
            "preview_excerpt": self.preview_excerpt,
            "anchor_terms": self.anchor_terms,
            "support_count": self.support_count,
            "related_targets": self.related_targets,
            "conflict_group": self.conflict_group,
            "expanded_text": self.expanded_text,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvidencePack:
        return cls(
            pack_id=payload["pack_id"],
            source_refs=payload.get("source_refs", []),
            preview_excerpt=payload.get("preview_excerpt", ""),
            anchor_terms=payload.get("anchor_terms", []),
            support_count=payload.get("support_count", 0),
            related_targets=payload.get("related_targets", []),
            conflict_group=payload.get("conflict_group"),
            expanded_text=payload.get("expanded_text"),
        )


def make_pack_id(prefix: str, *parts: Any) -> str:
    """Build a stable pack ID including a content hash suffix."""
    content = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(content.encode()).hexdigest()[:8]
    return f"{prefix}_{digest}"


def _workspace_text(
    interaction_locale: str,
    text_key: CopilotTextKey,
    **params: object,
) -> str:
    return get_copilot_text(text_key, locale=interaction_locale, **params)


@dataclass
class Workspace:
    evidence_packs: dict[str, EvidencePack] = field(default_factory=dict)
    tool_journal: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    opened_pack_ids: list[str] = field(default_factory=list)
    pending_tool_calls: list[dict[str, str]] = field(default_factory=list)
    tool_call_count: int = 0
    round_count: int = 0
    snapshot_fingerprint: str = ""
    final_answer_draft: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_packs": {key: value.to_dict() for key, value in self.evidence_packs.items()},
            "tool_journal": self.tool_journal,
            "messages": self.messages,
            "opened_pack_ids": self.opened_pack_ids,
            "pending_tool_calls": self.pending_tool_calls,
            "tool_call_count": self.tool_call_count,
            "round_count": self.round_count,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "final_answer_draft": self.final_answer_draft,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Workspace:
        packs = {
            key: EvidencePack.from_dict(value)
            for key, value in payload.get("evidence_packs", {}).items()
        }
        return cls(
            evidence_packs=packs,
            tool_journal=payload.get("tool_journal", []),
            messages=payload.get("messages", []),
            opened_pack_ids=payload.get("opened_pack_ids", []),
            pending_tool_calls=payload.get("pending_tool_calls", []),
            tool_call_count=payload.get("tool_call_count", 0),
            round_count=payload.get("round_count", 0),
            snapshot_fingerprint=payload.get("snapshot_fingerprint", ""),
            final_answer_draft=payload.get("final_answer_draft"),
        )


def serialize_tool_call(tool_call: ToolCall) -> dict[str, str]:
    return {
        "id": tool_call.id,
        "name": tool_call.name,
        "arguments": tool_call.arguments,
    }


def deserialize_tool_call(payload: dict[str, Any]) -> ToolCall:
    return ToolCall(
        id=str(payload.get("id") or ""),
        name=str(payload.get("name") or ""),
        arguments=str(payload.get("arguments") or ""),
    )


def build_follow_up_workspace_seed(workspace_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Carry reusable research memory into a fresh follow-up run.

    Follow-up runs should inherit evidence-pack memory but not stale pending
    tool calls, exhausted round counters, or old assistant drafts. Those are
    run-scoped, not session-scoped.
    """
    if not workspace_payload:
        return None

    prior_workspace = Workspace.from_dict(workspace_payload)
    return Workspace(
        evidence_packs=dict(prior_workspace.evidence_packs),
        opened_pack_ids=list(prior_workspace.opened_pack_ids),
        snapshot_fingerprint=prior_workspace.snapshot_fingerprint,
    ).to_dict()


def evidence_from_workspace(
    workspace: Workspace,
    base_evidence: list[EvidenceItem],
    interaction_locale: str = "zh",
) -> list[EvidenceItem]:
    """Merge tool-discovered evidence packs into the frontend evidence list."""
    seen_ids = {evidence.evidence_id for evidence in base_evidence}
    merged = list(base_evidence)
    opened_pack_ids = set(workspace.opened_pack_ids)

    for pack in workspace.evidence_packs.values():
        evidence_id = f"pack_{pack.pack_id}"
        if evidence_id in seen_ids:
            continue
        seen_ids.add(evidence_id)

        source_type = "evidence_pack"
        source_ref: dict[str, Any] = {}
        if pack.source_refs:
            first_ref = pack.source_refs[0]
            ref_type = first_ref.get("type", "")
            if ref_type == "chapter":
                source_type = "chapter_excerpt"
                source_ref = {
                    "chapter_id": first_ref.get("chapter_id"),
                    "chapter_number": first_ref.get("chapter_number"),
                    "start_pos": first_ref.get("start_pos", 0),
                    "end_pos": first_ref.get("end_pos", 0),
                }
            elif ref_type == "entity":
                source_type = "world_entity"
                source_ref = {"entity_id": first_ref.get("id")}
            elif ref_type == "relationship":
                source_type = "world_relationship"
                source_ref = {"relationship_id": first_ref.get("id")}
            elif ref_type == "system":
                source_type = "world_system"
                source_ref = {"system_id": first_ref.get("id")}

        merged.append(EvidenceItem(
            evidence_id=evidence_id,
            source_type=source_type,
            source_ref=source_ref,
            title=", ".join(pack.anchor_terms[:3]) or pack.pack_id,
            excerpt=pack.expanded_text or pack.preview_excerpt,
            why_relevant=(
                _workspace_text(
                    interaction_locale,
                    CopilotTextKey.WORKSPACE_EVIDENCE_COMPILED_MULTIPLE,
                    count=pack.support_count,
                )
                if pack.support_count and pack.support_count > 1
                else _workspace_text(interaction_locale, CopilotTextKey.WORKSPACE_EVIDENCE_COMPILED)
            ),
            pack_id=pack.pack_id,
            source_refs=list(pack.source_refs),
            anchor_terms=list(pack.anchor_terms),
            support_count=pack.support_count,
            preview_excerpt=pack.preview_excerpt,
            expanded=pack.pack_id in opened_pack_ids,
        ))

    return merged[:MAX_EVIDENCE_ITEMS * 2]
