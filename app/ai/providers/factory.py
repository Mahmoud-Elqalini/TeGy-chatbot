from __future__ import annotations

import logging
from typing import List

from app.ai.providers.base import LLMProvider
from app.ai.providers.fallback_provider import FallbackProvider
from app.ai.providers.registry import ProviderRegistry, discover_providers
from app.core.config import settings
from app.core.exceptions import LLMConfigurationError
from app.core.observability import get_logger

logger = get_logger(__name__)

class ProviderFactory:
    # Priority list defining the order of fallback
    # The first available provider in this list will be the primary.
    PRIORITY_LIST = ["groq", "gemini", "openrouter"]

    @classmethod
    def initialize_provider_chain(cls) -> LLMProvider:
        """
        Discovers, filters, and initializes the chain of active AI providers.
        Returns a FallbackProvider or a single LLMProvider.
        Raises LLMConfigurationError if no providers can be initialized.
        """
        # 1. Discover all providers via registry
        discover_providers()
        
        # 2. Check for providers that are registered but missing from PRIORITY_LIST
        registered = ProviderRegistry.get_all_names()
        for name in registered:
            if name not in cls.PRIORITY_LIST:
                logger.warning(f"Provider '{name}' is registered but not in PRIORITY_LIST — it will be ignored")

        active_providers: List[LLMProvider] = []
        
        # 3. Iterate through priority list and instantiate if configured
        for name in cls.PRIORITY_LIST:
            provider_class = ProviderRegistry.get(name)
            if not provider_class:
                logger.warning(f"Provider '{name}' in priority list but not found in registry")
                continue
                
            if cls._is_configured(provider_class):
                try:
                    instance = provider_class()
                    active_providers.append(instance)
                    logger.info(f"Initialized active provider: {name}")
                except Exception as e:
                    logger.error(f"Failed to instantiate provider '{name}': {e}")
            else:
                logger.debug(f"Provider '{name}' skipped: No API key configured")

        # 4. Handle exhaustion
        if not active_providers:
            available = ProviderRegistry.get_all_names()
            raise LLMConfigurationError(
                f"No AI providers could be initialized. "
                f"Check your .env keys. Registered in system: {available}"
            )

        # 5. Wrap in FallbackProvider if more than one
        if len(active_providers) > 1:
            logger.info(f"AI provider chain initialized: {[p.provider_name for p in active_providers]}")
            return FallbackProvider(active_providers)
        
        logger.info(f"Single AI provider initialized: {active_providers[0].provider_name}")
        return active_providers[0]

    @staticmethod
    def _is_configured(provider_class: type[LLMProvider]) -> bool:
        """Checks if the required settings/keys exist for a provider."""
        key_attr = getattr(provider_class, "api_key_setting", None)
        if not key_attr:
            logger.warning(f"Provider class {provider_class.__name__} has no api_key_setting defined")
            return False
            
        return bool(getattr(settings, key_attr, None))
