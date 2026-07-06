import time
import logging
import threading
from typing import Optional, Dict, Any, List, Tuple
import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

class SemanticCacheService:
    """
    Thread-safe In-memory Semantic Cache using FAISS and SentenceTransformers.
    - Uses lazy loading to prevent blocking server startup.
    - Stores metadata (timestamp, intent) with bounded size (FIFO eviction).
    - Includes proper concurrency locks, rollback logic, and instance-safe LRU caching.
    
    Known Limitations:
    1. TTL Eviction: Expired entries are skipped during read (lazy TTL) rather than actively 
       deleted from FAISS. This is because FAISS `IndexFlatIP` does not support `remove_ids` natively.
       The memory overhead is negligible since the cache size is hard-capped at 5000 items.
    2. Eviction Failure: If `_evict_oldest()` persistently fails, the cache could theoretically 
       grow beyond `max_size`.
    """
    
    def __init__(self, max_size: int = 5000, eviction_count: int = 1000):
        self.max_size = max_size
        self.eviction_count = eviction_count
        
        self.model = None
        self.index = None
        self.dimension = 384  # Dimension for all-MiniLM-L6-v2
        
        # Concurrency Locks
        self._init_lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._encode_lock = threading.Lock()
        
        # Instance-safe LRU cache for embeddings
        self._query_encode_cache: Dict[str, np.ndarray] = {}
        
        # Structure: list of tuples -> (metadata_dict, vector)
        self._cache_data: List[Tuple[Dict[str, Any], np.ndarray]] = []
        
        self.threshold = settings.SEMANTIC_CACHE_THRESHOLD
        self.ttl_seconds = settings.SEMANTIC_CACHE_TTL_DAYS * 24 * 60 * 60

    def _initialize_if_needed(self):
        """Lazy loads the embedding model and FAISS index with double-checked locking."""
        if self.model is not None:
            return
            
        with self._init_lock:
            if self.model is not None:
                return
                
            logger.info("semantic_cache.initialization_started", extra={"model": "all-MiniLM-L6-v2"})
            try:
                from sentence_transformers import SentenceTransformer
                import faiss
                
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
                self.index = faiss.IndexFlatIP(self.dimension)
                logger.info("semantic_cache.initialization_completed")
            except ImportError as e:
                logger.error("semantic_cache.import_failed", extra={"error": str(e)})
                raise

    def _encode_query(self, query: str) -> np.ndarray:
        """Encodes the query with a simple bounded dict cache to avoid lru_cache method leaks."""
        with self._encode_lock:
            if query in self._query_encode_cache:
                return self._query_encode_cache[query]
            
        vector = self.model.encode([query], normalize_embeddings=True)
        
        with self._encode_lock:
            # Keep encode cache bounded to prevent memory leaks
            if len(self._query_encode_cache) > 1000:
                # Drop the first (oldest) half of items roughly
                keys_to_drop = list(self._query_encode_cache.keys())[:500]
                for k in keys_to_drop:
                    self._query_encode_cache.pop(k, None)
                    
            self._query_encode_cache[query] = vector.copy()
            
        return vector

    def _evict_oldest(self):
        """
        Evicts the oldest items and rebuilds the FAISS index (FIFO eviction).
        Must be called with _cache_lock acquired.
        """
        import faiss
        
        if len(self._cache_data) <= self.max_size:
            return

        logger.info("semantic_cache.eviction_started", extra={"current_size": len(self._cache_data), "evicting": self.eviction_count})
        
        keep_count = self.max_size - self.eviction_count
        new_cache_data = self._cache_data[-keep_count:]
        
        new_index = faiss.IndexFlatIP(self.dimension)
        if new_cache_data:
            vectors = np.vstack([item[1] for item in new_cache_data])
            new_index.add(vectors)
            
        # Atomic swap to prevent desync if vstack or add fails
        self._cache_data = new_cache_data
        self.index = new_index
            
        logger.info("semantic_cache.eviction_completed", extra={"new_size": len(self._cache_data)})

    def search(self, query: str, user_id: Optional[str] = None, expected_intent: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Searches the semantic cache considering user context.
        Uses k=20 to skip expired/invalid entries, intent mismatches, and log near-misses.
        """
        try:
            self._initialize_if_needed()
            
            # CPU-heavy encoding is done OUTSIDE the cache lock to avoid serializing requests
            vector = self._encode_query(query)
            
            with self._cache_lock:
                if not self._cache_data or self.index is None or self.index.ntotal == 0:
                    logger.info("semantic_cache.miss", extra={"reason": "empty_cache"})
                    return None
                    
                # Search top 20 to handle intent filtering, expired items, or tenant mismatches
                similarities, indices = self.index.search(vector, 20)
                
                if len(similarities) == 0 or len(similarities[0]) == 0:
                    logger.info("semantic_cache.miss", extra={"reason": "no_results"})
                    return None

                now = time.time()
                best_near_miss = 0.0

                for i in range(len(indices[0])):
                    idx = indices[0][i]
                    similarity = similarities[0][i]

                    if idx == -1:
                        continue
                        
                    if similarity < self.threshold:
                        if similarity > best_near_miss:
                            best_near_miss = similarity
                        continue

                    metadata, _ = self._cache_data[idx]
                    
                    if user_id and metadata.get("user_id") != user_id:
                        continue
                        
                    if expected_intent and metadata.get("intent") != expected_intent:
                        continue
                    
                    age = now - metadata["timestamp"]
                    if age > self.ttl_seconds:
                        logger.debug("semantic_cache.skipped_expired", extra={"age_seconds": age})
                        continue

                    logger.info("semantic_cache.hit", extra={"similarity": float(similarity), "intent": metadata["intent"]})
                    return metadata

                if best_near_miss > 0:
                    logger.info("semantic_cache.miss", extra={"reason": "below_threshold", "near_miss_similarity": float(best_near_miss)})
                else:
                    logger.info("semantic_cache.miss", extra={"reason": "no_valid_matches"})
                    
                return None
                
        except Exception as e:
            logger.error("semantic_cache.search_failed", extra={"error": str(e)}, exc_info=True)
            return None

    def add(self, query: str, response: str, intent: str, user_id: Optional[str] = None):
        """
        Adds a new response to the semantic cache with strict synchronization.
        """
        try:
            self._initialize_if_needed()
            
            # CPU-heavy encoding is done OUTSIDE the cache lock
            vector = self._encode_query(query)
            
            metadata = {
                "response": response,
                "intent": intent,
                "user_id": user_id,
                "timestamp": time.time()
            }
            
            with self._cache_lock:
                try:
                    self._cache_data.append((metadata, vector[0].copy()))
                    self.index.add(vector)
                except Exception as e:
                    if len(self._cache_data) > self.index.ntotal:
                        self._cache_data.pop()
                    logger.error("semantic_cache.add_failed_sync", extra={"error": str(e)}, exc_info=True)
                    # We log and swallow the exception here (Fail-Silent) to not break the caller
                    return
                    
                logger.info("semantic_cache.store", extra={"cache_size": len(self._cache_data)})
                
                if len(self._cache_data) > self.max_size:
                    try:
                        self._evict_oldest()
                    except Exception as e:
                        logger.error("semantic_cache.eviction_failed", extra={"error": str(e)}, exc_info=True)
                        
        except Exception as e:
            # Catch all other outer errors (like encoding failure) and Fail-Silent
            logger.error("semantic_cache.add_failed", extra={"error": str(e)}, exc_info=True)
