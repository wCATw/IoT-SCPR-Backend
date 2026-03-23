import json
import threading
import paho.mqtt.client as mqtt
from sqlalchemy.orm import Session
from datetime import datetime
from app.db.session import SessionLocal
from app.db import models
from app.core.config import MOSQUITTO_PORT, MOSQUITTO_HOST, MOSQUITTO_USER, MOSQUITTO_PASSWORD
import logging
from uvicorn.logging import DefaultFormatter

logger = logging.getLogger("mqtt_service")
handler = logging.StreamHandler()
formatter = DefaultFormatter(
    fmt="%(levelprefix)s [%(name)s] %(message)s",
    use_colors=True,
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class MQTTService:
    def __init__(self, broker=MOSQUITTO_HOST, port=MOSQUITTO_PORT):
        self.broker = broker
        self.port = port

        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        self.thread = None
        self.running = False

    # -------- lifecycle --------

    def start(self):
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        try:
            self.client.disconnect()
        except Exception:
            pass

    def _run(self):
        self.client.username_pw_set(MOSQUITTO_USER, MOSQUITTO_PASSWORD)
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

    # -------- callbacks --------

    def on_connect(self, client, userdata, flags, rc):
        logger.info(f"Connected with result code {rc}")
        client.subscribe("sensors/+/data")
        client.subscribe("sensors/+/status")

    def on_message(self, client, userdata, msg):
        topic = msg.topic

        try:
            payload = msg.payload.decode()
        except Exception:
            logger.info(f"Decode error")
            return

        if topic.endswith("/data"):
            self.handle_sensor_data(payload)

        elif topic.endswith("/status"):
            logger.info(f"[STATUS] {topic}: {payload}")

    # -------- data handler --------

    def handle_sensor_data(self, payload: str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            print()
            logger.info(f"Invalid JSON: {payload}")
            return

        db: Session = SessionLocal()

        try:
            timestamp = None
            if data.get("timestamp"):
                timestamp = datetime.fromisoformat(data["timestamp"])

            record = models.SensorData(
                sensor_id=data.get("sensor_id"),
                temperature=data.get("temperature"),
                humidity=data.get("humidity"),
                co2=data.get("co2"),
                timestamp=timestamp
            )

            db.add(record)
            db.commit()

        except Exception as e:
            logger.info(f"DB error: {e}")
            db.rollback()

        finally:
            db.close()