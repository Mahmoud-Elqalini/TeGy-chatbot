"""
Test Cache Management Operations

Tests for cache cleanup, warming, and statistics gathering.
"""

import pytest
from app.ai.prompt_loader import PromptLoader
from app.services.cache_management import CacheManager


@pytest.mark.asyncio
async def test_cache_stats(redis_client):
    """Test gathering cache statistics."""
    cache_manager = CacheManager(redis_client)
    
    stats = await cache_manager.get_cache_stats()
    
    assert stats is not None
    assert hasattr(stats, 'timestamp')
    assert hasattr(stats, 'redis_stats')
    assert hasattr(stats, 'prompt_stats')
    assert hasattr(stats, 'summary')
    
    print(f"\n📊 Cache Stats: {stats.summary}")


@pytest.mark.asyncio
async def test_cache_health(redis_client):
    """Test cache health check."""
    cache_manager = CacheManager(redis_client)
    
    health = await cache_manager.get_cache_health()
    
    assert health is not None
    assert "status" in health
    assert health["status"] in ["healthy", "degraded", "error"]
    
    print(f"\n❤️  Cache Health: {health}")


@pytest.mark.asyncio
async def test_prompt_cache_operations():
    """Test prompt cache warm and clear operations."""
    # Test warming
    warmed = PromptLoader.load_all()
    assert len(warmed) > 0
    print(f"\n🔥 Warmed {len(warmed)} prompts")
    
    # Test cache access
    cached_names = PromptLoader.cached_names()
    assert len(cached_names) > 0
    print(f"✅ Cached names: {cached_names}")
    
    # Test clear
    PromptLoader.clear_cache()
    assert len(PromptLoader.cached_names()) == 0
    print("🧹 Prompt cache cleared")
    
    # Verify reload works
    warmed_again = PromptLoader.load_all()
    assert len(warmed_again) > 0
    print(f"🔄 Rewarmed {len(warmed_again)} prompts")


@pytest.mark.asyncio
async def test_redis_cache_clear_sessions(redis_client):
    """Test clearing session cache."""
    cache_manager = CacheManager(redis_client)
    
    # First, add some test data
    await redis_client.set("v1:session:test-123:context", "test-context", 3600)
    await redis_client.set("v1:session:test-123:messages", "test-messages", 3600)
    
    # Get initial count
    initial_keys = await redis_client.get_key_patterns("v1:session:*")
    initial_count = len(initial_keys)
    print(f"\n📦 Initial session keys: {initial_count}")
    
    # Clear sessions
    result = await cache_manager.clear_redis_cache(scope="sessions")
    
    assert result["status"] == "success"
    assert result["keys_deleted"] >= initial_count
    
    # Verify cleared
    final_keys = await redis_client.get_key_patterns("v1:session:*")
    assert len(final_keys) == 0
    
    print(f"🧹 Cleared {result['keys_deleted']} session keys")


@pytest.mark.asyncio
async def test_full_cache_reset(redis_client):
    """Test full cache reset operation."""
    cache_manager = CacheManager(redis_client)
    
    # Add test data
    await redis_client.set("v1:session:test-456:context", "test-context", 3600)
    await redis_client.set("v1:session:test-456:messages", "test-messages", 3600)
    
    # Perform full reset
    result = await cache_manager.full_cache_reset()
    
    assert result["status"] == "success"
    assert "operations" in result
    assert result["operations"]["prompt_cache_rewarmed"] > 0
    
    print(f"\n🔄 Full cache reset completed: {result['operations']}")


@pytest.mark.asyncio
async def test_redis_database_info(redis_client):
    """Test Redis database information."""
    info = await redis_client.get_database_info()
    
    assert "used_memory" in info
    assert "keys_total" in info
    assert "connected_clients" in info
    
    print(f"\n📊 Redis Info: {info}")


@pytest.mark.asyncio
async def test_cache_pattern_operations(redis_client):
    """Test Redis pattern-based operations."""
    # Add test keys
    await redis_client.set("test:key:1", "value1", 3600)
    await redis_client.set("test:key:2", "value2", 3600)
    await redis_client.set("other:key", "value3", 3600)
    
    # Get patterns
    test_keys = await redis_client.get_key_patterns("test:*")
    assert len(test_keys) >= 2
    print(f"\n🔍 Pattern match 'test:*': {len(test_keys)} keys found")
    
    # Clear pattern
    cleared = await redis_client.clear_pattern("test:*")
    assert cleared >= 2
    
    # Verify other keys still exist
    other_exists = await redis_client.exists("other:key")
    assert other_exists
    
    print(f"🧹 Cleared {cleared} keys matching 'test:*'")
    print(f"✅ Other keys preserved")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
