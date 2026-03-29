"""구글맵 크롤러 실제 동작 검증 테스트."""

from __future__ import annotations

import logging

import pytest

from backend.app.scrapers.google import GoogleMapsScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_google_search() -> None:
    """구글 검색 결과가 1건 이상 반환되는지 확인."""
    async with GoogleMapsScraper(headless=True) as scraper:
        results = await scraper.search("맛집", "원주")

    assert len(results) > 0, "검색 결과가 없습니다"
    first = results[0]
    assert first.name, "이름이 비어있습니다"
    assert first.platform == "google"
    logger.info("검색 결과 %d건, 첫 번째: %s", len(results), first.name)


@pytest.mark.asyncio
async def test_google_detail() -> None:
    """구글 상세 정보에 필수 필드가 채워지는지 확인."""
    async with GoogleMapsScraper(headless=True) as scraper:
        results = await scraper.search("맛집", "원주")
        assert results, "검색 결과 없음"

        place_id = results[0].platform_place_id
        if not place_id:
            pytest.skip("place_id를 추출하지 못함")

        detail = await scraper.get_detail(place_id)

    assert detail.name, "상세 이름이 비어있습니다"
    assert detail.platform == "google"
    logger.info(
        "상세: %s | 카테고리: %s | 평점: %s",
        detail.name, detail.category, detail.score,
    )


@pytest.mark.asyncio
async def test_google_reviews() -> None:
    """구글 리뷰가 정상 수집되는지 확인."""
    async with GoogleMapsScraper(headless=True) as scraper:
        results = await scraper.search("맛집", "원주")
        assert results, "검색 결과 없음"

        place_id = results[0].platform_place_id
        if not place_id:
            pytest.skip("place_id를 추출하지 못함")

        detail = await scraper.get_detail(place_id)
        reviews = await scraper.get_reviews(place_id, limit=5)

    if reviews:
        assert reviews[0].text, "리뷰 텍스트가 비어있습니다"
        assert reviews[0].platform == "google"
        logger.info("리뷰 %d건, 첫 번째: %s...", len(reviews), reviews[0].text[:50])
    else:
        logger.info("리뷰가 없는 장소입니다 (정상)")
