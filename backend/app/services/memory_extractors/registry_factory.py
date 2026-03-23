from __future__ import annotations

from .character_dynamic import CharacterDynamicExtractor
from .concept_state import ConceptStateExtractor
from .item_state import ItemStateExtractor
from .organization_state import OrganizationStateExtractor
from .registry import ExtractorRegistry
from .relation import RelationExtractor
from .scene_state import SceneStateExtractor


_DEFAULT_REGISTRY = ExtractorRegistry(
    [
        CharacterDynamicExtractor(),
        RelationExtractor(),
        SceneStateExtractor(),
        OrganizationStateExtractor(),
        ItemStateExtractor(),
        ConceptStateExtractor(),
    ]
)


def get_memory_extractor_registry() -> ExtractorRegistry:
    return _DEFAULT_REGISTRY
