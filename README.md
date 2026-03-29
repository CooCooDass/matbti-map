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

