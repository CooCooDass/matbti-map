"""구글맵 크롤러.

가장 엄격한 Anti-Bot 대응이 필요하며, aria-label 기반 셀렉터를 사용한다.

동적 클래스명 대응 전략:
  1. data-item-id 속성 우선 — 주소/전화 버튼은 data-item-id로 식별 (빌드간 불변)
  2. aria-label 속성 — 접근성 속성은 UX 요구상 안정적
  3. compareDocumentPosition — 알려진 요소(h1) 기준 상대 위치로 카테고리 버튼 탐색
  4. window.location.href 폴링 — SPA 라우팅 완료 후 URL에서 좌표 추출
  5. data-review-id 속성 — 리뷰 컨테이너 식별 (안정적)
  6. TreeWalker 텍스트 탐색 — 리뷰 텍스트를 클래스명 독립적으로 추출

URL 패턴:
  - 검색: https://www.google.com/maps/search/{query}
  - 상세: https://www.google.com/maps/place/?q=place_id:{place_id}
"""

from __future__ import annotations

import asyncio
import logging
import re

from backend.app.scrapers.anti_detect import random_delay
from backend.app.scrapers.base import BaseScraper, retry
from backend.app.scrapers.models import BasicInfo, DetailInfo, MenuItem, Review

logger = logging.getLogger(__name__)


