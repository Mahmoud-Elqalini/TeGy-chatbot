from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Optional, Union, Dict, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai.providers.base import LLMProvider

logger = logging.getLogger(__name__)

class ProviderRegistry:
    _providers: Dict[str, Type[LLMProvider]] = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a provider class."""
        def wrapper(provider_cls: Type[LLMProvider]):
            cls._providers[name.lower()] = provider_cls
            return provider_cls
        return wrapper

    @classmethod
    def get(cls, name: str) -> Type[LLMProvider] | None:
        """Get a provider class by name."""
        return cls._providers.get(name.lower())

    @classmethod
    def get_all_names(cls) -> list[str]:
        """Get all registered provider names."""
        return list(cls._providers.keys())

def register_provider(name: str):
    """Convenience decorator alias."""
    return ProviderRegistry.register(name)

def discover_providers() -> None:
    """
    Dynamically discover and import all modules in the current package
    to trigger @register_provider decorators.
    """
    import app.ai.providers as providers_pkg
    
    package_path = providers_pkg.__path__
    prefix = providers_pkg.__name__ + "."

    for _, module_name, is_pkg in pkgutil.iter_modules(package_path, prefix):
        if is_pkg:
            continue
        
        # Skip base, registry, factory, and resilience to avoid circular imports or redundant loads
        if module_name.split(".")[-1] in {"base", "registry", "factory", "resilience"}:
            continue
            
        try:
            importlib.import_module(module_name)
            logger.debug(f"Discovered and loaded provider module: {module_name}")
        except Exception as e:
            logger.error(f"Failed to load provider module {module_name}: {e}")
