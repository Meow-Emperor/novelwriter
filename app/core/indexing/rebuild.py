# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Chapter

from .builder import (
    ChapterText,
    build_window_index,
    compute_cooccurrence,
    extract_candidates,
    load_common_words,
    tokenize_text,
)
from .window_index import NovelIndex


@dataclass(slots=True)
class WindowIndexArtifacts:
    language: str
    tokens: list[str]
    candidates: dict[str, int]
    index: NovelIndex
    importance: dict[str, int]
    cooccurrence_pairs: list[tuple[str, str, int]]


def load_chapter_texts(db: Session, novel_id: int) -> list[ChapterText]:
    rows = (
        db.query(Chapter.id, Chapter.content)
        .filter(Chapter.novel_id == novel_id)
        .order_by(Chapter.chapter_number.asc())
        .all()
    )
    return [
        ChapterText(chapter_id=chapter_id, text=content or "")
        for chapter_id, content in rows
        if (content or "").strip()
    ]


def build_window_index_artifacts(
    chapters: Sequence[ChapterText],
    *,
    novel_language: str | None = None,
    settings: Settings | None = None,
    include_cooccurrence: bool = True,
) -> WindowIndexArtifacts:
    resolved_settings = settings or get_settings()
    if not chapters:
        return WindowIndexArtifacts(
            language=novel_language or "zh",
            tokens=[],
            candidates={},
            index=NovelIndex(),
            importance={},
            cooccurrence_pairs=[],
        )

    combined_text = "\n".join(chapter.text for chapter in chapters)
    language, tokens = tokenize_text(
        combined_text,
        language=novel_language,
    )
    common_words = load_common_words(
        language,
        common_words_dir=resolved_settings.bootstrap_common_words_dir,
    )
    candidates = extract_candidates(tokens, common_words, language=language)
    index, importance = build_window_index(
        chapters,
        candidates,
        window_size=resolved_settings.bootstrap_window_size,
        window_step=resolved_settings.bootstrap_window_step,
        min_window_count=resolved_settings.bootstrap_min_window_count,
        min_window_ratio=resolved_settings.bootstrap_min_window_ratio,
    )
    cooccurrence_pairs = compute_cooccurrence(index) if include_cooccurrence else []
    return WindowIndexArtifacts(
        language=language,
        tokens=tokens,
        candidates=candidates,
        index=index,
        importance=importance,
        cooccurrence_pairs=cooccurrence_pairs,
    )
