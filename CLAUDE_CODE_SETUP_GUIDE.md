# 맛BTI 맵 — Claude Code 설정 가이드

> 이 문서는 2026년 3월 기준 Claude Code의 설정 시스템을 조사한 결과와, 맛BTI 맵 프로젝트에 최적화된 설정 파일 구성을 설명합니다.

---

## 1. Claude Code 설정 시스템 조사 결과

### 1.1 설정 파일 계층 구조

Claude Code는 **계층적 설정 시스템**을 사용합니다. 낮은 레벨일수록 높은 우선순위를 가집니다:

| 계층 | 위치 | 용도 | 우선순위 |
|------|------|------|----------|
| Global | `~/.claude/CLAUDE.md` | 모든 프로젝트 공통 개인 선호 | 낮음 |
| Project | `./CLAUDE.md` (프로젝트 루트) | 프로젝트 전체에 적용되는 컨텍스트 | 중간 |
| Rules | `.claude/rules/*.md` | 파일 타입/영역별 세분화된 규칙 | 높음 |
| Local | `CLAUDE.local.md` | 개인 오버라이드 (.gitignore) | 최고 |

### 1.2 핵심 파일별 역할

#### CLAUDE.md (프로젝트 루트)
- **매 세션 시작 시 자동 로드** — 가장 중요한 파일
- 프로젝트 개요, 기술 스택, 빌드 명령어, 핵심 원칙을 담음
- **간결하게 유지해야 함**: 너무 길면 Claude가 지시를 무시하기 시작
- `@path/to/file` 문법으로 외부 문서 참조 가능
- `/init` 명령으로 초안 생성 후 수동으로 다듬는 것이 권장됨

#### .claude/rules/ (규칙 파일)
- **영역별로 분리된 지시사항** — CLAUDE.md 비대화 방지
- 모든 `.md` 파일이 자동 로드됨
- 백엔드/프론트엔드/DB/보안 등 관심사별로 분리
- 해당 영역 작업 시에만 관련 규칙이 활성화됨

#### .claude/skills/ (스킬)
- **온디맨드 로드** — 세션 시작 시에는 name + description만 로드
- 관련 작업이 감지되면 SKILL.md 전문을 로드
- `/skill-name`으로 직접 호출 가능
- YAML frontmatter (`name`, `description`) 필수
- description을 "pushy"하게 작성해야 트리거가 잘 됨

#### .claude/agents/ (서브에이전트)
- **독립 컨텍스트 윈도우**에서 실행되는 전문 에이전트
- 코드 리뷰, 테스트 작성 등 특정 도메인에 특화
- `tools` 필드로 접근 가능한 도구 제한 가능
- `model` 필드로 비용/품질 최적화 (sonnet vs opus vs haiku)

#### .claude/settings.json (설정)
- 허용/차단 명령어 (permissions)
- Hooks: 파일 수정 후 자동 린트 등 결정론적 동작
- MCP 서버 연결 설정

### 1.3 베스트 프랙티스 요약

1. **CLAUDE.md는 짧게**: "이 줄을 제거해도 Claude가 실수할까?" — 아니라면 삭제
2. **Rules로 분리**: 400줄짜리 CLAUDE.md 대신, 영역별 규칙 파일로 분산
3. **Skills는 도메인 지식**: 항상 필요하지 않지만 특정 작업에 깊은 맥락을 제공
4. **Agents는 격리 실행**: 탐색/리뷰 작업을 메인 대화에서 분리하여 컨텍스트 오염 방지
5. **Hooks는 필수 동작**: CLAUDE.md의 "권고"와 달리, 100% 실행 보장
6. **50% 컨텍스트에서 /compact**: 70% 넘으면 정밀도 하락, 90% 넘으면 환각 증가

---

## 2. 맛BTI 맵 프로젝트 설정 파일 구성

### 2.1 디렉토리 구조

```
matbti-map/
├── CLAUDE.md                          ← 프로젝트 핵심 컨텍스트 (매 세션 로드)
│
├── .claude/
│   ├── settings.json                  ← 권한, Hooks 설정
│   ├── .mcp.json                      ← MCP 서버 연결 (확장용)
│   │
│   ├── rules/                         ← 영역별 규칙 (자동 로드)
│   │   ├── backend-python.md          ← FastAPI, SQLAlchemy, 비동기 패턴
│   │   ├── frontend-nextjs.md         ← Next.js, 카카오맵, Zustand
│   │   ├── database.md                ← PostgreSQL, PostGIS, pgvector
│   │   └── security.md               ← API키, 인증, 입력 검증
│   │
│   ├── skills/                        ← 도메인 스킬 (온디맨드 로드)
│   │   ├── crawling/
│   │   │   └── SKILL.md               ← 3대 플랫폼 크롤링 전략
│   │   ├── entity-resolution/
│   │   │   └── SKILL.md               ← 동일 식당 병합 알고리즘
│   │   ├── rag-pipeline/
│   │   │   └── SKILL.md               ← RAG 추천 파이프라인
│   │   ├── taste-analysis/
│   │   │   └── SKILL.md               ← 맛BTI 취향 분석
│   │   └── phase-plan/
│   │       └── SKILL.md               ← 개발 단계별 계획
│   │
│   └── agents/                        ← 서브에이전트 (격리 실행)
│       ├── code-reviewer.md           ← 코드 리뷰 전문가
│       └── test-writer.md             ← 테스트 작성 전문가
│
└── docs/                              ← 참조 문서 (@import용)
    ├── project-spec.md                ← 전체 기술 명세서 Part 1
    └── db-schema.md                   ← 전체 기술 명세서 Part 2
```

