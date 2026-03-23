from app.core.config import FASTAPI_PORT
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.api import routes_auth, routes_sensors, routes_system
from app.db.session import Base, engine
from app.services.mqtt_service import MQTTService

# создаём таблицы
Base.metadata.create_all(bind=engine)

mqtt_service = MQTTService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    print("Starting MQTT service...")
    mqtt_service.start()

    yield

    # --- shutdown ---
    print("Stopping MQTT service...")
    mqtt_service.stop()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://iot.megameow.ru"],
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