-- 로컬 개발용 DB 초기화.
-- 운영에서는 DBA(또는 백엔드 담당자)가 동일한 권한 구성을 적용한다.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS ai;

-- AI 서비스 전용 계정.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_service') THEN
        CREATE ROLE ai_service LOGIN PASSWORD 'ai_service_pw';
    END IF;
END
$$;

GRANT USAGE, CREATE ON SCHEMA ai TO ai_service;
GRANT ALL ON ALL TABLES IN SCHEMA ai TO ai_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA ai GRANT ALL ON TABLES TO ai_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA ai GRANT ALL ON SEQUENCES TO ai_service;

-- 핵심: 업무 데이터(public)에 손댈 수 없게 만든다.
-- "AI 는 업무 DB 를 건드리지 않는다"를 문서상 약속이 아니라 권한으로 강제한다.
REVOKE ALL ON SCHEMA public FROM ai_service;
ALTER ROLE ai_service SET search_path = ai;
