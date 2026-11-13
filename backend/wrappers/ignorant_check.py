"""Runs Ignorant's modules for a phone number and prints one JSON object per line.

Usage: ignorant_check.py <country code> <national number>      (e.g. 39 3331234567)

It uses the interface documented by Ignorant: every module is an async function
`module(phone, country_code, client, out)` that appends to `out` a dictionary with
name, domain, method, frequent_rate_limit, rateLimit and exists.
It must be run with the Python in which Ignorant is installed (it brings httpx and trio along).
"""
import importlib
import inspect
import json
import os
import pkgutil
import re
import sys

import anyio

TIMEOUT = 20


def emit(obj):
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def discover():
    """[(name, function)] for every Ignorant module."""
    import ignorant.modules as root

    found = []
    for info in pkgutil.walk_packages(root.__path__, root.__name__ + "."):
        if info.ispkg:
            continue
        name = info.name.rsplit(".", 1)[-1]
        try:
            func = getattr(importlib.import_module(info.name), name, None)
        except Exception as exc:  # a broken module must not stop the others
            emit({"name": name, "error": f"import: {exc}"[:200]})
            continue
        if inspect.iscoroutinefunction(func):
            found.append((name, func))
    return found


async def check(name, func, phone, country, client):
    out = []
    try:
        with anyio.fail_after(TIMEOUT):
            await func(phone, country, client, out)
    except TimeoutError:
        emit({"name": name, "error": "timeout"})
        return
    except Exception as exc:
        emit({"name": name, "error": str(exc)[:200] or type(exc).__name__})
        return
    for row in out:
        if isinstance(row, dict):
            emit(row)


async def amain(country, phone):
    import httpx

    funcs = discover()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with anyio.create_task_group() as tg:
            for name, func in funcs:
                tg.start_soon(check, name, func, phone, country, client)
    emit({"done": len(funcs)})


def main():
    if len(sys.argv) != 3 or not re.fullmatch(r"\d{1,4}", sys.argv[1]) or not re.fullmatch(r"\d{4,15}", sys.argv[2]):
        print("usage: ignorant_check.py <country code> <number>", file=sys.stderr)
        return 2
    backend = os.environ.get("IGNORANT_BACKEND", "trio")  # Ignorant's modules are written for trio
    anyio.run(amain, sys.argv[1], sys.argv[2], backend=backend)
    return 0


if __name__ == "__main__":
    sys.exit(main())
