from dotenv import load_dotenv
import os

env_path = f'{os.getcwd()}/app/.env'
load_dotenv(env_path)

DB_USER = os.environ.get("DB_USER", '')
DB_PW = os.environ.get("DB_PW", '')
SECRET_SALT = os.environ.get("SECRET_SALT", '')
ACCESS_TOKEN_EXPIRE_HOURS = int(os.environ.get("ACCESS_TOKEN_EXPIRE_HOURS", 8))
ORACLE_CONNECTION_STRING = os.environ.get("ORACLE_CONNECTION_STRING", '')