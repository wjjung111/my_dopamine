# 우진 캘린더 (wj-calendar)

구글 캘린더 주간 화면처럼 생긴 개인용 캘린더 + 할 일. Claude가 커넥터(`wjcal`)로 직접 만들고 고칠 수 있다.

- 여는 법: 바탕화면 **우진 캘린더** 아이콘 더블클릭 (Ego Lite 앱 창으로 열림). 서버는 로그인할 때 자동으로 켜진다.
- Claude에게: "11/14 18:00~19:00 [작성] 홍길동 OO동 (담당자) 할 일 만들어 줘"처럼 말하면 된다. 시작, 종료 시각, 자정 넘김, 설명, 하위 할 일 모두 지원.
- 화면에서: 빈 칸 클릭 또는 드래그로 만들기, 항목 클릭해서 수정/삭제, 동그라미 클릭으로 완료. 단축키 t(오늘), ←/→(주 이동), c(할 일).
- 데이터: `data\calendar.db` (SQLite, 이 PC에만 있음, 깃허브에 안 올라감). 백업은 이 파일만 복사하면 된다.
- 고장 났을 때: "⚠ 서버 연결 끊김"이 뜨면 아이콘을 다시 더블클릭.

## 구조 (개발용)

| 파일 | 역할 |
|---|---|
| `db.py` | 저장소. 시간은 한국 시간 문자열(`YYYY-MM-DDTHH:MM`)로 저장 |
| `server.py` | 웹 서버 `http://127.0.0.1:18765` + JSON API (`/api/items`, `/api/calendars`, `/api/rev`) |
| `static/index.html` | 화면 (빌드 없는 순수 JS, 3초마다 변경 확인) |
| `mcp_server.py` | Claude용 MCP 커넥터. 웹 서버 없이 DB에 직접 씀 |
| `start.vbs` | 실행기 (`/server` 인자 = 서버만) |

설치: `python -m venv .venv` → `.venv\Scripts\pip install -r requirements.txt` → `python make_icon.py`
등록: `claude mcp add wjcal -s user -- C:\Users\wjjun\wj-calendar\.venv\Scripts\python.exe C:\Users\wjjun\wj-calendar\mcp_server.py`

폰 버전은 나중에: JSON API를 그대로 두고 저장소만 클라우드 DB로 바꾸면 된다.
