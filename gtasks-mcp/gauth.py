"""구글 로그인(OAuth) 공용 모듈. 토큰은 token.json에 저장하고 자동 갱신한다."""
import os
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials

BASE = Path(__file__).resolve().parent
CLIENT_FILE = BASE / "credentials.json"
TOKEN_FILE = BASE / "token.json"
SCOPES = ["https://www.googleapis.com/auth/tasks"]


class AuthError(Exception):
    pass


def _save(creds: Credentials) -> None:
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def login() -> Credentials:
    """브라우저를 열어 최초 로그인(동의)을 받는다. 사람이 직접 눌러야 한다."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not CLIENT_FILE.exists():
        raise AuthError(f"{CLIENT_FILE} 가 없습니다. README의 1회 설정을 먼저 하세요.")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    _save(creds)
    return creds


def session() -> AuthorizedSession:
    """저장된 토큰으로 인증된 세션을 돌려준다. 만료됐으면 자동 갱신."""
    if not TOKEN_FILE.exists():
        raise AuthError(
            "로그인 토큰이 없습니다. C:\\Users\\wjjun\\gtasks-mcp\\login.bat 을 더블클릭해 로그인하세요."
        )
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except Exception as e:  # 갱신 토큰 만료·철회
            raise AuthError(
                "토큰 갱신 실패(재인증 필요). login.bat 을 더블클릭해 다시 로그인하세요. "
                f"원인: {e}"
            ) from e
        _save(creds)
    return AuthorizedSession(creds)
