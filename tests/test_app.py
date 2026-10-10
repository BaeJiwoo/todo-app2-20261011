import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app import migrate
from app.db import Base, SessionLocal, Todo, database_url, engine

STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


def core(items):
    """created_at을 뺀 비교용 값. SQLite는 시간대를 저장하지 않아 생성 응답과 목록 응답의 표기가 달라진다(PostgreSQL은 같다)."""
    one = isinstance(items, dict)
    result = [{key: value for key, value in item.items() if key != "created_at"} for item in ([items] if one else items)]
    return result[0] if one else result


def add(client, title="할 일", **extra):
    response = client.post("/api/todos", json={"title": title, **extra})
    assert response.status_code == 201, response.text
    return response.json()


# --- DATABASE_URL -------------------------------------------------------------------------
@pytest.mark.parametrize("raw, expected", [
    ("postgresql://u:p@host:5432/db?sslmode=require", "postgresql+psycopg2://u:p@host:5432/db?sslmode=require"),
    ("postgres://u:p@db:5432/app", "postgresql+psycopg2://u:p@db:5432/app"),
    ("sqlite:///x.db", "sqlite:///x.db"),
])
def test_the_injected_database_url_gets_a_driver_and_keeps_its_options(raw, expected):
    assert database_url(raw) == expected


