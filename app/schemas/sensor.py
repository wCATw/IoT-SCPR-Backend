from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SensorData(BaseModel):
    sensor_id: str

    class Config:
        from_attributes = True