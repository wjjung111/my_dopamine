# gtasks-mcp (구글 할 일 커넥터)

- 쓰는 법: Claude Code에서 "11/13에 [작성] 홍길동 OO동 (담당자) 할 일 만들어 줘"처럼 말하면 `gtasks` 도구(조회, 생성, 일괄 생성, 수정, 완료, 삭제)가 처리한다. 계정은 개인 구글 계정(login.bat으로 로그인한 계정).
- 한계: 구글 Tasks API는 날짜만 저장한다. "09:15~12:00" 같은 시각은 넣을 수 없다(시각이 꼭 필요한 건만 Ego Lite 캘린더 화면에서 수동).
- 재인증: "토큰 갱신 실패"가 뜨면 `login.bat` 더블클릭 → 브라우저에서 계정 선택 → 허용. 끝.
- 1회 설정: Google Cloud에서 Tasks API 사용 설정 + OAuth 클라이언트(데스크톱 앱) JSON을 받아 이 폴더에 `credentials.json`으로 저장 후 `login.bat`.
- 비밀 파일: `credentials.json`, `token.json`은 `.gitignore`에 있어 커밋되지 않는다. 남에게 주지 말 것.
- 등록 명령: `claude mcp add gtasks -s user -- C:\Users\wjjun\gtasks-mcp\.venv\Scripts\python.exe C:\Users\wjjun\gtasks-mcp\server.py`
