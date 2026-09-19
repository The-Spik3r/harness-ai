"""One dedicated, bounded thread pool for every pipeline call (PRD-010 F4).

**Why not an async client inside call_openrouter instead (D1 correction to
the brief, PRD Section 6.3).** `run_query`/`run_conversation` is a
synchronous function. If `call_openrouter` awaited an async HTTP client
internally, something would still have to block a thread waiting for the
synchronous function to return -- anyio's threadpool for `/query`, the event
loop's default executor for `ChatState`. What frees those shared pools is
*whose* thread does the waiting, not whether the HTTP call inside is sync or
async. So the dedicated pool wraps the whole pipeline call, not one HTTP
request inside it.

The executor is process-wide and created lazily, under a lock, on first use
-- never at import -- so importing this module never reads `settings`
(PRD Risk 5; mirrors `app/db/database.py`'s `_shared_client`/`_client_lock`
pattern for the same reason). `shutdown()` is idempotent and is registered as
a lifespan task in both `app/main.py` (plain uvicorn) and
`chat_ui/chat_ui/chat_ui.py` (Reflex's `api_transformer` mount bypasses
`app.main`'s lifespan entirely).
"""

import asyncio
import functools
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from app.config import settings

_lock = threading.Lock()
_executor: Optional[ThreadPoolExecutor] = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.PIPELINE_MAX_WORKERS,
                thread_name_prefix="pipeline",
            )
        return _executor


async def run_in_pipeline(fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Await `fn(*args, **kwargs)` on the dedicated pipeline executor.

    The only way either ingress (`/query`, `ChatState`) runs the pipeline.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        _get_executor(), functools.partial(fn, *args, **kwargs)
    )


def shutdown() -> None:
    """Stop the executor if one was ever created. Safe to call more than once."""
    global _executor
    with _lock:
        if _executor is not None:
            _executor.shutdown(wait=True)
            _executor = None
