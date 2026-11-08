"""Current weather at a condominium from NEA's realtime readings on data.gov.sg.

Air temperature and humidity come from the nearest weather station, the outlook from the nearest
area of the 2-hour forecast. The condo is located from its postal code with OneMap. Everything is
cached, so phones and kiosks never call data.gov.sg directly and the site stays within its rate limits.
"""
import logging
import math

import requests
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)

API = "https://api-open.data.gov.sg/v2/real-time/api/"
ONEMAP = "https://www.onemap.gov.sg/api/common/elastic/search"
SINGAPORE = (1.3521, 103.8198)  # When the postal code is missing or unknown.
READINGS_TTL = 5 * 60
LOCATION_TTL = 30 * 24 * 3600


def _get(url, **params):
    headers = {"x-api-key": settings.DATA_GOV_SG_API_KEY} if settings.DATA_GOV_SG_API_KEY else {}
    response = requests.get(url, params=params, headers=headers, timeout=5)
    response.raise_for_status()
    return response.json()


def _readings(kind):
    """One realtime dataset (``air-temperature``, ``two-hr-forecast``…), shared by every site for 5 minutes."""
    key = f"weather:{kind}"
    data = cache.get(key)
    if data is None:
        data = _get(API + kind)["data"]
        cache.set(key, data, READINGS_TTL)
    return data


def locate(postal_code):
    """(latitude, longitude) of a Singapore postal code, or the island's centre."""
    if not postal_code:
        return SINGAPORE
    key = f"weather:postal:{postal_code}"
    where = cache.get(key)
    if where is None:
        try:
            results = _get(ONEMAP, searchVal=postal_code, returnGeom="Y", getAddrDetails="N", pageNum=1)["results"]
            where = (float(results[0]["LATITUDE"]), float(results[0]["LONGITUDE"])) if results else SINGAPORE
        except (requests.RequestException, KeyError, ValueError, IndexError):
            log.warning("Could not locate postal code %s; using the centre of Singapore", postal_code)
            return SINGAPORE
        cache.set(key, where, LOCATION_TTL)
    return tuple(where)


def _km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def _nearest_reading(kind, where):
    data = _readings(kind)
    reading = data["readings"][0]
    values = {r["stationId"]: r["value"] for r in reading["data"]}
    stations = [s for s in data["stations"] if s["id"] in values]
    if not stations:
        return None, None, reading["timestamp"]
    station = min(stations, key=lambda s: _km(where, (s["location"]["latitude"], s["location"]["longitude"])))
    return values[station["id"]], station["name"], reading["timestamp"]


def _forecast(where):
    data = _readings("two-hr-forecast")
    item = data["items"][0]
    area = min(data["area_metadata"], key=lambda a: _km(where, (a["label_location"]["latitude"], a["label_location"]["longitude"])))
    text = next((f["forecast"] for f in item["forecasts"] if f["area"] == area["name"]), "")
    return text, area["name"], item.get("valid_period", {}).get("text", "")


def current(condominium):
    """``{temperature, humidity, forecast, area, station, valid, updated_at}`` or None when NEA is unreachable."""
    where = locate(condominium.postal_code)
    try:
        temperature, station, updated_at = _nearest_reading("air-temperature", where)
        humidity, _, _ = _nearest_reading("relative-humidity", where)
        forecast, area, valid = _forecast(where)
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError):
        log.warning("Weather from data.gov.sg is unavailable", exc_info=True)
        return None
    return {
        "temperature": temperature, "humidity": humidity, "forecast": forecast, "area": area,
        "station": station or "", "valid": valid, "updated_at": updated_at,
    }
