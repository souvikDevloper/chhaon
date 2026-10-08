"""Open-Meteo client (free, no key, non-commercial use) for forecasts and the ERA5 archive."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

HOURLY = (
    "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,"
    "direct_radiation,diffuse_radiation,surface_pressure,wet_bulb_temperature_2m"
)
ARCHIVE_HOURLY = (
    "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,"
    "direct_radiation,diffuse_radiation,surface_pressure"
)
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
TZ = "Asia/Kolkata"


class WeatherError(RuntimeError):
    pass


def _get(url: str, params: dict, timeout: float = 8.0, retries: int = 2) -> dict:
    full = f"{url}?{urllib.parse.urlencode(params)}"
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(full, headers={"User-Agent": "chhaon/1.0 (heat-safety hackathon project)"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            if data.get("error"):
                raise WeatherError(data.get("reason", "weather API error"))
            return data
        except WeatherError:
            raise
        except Exception as exc:  # network hiccup: brief backoff
            last = exc
            time.sleep(0.4 * (attempt + 1))
    raise WeatherError(f"weather service unreachable: {last}")


def forecast(lat: float, lon: float, days: int = 3) -> dict:
    return _get(
        FORECAST_URL,
        {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "hourly": HOURLY,
            "wind_speed_unit": "ms",
            "timezone": TZ,
            "forecast_days": days,
            "past_days": 1,
        },
    )


def archive(lat: float, lon: float, date: str) -> dict:
    """ERA5 reanalysis for a past date (plus the next day, so the 23:00 slot is complete)."""
    from datetime import date as _d, timedelta

    end = (_d.fromisoformat(date) + timedelta(days=1)).isoformat()
    return _get(
        ARCHIVE_URL,
        {
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "hourly": ARCHIVE_HOURLY,
            "wind_speed_unit": "ms",
            "timezone": TZ,
            "start_date": date,
            "end_date": end,
        },
        timeout=15,
    )
