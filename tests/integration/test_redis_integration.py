import pytest


@pytest.mark.asyncio
async def test_redis_set_get_and_expiry(integration_redis):
    await integration_redis.set("sample-key", "value", ex=1)
    assert await integration_redis.get("sample-key") == "value"
    await integration_redis.expire("sample-key", 1)


@pytest.mark.asyncio
async def test_redis_cache_miss_returns_none(integration_redis):
    assert await integration_redis.get("missing-key") is None
