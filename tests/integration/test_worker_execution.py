import pytest
from arq.connections import create_pool

from app.workers.arq_jobs import get_arq_redis_settings


@pytest.mark.asyncio
async def test_arq_enqueue_job(redis_container_url, monkeypatch):
    host_port = redis_container_url.rsplit(":", 1)
    monkeypatch.setattr("app.core.config.settings.ARQ_REDIS_SETTINGS_HOST", host_port[0].split("//")[1])
    monkeypatch.setattr("app.core.config.settings.ARQ_REDIS_SETTINGS_PORT", int(host_port[1]))
    pool = await create_pool(get_arq_redis_settings())
    job = await pool.enqueue_job("sync_batch_job", {})
    assert job.job_id is not None
    await pool.close()
