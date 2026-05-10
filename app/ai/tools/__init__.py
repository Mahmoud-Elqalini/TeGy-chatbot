from __future__ import annotations
"""
Auto-discovery module for AI tools.
Scans all *_tools.py files in this package and registers them with the ToolRegistry.
"""
import importlib
import logging
import pkgutil

logger = logging.getLogger(__name__)


def discover_and_register() -> None:
    """
    Auto-discovers all tool modules in the app/ai/tools package.
    Importing the modules triggers the @ToolRegistry.register_tool decorators.
    
    IMPORTANT: This must be called BEFORE instantiating ToolRegistry to ensure
    the global catalog is populated.
    """
    from app.ai.tool_registry import _GLOBAL_TOOL_CATALOG
    
    package = importlib.import_module("app.ai.tools")
    discovered_modules_count = 0
    failed_modules = []
    
    for importer, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if module_name.startswith("_") or is_pkg:
            continue
        
        full_module_name = f"app.ai.tools.{module_name}"
        try:
            # Before import
            tools_before = set(_GLOBAL_TOOL_CATALOG.keys())
            
            importlib.import_module(full_module_name)
            discovered_modules_count += 1
            
            # After import - see what tools were added
            tools_after = set(_GLOBAL_TOOL_CATALOG.keys())
            new_tools = tools_after - tools_before
            
            if new_tools:
                logger.info(f"Discovered module '{module_name}': registered tools -> {', '.join(new_tools)}")
            else:
                logger.warning(f"Module '{module_name}' was loaded but registered no tools.")
                
        except Exception as e:
            logger.error(f"Failed to load tool module {module_name}: {e}")
            failed_modules.append(module_name)

    if failed_modules:
        logger.warning(f"Some tool modules failed to load: {', '.join(failed_modules)}")
    
    logger.info(
        f"Auto-discovery complete. "
        f"Loaded {discovered_modules_count} modules, "
        f"{len(_GLOBAL_TOOL_CATALOG)} tools registered total."
    )
