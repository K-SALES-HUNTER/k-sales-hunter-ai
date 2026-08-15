-- 로컬 개발용 DB 초기화.
-- 운영에서는 DBA(또는 백엔드 담당자)가 동일한 권한 구성을 적용한다.
--
-- 이 스크립트는 docker-entrypoint-initdb.d 에 마운트되어
-- 볼륨이 비어 있을 때 최초 1회만 실행된다.
-- 내용을 고친 뒤에는 반드시 `docker compose down -v` 로 볼륨을 지우고 다시 올려야 반영된다.

-- pgvector. superuser 권한이 필요하므로 여기서 처리한다.
-- public 스키마에 설치되며, ai_service 는 search_path 로 참조한다.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS ai;


-- ---------------------------------------------------------------------------
-- AI 서비스 전용 계정
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_service') THEN
        CREATE ROLE ai_service LOGIN PASSWORD 'ai_service_pw';
    END IF;
END
$$;

GRANT USAGE, CREATE ON SCHEMA ai TO ai_service;
GRANT ALL ON ALL TABLES IN SCHEMA ai TO ai_service;
GRANT ALL ON ALL SEQUENCES IN SCHEMA ai TO ai_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA ai GRANT ALL ON TABLES TO ai_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA ai GRANT ALL ON SEQUENCES TO ai_service;


-- ---------------------------------------------------------------------------
-- 핵심: 업무 데이터(public)에 손댈 수 없게 만든다.
-- "AI 는 업무 DB 를 건드리지 않는다"를 문서상 약속이 아니라 권한으로 강제한다.
--
-- [주의] 특정 유저에게서만 REVOKE 하면 실효가 없다.
--        public 스키마의 권한은 PUBLIC 이라는 암묵 롤에도 부여되어 있어서,
--        ai_service 에서 회수해도 PUBLIC 경유로 그대로 접근된다.
--        반드시 PUBLIC 롤에서 먼저 회수해야 한다.
-- ---------------------------------------------------------------------------

-- 1) PUBLIC 롤에서 회수. 이게 실질적인 차단이다.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;

-- 2) 앞으로 Spring(Flyway)이 만들 테이블에도 같은 규칙을 적용한다.
--    이게 없으면 신규 테이블이 생길 때마다 구멍이 다시 열린다.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM PUBLIC;

-- 3) ai_service 개별 권한도 회수.
REVOKE ALL ON SCHEMA public FROM ai_service;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM ai_service;

-- 4) 단, public 스키마 자체는 "볼 수" 있어야 한다.
--    vector 타입이 public 에 설치되어 있어서, USAGE 가 없으면
--    ai.rag_documents 생성이 'type "vector" does not exist' 로 실패한다.
--    USAGE 는 스키마 안의 객체를 참조할 수 있게 할 뿐,
--    테이블 조회 권한은 위 REVOKE 로 여전히 막혀 있다.
GRANT USAGE ON SCHEMA public TO ai_service;

-- 5) 검색 경로. ai 를 우선하되 public 은 타입 참조용으로 남긴다.
ALTER ROLE ai_service SET search_path = ai, public;


-- ---------------------------------------------------------------------------
-- 격리 검증용 더미 테이블.
-- 아래 두 명령의 결과가 기대와 다르면 권한 구성이 깨진 것이다.
--
--   docker compose exec postgres \
--     psql -U ai_service -d sales_hunter -c "select * from public._isolation_probe"
--   -> permission denied for table _isolation_probe   (이게 정상)
--
--   docker compose exec postgres \
--     psql -U ai_service -d sales_hunter -c "select 1::vector(1)"
--   -> 정상 출력  (vector 타입 참조는 되어야 한다)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public._isolation_probe (id int);
INSERT INTO public._isolation_probe VALUES (1);
REVOKE ALL ON public._isolation_probe FROM PUBLIC;
REVOKE ALL ON public._isolation_probe FROM ai_service;
