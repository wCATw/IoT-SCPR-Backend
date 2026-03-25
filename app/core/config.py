import os
from dotenv import load_dotenv

load_dotenv()

DB_USER=os.getenv("DB_USER")
DB_PORT=os.getenv("DB_PORT","5432")
DB_HOST=os.getenv("DB_HOST")
DB_PASSWORD=os.getenv("DB_PASSWORD")
DB_NAME=os.getenv("DB_NAME")

JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM","HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE","180"))
FASTAPI_PORT=int(os.getenv("FASTAPI_PORT","8000"))

MOSQUITTO_PORT = int(os.getenv("MOSQUITTO_PORT","1883"))
MOSQUITTO_HOST = os.getenv("MOSQUITTO_HOST")
MOSQUITTO_USER = os.getenv("MOSQUITTO_USER")
MOSQUITTO_PASSWORD = os.getenv("MOSQUITTO_PASSWORD")

LATITUDE = float(os.getenv("LATITUDE","0"))
LONGITUDE = float(os.getenv("LONGITUDE","0"))