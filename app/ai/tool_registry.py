from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

@dataclass
class ToolDefinition:
    """
    Represents the definition of a tool that the AI can call.
    It includes the tool's name, purpose, input parameters, and the actual function to run.
    """
    name: str
    description: str
    parameters: Dict[str, Any]
    func: Callable[..., Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

# Global catalog to store tools registered via decorators
_GLOBAL_TOOL_CATALOG: Dict[str, ToolDefinition] = {}

def _validate_tool_schema(name: str, parameters: Dict[str, Any]):
    """
    Validates that the tool parameters follow a basic JSON schema structure.
    """
    if not isinstance(parameters, dict):
        raise ValueError(f"Tool '{name}' parameters must be a dictionary.")
    
    # Check for valid types (Gemini/OpenAI compatible)
    valid_types = {"object", "string", "integer", "number", "boolean", "array"}
    p_type = parameters.get("type")
    
    if not p_type:
        raise ValueError(f"Tool '{name}' parameters must have a 'type' field.")
    
    if p_type not in valid_types:
        raise ValueError(f"Tool '{name}' has invalid type '{p_type}'. Must be one of {valid_types}.")
    
    if p_type == "object":
        if "properties" not in parameters:
            raise ValueError(f"Tool '{name}' of type 'object' must have a 'properties' field.")
        if not isinstance(parameters["properties"], dict):
            raise ValueError(f"Tool '{name}' properties must be a dictionary.")

class ToolRegistry:
    """
    The ToolRegistry keeps track of all tools available to the AI.
    It allows you to register new tools and execute them when the AI requests it.
    """
    def __init__(self):
        # Clone from global catalog to ensure instance isolation while 
        # supporting auto-discovery via decorators.
        self._tools: Dict[str, ToolDefinition] = dict(_GLOBAL_TOOL_CATALOG)

    @classmethod
    def register_tool(
        cls,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        A class-level decorator to register a function as a tool globally.
        Handles re-registration protection for reloads and collisions.
        """
        def decorator(func: Callable[..., Any]):
            tool_name = name or func.__name__
            tool_desc = description or (func.__doc__.strip() if func.__doc__ else "No description provided.")
            
            # Protection against double registration or naming collisions
            if tool_name in _GLOBAL_TOOL_CATALOG:
                existing = _GLOBAL_TOOL_CATALOG[tool_name]
                if existing.func is not func:
                    # True naming collision
                    raise ValueError(f"Tool name collision: '{tool_name}' is already registered by {existing.func.__module__}.{existing.func.__name__}")
                
                # Same function - likely a module reload (Hot Reload / importlib.reload)
                logger.debug(f"Tool '{tool_name}' re-registered by same function, skipping.")
                return func

            if parameters is None:
                raise ValueError(f"Tool '{tool_name}' must provide 'parameters' schema.")
            
            _validate_tool_schema(tool_name, parameters)
            
            _GLOBAL_TOOL_CATALOG[tool_name] = ToolDefinition(
                name=tool_name,
                description=tool_desc,
                parameters=parameters,
                func=func,
                metadata=metadata or {}
            )
            logger.debug(f"Tool '{tool_name}' registered globally.")
            return func
        return decorator

    def register(self, name: str, description: str, parameters: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None):
        """
        Instance-level registration (for dynamic or instance-specific tools).
        """
        _validate_tool_schema(name, parameters)
        
        def decorator(func: Callable[..., Any]):
            self._tools[name] = ToolDefinition(
                name=name,
                description=description,
                parameters=parameters,
                func=func,
                metadata=metadata or {}
            )
            return func
        return decorator

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Returns a list of all registered tool definitions in a format the AI understands.
        Sanitizes the schema types to uppercase for Gemini compatibility.
        """
        definitions = []
        for tool in self._tools.values():
            # Deep copy to avoid mutating the original tool definition
            params = self._sanitize_schema(tool.parameters)
            definitions.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": params,
            })
        return definitions

    def _sanitize_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitizes the JSON schema by uppercasing 'type' values."""
        if not isinstance(schema, dict):
            return schema
            
        new_schema = dict(schema)
        if "type" in new_schema and isinstance(new_schema["type"], str):
            new_schema["type"] = new_schema["type"].upper()
            
        if "properties" in new_schema and isinstance(new_schema["properties"], dict):
            new_schema["properties"] = {
                k: self._sanitize_schema(v) for k, v in new_schema["properties"].items()
            }
            
        if "items" in new_schema and isinstance(new_schema["items"], dict):
            new_schema["items"] = self._sanitize_schema(new_schema["items"])
            
        return new_schema

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Finds a tool by its name."""
        return self._tools.get(name)

    async def call_tool(
        self,
        name: str,
        runtime_deps: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """
        Executes a specific tool by name with the provided arguments.
        """
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool {name} not found")

        # Merge AI-generated arguments with system-provided dependencies
        if runtime_deps:
            kwargs = {**kwargs, **runtime_deps}
        
        # Check if the tool function is async or normal and run it accordingly.
        if inspect.iscoroutinefunction(tool.func):
            return await tool.func(**kwargs)
        return tool.func(**kwargs)
