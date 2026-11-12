"""구글 캘린더, 구글 할 일 -> 우진 캘린더 동기화 (구글이 원본, 읽기 전용).

- 캘린더 목록, 색, 표시 여부를 그대로 가져온다.
- 시각이 있는 구글 할 일은 캘린더의 FOCUS_TIME 일정(taskId)과 짝지어 시작, 종료 시각까지 가져온다.
- 구글에서 지워진 항목은 동기화 범위 안에서 같이 지운다.
- 예외: 할 일 완료 체크는 우진 캘린더에서 눌러도 구글에 반영한다(set_task_done).
"""
import base64
import threading
import time
from datetime import date, datetime, timedelta
from urllib.parse import quote

import db

CLIENT_FILE = db.DATA_DIR / "google_client.json"
TOKEN_FILE = db.DATA_DIR / "google_token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly", "https://www.googleapis.com/auth/tasks"]
CAL = "https://www.googleapis.com/calendar/v3"
TASKS = "https://tasks.googleapis.com/tasks/v1"
PAST_DAYS, FUTURE_DAYS = 60, 365
TASK_CAL = "g:tasks"

# 구글 캘린더 화면의 일정 색(colorId). 6, 11은 우진 화면에서 보이는 색에 맞춤.
EVENT_COLORS = {
    "1": "#7986cb", "2": "#33b679", "3": "#8e24aa", "4": "#e67c73", "5": "#f6bf26", "6": "#f2e600",
    "7": "#039be5", "8": "#616161", "9": "#3f51b5", "10": "#0b8043", "11": "#e8b400",
}

_lock = threading.Lock()
STATUS = {"last": None, "ok": None, "message": "아직 동기화 안 함", "counts": {}}


class NotLoggedIn(Exception):
    pass


# ---------- 인증 ----------
def login() -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")


def logged_in() -> bool:
    return TOKEN_FILE.exists()


def _session():
    from google.auth.transport.requests import AuthorizedSession, Request
    from google.oauth2.credentials import Credentials

    if not TOKEN_FILE.exists():
        raise NotLoggedIn("구글 로그인이 필요합니다. google_login.bat 을 더블클릭하세요.")
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except Exception as e:
            raise NotLoggedIn(f"구글 재로그인이 필요합니다(google_login.bat). 원인: {e}") from e
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return AuthorizedSession(creds)


def _get_all(s, url, params, key="items"):
    out, params = [], dict(params)
    while True:
        r = s.get(url, params=params, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"구글 API 오류 {r.status_code}: {r.text[:300]}")
        j = r.json()
        out += j.get(key, [])
        if not j.get("nextPageToken"):
            return out
        params["pageToken"] = j["nextPageToken"]


# ---------- 변환 ----------
def _local(dt: str) -> str:
    """'2026-11-02T12:45:00+09:00' -> 한국시간 'YYYY-MM-DDTHH:MM'."""
    d = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    if d.tzinfo:
        from datetime import timezone
        d = d.astimezone(timezone(timedelta(hours=9)))
    return d.strftime("%Y-%m-%dT%H:%M")


def _task_id_from_event(tid: str) -> str:
    return base64.b64encode(tid.encode()).decode().rstrip("=")


def _event_rows(cal_id: str, local_cal: str, ev: dict) -> list[dict]:
    """일정 1건 -> 항목 행들(여러 날 종일 일정은 날짜별로 나눔)."""
    base = {
        "kind": "event", "title": ev.get("summary") or "(제목 없음)",
        "notes": (ev.get("description") or "").strip(), "calendar_id": local_cal,
        "color": EVENT_COLORS.get(ev.get("colorId", "")), "source": "google",
    }
    st, en = ev.get("start", {}), ev.get("end", {})
    eid = f"gcal:{cal_id}:{ev['id']}"
    if "dateTime" in st:
        s, e = _local(st["dateTime"]), _local(en.get("dateTime", st["dateTime"]))
        return [base | {"ext_id": eid, "date": s[:10], "start": s, "end": e, "all_day": 0}]
    d0 = date.fromisoformat(st["date"])
    d1 = date.fromisoformat(en.get("date", st["date"]))
    n = max((d1 - d0).days, 1)
    rows = []
    for i in range(min(n, 31)):
        d = (d0 + timedelta(days=i)).isoformat()
        rows.append(base | {"ext_id": eid if i == 0 else f"{eid}#{i}", "date": d, "start": None, "end": None, "all_day": 1})
    return rows


# ---------- 동기화 ----------
def sync() -> dict:
    with _lock:
        try:
            counts = _sync()
            STATUS.update(last=time.time(), ok=True, message="동기화 완료", counts=counts)
        except NotLoggedIn as e:
            STATUS.update(last=time.time(), ok=False, message=str(e))
        except Exception as e:  # noqa
            STATUS.update(last=time.time(), ok=False, message=f"동기화 실패: {e}")
        return dict(STATUS)


