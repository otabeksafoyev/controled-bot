"""Pure-logic helpers for parsing episode + matching anime title in captions."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Qism raqami namunalari. Tartib muhim: avval aniqroqlari.
_EPISODE_PATTERNS = [
    re.compile(
        r"(?:^|[\s\[\(#])(?:qism|seri[yj]a|episode|epizod|ep|e)\s*[.#_-]?\s*(\d{1,4})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d{1,4})\s*(?:-?\s*)(?:qism|seri[yj]a|episode|epizod)",
        re.IGNORECASE,
    ),
    re.compile(r"[Ss](\d{1,3})[Ee](\d{1,4})"),
    re.compile(r"\bE(\d{2,4})\b"),
]

# "Season / Fasl" — faqat fasl ko'rsatilgan bo'lsa qism raqami emas.
_SEASON_ONLY = re.compile(
    r"(?:^|\s)(\d{1,2})[\s\-]*fasl(?!\s*\d)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedMeta:
    episode: int | None
    # "fasl" ko'rsatilgan-u qism raqami yo'q — trailer yoki e'lon
    is_season_only: bool


def parse_episode(text: str | None) -> int | None:
    if not text:
        return None
    for pat in _EPISODE_PATTERNS:
        m = pat.search(text)
        if m:
            return int(m.group(m.lastindex or 1))
    return None


def parse_meta(text: str | None) -> ParsedMeta:
    episode = parse_episode(text)
    is_season_only = False
    if episode is None and text and _SEASON_ONLY.search(text):
        is_season_only = True
    return ParsedMeta(episode=episode, is_season_only=is_season_only)


def _normalize(s: str) -> str:
    """Case fold + NFC. Title matching uchun."""
    if not s:
        return ""
    return unicodedata.normalize("NFC", s).casefold()


def find_anime_match(caption: str, titles: list[tuple[int, str]]) -> tuple[int, str] | None:
    """Caption ichidan anime nomini topish.

    `titles` — (anime_id, title) juftliklari ro'yxati. Caption normalize qilinib,
    har bir anime title-ni substring sifatida qidiradi. Eng uzun moslik g'olib.
    """
    if not caption or not titles:
        return None
    norm_caption = _normalize(caption)
    best: tuple[int, str] | None = None
    best_len = 0
    for anime_id, title in titles:
        norm_title = _normalize(title)
        if not norm_title:
            continue
        if norm_title in norm_caption and len(norm_title) > best_len:
            best = (anime_id, title)
            best_len = len(norm_title)
    return best
