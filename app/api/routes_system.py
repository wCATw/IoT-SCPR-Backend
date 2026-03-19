from fastapi import APIRouter
from app.services.mqtt_service import MQTTService

router = APIRouter()

@router.get("/status")
def system_status():
    mqtt = MQTTService()  # проверка соединения
    return {
        "mqtt_connected": mqtt.client.is_connected(),
        "db_connected": True  # можно потом добавить real check
    }