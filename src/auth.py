import os
import time
import requests
from dotenv import load_dotenv
import pykrx.website.comm.webio as webio

load_dotenv()

ENABLE_LOGIN = os.environ.get("KRX_ENABLE_LOGIN", "false").lower() == "true"
LOGIN_ID = os.environ.get("KRX_LOGIN_ID", "")
LOGIN_PW = os.environ.get("KRX_LOGIN_PW", "")
FAIL_POLICY = os.environ.get("KRX_LOGIN_FAIL_POLICY", "continue")

session = requests.Session()

def login_krx():
    if not ENABLE_LOGIN:
        print("[Auth] Login bypassed (KRX_ENABLE_LOGIN is not true).")
        return False

    print(f"[Auth] Attempting login for ID: {LOGIN_ID}")
    
    _LOGIN_PAGE = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001.cmd"
    _LOGIN_JSP  = "https://data.krx.co.kr/contents/MDC/COMS/client/view/login.jsp?site=mdc"
    _LOGIN_URL  = "https://data.krx.co.kr/contents/MDC/COMS/client/MDCCOMS001D1.cmd"
    _UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    try:
        # 1. 초기 세션 발급
        session.get(_LOGIN_PAGE, headers={"User-Agent": _UA}, timeout=15)
        session.get(_LOGIN_JSP, headers={"User-Agent": _UA, "Referer": _LOGIN_PAGE}, timeout=15)

        payload = {
            "mbrNm": "", "telNo": "", "di": "", "certType": "",
            "mbrId": LOGIN_ID, "pw": LOGIN_PW,
        }
        headers = {"User-Agent": _UA, "Referer": _LOGIN_PAGE}

        # 2. 로그인 POST
        resp = session.post(_LOGIN_URL, data=payload, headers=headers, timeout=15)
        data = resp.json()
        error_code = data.get("_error_code", "")

        # 3. CD011 중복 로그인 처리
        if error_code == "CD011":
            print("[Auth] Duplicate login detected. Retrying with skipDup=Y")
            payload["skipDup"] = "Y"
            resp = session.post(_LOGIN_URL, data=payload, headers=headers, timeout=15)
            data = resp.json()
            error_code = data.get("_error_code", "")

        if error_code == "CD001":
            print("[Auth] Login successful.")
            return True
        else:
            if FAIL_POLICY == "raise":
                raise RuntimeError(f"KRX Login failed. Error: {error_code} / {data.get('_error_message', '')}")
            print(f"[Auth] Login Failed. Error: {error_code} / {data.get('_error_message', '')}. Policy is continue.")
            return False

    except Exception as e:
        if FAIL_POLICY == "raise":
            raise e
        print(f"[Auth] Login Exception: {e}")
        return False

def install_pykrx_session_wrappers(custom_session=None):
    global session
    if custom_session is not None:
        session = custom_session
        
    # 1. Execute login
    login_krx()
    
    # Save original methods to avoid infinite loop
    original_post = session.post
    original_get = session.get
    
    def resilient_post(*args, **kwargs):
        headers = kwargs.get('headers', {})
        headers['X-Requested-With'] = 'XMLHttpRequest'
        kwargs['headers'] = headers
        
        res = original_post(*args, **kwargs)
        if "LOGOUT" in res.text:
            print("[Auth] KRX returned LOGOUT (session kicked out). Re-authenticating...")
            login_krx()
            res = original_post(*args, **kwargs)
        res.encoding = 'utf-8' # Fix encoding just in case
        return res
        
    def resilient_get(*args, **kwargs):
        headers = kwargs.get('headers', {})
        headers['X-Requested-With'] = 'XMLHttpRequest'
        kwargs['headers'] = headers
        
        res = original_get(*args, **kwargs)
        if "LOGOUT" in res.text:
            print("[Auth] KRX returned LOGOUT (session kicked out). Re-authenticating...")
            login_krx()
            res = original_get(*args, **kwargs)
        res.encoding = 'utf-8' # Fix encoding just in case
        return res
    
    # 2. Monkey patch pykrx webio requests
    webio.requests.get = resilient_get
    webio.requests.post = resilient_post
    
    print("[Auth] pykrx session wrapper patched with resilient auto-relogin.")

# To support backward compatibility or other approaches, we can also patch the requests library at module level
# if pykrx's webio implementation varies.
