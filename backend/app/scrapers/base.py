"""크롤러 베이스 클래스."""

from __future__ import annotations

import asyncio
import functools
import logging
from abc import ABC, abstractmethod
from typing import TypeVar, Callable, Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from backend.app.scrapers.anti_detect import (
    get_browser_launch_args,
    get_browser_context_options,
    random_delay,
)
from backend.app.scrapers.models import BasicInfo, DetailInfo, Review

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry(max_retries: int = 3, base_delay: float = 2.0) -> Callable:
    """Exponential backoff 재시도 데코레이터."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        "%s 재시도 %d/%d (%.1f초 후): %s",
                        func.__name__, attempt + 1, max_retries, delay, exc,
                    )
                    await asyncio.sleep(delay)
            logger.exception("%s 최종 실패", func.__name__)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


class BaseScraper(ABC):
    """모든 플랫폼 크롤러의 베이스 클래스."""

    platform: str = ""

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless
        self._playwright: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None

    async def launch_browser(self) -> None:
        """Playwright 브라우저 실행."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=get_browser_launch_args(),
        )
        self._context = await self._browser.new_context(
            **get_browser_context_options(),
        )
        self.page = await self._context.new_page()
        logger.info("[%s] 브라우저 실행 완료", self.platform)

    async def close(self) -> None:
        """브라우저 종료."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("[%s] 브라우저 종료", self.platform)

    async def __aenter__(self) -> "BaseScraper":
        await self.launch_browser()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    @abstractmethod
    async def search(self, query: str, region: str = "원주") -> list[BasicInfo]:
        """키워드+지역으로 식당 검색."""
        ...

    @abstractmethod
    async def get_detail(self, place_id: str) -> DetailInfo:
        """place_id로 상세 정보 조회."""
        ...

    @abstractmethod
    async def get_reviews(self, place_id: str, limit: int = 50) -> list[Review]:
        """place_id로 리뷰 수집."""
        ...

    async def _safe_text(self, selector: str, default: str = "") -> str:
        """셀렉터로 텍스트 추출. 실패 시 기본값 반환."""
        assert self.page is not None
        try:
            el = await self.page.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()
        except Exception:
            pass
        return default

    async def _safe_attr(self, selector: str, attr: str, default: str = "") -> str:
        """셀렉터에서 속성값 추출. 실패 시 기본값 반환."""
        assert self.page is not None
        try:
            el = await self.page.query_selector(selector)
            if el:
                val = await el.get_attribute(attr)
                return val.strip() if val else default
        except Exception:
            pass
        return default
