from __future__ import annotations

DEFAULT_LANGUAGE = "zh"
DEFAULT_COPILOT_INTERACTION_LOCALE = "zh"
SUPPORTED_COPILOT_INTERACTION_LOCALES = ("zh", "en")


def normalize_language_code(value: str | None, *, default: str | None = DEFAULT_LANGUAGE) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return default

    normalized = raw.replace("_", "-")
    parts = [part.strip().lower() for part in normalized.split("-") if part.strip()]
    if not parts:
        return default
    return "-".join(parts)


def get_language_fallback_chain(
    locale: str | None,
    *,
    default: str | None = DEFAULT_LANGUAGE,
) -> tuple[str, ...]:
    candidates: list[str] = []

    normalized = normalize_language_code(locale, default=None)
    if normalized:
        candidates.append(normalized)
        primary = normalized.split("-", 1)[0]
        if primary and primary != normalized:
            candidates.append(primary)

    normalized_default = normalize_language_code(default, default=None)
    if normalized_default:
        candidates.append(normalized_default)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return tuple(deduped)


def resolve_supported_locale(
    locale: str | None,
    *,
    supported: tuple[str, ...],
    default: str,
) -> str:
    normalized_supported = tuple(
        candidate
        for candidate in (
            normalize_language_code(item, default=None)
            for item in supported
        )
        if candidate
    )

    for candidate in get_language_fallback_chain(locale, default=None):
        if candidate in normalized_supported:
            return candidate

    normalized_default = normalize_language_code(default, default=None)
    if normalized_default and normalized_default in normalized_supported:
        return normalized_default
    if normalized_supported:
        return normalized_supported[0]
    return normalize_language_code(default, default=DEFAULT_LANGUAGE) or DEFAULT_LANGUAGE


def normalize_copilot_interaction_locale(locale: str | None) -> str:
    return resolve_supported_locale(
        locale,
        supported=SUPPORTED_COPILOT_INTERACTION_LOCALES,
        default=DEFAULT_COPILOT_INTERACTION_LOCALE,
    )


def resolve_prompt_locale(
    *,
    novel_language: str | None = None,
    interaction_locale: str | None = None,
    default: str = DEFAULT_LANGUAGE,
) -> str:
    candidates = (
        *get_language_fallback_chain(novel_language, default=None),
        *get_language_fallback_chain(interaction_locale, default=None),
        *get_language_fallback_chain(default, default=None),
    )
    for candidate in candidates:
        if candidate:
            return candidate
    return DEFAULT_LANGUAGE
