"""Anti-Bot 탐지 회피 유틸리티."""

from __future__ import annotations

import asyncio
import random

# 실제 브라우저 User-Agent 목록 (Windows/Mac Chrome 기반)
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]


def get_random_user_agent() -> str:
    """랜덤 User-Agent 반환."""
    return random.choice(USER_AGENTS)


async def random_delay(min_sec: float = 2.0, max_sec: float = 5.0) -> None:
    """랜덤 딜레이 (Anti-Bot 회피용)."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


def get_browser_launch_args() -> list[str]:
    """Playwright 브라우저 실행 인자 (헤드리스 감지 회피)."""
    return [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-accelerated-2d-canvas",
        "--disable-gpu",
        "--lang=ko-KR",
    ]


def get_browser_context_options(user_agent: str | None = None) -> dict:
    """Playwright 브라우저 컨텍스트 옵션."""
    ua = user_agent or get_random_user_agent()
    return {
        "user_agent": ua,
        "viewport": {"width": 1920, "height": 1080},
        "locale": "ko-KR",
        "timezone_id": "Asia/Seoul",
        "geolocation": {"latitude": 37.3422, "longitude": 127.9202},  # 원주시 중심
        "permissions": ["geolocation"],
    }
