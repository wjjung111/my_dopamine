"""최초 로그인 / 재인증. login.bat 이 이 파일을 실행한다."""
import gauth

if __name__ == "__main__":
    try:
        gauth.login()
        s = gauth.session()
        r = s.get("https://tasks.googleapis.com/tasks/v1/users/@me/lists", timeout=30)
        r.raise_for_status()
        names = [x.get("title") for x in r.json().get("items", [])]
        print("로그인 성공. 할 일 목록:", ", ".join(names))
    except Exception as e:
        print("실패:", e)
    input("엔터를 누르면 닫힙니다.")
