"""3대 플랫폼 크롤러 패키지."""

from backend.app.scrapers.base import BaseScraper
from backend.app.scrapers.models import BasicInfo, DetailInfo, MenuItem, Review
from backend.app.scrapers.naver import NaverMapsScraper
from backend.app.scrapers.kakao import KakaoMapsScraper
from backend.app.scrapers.google import GoogleMapsScraper

__all__ = [
    "BaseScraper",
    "BasicInfo",
    "DetailInfo",
    "MenuItem",
    "Review",
    "NaverMapsScraper",
    "KakaoMapsScraper",
    "GoogleMapsScraper",
]
