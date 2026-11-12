"""Google Tasks(할 일) MCP 서버 - 로컬 stdio.

주의: Google Tasks API는 due에 날짜만 저장한다(시각은 버려짐, 읽기·쓰기 모두 불가).
"""
import re
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

import gauth

API = "https://tasks.googleapis.com/tasks/v1"
mcp = FastMCP("gtasks")

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _due(d: str) -> str:
    """'YYYY-MM-DD' -> RFC3339. 시각이 붙어 와도 날짜만 쓴다(API가 시각을 버림)."""
    if not _DATE.match(d or ""):
        raise ValueError(f"날짜는 YYYY-MM-DD 형식이어야 합니다: {d!r}")
    return d[:10] + "T00:00:00.000Z"


def _call(method: str, path: str, params: dict | None = None, body: dict | None = None) -> Any:
    try:
        s = gauth.session()
    except gauth.AuthError as e:
        raise RuntimeError(str(e)) from e
    r = s.request(method, API + path, params=params, json=body, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Google Tasks API 오류 {r.status_code}: {r.text[:500]}")
    return r.json() if r.content else {}


def _slim(t: dict) -> dict:
    out = {
        "id": t.get("id"),
        "title": t.get("title", ""),
        "status": "완료" if t.get("status") == "completed" else "미완료",
    }
    if t.get("due"):
        out["due"] = t["due"][:10]
    if t.get("notes"):
        out["notes"] = t["notes"]
    if t.get("completed"):
        out["completed_at"] = t["completed"]
    if t.get("parent"):
        out["parent"] = t["parent"]
    return out


def _body(title=None, notes=None, due=None) -> dict:
    b: dict = {}
    if title is not None:
        b["title"] = title
    if notes is not None:
        b["notes"] = notes
    if due is not None:
        b["due"] = _due(due) if due else None  # "" 이면 날짜 제거
    return b


@mcp.tool()
def list_tasklists() -> list[dict]:
    """할 일 목록(리스트)들을 조회한다. 기본 목록은 tasklist='@default'로 쓸 수 있다."""
    items, token = [], None
    while True:
        res = _call("GET", "/users/@me/lists", {"maxResults": 100, "pageToken": token})
        items += [{"id": x["id"], "title": x.get("title", "")} for x in res.get("items", [])]
        token = res.get("nextPageToken")
        if not token:
            return items


@mcp.tool()
def list_tasks(
    tasklist: str = "@default",
    due_from: Optional[str] = None,
    due_to: Optional[str] = None,
    include_completed: bool = False,
    max_results: int = 100,
) -> list[dict]:
    """할 일을 조회한다. due_from, due_to는 YYYY-MM-DD(양끝 포함). include_completed=True면 완료된 것도 포함."""
    params: dict = {
        "maxResults": 100,
        "showCompleted": include_completed,
        "showHidden": include_completed,
    }
    if due_from:
        params["dueMin"] = _due(due_from)
    if due_to:
        params["dueMax"] = due_to[:10] + "T23:59:59.000Z"
    items: list[dict] = []
    while len(items) < max_results:
        res = _call("GET", f"/lists/{tasklist}/tasks", params)
        items += [_slim(t) for t in res.get("items", [])]
        if not res.get("nextPageToken"):
            break
        params["pageToken"] = res["nextPageToken"]
    items.sort(key=lambda t: (t.get("due", "9999"), t["title"]))
    return items[:max_results]


@mcp.tool()
def get_task(task_id: str, tasklist: str = "@default") -> dict:
    """할 일 1건을 조회한다."""
    return _slim(_call("GET", f"/lists/{tasklist}/tasks/{task_id}"))


@mcp.tool()
def create_task(
    title: str,
    due: Optional[str] = None,
    notes: Optional[str] = None,
    tasklist: str = "@default",
) -> dict:
    """할 일 1건을 만든다. due는 YYYY-MM-DD(날짜만 저장됨, 시각 지정 불가). notes는 메모(설명)."""
    return _slim(_call("POST", f"/lists/{tasklist}/tasks", body=_body(title, notes, due)))


@mcp.tool()
def create_tasks(tasks: list[dict], tasklist: str = "@default") -> dict:
    """할 일 여러 건을 한 번에 만든다. tasks 각 항목: {"title": 필수, "due": "YYYY-MM-DD", "notes": "메모"}.
    일부가 실패해도 나머지는 계속 만들고, 실패 건은 failed에 담아 돌려준다."""
    created, failed = [], []
    for i, t in enumerate(tasks):
        try:
            if not t.get("title"):
                raise ValueError("title 없음")
            body = _body(t["title"], t.get("notes"), t.get("due") or None)
            created.append(_slim(_call("POST", f"/lists/{t.get('tasklist', tasklist)}/tasks", body=body)))
        except Exception as e:
            failed.append({"index": i, "title": t.get("title"), "error": str(e)})
    return {"created_count": len(created), "created": created, "failed": failed}


@mcp.tool()
def update_task(
    task_id: str,
    title: Optional[str] = None,
    due: Optional[str] = None,
    notes: Optional[str] = None,
    completed: Optional[bool] = None,
    tasklist: str = "@default",
) -> dict:
    """할 일을 고친다. 넘긴 항목만 바뀐다. due=""이면 날짜 제거, completed=False면 완료 취소."""
    body = _body(title, notes, due)
    if completed is True:
        body["status"] = "completed"
    elif completed is False:
        body["status"] = "needsAction"
        body["completed"] = None
    if not body:
        raise ValueError("바꿀 내용이 없습니다.")
    return _slim(_call("PATCH", f"/lists/{tasklist}/tasks/{task_id}", body=body))


@mcp.tool()
def complete_task(task_id: str, tasklist: str = "@default") -> dict:
    """할 일을 완료 처리한다."""
    return _slim(_call("PATCH", f"/lists/{tasklist}/tasks/{task_id}", body={"status": "completed"}))


@mcp.tool()
def delete_task(task_id: str, tasklist: str = "@default") -> dict:
    """할 일을 삭제한다(되돌릴 수 없음)."""
    _call("DELETE", f"/lists/{tasklist}/tasks/{task_id}")
    return {"deleted": task_id}


if __name__ == "__main__":
    mcp.run()
