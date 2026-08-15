# 🛒 K-Sales Hunter AI Engine

> **해외 역직구(Cross-Border E-Commerce) 셀러를 위한 AI 기반 상품 분석 & 마진 정산 엔진**

`K-Sales Hunter AI`는 상품 수집, 통관/규제 검증, 관부가세/배송비 정산, 마진 계산 및 AI 리포트 생성까지의 전체 파이프라인을 **LangGraph** 기반의 에이전트 워크플로로 자동화하는 백엔드 AI 서비스입니다.

---

## 🛠 Tech Stack

| 구분                       | 기술 스택                                           |
| -------------------------- | --------------------------------------------------- |
| **Language & Environment** | Python 3.12+, uv (Package Manager)                  |
| **Frameworks**             | FastAPI, LangGraph, SQLAlchemy (Async), Pydantic v2 |
| **Database & Cache**       | PostgreSQL (pgvector), Redis (Event Bus & Cache)    |
| **Database Migration**     | Alembic                                             |
| **LLM & Search API**       | OpenAI GPT-4o, Tavily Search API                    |

---

## 🚀 Quick Start (빠른 실행 가이드)

### 1. 가상환경 세팅 및 패키지 설치

```bash
# uv로 파이썬 3.12 가상환경 생성
uv venv --python 3.12

# 가상환경 활성화 (Windows)
.venv\Scripts\activate
# 가상환경 활성화 (Mac/Linux)
source .venv/bin/activate

# 개발 의존성 패키지 설치
uv pip install -e ".[dev]"
2. 인프라 실행 (Docker Desktop 필수)
Bash
# PostgreSQL(pgvector) 및 Redis 컨테이너 실행
docker-compose up -d
3. DB 마이그레이션 (Alembic)
Bash
# DB 스키마 생성 및 업데이트
alembic upgrade head
4. 개발 서버 실행
Bash
# FastAPI 개발 서버 띄우기
uvicorn app.entrypoints.http:app --reload


📂 Project Structure
Plaintext
k-sales-hunter-ai/
├── migrations/             # Alembic DB 마이그레이션 파일
├── scripts/                # DB 초기화 및 스키마 검증 스크립트
├── src/
│   └── app/
│       ├── contracts/      # 백엔드(Spring)와 공유하는 API DTO/계약 스크립트
│       ├── core/           # 핵심 AI 및 비즈니스 로직
│       │   ├── graph/      # LangGraph 에이전트 워크플로 & 노드
│       │   └── pricing/    # 정밀 마진/비용 계산 엔진 (Pure Python)
│       ├── entrypoints/    # FastAPI / Runner 엔드포인트
│       └── infra/          # DB ORM 모델 및 Redis 이벤트 버스
├── tests/                  # Pytest 단위 및 통합 테스트
├── docker-compose.yml      # DB / Redis 컨테이너 정의
└── pyproject.toml          # 프로젝트 패키지 및 의존성 설정
```
