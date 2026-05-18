from __future__ import annotations

import os

import httpx


def main() -> None:
    base_url = os.getenv("EMERGYX_API_BASE_URL", "http://localhost:8000")
    response = httpx.post(
        f"{base_url.rstrip('/')}/events/simulate-fall",
        json={},
        timeout=10.0,
    )
    response.raise_for_status()
    print(response.text)


if __name__ == "__main__":
    main()
