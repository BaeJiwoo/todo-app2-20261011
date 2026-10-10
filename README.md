# Todo

FastAPI + PostgreSQL로 만든 할 일 앱입니다. 할 일 추가, 완료 표시, 제목·마감일 수정, 삭제, 진행 중/완료 필터, 완료 항목 일괄 삭제를 지원하고 마감이 지난 항목은 빨갛게 표시합니다.
[AnyShip](https://app.anyship.cloud)이 그대로 배포할 수 있게 **환경에 대해 아는 것이 없도록** 만들었습니다. 환경별로 달라지는 값은 모두 환경변수로 받습니다.

## 환경이 앱에 주는 값

| 환경변수 | 설명 |
|---|---|
| `DATABASE_URL` | `postgresql://계정:비밀번호@호스트:5432/DB?sslmode=require` 형식의 PostgreSQL 주소 (필수) |
| `PORT` | 요청을 받을 포트. 이미지의 기본값은 8080 |
| `LOG_LEVEL` | 로그 수준(기본 `INFO`). 로그는 표준 출력으로만 남깁니다 |

## 배포 계약 (`deploy-spec.yaml`)

- `/healthz`: DB에 닿으면 200, 닿지 않으면 503
- 마이그레이션: `python -m app.migrate` (배포 때 한 번 실행. 여러 번 실행해도 안전하고, 테이블을 **처음 만들 때만** 예시 항목 3개를 넣습니다)
- 상태는 DB에만 저장합니다. 컨테이너를 다시 시작하거나 교체해도 데이터가 유지됩니다.
- 루트 권한 없이 실행하며(`uid 10001`), 화면은 인라인 스크립트 없이 `Content-Security-Policy: default-src 'self'`를 지킵니다.

`deploy-spec.yaml`의 `source.repo`는 자기 저장소 주소로 바꾸세요(배포 동작에는 쓰이지 않습니다).

## 로컬에서 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export DATABASE_URL=sqlite:///todo.db          # 또는 postgresql://user:pass@localhost:5432/todo
python -m app.migrate
uvicorn app.main:app --reload --port 8080
```

http://localhost:8080 을 엽니다.

## 시험

```bash
pytest
```

시험은 SQLite를 쓰므로 PostgreSQL이 필요 없습니다.

## API

| 요청 | 설명 |
|---|---|
| `GET /api/todos?status=all\|active\|done` | 목록. 진행 중 먼저, 마감이 가까운 순 |
| `POST /api/todos` | `{"title": "...", "due_on": "2030-01-31"}` (`due_on`은 선택) |
| `PATCH /api/todos/{id}` | 보낸 항목만 변경(`title`, `done`, `due_on`). `due_on: null`이면 마감일 삭제 |
| `DELETE /api/todos/{id}` | 삭제 |
| `DELETE /api/todos?status=done` | 완료한 항목 모두 삭제 |
| `GET /healthz` | 상태 확인 |
