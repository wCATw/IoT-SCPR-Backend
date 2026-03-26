from app.core.config import FASTAPI_PORT, LATITUDE, LONGITUDE
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api import routes_auth, routes_sensors, routes_system
from app.db.session import Base, engine
from app.services.meteo_service import MeteoService
from app.services.mqtt_service import MQTTService
import logging
from uvicorn.logging import DefaultFormatter

logger = logging.getLogger("main")
handler = logging.StreamHandler()
formatter = DefaultFormatter(
    fmt="%(levelprefix)s [%(name)s] %(message)s",
    use_colors=True,
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

Base.metadata.create_all(bind=engine)

mqtt_service = MQTTService()
meteo_service = MeteoService(LATITUDE,LONGITUDE)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    logger.info("Starting MQTT service...")
    mqtt_service.start()
    logger.info("Starting METEO service...")
    meteo_service.start_auto(4)

    yield

    # --- shutdown ---
    logger.info("Stopping MQTT service...")
    mqtt_service.stop()
    logger.info("Starting METEO service...")
    meteo_service.stop_auto()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://iot.megameow.ru","http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_auth.router, prefix="/auth")
app.include_router(routes_sensors.router, prefix="/sensors")
app.include_router(routes_system.router, prefix="/system")

if __name__ == "__main__":
    import uvicorn
    port = FASTAPI_PORT
    uvicorn.run(app, host="0.0.0.0", port=port)