# --- 상태 확인 ----------------------------------------------------------------------------
def test_healthz_is_ok_when_the_database_answers(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_healthz_is_503_when_the_database_cannot_be_reached(client, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("password=secret-in-the-message")

    monkeypatch.setattr(engine, "connect", broken)
    response = client.get("/healthz")
    assert response.status_code == 503 and "secret" not in response.text


# --- 목록과 정렬 --------------------------------------------------------------------------
def test_an_empty_list_is_empty(client):
    assert client.get("/api/todos").json() == []


def test_created_items_come_back_with_their_fields(client):
    created = add(client, "  우유 사기  ", due_on="2030-01-02")
    assert (created["title"], created["done"], created["due_on"]) == ("우유 사기", False, "2030-01-02")
    assert core(client.get("/api/todos").json()) == [core(created)]


def test_open_items_come_first_then_by_due_date_then_newest(client):
    soon, later, nothing_old, nothing_new = date.today() + timedelta(days=1), date.today() + timedelta(days=9), None, None
    a = add(client, "마감 늦음", due_on=later.isoformat())
    b = add(client, "마감 빠름", due_on=soon.isoformat())
    c = add(client, "마감 없음 오래됨")
    d = add(client, "마감 없음 최근")
    finished = add(client, "끝난 것")
    client.patch(f"/api/todos/{finished['id']}", json={"done": True})
    assert [t["title"] for t in client.get("/api/todos").json()] == [
        "마감 빠름", "마감 늦음", "마감 없음 최근", "마감 없음 오래됨", "끝난 것"]


def test_the_status_filter_lists_only_open_or_only_done_items(client):
    open_item, done_item = add(client, "진행"), add(client, "완료")
    client.patch(f"/api/todos/{done_item['id']}", json={"done": True})
    assert [t["title"] for t in client.get("/api/todos?status=active").json()] == ["진행"]
    assert [t["title"] for t in client.get("/api/todos?status=done").json()] == ["완료"]
    assert len(client.get("/api/todos?status=all").json()) == 2
    assert client.get("/api/todos?status=bogus").status_code == 422


# --- 입력 검증 ----------------------------------------------------------------------------
@pytest.mark.parametrize("body", [
    {"title": ""}, {"title": "   "}, {"title": "x" * 201}, {}, {"title": "ok", "due_on": "내일"},
    {"title": "ok", "done": True}, {"title": "ok", "extra": 1}])
def test_invalid_new_items_are_refused(client, body):
    assert client.post("/api/todos", json=body).status_code == 422
    assert client.get("/api/todos").json() == []


def test_titles_of_exactly_the_maximum_length_are_accepted(client):
    assert len(add(client, "x" * 200)["title"]) == 200


# --- 수정 ---------------------------------------------------------------------------------
def test_only_the_sent_fields_change(client):
    item = add(client, "원래 제목", due_on="2030-05-05")
    done = client.patch(f"/api/todos/{item['id']}", json={"done": True}).json()
    assert (done["done"], done["title"], done["due_on"]) == (True, "원래 제목", "2030-05-05")
    renamed = client.patch(f"/api/todos/{item['id']}", json={"title": " 새 제목 "}).json()
    assert (renamed["title"], renamed["done"]) == ("새 제목", True)


def test_a_due_date_can_be_changed_and_removed(client):
    item = add(client, "마감 있음", due_on="2030-05-05")
    assert client.patch(f"/api/todos/{item['id']}", json={"due_on": "2031-01-01"}).json()["due_on"] == "2031-01-01"
    assert client.patch(f"/api/todos/{item['id']}", json={"due_on": None}).json()["due_on"] is None


@pytest.mark.parametrize("body", [{"title": ""}, {"title": None}, {"done": None}, {"unknown": 1}, {"due_on": "x"}])
def test_invalid_updates_are_refused_and_change_nothing(client, body):
    item = add(client, "그대로")
    assert client.patch(f"/api/todos/{item['id']}", json=body).status_code == 422
    assert core(client.get("/api/todos").json()) == [core(item)]


def test_unknown_items_are_404(client):
    assert client.patch("/api/todos/999", json={"done": True}).status_code == 404
    assert client.delete("/api/todos/999").status_code == 404


# --- 삭제 ---------------------------------------------------------------------------------
def test_an_item_can_be_deleted(client):
    keep, gone = add(client, "남김"), add(client, "삭제")
    assert client.delete(f"/api/todos/{gone['id']}").status_code == 204
    assert core(client.get("/api/todos").json()) == [core(keep)]


def test_completed_items_are_cleared_together_and_open_ones_stay(client):
    for title in ("a", "b", "c"):
        item = add(client, title)
        if title != "c":
            client.patch(f"/api/todos/{item['id']}", json={"done": True})
    assert client.delete("/api/todos?status=done").json() == {"deleted": 2}
    assert [t["title"] for t in client.get("/api/todos").json()] == ["c"]
    assert client.delete("/api/todos").status_code == 422  # status가 없으면 아무것도 지우지 않는다
    assert len(client.get("/api/todos").json()) == 1


# --- 마이그레이션 -------------------------------------------------------------------------
def count():
    with SessionLocal() as session:
        return session.scalar(select(func.count()).select_from(Todo))


def test_migrate_creates_the_table_and_seeds_examples_only_the_first_time(client):
    Base.metadata.drop_all(engine)
    migrate.main()
    assert count() == len(migrate.SAMPLES)
    migrate.main()
    assert count() == len(migrate.SAMPLES)  # 다시 실행해도 늘지 않는다


def test_migrate_does_not_bring_examples_back_after_the_user_cleared_them(client):
    Base.metadata.drop_all(engine)
    migrate.main()
    with SessionLocal() as session:
        session.query(Todo).delete()
        session.commit()
    migrate.main()
    assert count() == 0


# --- 화면과 보안 --------------------------------------------------------------------------
def test_the_page_and_its_static_files_are_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert all(client.get(path).status_code == 200 for path in ("/static/app.js", "/static/style.css"))


def test_security_headers_are_set_and_api_responses_are_not_cached(client):
    response = client.get("/api/todos")
    assert response.headers["x-content-type-options"] == "nosniff" and response.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "'unsafe-inline'" not in response.headers["content-security-policy"]


def test_the_page_uses_only_its_own_files_so_the_strict_policy_holds():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html) and "http://" not in html and "https://" not in html
    assert not re.search(r"\son[a-z]+\s*=", html)  # 인라인 이벤트 속성이 없다


def test_the_script_never_writes_server_data_as_html():
    script = (STATIC / "app.js").read_text(encoding="utf-8")
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(", script)


def test_docs_endpoints_are_off(client):
    assert all(client.get(path).status_code == 404 for path in ("/docs", "/redoc", "/openapi.json"))