### 2.2 각 파일의 역할과 설계 의도

#### CLAUDE.md (62줄)
- 프로젝트 한 줄 요약, 기술 스택, 디렉토리 구조
- 5개의 핵심 원칙 (할루시네이션 방지가 1번)
- 빌드/테스트/도커 명령어
- Git 컨벤션
- `@docs/` 참조로 상세 명세서 연결

#### Rules (4개 파일)
| 파일 | 적용 대상 | 핵심 내용 |
|------|-----------|-----------|
| `backend-python.md` | `backend/**/*.py` | FastAPI 컨벤션, 비동기 패턴, 에러 처리 |
| `frontend-nextjs.md` | `frontend/**/*.tsx` | App Router, 카카오맵 SDK, Zustand |
| `database.md` | SQL, 마이그레이션 | PostGIS 좌표, pgvector 쿼리, 네이밍 |
| `security.md` | 전체 | 환경 변수, 크롤링 보안, JWT, 입력 검증 |

#### Skills (5개)
| 스킬 | 트리거 | 내용 |
|------|--------|------|
| `crawling` | 크롤러, 스크래퍼, Playwright | 3대 플랫폼별 전략, Anti-Bot, 셀렉터 |
| `entity-resolution` | 식당 매칭, 병합, 중복 | 3단계 알고리즘, 대표값 선택 규칙 |
| `rag-pipeline` | 추천, 벡터 검색, LangChain | 4단계 파이프라인, SSE 스트리밍 |
| `taste-analysis` | 설문, 맛BTI, 프로파일 | 8문항 설문, LLM 프로파일링, 벡터화 |
| `phase-plan` | 진행 상황, 다음 단계 | Week별 구현 계획, 완료 기준 |

#### Agents (2개)
| 에이전트 | 도구 제한 | 모델 | 용도 |
|----------|-----------|------|------|
| `code-reviewer` | Read, Grep, Glob (읽기 전용) | Sonnet | 할루시네이션 방지, 비동기, 보안 리뷰 |
| `test-writer` | Read, Write, Edit, Bash, Glob, Grep | Sonnet | pytest/Jest 테스트 생성 |

#### settings.json
- **allow**: pytest, npm, alembic, docker-compose 등 개발 명령어 허용
- **deny**: `rm -rf /`, API키 출력 등 위험 명령어 차단
- **hooks**: Python 파일 수정 후 자동 구문 검사 (`py_compile`)

---

## 3. 사용법

### 3.1 초기 셋업

```bash
# 1. 프로젝트 루트에 설정 파일 배치
cp -r .claude/ matbti-map/.claude/
cp CLAUDE.md matbti-map/CLAUDE.md

# 2. 기술 명세서를 docs/에 배치
mkdir -p matbti-map/docs
cp matbti_project_spec.md matbti-map/docs/project-spec.md
cp matbti_project_spec_part2.md matbti-map/docs/db-schema.md

# 3. Claude Code 시작
cd matbti-map
claude
```

### 3.2 일상 작업 예시

```bash
# 크롤러 작업 시 — crawling 스킬 자동 활성화
> "카카오맵 크롤러 구현해줘"

# 스킬 직접 호출
> /crawling
> /entity-resolution
> /phase-plan

# 코드 리뷰 요청 시 — code-reviewer 에이전트 활성화
> "scrapers/ 폴더의 코드를 리뷰해줘"

# 테스트 작성 — test-writer 에이전트 활성화
> "recommendation.py에 대한 테스트를 작성해줘"

# 컨텍스트 관리
> /compact        # 50% 도달 시
> /clear          # 새 작업으로 전환 시
```

### 3.3 설정 유지보수

- **주기적 점검**: Claude가 지시를 무시하면 CLAUDE.md가 너무 긴지 확인
- **Rules 추가**: 새로운 패턴 반복 시 해당 영역 rules에 추가
- **Skills 업데이트**: 크롤러 셀렉터 변경 시 crawling/SKILL.md 갱신
- **Git 관리**: CLAUDE.md와 .claude/ 전체를 git에 커밋하여 팀 공유
