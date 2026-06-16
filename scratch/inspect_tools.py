import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from app.ai.tool_registry import ToolRegistry
from app.ai.tools import discover_and_register
import json

async def main():
    discover_and_register()
    registry = ToolRegistry()
    tools = registry.get_tool_definitions()
    total_size = 0
    for t in tools:
        schema_json = json.dumps(t)
        tokens = len(schema_json) // 4
        total_size += tokens
        name = t.get('name') or t.get('function', {}).get('name') or 'unknown'
        print(f"Tool: {name} - Size: {len(schema_json)} bytes (~{tokens} tokens)")

    print(f"\nTotal tools: {len(tools)}")
    print(f"Total tokens for tools: {total_size}")
    
if __name__ == "__main__":
    asyncio.run(main())
