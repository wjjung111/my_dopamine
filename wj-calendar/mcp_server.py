"""우진 캘린더 MCP 커넥터 (stdio). 웹 서버가 꺼져 있어도 DB에 직접 쓴다."""
from typing import Optional

from mcp.server.fastmcp import FastMCP

import db

mcp = FastMCP("wjcal")

RULES = (
    " 제목 규칙: [작성]/[출장] 머리말, 끝에 괄호로 고객담당자. 예 '[작성] 이미화 중곡동 (문형기)'. "
    "[출장]은 출장지마다 괄호에 동과 지번(아파트만 동호수). [마감] 항목은 만들지 않는다."
)

DESC_CREATE = (
    "할 일(kind='task', 기본) 또는 일정(kind='event')을 만든다. "
    "date='YYYY-MM-DD'. 시각이 있으면 start/end='HH:MM'(date 필요) 또는 'YYYY-MM-DDTHH:MM'. "
    "자정을 넘기면 end에 다음 날짜를 붙인다. 시각 없이 date만 주면 종일 항목, end 생략 시 1시간. "
    "parent_id를 주면 하위 할 일. calendar_id: woojin, tasks, silmu(감정평가 실무), private(개인), etc."
) + RULES

DESC_CREATE_MANY = (
    "여러 건을 한 번에 만든다. 각 항목은 create_item과 같은 키(title 필수, date, start, end, kind, notes, calendar_id). "
    "일부 실패해도 나머지는 만들고 failed로 알려 준다."
) + RULES


def _with(fn):
    con = db.connect()
    try:
        return fn(con)
    finally:
        con.close()


def _payload(**kw):
    return {k: v for k, v in kw.items() if v is not None}


@mcp.tool()
def list_items(date_from: Optional[str] = None, date_to: Optional[str] = None, include_done: bool = True) -> list[dict]:
    """일정과 할 일을 조회한다. date_from, date_to는 YYYY-MM-DD(양끝 포함). 날짜 없는 할 일도 함께 나온다."""
    return _with(lambda c: db.list_items(c, date_from, date_to, include_done))


@mcp.tool()
def get_item(item_id: int) -> dict:
    """항목 1건 조회."""
    return _with(lambda c: db.get_item(c, item_id))


@mcp.tool(description=DESC_CREATE)
def create_item(
    title: str,
    date: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    kind: str = "task",
    notes: Optional[str] = None,
    calendar_id: Optional[str] = None,
    parent_id: Optional[int] = None,
) -> dict:
    p = _payload(title=title, date=date, start=start, end=end, kind=kind, notes=notes,
                 calendar_id=calendar_id, parent_id=parent_id)
    return _with(lambda c: db.create_item(c, p))


@mcp.tool(description=DESC_CREATE_MANY)
def create_items(items: list[dict]) -> dict:
    def run(c):
        created, failed = [], []
        for i, it in enumerate(items):
            try:
                created.append(db.create_item(c, it))
            except Exception as e:
                failed.append({"index": i, "title": it.get("title"), "error": str(e)})
        return {"created_count": len(created), "created": created, "failed": failed}
    return _with(run)


@mcp.tool()
def update_item(
    item_id: int,
    title: Optional[str] = None,
    date: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    kind: Optional[str] = None,
    notes: Optional[str] = None,
    calendar_id: Optional[str] = None,
    done: Optional[bool] = None,
) -> dict:
    """항목을 고친다. 넘긴 값만 바뀐다. date만 바꾸면 시각은 유지한 채 날짜를 옮긴다. start=''이면 시각을 지워 종일로 만든다."""
    p = _payload(title=title, date=date, start=start, end=end, kind=kind, notes=notes,
                 calendar_id=calendar_id, done=done)
    return _with(lambda c: db.update_item(c, item_id, p))


@mcp.tool()
def complete_item(item_id: int, done: bool = True) -> dict:
    """할 일을 완료(done=True) 또는 완료 취소(False) 처리한다."""
    return _with(lambda c: db.update_item(c, item_id, {"done": done}))


@mcp.tool()
def delete_item(item_id: int) -> dict:
    """항목을 삭제한다(하위 할 일 포함, 되돌릴 수 없음)."""
    return _with(lambda c: db.delete_item(c, item_id))


@mcp.tool()
def list_calendars() -> list[dict]:
    """캘린더(색상 분류) 목록."""
    return _with(db.list_calendars)


if __name__ == "__main__":
    mcp.run()
