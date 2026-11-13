"""Fake httpx: only the context manager used by the ignorant_check script is needed."""


class AsyncClient:
    def __init__(self, timeout=None):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False
