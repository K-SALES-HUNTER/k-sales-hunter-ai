.PHONY: help up down migrate revision dev test test-live lint fmt contracts demo-job clean

help:  ## 명령 목록
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up:  ## Postgres(pgvector) + Redis 컨테이너 실행
	docker compose up -d

down:  ## 컨테이너 정리
	docker compose down

migrate:  ## DB 스키마 최신화
	alembic upgrade head

revision:  ## 마이그레이션 생성  예) make revision m="add jobs"
	alembic revision --autogenerate -m "$(m)"

dev:  ## 개발 서버 (http://localhost:8000/docs)
	uvicorn app.entrypoints.http:app --reload --port 8000 --app-dir src

test:  ## 테스트 (실 LLM 호출 제외)
	pytest -m "not live" -q

test-live:  ## 실제 LLM 호출 테스트 (비용 발생, 주 1회 수동)
	pytest -m live -q

lint:  ## 린트 검사
	ruff check . && ruff format --check .

fmt:  ## 린트 자동 수정 + 포맷
	ruff check --fix . && ruff format .

contracts:  ## Pydantic -> JSON Schema (백엔드 공유용)
	python scripts/generate_contracts.py

demo-job:  ## HTTP 없이 분석 잡 1건 로컬 실행
	python scripts/run_local_job.py

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache
