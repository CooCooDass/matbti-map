#Project Structure
```text
matbti-map/
├── backend/app/          # FastAPI 앱
│   ├── models/           # SQLAlchemy 모델
│   ├── schemas/          # Pydantic 스키마
│   ├── api/              # API 라우터
│   ├── services/         # 비즈니스 로직
│   ├── llm/              # LLM 체인, 프롬프트, 임베딩
│   └── scrapers/         # 3대 플랫폼 크롤러
├── frontend/src/         # Next.js 앱
│   ├── app/              # App Router pages
│   ├── components/       # React 컴포넌트
│   ├── store/            # Zustand 스토어
│   └── lib/              # API 클라이언트, 유틸
└── data/                 # seed 데이터, SQL 마이그레이션
```
#Phase Plan
<phase_1_a>
## Phase 1-A (Week 1-2): Crawler + Supabase Integration (크롤러 + Supabase 연동)

1. Implement `BaseScraper` abstract class
2. Implement 3 Platform Scrapers (Kakao, Naver, Google)
3. Set up local JSONL staging pipeline (`data/raw_listings.jsonl`에 임시 저장)
4. Create Supabase DB schema migration with Alembic
5. Implement Supabase bulk-push pipeline to `platform_listings` table (Supabase 일괄 푸시)
</phase_1_a>

<phase_1_b>
## Phase 1-B (Week 3): Data Processing (데이터 처리)

1. Entity Resolution logic (`entity_resolver.py`)
2. Review LLM analysis pipeline (`review_processor.py`)
3. Create review/restaurant embeddings -> load into pgvector (생성 → pgvector 적재)
</phase_1_b>

<phase_2>
## Phase 2 (Week 4): MatBTI System (맛BTI 시스템)

1. Survey API (`POST /api/taste/survey`)
2. LLM Taste Profiling (`taste_analyzer.py`)
3. Vectorize tastes -> `user_taste_profiles.taste_vector` (취향 벡터화)
</phase_2>

<phase_3>
## Phase 3 (Week 5-6): RAG Recommendation Engine (RAG 추천 엔진)

1. Hybrid Search (SQL Filter + Vector Similarity)
2. Implement LangChain RAG chain (`chains.py`)
3. Implement SSE streaming response
4. Course planning feature
</phase_3>

<phase_4>
## Phase 4 (Week 7-8): Frontend + Integration (프론트엔드 + 통합)

1. Next.js project setup
2. Kakao Map UI (Markers, clustering, overlays) (마커, 클러스터링, 오버레이)
3. Chat interface (SSE Streaming)
4. MatBTI survey UI (step-by-step wizard)
5. Restaurant detail page
6. API integration and E2E tests
</phase_4>

## 🚩 현재 진행 상황 (Phase 1-A)
- 네이버 연동 완료됨.
- 카카오 연동 완료됨.
- 구글 연동 및 Supabase 연동 준비 중
- 현재 크롤링 고도화 단계
## 🛠 개발 환경 세팅 (uv 사용)
우리 프로젝트는 패키지 관리를 위해 `uv`를 사용함. 기존 `pip`보다 훨씬 빠르고 버전 충돌 걱정 없음.

### 1. uv 설치

- **Windows (PowerShell)**:
  ```powershell
  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- **macOS / Linux**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
*(설치 후 터미널 한 번 껐다 키면 적용됨)*

### 2. 프로젝트 가져오기 및 설치

```bash
# 1. 저장소 복제 (GitHub 초기 설정)
git clone https://github.com/CooCooDass/matbti-map.git
cd matbti-map

# 2. 패키지 설치 및 동기화
uv sync
```

### 3. 프로젝트 실행
가상환경 활성화 번거롭게 할 필요 없음. 바로 `uv run` 쓰면 됨.

```bash
uv run main.py
```

### 4. 패키지 추가 (Library 설치 시)
새로 설치할 거 있으면 `pip` 말고 아래 명령어 사용 바람. `pyproject.toml`이랑 `uv.lock`에 자동 기록됨.

```bash
uv add [패키지명]
```

## 🤝 협업 규칙 (Git 초보용)
- 코드 수정 후에는 `git status`로 상태 수시로 확인.
- `git add .` -> `git commit -m "메시지"` 순서로 로컬에 저장.
- 마지막에 `git push`로 깃허브에 올리면 끝.
- **가장 중요**: 작업 시작 전에는 항상 `git pull` 받아서 남이 올린 최신 코드랑 합칠 것.

---

