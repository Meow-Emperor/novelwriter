# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Protocol, Sequence

from app.language_policy import (
    DEFAULT_CJK_SPACE_RATIO_THRESHOLD,
    detect_language_from_text,
    get_language_policy,
    resolve_text_processing_language,
)

from .window_index import NovelIndex, WindowRef

try:
    import ahocorasick
except ImportError:  # pragma: no cover - local fallback when dependency is missing
    ahocorasick = None

try:
    import jieba
except ImportError:  # pragma: no cover - local fallback when dependency is missing
    jieba = None


DEFAULT_WINDOW_SIZE = 500
DEFAULT_WINDOW_STEP = 250
DEFAULT_MIN_WINDOW_COUNT = 3
DEFAULT_MIN_WINDOW_RATIO = 0.005
DEFAULT_COMMON_WORDS_DIR = "data/common_words"

_COMMON_WORD_FILE_BY_LANGUAGE = {
    "zh": "zh.txt",
    "en": "en.txt",
}
_COMMON_WORDS_CACHE: dict[tuple[str, str], frozenset[str]] = {}
_COMMON_WORDS_COMBINED_CACHE: dict[tuple[str, str], frozenset[str]] = {}
_TRIM_CHARS = " \t\r\n.,!?;:\"'()[]{}<>，。！？；：、“”‘’（）【】《》、…·-—"


@dataclass(slots=True)
class ChapterText:
    chapter_id: int
    text: str


class Tokenizer(Protocol):
    def tokenize(self, text: str) -> list[str]: ...


class WhitespaceTokenizer:
    def tokenize(self, text: str) -> list[str]:
        return text.split()


class CharacterNgramTokenizer:
    def __init__(self, *, n: int = 2):
        self.n = max(2, int(n))

    def tokenize(self, text: str) -> list[str]:
        cleaned = "".join(ch if ch not in _TRIM_CHARS else " " for ch in text)
        chunks = [chunk for chunk in cleaned.split() if chunk]
        tokens: list[str] = []
        for chunk in chunks:
            if len(chunk) < 2:
                continue
            if len(chunk) <= self.n:
                tokens.append(chunk)
                continue
            tokens.extend(
                chunk[i : i + self.n] for i in range(0, len(chunk) - self.n + 1)
            )
        return tokens


class JiebaTokenizer:
    def tokenize(self, text: str) -> list[str]:
        if jieba is None:
            return CharacterNgramTokenizer(n=2).tokenize(text)
        return [token for token in jieba.lcut(text) if token]


def detect_language(
    text: str,
    *,
    cjk_space_ratio_threshold: float = DEFAULT_CJK_SPACE_RATIO_THRESHOLD,
) -> str:
    return detect_language_from_text(
        text, cjk_space_ratio_threshold=cjk_space_ratio_threshold
    )


def get_tokenizer(
    language: str,
    *,
    cjk_tokenizer: Tokenizer | None = None,
    cjk_ngram_tokenizer: Tokenizer | None = None,
    whitespace_tokenizer: Tokenizer | None = None,
) -> Tokenizer:
    policy = get_language_policy(language)
    if policy.tokenizer_kind == "jieba":
        return cjk_tokenizer or JiebaTokenizer()
    if policy.tokenizer_kind == "cjk_bigram":
        return cjk_ngram_tokenizer or CharacterNgramTokenizer(n=2)
    return whitespace_tokenizer or WhitespaceTokenizer()


def tokenize_text(
    text: str,
    *,
    language: str | None = None,
    tokenizer: Tokenizer | None = None,
) -> tuple[str, list[str]]:
    resolved_language = resolve_text_processing_language(language, sample_text=text)
    resolved_tokenizer = tokenizer or get_tokenizer(resolved_language)
    return resolved_language, resolved_tokenizer.tokenize(text)


def _resolve_common_words_base_dir(common_words_dir: str) -> Path:
    base_dir = Path(common_words_dir)
    if not base_dir.is_absolute():
        base_dir = Path(__file__).resolve().parents[3] / base_dir
    return base_dir.resolve()


def _load_common_words_file(file_path: Path, language_code: str) -> frozenset[str]:
    cache_key = (str(file_path), language_code)
    cached = _COMMON_WORDS_CACHE.get(cache_key)
    if cached is not None:
        return cached

    if not file_path.exists():
        raise FileNotFoundError(f"Common words file does not exist: {file_path}")

    words: set[str] = set()
    with file_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            word = raw_line.strip()
            if not word or word.startswith("#"):
                continue
            normalized_word = get_language_policy(language_code).normalize_for_matching(
                word
            )
            words.add(word)
            words.add(normalized_word)

    frozen_words = frozenset(words)
    _COMMON_WORDS_CACHE[cache_key] = frozen_words
    return frozen_words


def load_common_words(
    language: str,
    *,
    common_words_dir: str = DEFAULT_COMMON_WORDS_DIR,
) -> set[str]:
    policy = get_language_policy(language)
    normalized_language = policy.common_words_bucket
    base_dir = _resolve_common_words_base_dir(common_words_dir)
    combined_cache_key = (str(base_dir), normalized_language)
    cached = _COMMON_WORDS_COMBINED_CACHE.get(combined_cache_key)
    if cached is not None:
        return set(cached)

    fallback_language = "en" if normalized_language == "zh" else "zh"
    primary_words = _load_common_words_file(
        base_dir / _COMMON_WORD_FILE_BY_LANGUAGE[normalized_language],
        normalized_language,
    )
    fallback_words = _load_common_words_file(
        base_dir / _COMMON_WORD_FILE_BY_LANGUAGE[fallback_language],
        fallback_language,
    )
    merged = frozenset(set(primary_words) | set(fallback_words))
    _COMMON_WORDS_COMBINED_CACHE[combined_cache_key] = merged
    return set(merged)


