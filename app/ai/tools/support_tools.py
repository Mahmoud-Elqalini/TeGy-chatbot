from __future__ import annotations
import uuid
import logging
from typing import Union
from app.ai.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

@ToolRegistry.register_tool(
    name="report_support_issue",
    description="report_support_issue(issue_category, description, priority) -> opens a support case for the user (for technical, payment, or general issues)",
    parameters={
        "type": "object",
        "properties": {
            "issue_category": {
                "type": "string", 
                "description": "Category of the issue: 'technical', 'billing', or 'general'"
            },
            "description": {
                "type": "string",
                "description": "Detailed description of the user's problem"
            },
            "priority": {
                "type": "string",
                "description": "Priority level: 'low', 'medium', or 'high'"
            }
        },
        "required": ["issue_category", "description"]
    },
    metadata={"category": "support"}
)
async def report_support_issue(
    issue_category: str,
    description: str,
    priority: str = "medium",
    user_id: Union[str, uuid.UUID] = None,
    **kwargs
):
    """Mock function to simulate opening a support case."""
    if user_id is None:
        logger.warning("report_support_issue called without user_id")
        user_id = "anonymous"
        
    # Generate a mock issue ID
    issue_id = f"ISSUE-{str(uuid.uuid4())[:8].upper()}"
    
    logger.info(f"Created support issue {issue_id} for user {user_id}: {issue_category} - {priority}")
    
    return {
        "status": "success",
        "issue_id": issue_id,
        "message": f"Support case {issue_id} has been opened successfully. Our team will review it shortly."
    }
