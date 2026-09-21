# 협업 컨벤션

3개 레포(`k-sales-hunter-ai`, `k-sales-hunter-fe`, 백엔드) 공통으로 씁니다. 규칙은 다섯 줄로 끝납니다.

1. `main`에 직접 푸시하지 않는다. 브랜치를 파고 PR을 올린다.
2. 브랜치 이름은 `태그-기능`.
3. 커밋 메시지는 `태그: 내용`.
4. PR은 1명 이상 approve 후 머지한다.
5. 태그는 아래 5개만 쓴다.

## 태그 5개

| 태그 | 언제 | 브랜치 예시 | 커밋 예시 |
|---|---|---|---|
| `feat` | 새 기능 | `feat-copilot` | `feat: 코파일럿 도구 호출 추가` |
| `fix` | 버그 수정 | `fix-job-cancel` | `fix: 취소 후 결과가 저장되던 문제` |
| `refactor` | 동작 그대로 구조 개선 | `refactor-node-runtime` | `refactor: 노드 데코레이터 분리` |
| `chore` | 설정·의존성·스크립트 | `chore-ai-foundation` | `chore: 잡 테이블 마이그레이션 추가` |
| `docs` | 문서만 | `docs-api-spec` | `docs: 코파일럿 계약 수정` |

애매하면 `chore`를 씁니다. 태그를 고민하는 시간이 제일 아깝습니다.

## 브랜치

```
main ─────────────────────────────●───────────●──────
       ╲                         ╱           ╱
        ●── feat-copilot ───────●           ╱
         ╲                                 ╱
          ●── chore-ai-foundation ────────●
```

- `태그-기능` 형식. 소문자, 단어는 하이픈으로 잇는다. 예: `feat-product-fill`, `fix-report-mapping`
- 한 브랜치는 한 가지 일만. 커지면 쪼갠다.
- 머지된 브랜치는 삭제한다.

## 커밋

- `태그: 내용` 한 줄이면 충분하다. 내용은 한국어로 쓴다.
- 본문이 필요하면 빈 줄 뒤에 붙인다.
- 하루에 한 번 이상 푸시한다. 로컬에만 쌓아두지 않는다.

```
feat: 분석 잡 폴링 엔드포인트 추가

- GET /internal/ai/analysis-jobs/{jobId}
- 노드 경계마다 step·progress 갱신
```

## PR

- 제목은 커밋 메시지와 같은 형식.
- 본문에 세 줄만 쓴다. 무엇을 했는지, 어떻게 확인했는지, 리뷰어가 볼 곳.
- 리뷰어 1명 approve 후 머지. 24시간 안에 리뷰가 없으면 채팅에서 부른다.
- 충돌은 PR 올린 사람이 해결한다.

## API 스펙을 바꿀 때

`docs/API_SPEC_FE기준.md`를 고치는 `docs-` PR을 **먼저** 올리고, FE·BE·AI 담당이 승인한 뒤 코드를 바꿉니다. 선택 필드를 추가하는 건 자유이고, 필드 이름 변경·삭제·타입 변경만 이 절차를 탑니다.

## 레포별 추가 사항

- **AI**: 푸시 전 `make lint`와 `make test`. 실제 LLM을 부르는 테스트는 `@pytest.mark.live`로 표시하고 CI에서 뺀다.
- **FE**: 푸시 전 `pnpm lint`, `pnpm build`.
- **BE**: 푸시 전 `./gradlew test`.
- `.env`는 절대 커밋하지 않는다. 키가 늘면 `.env.example`에 이름만 추가한다.
