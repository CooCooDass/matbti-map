"""네이버 지도 크롤러.

SPA 구조이나, 페이지 로드 시 호출되는 GraphQL API(pcmap-api.place.naver.com/graphql)를
인터셉트하여 검색 결과(place_id, name, category, address, 좌표 등)를 추출한다.
상세 정보는 GraphQL 인터셉션 우선으로 추출하고, DOM 셀렉터는 폴백으로만 사용한다.

동적 클래스명 대응 전략:
  1. GraphQL API 인터셉션 — 클래스명과 무관한 원천 데이터 추출 (가장 안정적)
  2. 의미론적 속성 우선 — href^="tel:", data-*, aria-* (빌드간 불변)
  3. TreeWalker 텍스트 탐색 — 클래스 독립적 DOM 탐색
  4. 구조적 위치 셀렉터 — 알려진 안정 요소 기준 상대 탐색

URL 패턴:
  - 검색: https://pcmap.place.naver.com/restaurant/list?query={query}
  - 상세: https://pcmap.place.naver.com/restaurant/{place_id}/home
  - 리뷰: https://pcmap.place.naver.com/restaurant/{place_id}/review/visitor
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from backend.app.scrapers.anti_detect import random_delay
from backend.app.scrapers.base import BaseScraper, retry
from backend.app.scrapers.models import BasicInfo, DetailInfo, MenuItem, Review

logger = logging.getLogger(__name__)


class NaverMapsScraper(BaseScraper):
    """네이버 지도 크롤러."""

    platform = "naver"
    PLACE_BASE = "https://pcmap.place.naver.com/restaurant"
    GRAPHQL_HOST = "pcmap-api.place.naver.com/graphql"

    # ──────────────────────────────────────────────────────────
    # search() — GraphQL API 인터셉션
    # ──────────────────────────────────────────────────────────
    @retry(max_retries=3)
    async def search(self, query: str, region: str = "원주") -> list[BasicInfo]:
        """네이버 지도 GraphQL API 인터셉션으로 검색 결과 수집."""
        assert self.page is not None
        search_query = f"{region} {query}"

        # GraphQL 응답 캡처
        captured_places: list[dict[str, Any]] = []

        async def handle_response(response: Any) -> None:
            if self.GRAPHQL_HOST not in response.url:
                return
            try:
                body = await response.json()
                self._extract_places_from_graphql(body, captured_places)
            except Exception:
                pass

        self.page.on("response", handle_response)

        url = f"{self.PLACE_BASE}/list?query={search_query}"
        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        await random_delay(3, 5)   # GraphQL 응답 수신 대기

        self.page.remove_listener("response", handle_response)

        results: list[BasicInfo] = []
        for p in captured_places:
            pid = str(p.get("id", ""))
            name = p.get("name", "")
            if not name:
                continue

            # 좌표
            lat: float | None = None
            lng: float | None = None
            try:
                lat = float(p.get("y", 0)) or None
                lng = float(p.get("x", 0)) or None
            except (ValueError, TypeError):
                pass

            results.append(BasicInfo(
                name=name,
                platform_place_id=pid,
                platform=self.platform,
                category=p.get("category", ""),
                address_road=p.get("roadAddress", "") or p.get("address", ""),
                latitude=lat,
                longitude=lng,
                score=None,  # 네이버 검색 결과 GraphQL에 별점 없음 → get_detail()에서 추출
                review_count=int(p.get("totalReviewCount", 0) or 0),
            ))

        # 중복 제거 (같은 id가 두 번 올 수 있음)
        seen: set[str] = set()
        final: list[BasicInfo] = []
        for r in results:
            if r.platform_place_id and r.platform_place_id not in seen:
                seen.add(r.platform_place_id)
                final.append(r)

        logger.info("[네이버] '%s' 검색 결과: %d건", search_query, len(final))
        return final

    def _extract_places_from_graphql(
        self, obj: Any, out: list[dict[str, Any]], depth: int = 0
    ) -> None:
        """GraphQL 응답에서 재귀적으로 place 항목 추출."""
        if depth > 8:
            return
        if isinstance(obj, dict):
            if "id" in obj and "name" in obj and "businessCategory" in obj:
                out.append(obj)
            else:
                for v in obj.values():
                    self._extract_places_from_graphql(v, out, depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                self._extract_places_from_graphql(v, out, depth + 1)

    def _extract_detail_from_graphql(
        self, obj: Any, out: dict[str, Any], depth: int = 0
    ) -> None:
        """GraphQL 상세 응답에서 전화번호·이름·카테고리 추출.

        네이버 GraphQL은 빌드마다 구조가 달라질 수 있으므로
        재귀적으로 탐색하여 패턴 매칭으로 추출한다.

        핵심 원칙:
          - 이름은 식당 노드(businessCategory 또는 roadAddress 포함)에서만 추출
          - 카테고리는 categoryId(PLACE 등 enum) 제외, businessCategory/categoryName만 사용
          - 전화번호는 원본 값 그대로 저장 후 정규화
        """
        if depth > 10:
            return
        if isinstance(obj, dict):
            # 식당 노드 판별 — businessCategory 또는 roadAddress/x,y 좌표 포함 객체
            is_restaurant_node = any(k in obj for k in (
                "businessCategory", "roadAddress", "x", "y"
            ))

            # 이름 — 식당 노드에서만 추출 (리뷰 텍스트·사용자명 혼입 방지)
            if is_restaurant_node and "name" in obj and obj["name"]:
                val = str(obj["name"]).strip()
                if val and len(val) < 50 and "name" not in out:
                    out["name"] = val

            # 카테고리 — categoryId(enum 값 "PLACE" 등) 제외
            for key in ("businessCategory", "categoryName"):
                if key in obj and obj[key] and "category" not in out:
                    val = str(obj[key]).strip()
                    if val and len(val) < 30 and not val.isdigit():
                        out["category"] = val

            # 전화번호 — tel/phone/telephone 키 탐색, 한국 번호 형식 검증
            for key in ("tel", "phone", "telephone", "phoneNumber", "callPhone"):
                if key in obj and obj[key] and "phone" not in out:
                    raw = str(obj[key]).strip()
                    # 하이픈 제거 후 숫자만으로 패턴 확인 (9~11자리 한국 번호)
                    digits_only = re.sub(r"[^\d]", "", raw)
                    if re.match(r"0\d{8,10}$", digits_only):
                        out["phone"] = raw  # 원본 형식 그대로 저장

            # 재귀
            for v in obj.values():
                self._extract_detail_from_graphql(v, out, depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                self._extract_detail_from_graphql(v, out, depth + 1)

    # ──────────────────────────────────────────────────────────
    # get_detail() — GraphQL 인터셉션 + DOM 폴백
    # ──────────────────────────────────────────────────────────
    @retry(max_retries=3)
    async def get_detail(self, place_id: str) -> DetailInfo:
        """place_id로 상세 정보 조회.

        전화번호 등 동적 클래스명에 취약한 데이터는 GraphQL 인터셉션으로 추출.
        DOM 셀렉터는 폴백으로만 사용한다.
        """
        assert self.page is not None
        url = f"{self.PLACE_BASE}/{place_id}/home"

        # GraphQL 상세 응답 캡처 (전화번호·이름 등 안정적 추출)
        api_data: dict[str, Any] = {}

        async def handle_response(response: Any) -> None:
            if self.GRAPHQL_HOST not in response.url:
                return
            try:
                body = await response.json()
                self._extract_detail_from_graphql(body, api_data)
            except Exception:
                pass

        self.page.on("response", handle_response)
        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        await random_delay(2, 4)
        self.page.remove_listener("response", handle_response)

        logger.debug("[네이버] GraphQL api_data keys: %s", list(api_data.keys()))

        # 이름 — GraphQL 우선, og:title 메타태그, document.title 순 폴백
        name = api_data.get("name", "")
        # GraphQL 이름에도 suffix가 붙는 경우 제거
        if name:
            name = re.sub(r"\s*[:\-|：]\s*(네이버|Naver).*$", "", name).strip()
        if not name:
            name = await self.page.evaluate("""() => {
                // 1) og:title 메타 태그 (안정적) — ": 네이버" 등 suffix 제거
                const og = document.querySelector('meta[property="og:title"]');
                if (og) {
                    const t = og.getAttribute('content');
                    if (t) return t.replace(/\\s*[:\\-|].*$/, '').trim();
                }
                // 2) title 태그 — suffix 제거
                const title = document.title;
                return title ? title.replace(/\\s*[:\\-|][^:\\-|]*$/, '').trim() : '';
            }""") or ""
            # CSS 셀렉터 최종 폴백
            if not name:
                for sel in ("span.GHAoO", "h1.GHAoO", "span.Fc1rA", ".place_head_name span"):
                    el = await self.page.query_selector(sel)
                    if el:
                        name = (await el.inner_text()).strip()
                        if name:
                            break

        # 카테고리 — GraphQL 우선, CSS 셀렉터 폴백
        category = api_data.get("category", "")
        if not category:
            for sel in ("span.DJJvD", "span.lnJFt", "span.CH79B", "nav.veBoZ a:first-child"):
                el = await self.page.query_selector(sel)
                if el:
                    category = (await el.inner_text()).strip()
                    if category:
                        break

        # 주소 — "주소" 레이블 기반 DOM 탐색 (클래스명 독립적)
        address = await self.page.evaluate("""() => {
            // "주소" 텍스트를 가진 요소의 인접 형제/자식에서 주소 추출
            for (const sp of document.querySelectorAll('span, dt, th, div')) {
                if ((sp.innerText || '').trim() !== '주소') continue;
                const parent = sp.closest('li, tr, div[class]');
                if (!parent) continue;
                // 주소 내용 스팬 탐색
                for (const child of parent.querySelectorAll('a span, span.LDgIH, span.LDKhP, span.Pb4bU')) {
                    const t = (child.innerText || '').trim();
                    if (t && t.length > 5) return t;
                }
                // 폴백: 라벨을 제외한 가장 긴 텍스트 노드
                const texts = Array.from(parent.querySelectorAll('span, a'))
                    .filter(el => el.children.length === 0)
                    .map(el => (el.innerText || '').trim())
                    .filter(t => t && t !== '주소' && t.length > 5);
                if (texts.length) return texts.sort((a, b) => b.length - a.length)[0];
            }
            // 최종 폴백: 클래스명 직접 접근
            const el = document.querySelector('.LDgIH, .LDKhP, span.Pb4bU');
            return el ? (el.innerText || '').trim() : '';
        }""") or ""

        # 전화번호 — GraphQL 우선 (가장 안정적), DOM 폴백
        phone = api_data.get("phone", "")
        if not phone:
            phone = await self.page.evaluate("""() => {
                // 1. tel: 링크 (표준 방식)
                const telLink = document.querySelector('a[href^="tel:"]');
                if (telLink) return telLink.href.replace('tel:', '').trim();
                // 2. TreeWalker로 전화번호 패턴 탐색 (클래스명 독립적)
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
                const pattern = /^0\\d{1,2}-\\d{3,4}-\\d{4}$/;
                while (walker.nextNode()) {
                    const t = (walker.currentNode.textContent || '').trim();
                    if (pattern.test(t)) return t;
                }
                // 3. 전화번호 포함 텍스트에서 패턴 추출
                for (const el of document.querySelectorAll('span, p, div')) {
                    if (el.children.length > 0) continue;
                    const t = (el.innerText || '').trim();
                    const m = t.match(/0\\d{1,2}-\\d{3,4}-\\d{4}/);
                    if (m) return m[0];
                }
                return '';
            }""") or ""

        # 평점
        score: float | None = None
        for sel in ("span.PXNBD em", "em.PXNBD", "span.h693S em", "span.xlS6f"):
            el = await self.page.query_selector(sel)
            if el:
                try:
                    score = float((await el.inner_text()).strip())
                    break
                except ValueError:
                    pass

        # 좌표 — 페이지 소스 JSON 파싱 (네이버는 URL에 좌표 없음)
        lat, lng = None, None
        try:
            content = await self.page.content()
            m = re.search(r'"x"\s*:\s*"?([\d.]+)"?\s*,\s*"y"\s*:\s*"?([\d.]+)"?', content)
            if m:
                lng = float(m.group(1))
                lat = float(m.group(2))
        except Exception:
            pass

        # 영업시간
        business_hours: dict[str, str] = {}
        hours_els = await self.page.query_selector_all(
            ".A_cdD li, .MxgIj li, .O8qh7 li, table.running_time_warp tr"
        )
        for el in hours_els:
            text = (await el.inner_text()).strip()
            if text:
                parts = text.split(None, 1)
                if len(parts) == 2:
                    business_hours[parts[0]] = parts[1]

        # 메뉴
        menu_items: list[MenuItem] = []
        menu_els = await self.page.query_selector_all(
            ".E2jtL, .ChEfo, li.lX3qU, .order_list_item"
        )
        for el in menu_els[:20]:
            try:
                m_name = ""
                m_price = ""
                for sel in (".lPzHi", "span.HbvYf", ".name_text", ".tit"):
                    n_el = await el.query_selector(sel)
                    if n_el:
                        m_name = (await n_el.inner_text()).strip()
                        break
                for sel in (".GXS1X", "div.l9Y0S", ".price_text", ".cost"):
                    p_el = await el.query_selector(sel)
                    if p_el:
                        m_price = (await p_el.inner_text()).strip()
                        break
                if m_name:
                    menu_items.append(MenuItem(name=m_name, price=m_price))
            except Exception:
                continue

        logger.info("[네이버] 상세 조회: %s (place_id=%s, phone=%s)", name, place_id, phone or "없음")
        return DetailInfo(
            name=name,
            platform_place_id=place_id,
            platform=self.platform,
            category=category,
            address_road=address,
            phone=phone,
            latitude=lat,
            longitude=lng,
            score=score,
            business_hours=business_hours,
            menu_items=menu_items,
        )

    # ──────────────────────────────────────────────────────────
    # get_reviews()
    # ──────────────────────────────────────────────────────────
    @retry(max_retries=3)
    async def get_reviews(self, place_id: str, limit: int = 50) -> list[Review]:
        """방문자 리뷰 수집.

        리뷰 텍스트는 클래스명 독립적인 TreeWalker 방식으로 추출한다.
        네이버 pui__ 접두사는 빌드마다 변경되므로 구조 기반 탐색을 우선한다.

        리뷰 페이지 URL 우선순위:
          1. /review/visitor (방문자 리뷰)
          2. /review/list (전체 리뷰 목록, 폴백)
        """
        assert self.page is not None
        # 방문자 리뷰 URL 우선, 없으면 list 폴백
        url = f"{self.PLACE_BASE}/{place_id}/review/visitor"

        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        await random_delay(3, 5)  # 봇 탐지 우회를 위한 충분한 대기

        # 페이지에 리뷰가 없으면 /review/list로 폴백
        initial_items = await self.page.query_selector_all(
            "li[class*='pui__'], ul[class*='pui__'] li, .place_review_list li"
        )
        if not initial_items:
            fallback_url = f"{self.PLACE_BASE}/{place_id}/review/list"
            await self.page.goto(fallback_url, wait_until="networkidle", timeout=30000)
            await random_delay(2, 3)
            logger.debug("[네이버] visitor URL 실패 → list URL 폴백 (place_id=%s)", place_id)

        reviews: list[Review] = []

        while len(reviews) < limit:
            # 리뷰 아이템 탐색 — 다중 셀렉터 시도
            # 우선순위:
            #   1. li.place_apply_pui — Naver 2025+ 리뷰 아이템 클래스 (실증 확인)
            #   2. li[class*='pui'] — pui 접두사/접미사 일반 패턴
            #   3. 구 버전 패턴 폴백
            review_items = await self.page.query_selector_all(
                "li.place_apply_pui, li[class*='place_apply_pui'], "
                "li[class*='pui__'], ul[class*='pui__'] li, "
                ".place_review_list li, .ZZ4OK li, li.place_apply_review"
            )
            if not review_items:
                logger.warning("[네이버] 리뷰 아이템 없음 (place_id=%s)", place_id)
                # 페이지 DOM 진단 로그 (셀렉터 디버깅용)
                item_count = await self.page.evaluate("""() => ({
                    allLi: document.querySelectorAll('li').length,
                    puiLi: document.querySelectorAll('[class*="pui"]').length,
                    reviewDiv: document.querySelectorAll('[class*="review"]').length,
                    url: window.location.href,
                    title: document.title
                })""")
                logger.info("[네이버] DOM 진단: %s", item_count)
                break

            new_count = 0
            for item in review_items[len(reviews):]:
                if len(reviews) >= limit:
                    break
                try:
                    # 작성자 — innerText 첫번째 줄에서 직접 추출 (가장 안정적)
                    # Naver 리뷰 구조: [작성자명]\n[리뷰N사진N]\n[팔로우]\n[리뷰텍스트]...
                    item_text = await item.inner_text()
                    lines = [l.strip() for l in item_text.split('\n') if l.strip()]
                    author = ""
                    if lines:
                        candidate = lines[0]
                        # 리뷰/사진 통계 줄이나 UI 버튼 제외
                        skip_patterns = (
                            re.match(r'^리뷰\s*\d|^사진\s*\d', candidate),
                            candidate in ('팔로우', '팔로잉', '신고', '더보기', '공감'),
                            len(candidate) > 30,
                        )
                        if not any(skip_patterns):
                            author = candidate

                    # 리뷰 텍스트 — TreeWalker로 가장 긴 텍스트 추출 (클래스명 독립)
                    # Naver place_apply_pui 구조: 사용자명 → 통계 → 팔로우 → 리뷰텍스트 → 방문유형 → 날짜
                    text = await item.evaluate("""el => {
                        const skipPatterns = [
                            /^\\d{4}[.년]/,         // 날짜
                            /^\\d{4}년 \\d{1,2}월/,  // 날짜 2
                            /^\\d+번째 방문/,         // 방문 회차
                            /^방문일$/,
                            /^인증 수단$/,
                            /^영수증$/,
                        ];
                        const skipTexts = new Set([
                            '더보기', '신고', '좋아요', '답글', '리뷰', '사진',
                            '공감', '팔로우', '팔로잉', '반응 남기기'
                        ]);

                        // 리뷰 통계 텍스트 (예: "리뷰 81사진 117") 패턴
                        const statsPattern = /^리뷰\\s*\\d|^사진\\s*\\d/;

                        let best = '';
                        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
                        while (walker.nextNode()) {
                            const t = (walker.currentNode.textContent || '').trim();
                            if (!t || t.length < 5) continue;
                            if (skipTexts.has(t)) continue;
                            if (statsPattern.test(t)) continue;
                            if (/^\\d+$/.test(t)) continue;
                            let skip = false;
                            for (const pat of skipPatterns) {
                                if (pat.test(t)) { skip = true; break; }
                            }
                            if (skip) continue;
                            if (t.length > best.length) best = t;
                        }
                        return best;
                    }""") or ""

                    # 날짜 — 날짜 패턴 매칭 (구조 독립적)
                    date = await item.evaluate("""el => {
                        // "2026년 3월 28일" 또는 "2026.3.28" 패턴
                        const patterns = [
                            /\\d{4}년\\s*\\d{1,2}월\\s*\\d{1,2}일/,
                            /\\d{4}[.]\\d{1,2}[.]\\d{1,2}/,
                            /\\d{4}[.년]\\s*\\d{1,2}[.월]/,
                        ];
                        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
                        while (walker.nextNode()) {
                            const t = (walker.currentNode.textContent || '').trim();
                            for (const pat of patterns) {
                                if (pat.test(t) && t.length < 30) return t;
                            }
                        }
                        return '';
                    }""") or ""

                    if text and len(text) > 3:
                        reviews.append(Review(
                            author=author,
                            text=text,
                            score=None,  # 방문자 리뷰에는 별점 없음
                            date=date,
                            platform=self.platform,
                        ))
                        new_count += 1
                except Exception as exc:
                    logger.warning("[네이버] 리뷰 파싱 실패: %s", exc)
                    continue

            if new_count == 0:
                break  # 새 리뷰 없으면 종료

            # 더보기 버튼 클릭
            more_btn = self.page.locator(
                "a:has-text('더보기'), button:has-text('더보기'), a.place_review_list_more"
            )
            visible_more = await more_btn.count() > 0 and await more_btn.first.is_visible()
            if visible_more and len(reviews) < limit:
                await more_btn.first.click()
                await random_delay(2, 4)
            else:
                break

        logger.info("[네이버] 리뷰 수집: place_id=%s, %d건", place_id, len(reviews))
        return reviews[:limit]
