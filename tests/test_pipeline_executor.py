"""PRD-010 STORY-006: `pipeline_executor` in isolation, before any production
caller is wired to it (routers/query.py, chat_ui/chat_ui/state.py)."""

import os

os.environ.setdefault("OPENROUTER_API_KEY", "test-key")
os.environ.setdefault("ADMIN_TOKEN", "test-token")

import asyncio
import threading

import pytest

from app.config import settings
from app.services import pipeline_executor


@pytest.fixture(autouse=True)
def _reset_executor():
    """The executor is a process-wide singleton -- never leave one test's
    instance (or a `PIPELINE_MAX_WORKERS` override's) lying around for the
    next test to observe."""
    pipeline_executor.shutdown()
    yield
    pipeline_executor.shutdown()


@pytest.mark.asyncio
async def test_run_in_pipeline_returns_the_function_result():
    result = await pipeline_executor.run_in_pipeline(lambda x: x + 1, 41)
    assert result == 42


@pytest.mark.asyncio
async def test_run_in_pipeline_forwards_args_and_kwargs():
    def _fn(a, b, c=None):
        return (a, b, c)

    result = await pipeline_executor.run_in_pipeline(_fn, 1, 2, c=3)
    assert result == (1, 2, 3)


@pytest.mark.asyncio
async def test_run_in_pipeline_runs_on_a_pipeline_named_thread():
    name = await pipeline_executor.run_in_pipeline(lambda: threading.current_thread().name)
    assert name.startswith("pipeline")


@pytest.mark.asyncio
async def test_executor_created_lazily_on_first_use():
    assert pipeline_executor._executor is None
    await pipeline_executor.run_in_pipeline(lambda: None)
    assert pipeline_executor._executor is not None


@pytest.mark.asyncio
async def test_executor_sized_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "PIPELINE_MAX_WORKERS", 3)
    await pipeline_executor.run_in_pipeline(lambda: None)
    assert pipeline_executor._executor._max_workers == 3


@pytest.mark.asyncio
async def test_concurrent_first_use_creates_exactly_one_executor(monkeypatch):
    """Proves the lock, not just the `is None` check: twenty callers racing to
    be the first to use the executor must still construct exactly one."""
    real_pool_cls = pipeline_executor.ThreadPoolExecutor
    created = []

    def _counting_pool(*args, **kwargs):
        pool = real_pool_cls(*args, **kwargs)
        created.append(pool)
        return pool

    monkeypatch.setattr(pipeline_executor, "ThreadPoolExecutor", _counting_pool)

    await asyncio.gather(
        *(pipeline_executor.run_in_pipeline(lambda: None) for _ in range(20))
    )

    assert len(created) == 1


@pytest.mark.asyncio
async def test_shutdown_is_idempotent():
    await pipeline_executor.run_in_pipeline(lambda: None)
    pipeline_executor.shutdown()
    pipeline_executor.shutdown()  # must not raise
    assert pipeline_executor._executor is None


def test_shutdown_before_any_use_is_a_noop():
    pipeline_executor.shutdown()  # must not raise
    assert pipeline_executor._executor is None


@pytest.mark.asyncio
async def test_run_in_pipeline_propagates_exceptions():
    def _boom():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await pipeline_executor.run_in_pipeline(_boom)
