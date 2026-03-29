<overview>
Interactive map web service that integrates NAVER Map, Kakao Map, and Google Maps reviews into a unified DB, providing personalized restaurant/course recommendations through LLM-based taste analysis (맛BTI) + RAG. Target region: Wonju. (원주시)
</overview>

<tech_stack>
**versionControl**: uv 
**Backend**: Python 3.11+, FastAPI (async), SQLAlchemy 2.0 (async), Celery + Redis, Playwright (async)
**AI/LLM**: OpenAI GPT-4o / GPT-4o-mini, text-embedding-3-small (1536dim), LangChain
**DB**: Supabase (PostgreSQL 16 + PostGIS + pgvector), Redis
**Frontend**: Next.js 14 (App Router), Kakao Maps SDK, Zustand, TypeScript
**Infra**: Local JSONL Staging -> Supabase Bulk Push (Docker optional)
</tech_stack>

<project_structure>
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
</project_structure>

<core_principles>
**All recommendations MUST be based on the internal DB (RDB + VectorDB).** The LLM must absolutely not fabricate restaurants that do not exist in the DB.
**Anti-Hallucination (할루시네이션 방지)**: When generating a RAG response, reference only the restaurant data included in the context. If the DB query returns no results, honestly answer "There is no data" ("데이터가 없습니다").
**Async Priority (비동기 우선)**: All I/O operations must use async/await. Use `async def` instead of `def`.
**Type Hinting Required (타입 힌트 필수)**: Python requires type hints for all functions. TypeScript must be in strict mode.
**Korean Comments (한글 주석)**: Write code comments and docstrings in Korean.
</core_principles>

<build_and_test_commands>
```bash
# Backend
pytest tests/ -v                          # 전체 테스트
pytest tests/test_api/ -v -k "test_name"  # 단일 테스트
alembic upgrade head                      # DB 마이그레이션

# Frontend
cd frontend && npm install
npm run dev                               # 개발 서버 (localhost:3000)
npm run build                             # 프로덕션 빌드
npm run lint                              # ESLint

# DB (Supabase)
# Configure .env with SUPABASE_URL and SUPABASE_KEY
```
</build_and_test_commands>

<git_convention>
- Commit message: `type(scope): description` (예: `feat(scraper): 카카오맵 크롤러 구현`)
- Types: feat, fix, refactor, test, docs, chore
- Branches: `feature/xxx`, `fix/xxx`, `refactor/xxx`
</git_convention>

<references>
- @docs/project-spec.md (전체 기술 명세서)
- @docs/db-schema.md (DB 스키마 정의)
</references>
