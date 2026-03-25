import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db import models
import logging

logger = logging.getLogger("meteo_service")


class MeteoService:
    def __init__(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude
        self.base_url = "https://api.open-meteo.com/v1/forecast"

        self.running = False
        self.task = None

    # =========================
    # HTTP запрос
    # =========================

    async def fetch_weather(self, start: datetime, end: datetime):
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "hourly": ",".join([
                "temperature_2m",
                "relative_humidity_2m",
                "wind_speed_10m",
                "wind_gusts_10m",
                "dewpoint_2m",
                "shortwave_radiation"
            ]),
            "start_date": start.strftime("%Y-%m-%d"),
            "end_date": end.strftime("%Y-%m-%d"),
            "timezone": "auto"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(self.base_url, params=params)
            response.raise_for_status()
            return response.json()

    # =========================
    # Сохранение в БД
    # =========================

    def save_to_db(self, data: dict):
        db: Session = SessionLocal()

        try:
            hourly = data.get("hourly", {})

            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            humidity = hourly.get("relative_humidity_2m", [])
            wind = hourly.get("wind_speed_10m", [])
            gusts = hourly.get("wind_gusts_10m", [])
            dew = hourly.get("dewpoint_2m", [])
            radiation = hourly.get("shortwave_radiation", [])

            for i in range(len(times)):
                timestamp = datetime.fromisoformat(times[i])

                # защита от дублей
                exists = db.query(models.MeteoData).filter(
                    models.MeteoData.timestamp == timestamp
                ).first()

                if exists:
                    continue

                record = models.MeteoData(
                    timestamp=timestamp,
                    temperature_2m=temps[i] if i < len(temps) else None,
                    relative_humidity_2m=humidity[i] if i < len(humidity) else None,
                    wind_speed_10m=wind[i] if i < len(wind) else None,
                    wind_gusts_10m=gusts[i] if i < len(gusts) else None,
                    dew_point_1m=dew[i] if i < len(dew) else None,
                    shortwave_radiation=radiation[i] if i < len(radiation) else None,
                )

                db.add(record)

            db.commit()
            logger.info(f"Meteo data saved: {len(times)} records")

        except Exception as e:
            db.rollback()
            logger.error(f"DB error: {e}")

        finally:
            db.close()

    # =========================
    # РУЧНОЙ режим
    # =========================

    async def load_history(self, days_back: int):
        """
        Загрузка исторических данных за N дней назад
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)

        logger.info(f"Loading history: {start} - {end}")

        data = await self.fetch_weather(start, end)
        self.save_to_db(data)

    # =========================
    # АВТО режим
    # =========================

    async def _auto_loop(self, interval_hours: int, forecast_hours: int):
        """
        interval_hours — как часто обновлять
        forecast_hours — на сколько часов вперед брать прогноз
        """

        while self.running:
            try:
                now = datetime.utcnow()
                end = now + timedelta(hours=forecast_hours)

                logger.info(f"Fetching forecast: now → +{forecast_hours}h")

                data = await self.fetch_weather(now, end)
                self.save_to_db(data)

            except Exception as e:
                logger.error(f"Fetch error: {e}")

            await asyncio.sleep(interval_hours * 3600)

    def start_auto(self, interval_hours: int = 3, forecast_hours: int = 24):
        """
        Запуск автообновления
        """
        if self.running:
            return

        self.running = True
        self.task = asyncio.create_task(
            self._auto_loop(interval_hours, forecast_hours)
        )

    def stop_auto(self):
        self.running = False
        if self.task:
            self.task.cancel()