class GoogleMapsScraper(BaseScraper):
    """구글맵 크롤러."""

    platform = "google"
    BASE_URL = "https://www.google.com/maps"

    async def launch_browser(self) -> None:
        """Playwright 브라우저 실행 후 Google Maps 세션 초기화.

        Google Maps는 메인 페이지를 먼저 방문해야 쿠키/세션이 초기화되어
        이후 상세 페이지에서 리뷰 탭 등 전체 콘텐츠가 로드됨.
        """
        await super().launch_browser()
        assert self.page is not None
        # 세션 warm-up: Google Maps 메인 방문 (동의 버튼 처리 포함)
        await self.page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=20000)
        await random_delay(2, 3)
        # 동의/약관 버튼 자동 클릭 (발생 시)
        try:
            consent_btn = self.page.locator(
                "button:has-text('동의'), button:has-text('Accept'), button:has-text('Agree')"
            )
            if await consent_btn.count() > 0:
                await consent_btn.first.click()
                await random_delay(1, 2)
        except Exception:
            pass
        logger.info("[구글] 세션 초기화 완료 (maps.google.com 방문)")

    # ──────────────────────────────────────────────────────────
    # search()
    # ──────────────────────────────────────────────────────────
    @retry(max_retries=3)
    async def search(self, query: str, region: str = "원주") -> list[BasicInfo]:
        """구글맵에서 검색."""
        assert self.page is not None
        search_query = f"{region} {query}"
        url = f"{self.BASE_URL}/search/{search_query}"

        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(3, 5)

        results: list[BasicInfo] = []

        # 검색 결과 feed 대기
        feed = self.page.locator("div[role='feed']")
        if await feed.count() == 0:
            logger.warning("[구글] 검색 결과 feed를 찾을 수 없음")
            return results

        # 3번 스크롤하여 결과 로드
        for _ in range(3):
            await feed.evaluate("el => el.scrollTop = el.scrollHeight")
            await random_delay(1, 2)

        # 결과 아이템 — a.hfpxzc 가 각 장소 링크
        links = await self.page.query_selector_all("a.hfpxzc")

        for link in links:
            try:
                # 이름 — aria-label 또는 내부 div 텍스트
                name = await link.get_attribute("aria-label") or ""
                if not name:
                    name_el = await link.query_selector("div.qBF1Pd, div.fontHeadlineSmall")
                    name = (await name_el.inner_text()).strip() if name_el else ""
                if not name:
                    continue
                name = name.strip()

                # href에서 place_id 추출
                href = await link.get_attribute("href") or ""
                place_id = ""
                chij_m = re.search(r"(ChIJ[\w-]+)", href)
                cid_m = re.search(r"!(1s)(0x[\da-fA-F]+:0x[\da-fA-F]+)", href)
                if chij_m:
                    place_id = chij_m.group(1)
                elif cid_m:
                    place_id = cid_m.group(2)

                # 좌표
                lat, lng = None, None
                coord_m = re.search(r"@(-?\d+\.?\d*),(-?\d+\.?\d*)", href)
                if coord_m:
                    lat = float(coord_m.group(1))
                    lng = float(coord_m.group(2))

                # 부모 카드에서 추가 정보 추출
                card = await link.evaluate_handle(
                    "el => el.closest('div.Nv2YUb') || el.closest('div.Ua6G7e') || el.parentElement"
                )

                # 평점
                score: float | None = None
                rating_el = await card.query_selector("span.MW4etd, span.MW4T7d, span.ceS6Me")
                if rating_el:
                    try:
                        score = float((await rating_el.inner_text()).strip())
                    except ValueError:
                        pass

                # 리뷰 수
                review_count = 0
                rev_el = await card.query_selector(
                    "span.UY7F9, span[aria-label*='리뷰'], span[aria-label*='review']"
                )
                if rev_el:
                    text = (await rev_el.inner_text()).strip().strip("()")
                    text = text.replace(",", "").replace("K", "000")
                    nums = re.findall(r"\d+", text)
                    if nums:
                        review_count = int(nums[0])

                # 카테고리·주소 — compareDocumentPosition 기반 텍스트 수집 (클래스명 독립)
                # 이름(aria-label) 이후, 숫자/괄호/구분자/가격표시/영업시간 텍스트 제외
                info_texts: list[str] = await card.evaluate("""(el) => {
                    const result = [];
                    const seen = new Set();
                    const nameEl = el.querySelector('a[aria-label]');
                    const name = nameEl ? nameEl.getAttribute('aria-label') : '';
                    for (const node of el.querySelectorAll('span, div')) {
                        if (node.children.length > 0) continue;
                        const t = (node.innerText || '').trim();
                        if (!t || seen.has(t)) continue;
                        if (t === name) continue;
                        if (t.length < 2) continue;       // "·" 등 구분자 제외
                        if (/^·/.test(t)) continue;       // "· AM 11:30" 등 구분자로 시작하는 텍스트 제외
                        if (/^[\\d.,·\\-\\s]+$/.test(t)) continue;  // 숫자/구분자만인 경우 제외
                        if (/^\\([\\d,K천만]+\\)$/.test(t)) continue;  // (리뷰수) 형태 제외
                        if (/^[\\W\\d,]+$/.test(t)) continue;   // 특수문자+숫자만인 경우 제외
                        if (/^₩/.test(t)) continue;        // 가격 표시 ("₩10,000~20,000") 제외
                        if (/AM\\s|PM\\s|영업|휴무|오전|오후/.test(t)) continue;  // 영업시간 텍스트 제외
                        if (t.startsWith('"') || t.startsWith('\\u201c')) continue;  // 인용 텍스트(리뷰 미리보기) 제외
                        if (t.includes('\\n')) continue;  // 여러 줄 텍스트 제외 (리뷰 스니펫)
                        if (t.length > 100) continue;
                        seen.add(t);
                        result.push(t);
                    }
                    return result;
                }""") or []

                category = info_texts[0] if info_texts else ""
                address = info_texts[1] if len(info_texts) > 1 else ""

                results.append(BasicInfo(
                    name=name,
                    platform_place_id=place_id,
                    platform=self.platform,
                    category=category,
                    address_road=address,
                    latitude=lat,
                    longitude=lng,
                    score=score,
                    review_count=review_count,
                ))

            except Exception as exc:
                logger.warning("[구글] 검색 결과 파싱 실패: %s", exc)
                continue

        logger.info("[구글] '%s' 검색 결과: %d건", search_query, len(results))
        return results

    # ──────────────────────────────────────────────────────────
    # get_detail()
    # ──────────────────────────────────────────────────────────
    @retry(max_retries=3)
    async def get_detail(self, place_id: str) -> DetailInfo:
        """place_id로 상세 정보 조회."""
        assert self.page is not None
        url = f"{self.BASE_URL}/place/?q=place_id:{place_id}"

        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(3, 5)

        # 이름 — h1.DUwDvf (구글은 이 클래스가 비교적 안정적)
        name = ""
        name_el = await self.page.query_selector("h1.DUwDvf, h1[class*='DUwDvf']")
        if name_el:
            name = (await name_el.inner_text()).strip()
        if not name:
            # title 태그 폴백
            name = await self.page.evaluate("""() => {
                const t = document.title;
                return t ? t.replace(/\\s*[-|·].*$/, '').trim() : '';
            }""") or ""

        # 카테고리 — compareDocumentPosition으로 h1 이후~data-item-id 버튼 이전 첫 텍스트 버튼 탐색
        # 구글 클래스명(DkEaL 등)은 빌드마다 변경되므로 위치 기반 탐색이 더 안정적
        category = await self.page.evaluate("""() => {
            const h1 = document.querySelector('h1');
            const firstDataBtn = document.querySelector('button[data-item-id]');
            if (!h1) return '';

            const skipTexts = new Set([
                '공유', '저장', '길안내', '전화', '사진', '리뷰', '더보기',
                'Share', 'Save', 'Directions', 'Call', 'Photos', 'Reviews', 'More'
            ]);

            // 버튼·링크를 DOM 순서대로 탐색
            for (const el of document.querySelectorAll('button:not([data-item-id]), a[jsaction]')) {
                // h1 이후인지 확인 (DOCUMENT_POSITION_FOLLOWING = 4)
                if (!(h1.compareDocumentPosition(el) & 4)) continue;
                // data-item-id 버튼 이전인지 확인 (DOCUMENT_POSITION_PRECEDING = 2)
                if (firstDataBtn && !(firstDataBtn.compareDocumentPosition(el) & 2)) continue;
                // SVG 아이콘(액션 버튼) 제외
                if (el.querySelector('svg, img, [role="img"]')) continue;

                const text = (el.innerText || el.textContent || '').trim();
                if (!text || text.length > 40) continue;
                if (skipTexts.has(text)) continue;
                if (/^[\\d.]+$/.test(text)) continue;        // 숫자만인 경우 제외
                if (/^\\([\\d,K천만]+\\)$/.test(text)) continue;  // (리뷰수) 형태 제외

                return text;
            }
            return '';
        }""") or ""

        # 평점 — aria-label 기반 (구글 접근성 속성은 안정적)
        score: float | None = None
        score_text = await self.page.evaluate("""() => {
            // aria-label에 '별' 또는 'star' 포함된 요소
            for (const el of document.querySelectorAll('[aria-label*="별"], [aria-label*="star"]')) {
                const m = el.getAttribute('aria-label').match(/([\\d.]+)/);
                if (m) return m[1];
            }
            // 클래스 직접 접근 (폴백)
            for (const sel of ['span.ceS6Me', 'div.F7ueS span', 'span.MW4etd']) {
                const el = document.querySelector(sel);
                if (el && /^[\\d.]+$/.test(el.innerText.trim())) return el.innerText.trim();
            }
            return '';
        }""") or ""
        if score_text:
            try:
                score = float(score_text)
            except ValueError:
                pass

        # 주소 — data-item-id='address' (구글이 안정적으로 유지하는 data 속성)
        address = ""
        addr_el = await self.page.query_selector("button[data-item-id='address']")
        if not addr_el:
            # 폴백: aria-label에 '주소' 포함
            addr_el = await self.page.query_selector(
                "button[aria-label*='주소'], button[aria-label*='Address'], "
                "[data-tooltip*='주소']"
            )
        if addr_el:
            # aria-label에서 "주소: " 접두사 제거
            label = await addr_el.get_attribute("aria-label") or ""
            if label:
                address = re.sub(r"^[^:：]+[:：]\s*", "", label).strip()
            if not address:
                # 내부 텍스트에서 aria-hidden 요소 제외하고 추출
                address = await addr_el.evaluate("""el => {
                    const spans = el.querySelectorAll('span:not([aria-hidden="true"])');
                    for (const s of spans) {
                        const t = (s.innerText || '').trim();
                        if (t && t.length > 5) return t;
                    }
                    return (el.innerText || '').trim();
                }""") or ""

        # 전화번호 — data-item-id^='phone' 만 사용 (aria-label*='전화'는 너무 광범위)
        # data-item-id='phone:tel:...' 형식으로 구글이 안정적으로 유지
        phone = ""
        phone_el = await self.page.query_selector("button[data-item-id^='phone']")
        if phone_el:
            label = await phone_el.get_attribute("aria-label") or ""
            if label:
                phone = re.sub(r"^[^:：]+[:：]\s*", "", label).strip()
            if not phone:
                phone = (await phone_el.inner_text()).strip()

        # 좌표 — Google Maps URL의 !3d(lat)!4d(lng) 인코딩 패턴 우선 추출
        # URL 예시: /maps/place/Name/data=...!3d37.3303!4d127.9449...
        lat, lng = None, None
        for _ in range(4):
            current_url = await self.page.evaluate("() => window.location.href")
            # 방법 1: 신버전 URL 데이터 파라미터 (most reliable)
            coord_m = re.search(r"!3d(-?\d+\.?\d+)!4d(-?\d+\.?\d+)", current_url)
            if coord_m:
                try:
                    lat_c = float(coord_m.group(1))
                    lng_c = float(coord_m.group(2))
                    if 33 < lat_c < 39 and 124 < lng_c < 132:
                        lat, lng = lat_c, lng_c
                        break
                except ValueError:
                    pass
            # 방법 2: 구버전 @lat,lng 형식
            coord_m2 = re.search(r"@(-?\d+\.?\d+),(-?\d+\.?\d+)", current_url)
            if coord_m2:
                try:
                    lat_c = float(coord_m2.group(1))
                    lng_c = float(coord_m2.group(2))
                    if 33 < lat_c < 39 and 124 < lng_c < 132:
                        lat, lng = lat_c, lng_c
                        break
                except ValueError:
                    pass
            await asyncio.sleep(2)

        if not lat:
            # 페이지 소스에서 좌표 추출 (최종 폴백)
            content = await self.page.content()
            for pattern in (
                r'"latitude":([-\d.]+),"longitude":([-\d.]+)',
                r'"lat":([-\d.]+),"lng":([-\d.]+)',
                r"!3d(-?\d+\.?\d+)!4d(-?\d+\.?\d+)",
            ):
                coord_m3 = re.search(pattern, content)
                if coord_m3:
                    try:
                        lat_c = float(coord_m3.group(1))
                        lng_c = float(coord_m3.group(2))
                        if 33 < lat_c < 39 and 124 < lng_c < 132:
                            lat, lng = lat_c, lng_c
                            break
                    except (ValueError, IndexError):
                        pass

        # 영업시간 — div.OMl5r 클릭 후 table tr 추출
        business_hours: dict[str, str] = {}
        try:
            hours_toggle = await self.page.query_selector(
                "div.OMl5r, button[aria-label*='영업시간'], div[aria-label*='영업']"
            )
            if hours_toggle:
                await hours_toggle.click()
                await random_delay(1, 2)

            rows = await self.page.query_selector_all(
                "table[aria-label*='영업'] tr, table[aria-label*='hour'] tr, "
                "div[aria-label*='영업시간'] tr, .t39EBf tr"
            )
            for row in rows:
                cells = await row.query_selector_all("td, th")
                if len(cells) >= 2:
                    day = (await cells[0].inner_text()).strip()
                    time_text = (await cells[1].inner_text()).strip()
                    if day:
                        business_hours[day] = time_text
        except Exception:
            pass

        menu_items: list[MenuItem] = []

        logger.info(
            "[구글] 상세 조회: %s | 카테고리=%s | 주소=%s | 좌표=(%s,%s)",
            name, category or "없음", address or "없음",
            lat or "없음", lng or "없음",
        )
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
        """리뷰 수집.

        data-review-id 속성으로 리뷰 컨테이너를 식별하고,
        내부 텍스트는 TreeWalker로 클래스명 독립적으로 추출한다.
        """
        assert self.page is not None

        url = f"{self.BASE_URL}/place/?q=place_id:{place_id}"
        if "place_id" not in self.page.url:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await random_delay(3, 5)

        # 리뷰 탭 클릭 — '리뷰' 텍스트 포함 탭 버튼 (작성 버튼 제외)
        # aria-label이 정확히 '리뷰' 이거나 '리뷰 N건' 형태인 탭만 클릭
        review_tab_clicked = False
        all_tabs = await self.page.query_selector_all("button[role='tab'], div[role='tab']")
        for tab in all_tabs:
            label = await tab.get_attribute("aria-label") or ""
            text = (await tab.inner_text()).strip()
            # "리뷰 작성" 등 쓰기 버튼 제외, 보기용 탭만 클릭
            if text in ("리뷰", "Reviews") or re.match(r"^리뷰\s*\d|^Reviews?\s*\d", label or text):
                await tab.click()
                await random_delay(2, 4)
                review_tab_clicked = True
                break

        # 위 방법 실패 시 리뷰 링크/버튼 탐색
        if not review_tab_clicked:
            review_link = self.page.locator(
                "a:has-text('리뷰'), button:has-text('리뷰')"
            ).filter(has_not_text="작성")
            if await review_link.count() > 0:
                await review_link.first.click()
                await random_delay(2, 4)

        reviews: list[Review] = []
        # 중복 방지: 이미 처리된 data-review-id 추적
        seen_review_ids: set[str] = set()

        # 리뷰 컨테이너 — data 속성 기반 (안정적)
        review_container = self.page.locator(
            "div.m6QErb.DxyBCb, div[role='main'] div.m6QErb"
        )

        scroll_count = 0
        max_scrolls = (limit // 5) + 5

        while len(reviews) < limit and scroll_count < max_scrolls:
            # data-review-id 속성 기반으로만 수집 (중복 셀렉터로 인한 중복 방지)
            review_items = await self.page.query_selector_all("div[data-review-id]")
            if not review_items:
                break

            new_count = 0
            for item in review_items:
                if len(reviews) >= limit:
                    break
                try:
                    # 중복 리뷰 건너뜀
                    review_id = await item.get_attribute("data-review-id") or ""
                    if review_id in seen_review_ids:
                        continue
                    seen_review_ids.add(review_id)

                    # "더보기" 버튼 클릭 (전문 보기)
                    more_btn = await item.query_selector(
                        "button.w8nwRe, button[aria-label*='더보기'], button[aria-label*='More']"
                    )
                    if more_btn:
                        await more_btn.click()
                        await random_delay(0.3, 0.8)

                    # 작성자 — 구조적 탐색 (첫번째 버튼의 텍스트)
                    author = await item.evaluate("""el => {
                        // 작성자는 보통 프로필 링크 또는 첫번째 버튼
                        const profileLink = el.querySelector('a[href*="contrib"], button.al6Kxe');
                        if (profileLink) {
                            const s = profileLink.querySelector('div, span');
                            if (s) return (s.innerText || '').trim();
                        }
                        // 폴백: class에 'd4r55' 포함 (작성자 div)
                        const d = el.querySelector('div.d4r55, [class*="d4r55"]');
                        return d ? (d.innerText || '').trim() : '';
                    }""") or ""

                    # 리뷰 텍스트 — TreeWalker로 가장 긴 텍스트 추출 (클래스명 독립)
                    text = await item.evaluate("""el => {
                        // "더보기" 클릭 후 span.wiI7pd가 없을 수도 있으므로 TreeWalker 사용
                        const datePattern = /^\\d+일|^\\d+주|^\\d+개월|^\\d+년/;
                        const uiTexts = new Set(['더보기', '좋아요', '신고']);
                        let best = '';
                        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
                        while (walker.nextNode()) {
                            const t = (walker.currentNode.textContent || '').trim();
                            if (!t || t.length < 5) continue;
                            if (datePattern.test(t)) continue;
                            if (uiTexts.has(t)) continue;
                            if (/^[\\d.]+$/.test(t)) continue;
                            if (t.length > best.length) best = t;
                        }
                        return best;
                    }""") or ""

                    # 평점 — aria-label 기반 (접근성 속성은 안정적)
                    r_score: float | None = None
                    star_el = await item.query_selector(
                        "span[role='img'][aria-label*='별'], span[role='img'][aria-label*='star']"
                    )
                    if star_el:
                        label = await star_el.get_attribute("aria-label") or ""
                        nums = re.findall(r"[\d.]+", label)
                        if nums:
                            try:
                                r_score = float(nums[0])
                            except ValueError:
                                pass

                    # 날짜 — 상대 날짜 패턴 탐색
                    date = await item.evaluate("""el => {
                        const datePattern = /\\d+일|\\d+주|\\d+개월|\\d+년/;
                        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
                        while (walker.nextNode()) {
                            const t = (walker.currentNode.textContent || '').trim();
                            if (datePattern.test(t) && t.length < 20) return t;
                        }
                        return '';
                    }""") or ""

                    if text:
                        reviews.append(Review(
                            author=author,
                            text=text,
                            score=r_score,
                            date=date,
                            platform=self.platform,
                        ))
                        new_count += 1
                except Exception as exc:
                    logger.warning("[구글] 리뷰 파싱 실패: %s", exc)
                    continue

            if new_count == 0:
                break  # 새 리뷰 없으면 종료

            # 스크롤 — .first 사용하여 strict mode violation 방지
            if await review_container.count() > 0:
                await review_container.first.evaluate("el => el.scrollTop = el.scrollHeight")
                await random_delay(1, 2)
            scroll_count += 1

        logger.info("[구글] 리뷰 수집: place_id=%s, %d건", place_id, len(reviews))
        return reviews[:limit]
