from dotenv import load_dotenv
import os

env_path = f'{os.getcwd()}/app/.env'
load_dotenv(env_path)

DB_HOST = os.environ.get("DB_HOST", '')
DB_USER = os.environ.get("DB_USER", '')
DB_PW = os.environ.get("DB_PW", '')
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_DB = os.environ.get("DB_DB", '')
SECRET_SALT = os.environ.get("SECRET_SALT", '')
ACCESS_TOKEN_EXPIRE_HOURS = int(os.environ.get("ACCESS_TOKEN_EXPIRE_HOURS", 8))
