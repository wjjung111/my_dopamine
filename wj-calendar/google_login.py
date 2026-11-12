"""구글 로그인(최초 1회, 또는 재로그인). 끝나면 바로 한 번 동기화한다."""
import gsync

if __name__ == "__main__":
    try:
        gsync.login()
        st = gsync.sync()
        print("로그인 성공." if st["ok"] else "로그인은 됐지만 동기화 실패:", st["message"])
        if st.get("counts"):
            c = st["counts"]
            print(f"캘린더 {c['calendars']}개, 일정 {c['events']}개, 할 일 {c['tasks']}개(시각 있는 것 {c['timed_tasks']}개)")
    except Exception as e:
        print("실패:", e)
    input("엔터를 누르면 닫힙니다.")
