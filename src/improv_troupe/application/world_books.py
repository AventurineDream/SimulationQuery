"""Deterministic, privacy-aware world-book activation."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain import WorldBook, WorldBookEntry


@dataclass(frozen=True)
class ActiveLoreEntry:
    entry_id: str
    name: str
    content: str
    position: str


class WorldBookEngine:
    """Resolve relevant lore without asking a model or leaking private entries."""

    def activate(
        self,
        books: tuple[WorldBook, ...],
        *,
        text: str,
        recipient: str,
        is_director: bool = False,
    ) -> tuple[ActiveLoreEntry, ...]:
        active: list[tuple[int, int, WorldBookEntry]] = []
        for book in books:
            scan = "\n".join(text.splitlines()[-book.scan_depth :])
            selected: list[WorldBookEntry] = []
            for entry in book.entries:
                if not entry.enabled or not self._visible(entry, recipient, is_director):
                    continue
                if entry.constant or self._matches(entry, scan):
                    selected.append(entry)
            if book.recursive_scanning:
                expanded = scan + "\n" + "\n".join(item.content for item in selected)
                for entry in book.entries:
                    if entry not in selected and entry.enabled and self._visible(entry, recipient, is_director) and self._matches(entry, expanded):
                        selected.append(entry)
            budget = book.token_budget
            for entry in sorted(selected, key=lambda item: (item.insertion_order, -item.priority, item.entry_id)):
                cost = max(1, len(entry.content.split()))
                if cost > budget:
                    continue
                active.append((entry.insertion_order, -entry.priority, entry))
                budget -= cost
        return tuple(
            ActiveLoreEntry(item.entry_id, item.name, item.content, item.position)
            for _, _, item in sorted(active, key=lambda value: (value[0], value[1], value[2].entry_id))
        )

    @staticmethod
    def _visible(entry: WorldBookEntry, recipient: str, is_director: bool) -> bool:
        if entry.visibility == "DIRECTOR_ONLY":
            return is_director
        if entry.visibility == "CHARACTER_PRIVATE":
            return recipient in entry.character_ids
        return True

    @staticmethod
    def _matches(entry: WorldBookEntry, text: str) -> bool:
        haystack = text if entry.case_sensitive else text.casefold()
        keys = entry.keys if entry.case_sensitive else [key.casefold() for key in entry.keys]
        secondary = entry.secondary_keys if entry.case_sensitive else [key.casefold() for key in entry.secondary_keys]
        primary_hit = any(key and key in haystack for key in keys)
        return primary_hit and (not entry.selective or any(key and key in haystack for key in secondary))


__all__ = ["ActiveLoreEntry", "WorldBookEngine"]