def extract_candidates(
    tokens: Sequence[str],
    common_words: set[str],
    *,
    language: str | None = None,
) -> dict[str, int]:
    policy = get_language_policy(language)
    counts: Counter[str] = Counter()
    for token in tokens:
        normalized = policy.normalize_token(token)
        if len(normalized) < 2:
            continue
        match_key = policy.normalize_for_matching(normalized)
        if normalized in common_words or match_key in common_words:
            continue
        counts[normalized] += 1
    return dict(counts)


def _window_offsets(text_length: int, window_size: int, window_step: int) -> list[int]:
    if text_length <= 0:
        return []
    if text_length <= window_size:
        return [0]

    offsets = list(range(0, max(text_length - window_size + 1, 1), window_step))
    last_start = text_length - window_size
    if offsets and offsets[-1] != last_start:
        offsets.append(last_start)
    return offsets


def _build_automaton(candidate_names: Sequence[str]):
    if ahocorasick is None:
        return None

    automaton = ahocorasick.Automaton()
    for name in candidate_names:
        if name:
            automaton.add_word(name, name)
    automaton.make_automaton()
    return automaton


def _match_candidates_in_window(
    window_text: str, candidate_names: Sequence[str], automaton
) -> set[str]:
    if not window_text:
        return set()

    if automaton is not None:
        matches: set[str] = set()
        for _, candidate in automaton.iter(window_text):
            matches.add(candidate)
        return matches

    return {candidate for candidate in candidate_names if candidate in window_text}


def build_window_index(
    chapters: Sequence[ChapterText],
    candidates: dict[str, int],
    *,
    window_size: int = DEFAULT_WINDOW_SIZE,
    window_step: int = DEFAULT_WINDOW_STEP,
    min_window_count: int = DEFAULT_MIN_WINDOW_COUNT,
    min_window_ratio: float = DEFAULT_MIN_WINDOW_RATIO,
    use_automaton: bool = True,
) -> tuple[NovelIndex, dict[str, int]]:
    if window_size <= 0 or window_step <= 0:
        raise ValueError("Window size and step must be positive")
    if min_window_count < 1:
        raise ValueError("min_window_count must be >= 1")
    if min_window_ratio < 0:
        raise ValueError("min_window_ratio must be >= 0")

    candidate_names = [name for name in candidates if name]
    if not candidate_names or not chapters:
        return NovelIndex(), {}

    automaton = _build_automaton(candidate_names) if use_automaton else None

    entity_windows_raw: dict[str, list[WindowRef]] = defaultdict(list)
    window_entities_raw: dict[int, set[str]] = defaultdict(set)
    importance_counter: Counter[str] = Counter()

    total_windows = 0
    window_id = 1

    for chapter in chapters:
        chapter_text = chapter.text or ""
        if not chapter_text.strip():
            continue
        for start_pos in _window_offsets(len(chapter_text), window_size, window_step):
            end_pos = min(start_pos + window_size, len(chapter_text))
            window_text = chapter_text[start_pos:end_pos]
            total_windows += 1

            present_candidates = _match_candidates_in_window(
                window_text, candidate_names, automaton
            )
            if not present_candidates:
                window_id += 1
                continue

            entity_count = len(present_candidates)
            for candidate in present_candidates:
                ref = WindowRef(
                    window_id=window_id,
                    chapter_id=chapter.chapter_id,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    entity_count=entity_count,
                )
                entity_windows_raw[candidate].append(ref)
                window_entities_raw[window_id].add(candidate)
                importance_counter[candidate] += 1
            window_id += 1

    if total_windows == 0:
        return NovelIndex(), {}

    threshold = max(min_window_count, math.ceil(total_windows * min_window_ratio))

    filtered_entity_windows: dict[str, list[WindowRef]] = {}
    filtered_window_entities: dict[int, set[str]] = defaultdict(set)
    filtered_importance: dict[str, int] = {}

    for candidate, count in importance_counter.items():
        if count < threshold:
            continue
        windows = sorted(
            entity_windows_raw[candidate],
            key=lambda ref: (-ref.entity_count, ref.window_id),
        )
        filtered_entity_windows[candidate] = windows
        filtered_importance[candidate] = count
        for window_ref in windows:
            filtered_window_entities[window_ref.window_id].add(candidate)

    return (
        NovelIndex(
            entity_windows=filtered_entity_windows,
            window_entities=dict(filtered_window_entities),
        ),
        filtered_importance,
    )


def compute_cooccurrence(index: NovelIndex) -> list[tuple[str, str, int]]:
    pair_counts: Counter[tuple[str, str]] = Counter()
    for entities in index.window_entities.values():
        if len(entities) < 2:
            continue
        for left, right in combinations(sorted(entities), 2):
            pair_counts[(left, right)] += 1

    return sorted(
        [(left, right, count) for (left, right), count in pair_counts.items()],
        key=lambda item: (-item[2], item[0], item[1]),
    )


__all__ = [
    "ChapterText",
    "Tokenizer",
    "WhitespaceTokenizer",
    "CharacterNgramTokenizer",
    "JiebaTokenizer",
    "detect_language",
    "get_tokenizer",
    "tokenize_text",
    "load_common_words",
    "extract_candidates",
    "build_window_index",
    "compute_cooccurrence",
]
