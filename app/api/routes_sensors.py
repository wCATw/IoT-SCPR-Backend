from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.sensor_service import get_latest_sensor_data
from app.schemas.sensor import SensorData

router = APIRouter()

@router.get("/", response_model=list[SensorData])
def list_sensors(db: Session = Depends(get_db)):
    return get_latest_sensor_data(db)