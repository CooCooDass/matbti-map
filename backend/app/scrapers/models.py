"""크롤링 데이터 모델 정의."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BasicInfo:
    """검색 결과에서 추출하는 기본 정보."""

    name: str
    platform_place_id: str
    platform: str  # "naver" | "kakao" | "google"
    category: str = ""
    address_road: str = ""
    latitude: float | None = None
    longitude: float | None = None
    score: float | None = None  # 네이버는 평점 없으므로 None 허용
    review_count: int = 0


@dataclass
class MenuItem:
    """메뉴 항목."""

    name: str
    price: str = ""


@dataclass
class DetailInfo:
    """상세 페이지에서 추출하는 정보."""

    name: str
    platform_place_id: str
    platform: str
    category: str = ""
    address_road: str = ""
    phone: str = ""
    latitude: float | None = None
    longitude: float | None = None
    score: float | None = None
    review_count: int = 0
    business_hours: dict[str, str] = field(default_factory=dict)
    menu_items: list[MenuItem] = field(default_factory=list)


@dataclass
class Review:
    """리뷰 데이터."""

    author: str = ""
    text: str = ""
    score: float | None = None
    date: str = ""
    platform: str = ""
    visited_date: str = ""