def _sync() -> dict:
    s = _session()
    today = date.today()
    tmin = (today - timedelta(days=PAST_DAYS)).isoformat()
    tmax = (today + timedelta(days=FUTURE_DAYS)).isoformat()

    cals = _get_all(s, f"{CAL}/users/me/calendarList", {"maxResults": 250})
    rows: list[dict] = []
    cal_rows = []
    focus: dict[str, dict] = {}  # 구글 task id -> 시각 정보
    for i, c in enumerate(cals):
        if c.get("deleted"):
            continue
        local_cal = f"g:{c['id']}"
        name = c.get("summaryOverride") or ("내 구글 캘린더" if c.get("primary") else c.get("summary")) or c["id"]
        cal_rows.append((local_cal, name,
                         c.get("backgroundColor") or "#039be5", 1 if c.get("selected") else 0, 100 + i))
        evs = _get_all(s, f"{CAL}/calendars/{quote(c['id'], safe='')}/events", {
            "timeMin": f"{tmin}T00:00:00+09:00", "timeMax": f"{tmax}T00:00:00+09:00",
            "singleEvents": "true", "maxResults": 2500, "showDeleted": "false",
        })
        for ev in evs:
            if ev.get("status") == "cancelled":
                continue
            if ev.get("eventType") == "focusTime" and ev.get("taskId") or ev.get("taskId"):
                st, en = ev.get("start", {}), ev.get("end", {})
                if "dateTime" in st:
                    focus[_task_id_from_event(ev["taskId"])] = {
                        "start": _local(st["dateTime"]), "end": _local(en.get("dateTime", st["dateTime"])),
                        "color": EVENT_COLORS.get(ev.get("colorId", "")),
                    }
                continue
            rows += _event_rows(c["id"], local_cal, ev)

    # 구글 할 일
    cal_rows.append((TASK_CAL, "Tasks", "#b39ddb", 1, 99))
    tlists = _get_all(s, f"{TASKS}/users/@me/lists", {"maxResults": 100})
    task_rows, parents = [], {}
    for tl in tlists:
        for t in _get_all(s, f"{TASKS}/lists/{tl['id']}/tasks", {
            "maxResults": 100, "showCompleted": "true", "showHidden": "true", "showDeleted": "false",
        }):
            if not (t.get("title") or "").strip():
                continue
            done = t.get("status") == "completed"
            due = (t.get("due") or "")[:10] or None
            # 오래전에 끝난 할 일은 가져오지 않는다
            if done and (due or (t.get("completed") or "")[:10] or "9999") < tmin:
                continue
            f = focus.get(t["id"], {})
            row = {
                "kind": "task", "title": t["title"], "notes": (t.get("notes") or "").strip(),
                "date": (f.get("start") or "")[:10] or due, "start": f.get("start"), "end": f.get("end"),
                "all_day": 0 if f.get("start") else (1 if due else 0), "done": 1 if done else 0,
                "calendar_id": TASK_CAL, "color": f.get("color"), "source": "google",
                "ext_id": f"gtask:{tl['id']}:{t['id']}",
            }
            if t.get("parent"):
                parents[row["ext_id"]] = f"gtask:{tl['id']}:{t['parent']}"
            task_rows.append(row)

    con = db.connect()
    try:
        con.execute("BEGIN")
        for cid, name, color, vis, sort in cal_rows:
            ex = con.execute("SELECT visible FROM calendars WHERE id=?", (cid,)).fetchone()
            if ex:  # 표시 여부는 우진 캘린더에서 바꾼 값을 유지
                con.execute("UPDATE calendars SET name=?, color=?, sort=?, source='google' WHERE id=?", (name, color, sort, cid))
            else:
                con.execute("INSERT INTO calendars(id,name,color,visible,sort,source) VALUES(?,?,?,?,?,'google')",
                            (cid, name, color, vis, sort))
        seen = set()
        now = time.time()
        cols = ["kind", "title", "notes", "date", "start", "end", "all_day", "done", "calendar_id", "color", "source", "ext_id"]
        qc = {k: ('"end"' if k == "end" else k) for k in cols}
        upd = [k for k in cols if k != "ext_id"]
        sql = (
            f"INSERT INTO items({','.join(qc[k] for k in cols)},created_at,updated_at) "
            f"VALUES({','.join('?' * len(cols))},?,?) "
            "ON CONFLICT(ext_id) WHERE ext_id IS NOT NULL DO UPDATE SET "
            + ",".join(f"{qc[k]}=excluded.{qc[k]}" for k in upd)
            + ", updated_at=excluded.updated_at WHERE "
            + " OR ".join(f"items.{qc[k]} IS NOT excluded.{qc[k]}" for k in upd)
        )
        for r in rows + task_rows:
            seen.add(r["ext_id"])
            r.setdefault("done", 0)
            con.execute(sql, [r.get(k) for k in cols] + [now, now])
        # 하위 할 일 연결
        for child, parent in parents.items():
            con.execute("UPDATE items SET parent_id=(SELECT id FROM items WHERE ext_id=?) WHERE ext_id=?", (parent, child))
        # 구글에서 없어진 항목 정리(일정은 동기화 범위 안의 것만)
        gone = 0
        for iid, ext, d in con.execute("SELECT id, ext_id, date FROM items WHERE source='google'").fetchall():
            if ext in seen:
                continue
            if ext.startswith("gtask:") or (d and tmin <= d < tmax):
                con.execute("DELETE FROM items WHERE id=?", (iid,))
                gone += 1
        db._bump(con)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return {"calendars": len(cal_rows), "events": len(rows), "tasks": len(task_rows), "timed_tasks": sum(1 for t in task_rows if t["start"]), "removed": gone}


def set_task_done(ext_id: str, done: bool) -> None:
    """우진 캘린더에서 구글 할 일 완료 체크 -> 구글에도 반영."""
    _, tl, tid = ext_id.split(":", 2)
    body = {"status": "completed"} if done else {"status": "needsAction", "completed": None}
    r = _session().patch(f"{TASKS}/lists/{tl}/tasks/{tid}", json=body, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"구글 할 일 반영 실패 {r.status_code}: {r.text[:200]}")


def toggle_done(con, item: dict, done: bool) -> dict:
    """완료 체크 공용 처리(웹 서버, MCP 둘 다 사용)."""
    if item.get("source") == "google" and (item.get("ext_id") or "").startswith("gtask:"):
        set_task_done(item["ext_id"], done)
    return db.update_item(con, item["id"], {"done": done}, force=True)


def start_background(interval: int = 300) -> None:
    def loop():
        while True:
            if logged_in():
                sync()
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True).start()
