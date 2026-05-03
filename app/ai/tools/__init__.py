"""
Auto-discovery module for AI tools.
Scans all *_tools.py files in this package and registers them with the ToolRegistry.
"""
import importlib
import logging
import pkgutil

logger = logging.getLogger(__name__)


def discover_and_register(tool_registry) -> None:
    """
    Auto-discovers all tool modules in the app/ai/tools package
    and calls their register() function to register tools with the registry.
    """
    package = importlib.import_module("app.ai.tools")
    
    for importer, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if module_name.startswith("_"):
            continue
        
        module = importlib.import_module(f"app.ai.tools.{module_name}")
        
        if hasattr(module, "register"):
            module.register(tool_registry)
            logger.info(f"Registered tools from: {module_name}")
        else:
            logger.warning(f"Tool module {module_name} has no register() function, skipping.")
