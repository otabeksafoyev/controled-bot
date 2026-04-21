"""Pure-logic helpers for parsing episode numbers and titles from captions."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Tartib muhim: avval aniqroq namunalar.
_EPISODE_PATTERNS = [
    re.compile(r"(?:^|\s|#)(?:qism|seri[yj]a|episode|epizod|ep|e)\s*[.#_-]?\s*(\d{1,4})", re.IGNORECASE),
    re.compile(r"(\d{1,4})\s*(?:-?\s*)(?:qism|seri[yj]a|episode|epizod)", re.IGNORECASE),
    re.compile(r"[Ss](\d{1,3})[Ee](\d{1,4})"),
    re.compile(r"\bE(\d{2,4})\b"),
]

# Anime nomi odatda qism raqamidan oldin keladi. Kerak bo'lsa shu regex ishlatiladi.
_TITLE_EPISODE_RE = re.compile(
    r"^(?P<title>.+?)\s*[-—–|]\s*(?:qism|seri[yj]a|episode|epizod|ep|e)\s*[.#_-]?\s*(?P<ep>\d{1,4})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedMeta:
    episode: int | None
    title: str | None


def parse_episode(text: str | None) -> int | None:
    """Mumkin bo'lsa qism raqamini qaytaradi."""
    if not text:
        return None
    for pat in _EPISODE_PATTERNS:
        m = pat.search(text)
        if m:
            # S01E12 ko'rinishida — oxirgi guruhni olish
            return int(m.group(m.lastindex or 1))
    # Sof raqam: "12" yoki "12 qism" xavfli — faqat alohida so'z bo'lsa
    m = re.fullmatch(r"\s*(\d{1,4})\s*", text)
    if m:
        return int(m.group(1))
    return None


def parse_title(text: str | None) -> str | None:
    if not text:
        return None
    m = _TITLE_EPISODE_RE.match(text.strip())
    if m:
        return m.group("title").strip().strip("\"'«»“”")
    # Birinchi qatordan sarlavha sifatida foydalanish (fallback)
    first_line = text.strip().splitlines()[0].strip()
    # Qism belgisini o'chirish
    cleaned = re.sub(
        r"[-—–|]?\s*(?:qism|seri[yj]a|episode|epizod|ep|e)\s*[.#_-]?\s*\d{1,4}.*$",
        "",
        first_line,
        flags=re.IGNORECASE,
    ).strip("\"'«»“” -—–|")
    return cleaned or None


def parse_meta(text: str | None) -> ParsedMeta:
    return ParsedMeta(episode=parse_episode(text), title=parse_title(text))
