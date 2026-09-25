# 협업 컨벤션

3개 레포(`k-sales-hunter-ai`, `k-sales-hunter-be`, `k-sales-hunter-fe`) 공통입니다.

1. `main`에 직접 푸시하지 않는다.
2. 브랜치를 파고 **`develop`으로 PR**을 올린다. `main`은 데모 태그용이다.
3. 브랜치 이름은 `태그/파트-기능`.
4. 커밋 메시지는 `태그: 내용`.
5. PR은 1명 이상 approve 후 머지한다.

## 태그

프론트 레포 README의 표를 3개 레포 공통으로 씁니다.

| 태그 | 언제 | 브랜치 예시 | 커밋 예시 |
|---|---|---|---|
| `Feat` | 새 기능 | `feat/ai-copilot` | `Feat: 코파일럿 도구 호출 추가` |
| `Fix` | 버그 수정 | `fix/ai-job-cancel` | `Fix: 취소 후 결과가 저장되던 문제` |
| `Design` | UI 스타일·레이아웃 | `design/fe-report-card` | `Design: 국가 카드 여백 조정` |
| `Docs` | 문서만 | `docs/api-spec` | `Docs: 코파일럿 계약 수정` |
| `Refactor` | 동작 그대로 구조 개선 | `refactor/ai-node-runtime` | `Refactor: 노드 데코레이터 분리` |
| `Chore` | 설정·의존성·스크립트 | `chore/be-flyway-init` | `Chore: 잡 테이블 마이그레이션 추가` |

브랜치 이름의 태그는 소문자로 씁니다. 커밋 메시지는 위 표대로 첫 글자를 대문자로 씁니다.

애매하면 `Chore`를 씁니다. 태그를 고민하는 시간이 제일 아깝습니다.

## 브랜치

```
main ────────────────────────────────────●──── 데모 태그
                                        ╱
develop ──────●───────────●────────────●───── 평소 기준선
               ╲         ╱  ╲         ╱
                ●───────●    ●───────●
           feat/ai-copilot   chore/be-flyway-init
```

- `태그/파트-기능` 형식. 파트는 `ai` · `be` · `fe` 중 하나입니다.
- 한 브랜치는 한 가지 일만 합니다. 커지면 쪼갭니다.
- 머지된 브랜치는 삭제합니다.
- `develop`이 평소 기준선입니다. 새 브랜치는 `develop`에서 땁니다.
- `main`은 데모나 제출 시점에 `develop`을 머지해 찍습니다.

## 커밋

- `태그: 내용` 한 줄이면 충분합니다. 내용은 한국어로 씁니다.
- 본문이 필요하면 빈 줄 뒤에 붙입니다.
- 하루에 한 번 이상 푸시합니다. 로컬에만 쌓아두지 않습니다.

```
Feat: 분석 잡 폴링 엔드포인트 추가

- GET /internal/ai/analysis-jobs/{jobId}
- 노드 경계마다 step·progress 갱신
```

## PR

- 제목은 커밋 메시지와 같은 형식입니다.
- 본문에 세 줄만 씁니다. 무엇을 했는지, 어떻게 확인했는지, 리뷰어가 볼 곳.
- 리뷰어 1명 approve 후 머지합니다. 24시간 안에 리뷰가 없으면 채팅에서 부릅니다.
- 충돌은 PR 올린 사람이 해결합니다.

## API 스펙을 바꿀 때

`k-sales-hunter-ai/docs/API_SPEC_FE기준.md`를 고치는 `docs/` PR을 **먼저** 올리고, 프론트·백엔드·AI 담당이 승인한 뒤 코드를 바꿉니다. 선택 필드를 추가하는 건 자유이고, 필드 이름 변경·삭제·타입 변경만 이 절차를 탑니다.

## 레포별 추가 사항

| 레포 | 푸시 전 확인 | 비고 |
|---|---|---|
| AI | `make lint` · `make test` | 실제 LLM을 부르는 테스트는 `@pytest.mark.live`로 표시하고 CI에서 뺀다 |
| BE | `./gradlew build` | JDK 21 필요. 스키마 변경은 `src/main/resources/db/migration/V{n}__{설명}.sql` |
| FE | `pnpm lint` · `pnpm build` | |

`.env`는 절대 커밋하지 않습니다. 키가 늘면 `.env.example`에 이름만 추가합니다.

## 아직 어긋나 있는 것

- 프론트 레포의 기준선 브랜치 이름이 `dev`입니다. `develop`으로 맞추거나 이 문서를 고쳐야 합니다.
- AI 레포에는 `develop`이 없었습니다. 이 문서와 함께 만듭니다.
