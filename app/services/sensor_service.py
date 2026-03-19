from sqlalchemy.orm import Session
from app.db import models

def get_latest_sensor_data(db: Session):
    return db.query(models.SensorData).order_by(models.SensorData.timestamp.desc()).limit(10).all()

def add_sensor_data(db: Session, sensor_id: str, temperature: float, humidity: float, co2: float):
    data = models.SensorData(sensor_id=sensor_id, temperature=temperature, humidity=humidity, co2=co2)
    db.add(data)
    db.commit()
    db.refresh(data)
    return data