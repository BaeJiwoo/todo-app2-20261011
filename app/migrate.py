"""테이블을 만든다. 배포할 때마다 한 번 실행되는 일회성 작업이라 여러 번 실행해도 안전하다.

테이블이 **처음 만들어질 때만** 예시 항목을 넣는다. 사용자가 항목을 모두 지운 뒤 다시 배포해도 예시가 되살아나지 않는다.
"""
from sqlalchemy import inspect

from app.db import Base, SessionLocal, Todo, engine

SAMPLES = ("AnyShip으로 배포한 앱입니다. 완료 표시를 눌러 보세요", "제목을 더블클릭하거나 ✎ 버튼으로 수정할 수 있습니다",
           "마감일을 지정하면 지난 항목이 빨갛게 표시됩니다")


def main() -> None:
    fresh = not inspect(engine).has_table(Todo.__tablename__)
    Base.metadata.create_all(engine)
    if fresh:
        with SessionLocal() as session:
            session.add_all(Todo(title=title) for title in SAMPLES)
            session.commit()


if __name__ == "__main__":
    main()
