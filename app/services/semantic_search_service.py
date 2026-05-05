import httpx
from typing import Dict, Any
from app.core.config import settings
from app.core.observability import get_logger

logger = get_logger(__name__)

class SemanticSearchService:
    """
    Service responsible for interacting with the external Semantic Search API asynchronously.
    """
    
    @staticmethod
    async def search(q: str, limit: int = 8) -> Dict[str, Any]:
        """
        Calls the semantic search API.
        
        Args:
            q: The search query.
            limit: The maximum number of results to return.
            
        Returns:
            A dictionary containing the search results and metadata.
        """
        if not q or not q.strip():
            return {"error": "Missing search query"}
            
        limit = max(1, min(limit, 30))
        
        url = settings.SEMANTIC_SEARCH_API_URL
        
        try:
            logger.info("semantic_search.api.request", query=q, limit=limit)
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json={"q": q.strip(), "limit": limit}
                )
                response.raise_for_status()
                
                data = response.json()
                logger.info("semantic_search.api.success", hits_count=len(data.get("hits", [])))
                return data
                
        except httpx.HTTPStatusError as e:
            logger.error("semantic_search.api.http_error", status_code=e.response.status_code, error=str(e))
            raise
        except httpx.RequestError as e:
            logger.error("semantic_search.api.request_error", url=url, error=str(e))
            raise
