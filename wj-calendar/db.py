"""우진 캘린더 저장소 (SQLite). 웹 서버와 MCP 커넥터가 같이 쓴다.

시간은 모두 한국 시간(로컬) 문자열로 저장한다: date='YYYY-MM-DD', start/end='YYYY-MM-DDTHH:MM'.
"""
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.environ.get("WJCAL_DATA", Path(__file__).resolve().parent / "data"))
DB_FILE = DATA_DIR / "calendar.db"

DEFAULT_CALENDARS = [
    ("woojin", "Woojin Jung", "#039be5"),
    ("tasks", "할 일", "#b39ddb"),
    ("silmu", "감정평가 실무", "#3f51b5"),
    ("private", "개인", "#f6bf26"),
    ("etc", "기타", "#616161"),
]

ITEM_FIELDS = ("kind", "title", "notes", "date", "start", "end", "all_day", "done", "calendar_id", "parent_id")


def _now() -> float:
    return time.time()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_FILE, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=10000")
    con.execute("PRAGMA foreign_keys=ON")
    _init(con)
    return con


def _init(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS calendars(
            id TEXT PRIMARY KEY, name TEXT NOT NULL, color TEXT NOT NULL,
            visible INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK(kind IN ('event','task')),
            title TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            date TEXT,
            start TEXT,
            "end" TEXT,
            all_day INTEGER NOT NULL DEFAULT 0,
            done INTEGER NOT NULL DEFAULT 0,
            calendar_id TEXT,
            parent_id INTEGER REFERENCES items(id) ON DELETE CASCADE,
            sort INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS ix_items_date ON items(date);
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
        """
    )
    if con.execute("SELECT COUNT(*) FROM calendars").fetchone()[0] == 0:
        for i, (cid, name, color) in enumerate(DEFAULT_CALENDARS):
            con.execute("INSERT INTO calendars(id,name,color,sort) VALUES(?,?,?,?)", (cid, name, color, i))


def _bump(con: sqlite3.Connection) -> None:
    con.execute("INSERT INTO meta(k,v) VALUES('rev',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (str(_now()),))


def revision(con: sqlite3.Connection) -> str:
    r = con.execute("SELECT v FROM meta WHERE k='rev'").fetchone()
    return r[0] if r else "0"


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["all_day"] = bool(d["all_day"])
    d["done"] = bool(d["done"])
    return d


# ---------- 검증 ----------
def _check_date(s: str) -> str:
    datetime.strptime(s, "%Y-%m-%d")
    return s


def _check_dt(s: str) -> str:
    s = s.replace(" ", "T")[:16]
    datetime.strptime(s, "%Y-%m-%dT%H:%M")
    return s


def normalize(data: dict, partial: bool = False) -> dict:
    """입력값을 정리한다. start/end에 'HH:MM'만 오면 date를 붙인다."""
    out = {k: data[k] for k in ITEM_FIELDS if k in data}
    if "kind" in out and out["kind"] not in ("event", "task"):
        raise ValueError("kind는 event 또는 task")
    if not partial:
        if not (out.get("title") or "").strip():
            raise ValueError("제목이 필요합니다")
        out.setdefault("kind", "task")
    date = out.get("date")
    for k in ("start", "end"):
        v = out.get(k)
        if v:
            if len(v) <= 5 and ":" in v:  # 'HH:MM'
                base = date or (out.get("start") or "")[:10]
                if not base:
                    raise ValueError(f"{k}에 시각만 줄 때는 date가 필요합니다")
                v = f"{base}T{v.zfill(5)}"
            out[k] = _check_dt(v)
        elif k in out:
            out[k] = None
    if out.get("start") and not out.get("date"):
        out["date"] = out["start"][:10]
    if out.get("date"):
        out["date"] = _check_date(out["date"])
    if out.get("start") and not out.get("end") and not partial:
        h, m = map(int, out["start"][11:16].split(":"))
        h2 = min(h + 1, 23)
        out["end"] = f"{out['start'][:11]}{h2:02d}:{m:02d}" if h < 23 else f"{out['start'][:11]}23:59"
    if out.get("start") and out.get("end") and out["end"] < out["start"]:
        raise ValueError("종료가 시작보다 빠릅니다")
    if not partial and not out.get("start"):
        out["all_day"] = True if out.get("date") else False
    elif out.get("start"):
        out["all_day"] = False
    for b in ("all_day", "done"):
        if b in out:
            out[b] = 1 if out[b] else 0
    if not partial and not out.get("calendar_id"):
        out["calendar_id"] = "tasks" if out.get("kind") == "task" else "woojin"
    return out


# ---------- CRUD ----------
def list_items(con, date_from: str | None = None, date_to: str | None = None, include_done: bool = True, undated: bool = True) -> list[dict]:
    q, args = "SELECT * FROM items WHERE 1=1", []
    if date_from or date_to:
        cond = []
        if date_from:
            cond.append("COALESCE(substr(\"end\",1,10), date) >= ?")
            args.append(date_from)
        if date_to:
            cond.append("date <= ?")
            args.append(date_to)
        rng = " AND ".join(cond)
        q += f" AND ((date IS NOT NULL AND {rng})" + (" OR date IS NULL" if undated else "") + " OR parent_id IS NOT NULL)"
    if not include_done:
        q += " AND done=0"
    q += " ORDER BY date IS NULL, date, start IS NULL, start, sort, id"
    return [_row(r) for r in con.execute(q, args)]


def get_item(con, item_id: int) -> dict:
    r = con.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not r:
        raise KeyError(f"항목 {item_id} 없음")
    return _row(r)


def create_item(con, data: dict) -> dict:
    d = normalize(data)
    now = _now()
    cols = list(d) + ["created_at", "updated_at"]
    vals = list(d.values()) + [now, now]
    qcols = ",".join('"end"' if c == "end" else c for c in cols)
    cur = con.execute(f"INSERT INTO items({qcols}) VALUES({','.join('?' * len(cols))})", vals)
    _bump(con)
    return get_item(con, cur.lastrowid)


def update_item(con, item_id: int, data: dict) -> dict:
    cur = get_item(con, item_id)
    merged = {**{k: cur[k] for k in ITEM_FIELDS}, **{k: data[k] for k in ITEM_FIELDS if k in data}}
    # 날짜만 바꾸면 시각은 그대로 옮긴다
    if "date" in data and data["date"] and "start" not in data and cur.get("start"):
        merged["start"] = data["date"] + cur["start"][10:]
        if cur.get("end"):
            days = (datetime.strptime(cur["end"][:10], "%Y-%m-%d") - datetime.strptime(cur["start"][:10], "%Y-%m-%d")).days
            from datetime import timedelta
            merged["end"] = (datetime.strptime(data["date"], "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d") + cur["end"][10:]
    if "start" in data and not data["start"]:
        merged["start"] = merged["end"] = None
        merged["all_day"] = bool(merged.get("date"))
    d = normalize(merged, partial=True)
    if not d.get("start"):
        d["all_day"] = 1 if d.get("date") else 0
    sets = ",".join(('"end"' if k == "end" else k) + "=?" for k in d)
    con.execute(f"UPDATE items SET {sets}, updated_at=? WHERE id=?", list(d.values()) + [_now(), item_id])
    _bump(con)
    return get_item(con, item_id)


def delete_item(con, item_id: int) -> dict:
    get_item(con, item_id)
    con.execute("DELETE FROM items WHERE id=?", (item_id,))
    _bump(con)
    return {"deleted": item_id}


def list_calendars(con) -> list[dict]:
    return [dict(r) | {"visible": bool(r["visible"])} for r in con.execute("SELECT * FROM calendars ORDER BY sort")]


def update_calendar(con, cid: str, data: dict) -> dict:
    for k in ("name", "color", "visible"):
        if k in data:
            con.execute(f"UPDATE calendars SET {k}=? WHERE id=?", (int(data[k]) if k == "visible" else data[k], cid))
    _bump(con)
    return [c for c in list_calendars(con) if c["id"] == cid][0]
