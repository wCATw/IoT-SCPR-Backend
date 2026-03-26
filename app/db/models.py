from sqlalchemy import Column, Integer, String, Float, DateTime
from app.db.session import Base
from datetime import datetime,timezone

def getNow():
    return datetime.now()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

class SensorData(Base):
    __tablename__ = "sensor_data"
    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(String, index=True)
    temperature = Column(Float)
    humidity = Column(Float)
    co2 = Column(Float)
    timestamp = Column(DateTime, default=getNow)
    timestamp_server = Column(DateTime, default=getNow)

class MeteoData(Base):
    __tablename__ = "meteo_data"
    id = Column(Integer, primary_key=True, index=True)
    getting_timestamp = Column(DateTime, default=getNow)
    timestamp = Column(DateTime)
    temperature_2m = Column(Float)
    relative_humidity_2m = Column(Float)
    wind_speed_10m = Column(Float)
    wind_gusts_10m = Column(Float)
    dew_point_1m = Column(Float)
    shortwave_radiation = Column(Float)

class RoomStateData(Base):
    __tablename__ = "room_state_data"
    id = Column(Integer, primary_key=True, index=True)