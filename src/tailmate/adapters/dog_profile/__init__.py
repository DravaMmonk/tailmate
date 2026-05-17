"""Adapters for the dog_profile slice."""

from tailmate.adapters.dog_profile.db_adapter import (
    DatabaseDogProfileDBAdapter,
    ProfileMutation,
    apply_extraction_result,
)
from tailmate.adapters.dog_profile.extractors import (
    BreedMatcher,
    CompositeExtractor,
    GeminiStructuredExtractorClient,
    LLMFlashExtractor,
    LLMProExtractor,
    RuleBasedExtractor,
    detect_dog_name,
    looks_like_dog_profile_trigger,
)

__all__ = [
    "BreedMatcher",
    "CompositeExtractor",
    "DatabaseDogProfileDBAdapter",
    "GeminiStructuredExtractorClient",
    "LLMFlashExtractor",
    "LLMProExtractor",
    "ProfileMutation",
    "RuleBasedExtractor",
    "apply_extraction_result",
    "detect_dog_name",
    "looks_like_dog_profile_trigger",
]
