"""Kaworai DB-dan ma'lumot olish: anime title list + seriya (qism) mavjudligi."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy import text

from config import settings
from kaworai.engine import get_session

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnimeRow:
    id: int
    title: str


_cache: list[AnimeRow] = []
_cache_ts: float = 0.0


async def get_animes(force: bool = False) -> list[AnimeRow]:
    """Barcha animelarni qaytaradi (ID + title). Keshlanadi."""
    global _cache, _cache_ts
    now = time.monotonic()
    if not force and _cache and (now - _cache_ts) < settings.ANIME_CACHE_TTL:
        return _cache

    sess = get_session()
    if sess is None:
        return []
    try:
        async with sess as s:
            result = await s.execute(text("SELECT id, title FROM animes ORDER BY LENGTH(title) DESC"))
            rows = [AnimeRow(id=int(r[0]), title=str(r[1])) for r in result.all() if r[1]]
    except Exception as exc:
        log.warning("Kaworai DB so'rovida xato: %s", exc)
        return _cache  # eski kesh saqlansin

    _cache = rows
    _cache_ts = now
    log.info("Kaworai anime keshi yangilandi: %d ta", len(rows))
    return rows


async def get_anime_by_id(anime_id: int) -> AnimeRow | None:
    sess = get_session()
    if sess is None:
        return None
    try:
        async with sess as s:
            result = await s.execute(
                text("SELECT id, title FROM animes WHERE id = :aid"),
                {"aid": anime_id},
            )
            row = result.first()
            if row is None:
                return None
            return AnimeRow(id=int(row[0]), title=str(row[1]))
    except Exception as exc:
        log.warning("Kaworai DB get_anime_by_id xato: %s", exc)
        return None


async def search_animes(query: str, limit: int = 15) -> list[AnimeRow]:
    """ILIKE asosida qidirish — kichik-katta harf farq qilmaydi."""
    query = (query or "").strip()
    if not query:
        return []
    sess = get_session()
    if sess is None:
        # Fallback: keshdan
        all_rows = await get_animes()
        q = query.lower()
        hits = [a for a in all_rows if q in a.title.lower()][:limit]
        return hits
    try:
        async with sess as s:
            result = await s.execute(
                text("SELECT id, title FROM animes WHERE title ILIKE :q ORDER BY title LIMIT :lim"),
                {"q": f"%{query}%", "lim": limit},
            )
            return [AnimeRow(id=int(r[0]), title=str(r[1])) for r in result.all()]
    except Exception as exc:
        log.warning("Kaworai DB search_animes xato: %s", exc)
        return []


async def episode_exists(anime_id: int, episode: int) -> bool:
    """series jadvalida (anime_id, episode) bor-yo'qligini tekshirish."""
    sess = get_session()
    if sess is None:
        return False
    try:
        async with sess as s:
            result = await s.execute(
                text("SELECT 1 FROM series WHERE anime_id = :aid AND episode = :ep LIMIT 1"),
                {"aid": anime_id, "ep": episode},
            )
            return result.first() is not None
    except Exception as exc:
        log.warning("Kaworai DB episode_exists xato: %s", exc)
        return False
