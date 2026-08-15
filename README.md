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

````bash
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


### 📂 프로젝트 폴더 및 파일 역할 명세서

```text
k-sales-hunter-ai/
├── .venv/                      # Python 가상환경 (Git 제외)
├── docs/                       # 기술 문서, 아키텍처 다이어그램 등 프로젝트 문서 보관
├── evals/                      # LLM 응답 품질 및 파이프라인 평가(Evaluation) 데이터/스크립트
├── migrations/                 # Alembic 데이터베이스 마이그레이션 버전 관리
├── scripts/                    # DB 초기화 및 관리 스크립트
│   └── init_db.sql             # Docker 실행 시 'ai' 전용 스키마 생성 및 권한 격리 SQL
│
├── src/app/                    # 메인 애플리케이션 소스 코드
│   ├── contracts/v1/           # 백엔드(Spring)와 공유하는 API DTO 스키마 및 계약 정의
│   │
│   ├── core/                   # 핵심 비즈니스 로직 및 AI 파이프라인
│   │   ├── agents/             # 특정 역할(통관, 마진 분석 등)을 수행하는 LLM 서브 에이전트
│   │   ├── graph/              # LangGraph 기반 워크플로 관리
│   │   │   ├── nodes/          # Graph 내 개별 실행 노드(수집, 검증, 계산 등)
│   │   │   ├── analysis.py     # 에이전트 노드 연결 및 Graph 구축 파일
│   │   │   └── state.py        # Graph 실행 중 공유되는 데이터 상태 구조체 (State)
│   │   │
│   │   ├── pricing/            # 정밀 수치 계산 엔진 (Pure Python)
│   │   │   └── engine.py       # 관부가세, 배송비, 마진율 정밀 계산 수식 코드
│   │   │
│   │   ├── providers/          # 외부 API 연동 모듈 (OpenAI, Tavily 등)
│   │   ├── rag/                # VectorDB(pgvector) 기반 규정 및 상품 문서 임베딩/검색 로직
│   │   └── tools/              # LLM이 사용할 커스텀 도구 함수 모음 (웹 크롤러 등)
│   │
│   ├── entrypoints/            # 서비스 실행 엔드포인트
│   │   └── runner.py           # Redis 메시지를 수신하여 비동기 AI 분석을 실행하는 워커 프로세스
│   │
│   ├── infra/                  # 데이터베이스 및 외부 인프라 레이어
│   │   ├── models.py           # SQLAlchemy 기반 DB 테이블 (ORM 모델)
│   │   └── redis_bus.py        # Redis Pub/Sub 이벤트 발신 및 작업 분산 락 관리
│   │
│   └── observability/          # LLM 호출 로그, 토큰 사용량, 파이프라인 모니터링 추적 모듈
│
├── tests/                      # Pytest 기반 단위 및 통합 테스트 코드
├── .env                        # [Git 제외] 비밀키 및 DB 접속 URL 등 환경 변수
├── .gitignore                  # Git 추적 제외 대상 목록
├── alembic.ini                 # Alembic DB 마이그레이션 설정 파일
├── docker-compose.yml          # PostgreSQL(pgvector) 및 Redis 컨테이너 구성 파일
├── pyproject.toml              # uv 기반 파이썬 의존성 패키지 및 프로젝트 설정 파일
└── README.md                   # 프로젝트 요약 및 Quick Start 가이드
````
