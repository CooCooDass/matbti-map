"""원주시 격자 분할 유틸리티.

원주시를 500m × 500m 격자로 나누어 각 격자 중심점 좌표를 생성한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# 원주시 바운딩 박스 (WGS84)
WONJU_BOUNDS = {
    "south": 37.2800,  # 남쪽 위도
    "north": 37.4100,  # 북쪽 위도
    "west": 127.8600,  # 서쪽 경도
    "east": 127.9900,  # 동쪽 경도
}

# 격자 크기 (미터)
GRID_SIZE_M = 500


@dataclass
class GridPoint:
    """격자 중심점."""

    latitude: float
    longitude: float
    row: int
    col: int


def _meters_to_lat_deg(meters: float) -> float:
    """미터 → 위도 변환 (근사치)."""
    return meters / 111_320.0


def _meters_to_lng_deg(meters: float, lat: float) -> float:
    """미터 → 경도 변환 (위도에 따른 보정)."""
    return meters / (111_320.0 * math.cos(math.radians(lat)))


def generate_grid_points(
    bounds: dict[str, float] | None = None,
    grid_size_m: int = GRID_SIZE_M,
) -> list[GridPoint]:
    """바운딩 박스를 격자로 나누어 중심점 리스트를 반환한다.

    Args:
        bounds: {"south", "north", "west", "east"} 위경도. 기본값은 원주시.
        grid_size_m: 격자 크기 (미터). 기본값 500m.

    Returns:
        격자 중심점 리스트.
    """
    b = bounds or WONJU_BOUNDS
    lat_step = _meters_to_lat_deg(grid_size_m)
    mid_lat = (b["south"] + b["north"]) / 2
    lng_step = _meters_to_lng_deg(grid_size_m, mid_lat)

    points: list[GridPoint] = []
    row = 0
    lat = b["south"] + lat_step / 2
    while lat < b["north"]:
        col = 0
        lng = b["west"] + lng_step / 2
        while lng < b["east"]:
            points.append(GridPoint(latitude=lat, longitude=lng, row=row, col=col))
            lng += lng_step
            col += 1
        lat += lat_step
        row += 1

    return points
