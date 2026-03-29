"""카카오맵 크롤러.

iframe 없이 메인 DOM에서 결과를 렌더링하므로 가장 크롤링이 용이하다.
페이지네이션: 1~5페이지, 페이지당 15개.
"""

from __future__ import annotations

import logging
import re

from backend.app.scrapers.anti_detect import random_delay
from backend.app.scrapers.base import BaseScraper, retry
from backend.app.scrapers.models import BasicInfo, DetailInfo, MenuItem, Review

logger = logging.getLogger(__name__)


class KakaoMapsScraper(BaseScraper):
    """카카오맵 크롤러."""

    platform = "kakao"
    BASE_URL = "https://map.kakao.com"

    @retry(max_retries=3)
    async def search(self, query: str, region: str = "원주") -> list[BasicInfo]:
        """카카오맵에서 검색."""
        assert self.page is not None
        search_query = f"{region} {query}"

        await self.page.goto(self.BASE_URL, wait_until="networkidle", timeout=30000)
        await random_delay(1, 2)

        # 검색어 입력
        search_input = self.page.locator("#search\\.keyword\\.query, #search\\.keyword\\.input")
        await search_input.fill(search_query)
        await self.page.keyboard.press("Enter")
        await random_delay(2, 4)

        results: list[BasicInfo] = []

        # 최대 5페이지 크롤링
        for page_num in range(1, 6):
            # 검색 결과 리스트 대기
            await self.page.wait_for_selector(
                ".PlaceItem, .placelist > .lazyload_wrapper",
                timeout=10000,
            )

            items = await self.page.query_selector_all(
                ".PlaceItem, .placelist > .lazyload_wrapper"
            )

            for item in items:
                try:
                    # 이름
                    name_el = await item.query_selector(
                        ".link_name, .head_item .tit_name .link_name"
                    )
                    name = (await name_el.inner_text()).strip() if name_el else ""
                    if not name:
                        continue

                    # 카테고리
                    cat_el = await item.query_selector(
                        ".subcategory, .head_item .subcategory"
                    )
                    category = (await cat_el.inner_text()).strip() if cat_el else ""

                    # 주소
                    addr_el = await item.query_selector(
                        ".addr p:first-child, .info_item .addr"
                    )
                    address = (await addr_el.inner_text()).strip() if addr_el else ""

                    # 평점
                    score: float | None = None
                    score_el = await item.query_selector(".score .num, .rating .score")
                    if score_el:
                        score_text = (await score_el.inner_text()).strip()
                        try:
                            score = float(score_text)
                        except ValueError:
                            score = None

                    # 리뷰 수
                    review_count = 0
                    review_el = await item.query_selector(
                        ".review em, .numberofscore, .cnt_review"
                    )
                    if review_el:
                        text = (await review_el.inner_text()).strip()
                        nums = re.findall(r"\d+", text.replace(",", ""))
                        if nums:
                            review_count = int(nums[0])

                    # place_id — moreview/numberofscore 링크에서 추출
                    place_id = ""
                    for pid_sel in ["a.moreview", "a.numberofscore", "a.review"]:
                        link = await item.query_selector(pid_sel)
                        if link:
                            href = await link.get_attribute("href") or ""
                            pid_match = re.search(r"/(\d+)", href)
                            if pid_match:
                                place_id = pid_match.group(1)
                                break

                    results.append(BasicInfo(
                        name=name,
                        platform_place_id=place_id,
                        platform=self.platform,
                        category=category,
                        address_road=address,
                        score=score,
                        review_count=review_count,
                    ))

                except Exception as exc:
                    logger.warning("카카오 검색 결과 파싱 실패: %s", exc)
                    continue

            # 다음 페이지
            if page_num < 5:
                next_btn = self.page.locator(f"#info\\.search\\.page\\.no{page_num + 1}")
                if await next_btn.count() > 0 and await next_btn.is_visible():
                    await next_btn.click()
                    await random_delay(2, 3)
                else:
                    break

        logger.info("[카카오] '%s' 검색 결과: %d건", search_query, len(results))
        return results

    @retry(max_retries=3)
    async def get_detail(self, place_id: str) -> DetailInfo:
        """place_id로 상세 정보 조회."""
        assert self.page is not None
        url = f"https://place.map.kakao.com/{place_id}"

        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        await random_delay(2, 3)

        # 이름 — 새 SPA: h3.tit_place / 구버전: h2.tit_location
        name = ""
        for sel in ["h3.tit_place", ".tit_place", "h2.tit_location", ".tit_location"]:
            el = await self.page.query_selector(sel)
            if el:
                name = (await el.inner_text()).strip()
                break

        # 카테고리 — 새 SPA: span.info_cate / 구버전: span.txt_location
        category = ""
        for sel in ["span.info_cate", ".info_cate", "span.txt_location", ".subcategory"]:
            el = await self.page.query_selector(sel)
            if el:
                raw = (await el.inner_text()).strip()
                # "장소 카테고리" 스크린리더 텍스트 제거
                category = raw.replace("장소 카테고리", "").strip()
                break

        # 주소 — 새 SPA: .tit_info 중 "주소" 찾기 / 구버전: span.txt_address
        address = await self.page.evaluate('''() => {
            // 새 SPA 레이아웃
            let icons = document.querySelectorAll(".tit_info");
            for (let icon of icons) {
                if (icon.innerText.includes("주소")) {
                    let container = icon.closest(".unit_default");
                    if (container) {
                        let txt = container.querySelector(".txt_detail");
                        if (txt) return txt.innerText.replace(/\(우\).*$/, "").trim();
                    }
                }
            }
            // 구버전 레이아웃
            let el = document.querySelector("span.txt_address, .txt_address");
            return el ? el.innerText.trim() : "";
        }''') or ""

        # 전화번호 — 새 SPA: .tit_info 중 "전화" 찾기 / 구버전: span.txt_contact
        phone = await self.page.evaluate('''() => {
            let icons = document.querySelectorAll(".tit_info");
            for (let icon of icons) {
                if (icon.innerText.includes("전화")) {
                    let container = icon.closest(".unit_default");
                    if (container) {
                        let txt = container.querySelector(".txt_detail");
                        if (txt) return txt.innerText.trim();
                    }
                }
            }
            let el = document.querySelector("span.txt_contact, .txt_contact");
            return el ? el.innerText.trim() : "";
        }''') or ""

        # 평점 — 새 SPA: span.num_star / 구버전: span.num_rate, .score .num
        score: float | None = None
        for sel in [".num_star", "span.num_rate", ".score .num"]:
            el = await self.page.query_selector(sel)
            if el:
                try:
                    score = float((await el.inner_text()).strip())
                except ValueError:
                    pass
                break

        # 영업시간 — 새 SPA: .line_fold / 구버전: .list_operation li
        business_hours: dict[str, str] = {}
        hours_els = await self.page.query_selector_all(
            ".line_fold, .list_operation li, .openhour_list li"
        )
        for el in hours_els:
            day_el = await el.query_selector(".tit_fold, .day")
            time_el = await el.query_selector(".detail_fold, .time")
            if day_el and time_el:
                day = (await day_el.inner_text()).strip()
                time_text = (await time_el.inner_text()).strip()
                business_hours[day] = time_text.replace("\n", " ")
            else:
                text = (await el.inner_text()).strip()
                if text:
                    parts = text.split(None, 1)
                    if len(parts) == 2:
                        business_hours[parts[0]] = parts[1]

        # 메뉴 — 새 SPA: .list_goods > li / 구버전: .list_menu li
        menu_items: list[MenuItem] = []
        menu_els = await self.page.query_selector_all(
            ".list_goods > li, .list_menu li, .menuinfo_list li"
        )
        for el in menu_els[:20]:
            try:
                m_name_el = await el.query_selector(".tit_item, .tit_menu, .loss_word, .name")
                m_price_el = await el.query_selector(".desc_item, .price_menu, .price")
                m_name = (await m_name_el.inner_text()).strip() if m_name_el else ""
                m_price = (await m_price_el.inner_text()).strip() if m_price_el else ""
                if m_name:
                    menu_items.append(MenuItem(name=m_name, price=m_price))
            except Exception:
                continue

        # 좌표 — 메타 태그 또는 스크립트에서 추출
        lat, lng = None, None
        try:
            content = await self.page.content()
            lat_match = re.search(r'"lat":\s*([\d.]+)', content)
            lng_match = re.search(r'"lng":\s*([\d.]+)', content)
            if lat_match and lng_match:
                lat = float(lat_match.group(1))
                lng = float(lng_match.group(1))
        except Exception:
            pass

        logger.info("[카카오] 상세 조회: %s (place_id=%s)", name, place_id)
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

    @retry(max_retries=3)
    async def get_reviews(self, place_id: str, limit: int = 50) -> list[Review]:
        """리뷰 수집."""
        assert self.page is not None
        url = f"https://place.map.kakao.com/{place_id}"

        if place_id not in self.page.url:
            await self.page.goto(url, wait_until="networkidle", timeout=30000)
            await random_delay(2, 3)

        # 리뷰 탭 클릭 — 새 SPA: a.link_tab 중 "후기"
        review_tab = self.page.locator(
            "a.link_tab:has-text('후기'), a[href*='comment'], a[href*='review']"
        )
        if await review_tab.count() > 0:
            await review_tab.first.click()
            await random_delay(2, 3)

        reviews: list[Review] = []

        while len(reviews) < limit:
            # 새 SPA: .list_review > li / 구버전: .list_evaluation li
            review_items = await self.page.query_selector_all(
                ".list_review > li, .list_evaluation li, .comment_item"
            )
            if not review_items:
                break

            for item in review_items:
                if len(reviews) >= limit:
                    break
                try:
                    # 작성자 — 새 SPA: .name_user / 구버전: .txt_name
                    author = ""
                    for sel in [".name_user", ".txt_name", ".author"]:
                        a_el = await item.query_selector(sel)
                        if a_el:
                            author = (await a_el.inner_text()).strip()
                            # 스크린리더 텍스트 제거
                            author = author.replace("리뷰어 이름,", "").strip()
                            break

                    # 리뷰 텍스트 — 새 SPA: .desc_review / 구버전: .txt_comment
                    text = ""
                    for sel in [".desc_review", "p.desc_review", ".txt_comment", ".comment_txt"]:
                        t_el = await item.query_selector(sel)
                        if t_el:
                            text = (await t_el.inner_text()).strip()
                            # "더보기" 텍스트 제거
                            text = text.replace("더보기", "").strip()
                            break

                    # 평점 — 새 SPA: .figure_star.on 개수로 추정 / 구버전: .num_rate
                    r_score: float | None = None
                    stars = await item.query_selector_all(".figure_star.on")
                    if stars:
                        r_score = float(len(stars))
                    else:
                        for sel in [".num_rate", ".score .num"]:
                            s_el = await item.query_selector(sel)
                            if s_el:
                                try:
                                    r_score = float((await s_el.inner_text()).strip())
                                except ValueError:
                                    pass
                                break

                    # 날짜 — 새 SPA: .txt_date / 구버전: .time_write
                    date = ""
                    for sel in [".txt_date", ".time_write", ".date"]:
                        d_el = await item.query_selector(sel)
                        if d_el:
                            date = (await d_el.inner_text()).strip()
                            break

                    if text:
                        reviews.append(Review(
                            author=author,
                            text=text,
                            score=r_score,
                            date=date,
                            platform=self.platform,
                        ))
                except Exception as exc:
                    logger.warning("카카오 리뷰 파싱 실패: %s", exc)
                    continue

            # 더보기 버튼 — 새 SPA: .link_more / 구버전: .btn_more
            more_btn = self.page.locator(
                "a.link_more:has-text('더보기'), .link_more:has-text('더보기'), .btn_more"
            )
            if await more_btn.count() > 0 and await more_btn.first.is_visible() and len(reviews) < limit:
                await more_btn.first.click()
                await random_delay(2, 3)
            else:
                break

        logger.info("[카카오] 리뷰 수집: place_id=%s, %d건", place_id, len(reviews))
        return reviews[:limit]
