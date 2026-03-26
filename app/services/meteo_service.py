import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.db.session import SessionLocal
from app.db import models
import logging

logger = logging.getLogger("meteo_service")


class MeteoService:
    def __init__(self, latitude: float, longitude: float):
        self.latitude = latitude
        self.longitude = longitude
        self.base_url = "https://api.open-meteo.com/v1/forecast"

        self._lock = asyncio.Lock()
        self._running = False
        self._task = None

    # =========================
    # Вспомогательные методы для работы с данными
    # =========================

    def _create_meteo_record(self, timestamp: str, hourly_data: dict, index: int) -> models.MeteoData:
        """Создает объект MeteoData из данных часового слоя"""
        return models.MeteoData(
            timestamp=datetime.fromisoformat(timestamp),
            temperature_2m=hourly_data.get("temperature_2m", [])[index] if index < len(
                hourly_data.get("temperature_2m", [])) else None,
            relative_humidity_2m=hourly_data.get("relative_humidity_2m", [])[index] if index < len(
                hourly_data.get("relative_humidity_2m", [])) else None,
            wind_speed_10m=hourly_data.get("wind_speed_10m", [])[index] if index < len(
                hourly_data.get("wind_speed_10m", [])) else None,
            wind_gusts_10m=hourly_data.get("wind_gusts_10m", [])[index] if index < len(
                hourly_data.get("wind_gusts_10m", [])) else None,
            dew_point_1m=hourly_data.get("dewpoint_2m", [])[index] if index < len(
                hourly_data.get("dewpoint_2m", [])) else None,
            shortwave_radiation=hourly_data.get("shortwave_radiation", [])[index] if index < len(
                hourly_data.get("shortwave_radiation", [])) else None,
        )

    def _save_weather_data(self, hourly_data: dict, indices: list[int]) -> int:
        """Сохраняет выбранные индексы часовых данных в БД"""
        db: Session = SessionLocal()
        try:
            times = hourly_data.get("time", [])
            for i in indices:
                if i < len(times):
                    record = self._create_meteo_record(times[i], hourly_data, i)
                    db.add(record)

            db.commit()
            logger.info(f"Meteo data saved: {len(indices)} records")
            return len(indices)
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Database integrity error: {e}")
            return 0
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Database error: {e}")
            return 0
        except Exception as e:
            db.rollback()
            logger.error(f"Unexpected DB error: {e}")
            return 0
        finally:
            db.close()

    async def fetch_with_retry(self, start: datetime, end: datetime, max_retries: int = 3):
        """Повторяет запрос при временных ошибках"""
        for attempt in range(max_retries):
            try:
                return await self.fetch_weather(start, end)
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2 ** attempt  # экспоненциальная задержка
                logger.warning(f"Request failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)

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
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])

        if not times:
            logger.warning("No data to save")
            return

        indices = list(range(len(times)))
        self._save_weather_data(hourly, indices)

    # =========================
    # РУЧНОЙ режим
    # =========================

    async def load_history(self, days_back: int):
        """
        Загрузка исторических данных за N дней назад
        """
        end = datetime.now()
        start = end - timedelta(days=days_back)

        logger.info(f"Loading history: {start} - {end}")

        try:
            data = await self.fetch_with_retry(start, end)
            self.save_to_db(data)
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error while loading history: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while loading history: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error while loading history: {e}", exc_info=True)
            raise

    # =========================
    # АВТО режим
    # =========================

    async def _auto_loop(self, interval_hours: int, forecast_hours: int):
        """
        Автообновление прогноза - сохраняет прогнозы с интервалом interval_hours/2
        Проверяет, не были ли данные уже сохранены за последние interval_hours
        """
        request_interval = interval_hours * 3600 / 2

        while self._running:
            try:
                now = datetime.now()

                start = now
                end = now + timedelta(hours=forecast_hours)

                start_date = start.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = end.replace(hour=0, minute=0, second=0, microsecond=0)

                logger.info(f"Fetching forecast: from {start.isoformat()} to {end.isoformat()}")
                logger.info(f"API date range: {start_date.date()} to {end_date.date()}")

                try:
                    data = await self.fetch_weather(start_date, end_date)
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
                    if e.response.status_code >= 500:
                        logger.warning("Server error, will retry on next cycle")
                    await asyncio.sleep(request_interval)
                    continue
                except httpx.RequestError as e:
                    logger.error(f"Network error: {e}")
                    await asyncio.sleep(request_interval)
                    continue
                except asyncio.TimeoutError:
                    logger.error("Request timeout")
                    await asyncio.sleep(request_interval)
                    continue

                hourly = data.get("hourly")
                if not hourly:
                    logger.error("Invalid API response: missing 'hourly' field")
                    await asyncio.sleep(request_interval)
                    continue

                times = hourly.get("time", [])
                if not times:
                    logger.warning("No time data in response")
                    await asyncio.sleep(request_interval)
                    continue

                current_hour_rounded = now.replace(minute=0, second=0, microsecond=0)
                if now.minute > 0 or now.second > 0 or now.microsecond > 0:
                    current_hour_rounded += timedelta(hours=1)

                end_time = now + timedelta(hours=forecast_hours)

                filtered_indexes = []
                for i, t in enumerate(times):
                    timestamp = datetime.fromisoformat(t)
                    if current_hour_rounded <= timestamp <= end_time:
                        filtered_indexes.append(i)

                if not filtered_indexes:
                    logger.warning(f"No data in forecast horizon from {current_hour_rounded} to {end_time}")
                    await asyncio.sleep(request_interval)
                    continue

                records_to_save = self._filter_recent_records(hourly, filtered_indexes, interval_hours)

                if not records_to_save:
                    logger.info(f"No new records to save (all within last {interval_hours} hours)")
                    await asyncio.sleep(request_interval)
                    continue

                saved_count = self._save_weather_data_with_indices(hourly, records_to_save)
                logger.info(
                    f"Saved {saved_count} new forecast records for hours: {[times[i] for i in records_to_save]}")
                logger.info(f"Next update in {request_interval / 3600} hours")

                await asyncio.sleep(request_interval)

            except asyncio.CancelledError:
                logger.info("Auto-update task cancelled")
                break
            except Exception as e:
                logger.exception(f"Unexpected error in auto-update loop: {e}")
                await asyncio.sleep(request_interval)

    def _filter_recent_records(self, hourly: dict, indices: list[int], interval_hours: int) -> list[int]:
        """
        Фильтрует записи, оставляя только те, которые не были сохранены за последние interval_hours часов
        """
        db: Session = SessionLocal()
        try:
            times = hourly.get("time", [])
            cutoff_time = datetime.now() - timedelta(hours=interval_hours)

            records_to_save = []

            for i in indices:
                timestamp_str = times[i]
                timestamp = datetime.fromisoformat(timestamp_str)

                existing_record = db.query(models.MeteoData).filter(
                    models.MeteoData.timestamp == timestamp,
                    models.MeteoData.getting_timestamp >= cutoff_time
                ).first()

                if not existing_record:
                    records_to_save.append(i)
                else:
                    logger.debug(
                        f"Record for {timestamp_str} already exists (saved at {existing_record.getting_timestamp})")

            return records_to_save

        except Exception as e:
            logger.error(f"Error filtering recent records: {e}")
            return []
        finally:
            db.close()

    def _save_weather_data_with_indices(self, hourly: dict, indices: list[int]) -> int:
        """Сохраняет выбранные индексы часовых данных в БД"""
        db: Session = SessionLocal()
        try:
            times = hourly.get("time", [])
            for i in indices:
                if i < len(times):
                    record = self._create_meteo_record(times[i], hourly, i)
                    db.add(record)

            db.commit()
            logger.info(f"Meteo data saved: {len(indices)} records")
            return len(indices)
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Database integrity error: {e}")
            return 0
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"Database error: {e}")
            return 0
        except Exception as e:
            db.rollback()
            logger.error(f"Unexpected DB error: {e}")
            return 0
        finally:
            db.close()

    async def start_auto(self, interval_hours: int = 6):
        """
        Запуск автообновления каждые interval_hours
        с горизонтом прогноза = interval_hours
        """
        async with self._lock:
            if self._running:
                logger.warning("Auto-update already running")
                return

            if self._task and not self._task.done():
                logger.warning("Previous task still running, cancelling...")
                self._task.cancel()
                try:
                    await asyncio.wait_for(self._task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass

            self._running = True
            self._task = asyncio.create_task(
                self._auto_loop(interval_hours, interval_hours)
            )
            logger.info(f"Auto-update started with interval {interval_hours}h")

    async def stop_auto(self, timeout: float = 10.0):
        """
        Остановка автообновления с graceful shutdown
        """
        async with self._lock:
            if not self._running:
                logger.info("Auto-update not running")
                return

            self._running = False
            logger.info("Stopping auto-update...")

            if self._task and not self._task.done():
                try:
                    await asyncio.wait_for(self._task, timeout=timeout)
                    logger.info("Auto-update stopped gracefully")
                except asyncio.TimeoutError:
                    logger.warning(f"Auto-update task didn't stop within {timeout}s, cancelling...")
                    self._task.cancel()
                    try:
                        await self._task
                    except asyncio.CancelledError:
                        pass
                except Exception as e:
                    logger.error(f"Error while stopping: {e}")
                    self._task.cancel()

            self._task = None