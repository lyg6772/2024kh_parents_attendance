from dotenv import load_dotenv
import os

env_path = f'{os.getcwd()}/app/.env'
load_dotenv(env_path)

DB_URL = os.environ.get("DB_URL", "")
DB_USER = os.environ.get("DB_USER", '')
DB_PW = os.environ.get("DB_PW", '')
SECRET_SALT = os.environ.get("SECRET_SALT", '')
if not SECRET_SALT:
    raise RuntimeError("SECRET_SALT 환경변수가 설정되지 않았습니다. app/.env를 확인하세요.")
ACCESS_TOKEN_EXPIRE_HOURS = int(os.environ.get("ACCESS_TOKEN_EXPIRE_HOURS", 8))
ORACLE_CONNECTION_STRING = os.environ.get("ORACLE_CONNECTION_STRING", '')

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
# 콤마로 구분한 후보 목록 — 앞에서부터 순서대로 시도, 하나 죽으면(모델 폐기/레이트리밋) 다음으로 넘어간다.
GROQ_MODELS = [
    m.strip()
    for m in os.environ.get(
        "GROQ_MODEL", "qwen/qwen3.8-27b,qwen/qwen3.6-27b,openai/gpt-oss-120b"
    ).split(",")
    if m.strip()
]
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")