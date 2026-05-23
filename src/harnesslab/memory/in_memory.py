from __future__ import annotations


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def put(self, key: str, value: str) -> None:
        self._data[key] = value

    def get(self, key: str) -> str | None:
        return self._data.get(key)

