import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, select, text

from app.db import SessionLocal, Todo, engine

logging.basicConfig(stream=sys.stdout, level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("todo")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    engine.dispose()


app = FastAPI(title="Todo", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def clean_title(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("제목을 입력해 주세요.")
    return value


class TodoCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(max_length=200)
    due_on: date | None = None

    _title = field_validator("title")(clean_title)


class TodoUpdate(BaseModel):
    """보낸 항목만 바꾼다. 마감일은 null을 보내면 지워진다."""
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=200)
    done: bool | None = None
    due_on: date | None = None

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value):
        return value if value is None else clean_title(value)

    @model_validator(mode="after")
    def required_fields_are_not_null(self):
        for name in ("title", "done"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name}은(는) null일 수 없습니다.")
        return self


class TodoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    done: bool
    due_on: date | None
    created_at: datetime


@app.get("/healthz")
def healthz(response: Response):
    """DB에 닿는지까지 확인한다. 닿지 않으면 503이라 배포의 헬스체크가 실패로 알려 준다."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as error:  # 오류 문구에는 접속 정보가 섞일 수 있어 종류만 남긴다
        log.error("healthz: database unreachable (%s)", type(error).__name__)
        response.status_code = 503
        return {"status": "unavailable"}
    return {"status": "ok"}


@app.get("/api/todos", response_model=list[TodoOut])
def list_todos(status: Literal["all", "active", "done"] = "all"):
    # 진행 중 먼저, 마감이 가까운 순(마감 없음은 뒤), 같으면 최근 것 먼저
    query = select(Todo).order_by(Todo.done, Todo.due_on.is_(None), Todo.due_on, Todo.id.desc())
    if status != "all":
        query = query.where(Todo.done.is_(status == "done"))
    with SessionLocal() as session:
        return list(session.scalars(query))


@app.post("/api/todos", response_model=TodoOut, status_code=201)
def create_todo(body: TodoCreate):
    with SessionLocal() as session:
        todo = Todo(title=body.title, due_on=body.due_on)
        session.add(todo)
        session.commit()
        log.info("created todo id=%s", todo.id)
        return todo


@app.patch("/api/todos/{todo_id}", response_model=TodoOut)
def update_todo(todo_id: int, body: TodoUpdate):
    with SessionLocal() as session:
        todo = session.get(Todo, todo_id)
        if todo is None:
            raise HTTPException(404, "할 일을 찾을 수 없습니다.")
        for name, value in body.model_dump(exclude_unset=True).items():
            setattr(todo, name, value)
        session.commit()
        return todo


@app.delete("/api/todos/{todo_id}", status_code=204)
def delete_todo(todo_id: int):
    with SessionLocal() as session:
        todo = session.get(Todo, todo_id)
        if todo is None:
            raise HTTPException(404, "할 일을 찾을 수 없습니다.")
        session.delete(todo)
        session.commit()
    return Response(status_code=204)


@app.delete("/api/todos")
def clear_done(status: Literal["done"] = Query(...)):
    """완료한 항목을 한꺼번에 지운다."""
    with SessionLocal() as session:
        removed = session.execute(delete(Todo).where(Todo.done.is_(True))).rowcount
        session.commit()
    log.info("cleared %s completed todos", removed)
    return {"deleted": removed}


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
