from __future__ import annotations

from typing import Iterable

from .memory_base import BaseMemoryExtractor


class ExtractorRegistry:
    def __init__(self, extractors: Iterable[BaseMemoryExtractor] | None = None) -> None:
        self._extractors: dict[str, BaseMemoryExtractor] = {}
        for extractor in extractors or []:
            self.register(extractor)

    def register(self, extractor: BaseMemoryExtractor) -> None:
        self._extractors[extractor.code] = extractor

    def get(self, code: str) -> BaseMemoryExtractor:
        extractor = self._extractors.get(code)
        if extractor is None:
            raise KeyError(code)
        return extractor

    def list_all(self) -> list[BaseMemoryExtractor]:
        return list(self._extractors.values())
