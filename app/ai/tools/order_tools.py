from __future__ import annotations
from typing import Union, Optional, Any, List, Dict
"""
Order-related tools for the AI chatbot.
"""
import uuid
from app.ai.tool_registry import ToolRegistry


@ToolRegistry.register_tool(
    name="search_orders",
    description="search_orders() -> returns past user orders and their details",
    parameters={"type": "object", "properties": {}},
    metadata={"category": "orders"}
)
async def search_orders(user_id: Union[str, uuid.UUID] = None, main_db: Any = None, **kwargs):
    """Fetches user orders from the Main Database."""
    from sqlalchemy import text
    
    if user_id is None:
        return {"error": "Internal Error: user_id not injected."}
    if main_db is None:
        return {"error": "Internal Error: main_db not injected."}
        
    try:
        user_str = str(user_id)
        query = text("""
            SELECT o.Id as order_id, o.Status, o.Price as amount, o.CreatedAt as created_at,
                   e.Id as event_id, e.Title as event_name, e.StartDate as start_date
            FROM Orders o
            LEFT JOIN Events e ON o.EventId = e.Id
            WHERE o.UserId = :uid
            ORDER BY o.CreatedAt DESC
        """)
        result = await main_db.execute(query, {"uid": user_str})
        
        orders = []
        for row in result:
            orders.append({
                "order_id": row.order_id,
                "status": row.Status,
                "amount": float(row.amount) if row.amount is not None else 0.0,
                "event_id": row.event_id,
                "event_name": row.event_name,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "start_date": row.start_date.isoformat() if row.start_date else None,
            })
            
        if not orders:
            return {"message": "لا توجد حجوزات سابقة لك في النظام."}
            
        return {"orders": orders}
        
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(f"Error fetching orders: {exc}")
        return {"error": "Failed to fetch orders from database."}