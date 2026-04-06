#!/usr/bin/env python3

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.environ.get("OPENAGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("OPENAGENT_PORT", "8000"))
    uvicorn.run("backend.api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()

