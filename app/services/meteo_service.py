import asyncio
import httpx
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.db.session import SessionLocal
from app.db import models
import logging

logger = logging.getLogger("meteo_service")


class MeteoService:
    def __init__(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude
        self.base_url = "https://api.open-meteo.com/v1/forecast"
        self.http_timeout = httpx.Timeout(10.0, connect=5.0)

        self._lock = asyncio.Lock()
        self._running = False
        self._task = None

    # =========================
    # helpers
    # =========================

    def _get(self, hourly: dict, key: str, i: int):
        arr = hourly.get(key, [])
        return arr[i] if i < len(arr) else None

    def _create_record(self, timestamp: str, hourly: dict, i: int):
        return models.MeteoData(
            timestamp=datetime.fromisoformat(timestamp),
            temperature_2m=self._get(hourly, "temperature_2m", i),
            relative_humidity_2m=self._get(hourly, "relative_humidity_2m", i),
            wind_speed_10m=self._get(hourly, "wind_speed_10m", i),
            wind_gusts_10m=self._get(hourly, "wind_gusts_10m", i),
            dew_point_1m=self._get(hourly, "dewpoint_2m", i),
            shortwave_radiation=self._get(hourly, "shortwave_radiation", i),
        )

    def _save(self, hourly: dict, indices: list[int]) -> int:
        db: Session = SessionLocal()
        try:
            times = hourly.get("time", [])

            for i in indices:
                if i >= len(times):
                    continue
                db.add(self._create_record(times[i], hourly, i))

            db.commit()
            return len(indices)

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"DB error: {e}")
            return 0
        finally:
            db.close()

    def _now(self) -> datetime:
        return datetime.now()

    # =========================
    # HTTP
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
        }

        async with httpx.AsyncClient(timeout=self.http_timeout) as client:
            r = await client.get(self.base_url, params=params)
            r.raise_for_status()
            return r.json()

    async def fetch_with_retry(self, start: datetime, end: datetime, retries: int = 3):
        for attempt in range(retries):
            try:
                return await self.fetch_weather(start, end)
            except Exception as e:
                if attempt == retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning(f"Retry in {wait}s: {e}")
                await asyncio.sleep(wait)

    # =========================
    # manual
    # =========================

    async def load_history(self, days_back: int):
        end = self._now()
        start = end - timedelta(days=days_back)

        data = await self.fetch_with_retry(start, end)
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])

        await asyncio.to_thread(self._save, hourly, list(range(len(times))))

    # =========================
    # auto loop
    # =========================

    async def _auto_loop(self, interval_hours: int, forecast_hours: int):
        request_interval = interval_hours * 3600 / 2

        while self._running:
            try:
                now = self._now()

                start = now
                end = now + timedelta(hours=forecast_hours)

                start_date = start.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = end.replace(hour=0, minute=0, second=0, microsecond=0)

                data = await self.fetch_with_retry(start_date, end_date)

                hourly = data.get("hourly", {})
                times = hourly.get("time", [])

                if not times:
                    logger.warning("No data")
                    continue

                current_hour = now.replace(minute=0, second=0, microsecond=0)
                if now.minute or now.second or now.microsecond:
                    current_hour += timedelta(hours=1)

                end_time = now + timedelta(hours=forecast_hours)

                indices = [
                    i for i, t in enumerate(times)
                    if current_hour <= datetime.fromisoformat(t) <= end_time
                ]

                if not indices:
                    logger.warning("No forecast in range")
                    continue

                saved = await asyncio.to_thread(self._save, hourly, indices)
                logger.info(f"Saved {saved} records")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Auto loop error: {e}")

            await asyncio.sleep(request_interval)

    # =========================
    # control
    # =========================

    async def start_auto(self, interval_hours: int = 6):
        async with self._lock:
            if self._running:
                return

            self._running = True
            self._task = asyncio.create_task(
                self._auto_loop(interval_hours, interval_hours)
            )

    async def stop_auto(self, timeout: float = 10.0):
        async with self._lock:
            if not self._running:
                return

            self._running = False

            if self._task:
                try:
                    await asyncio.wait_for(self._task, timeout)
                except asyncio.TimeoutError:
                    self._task.cancel()
                finally:
                    self._task = None