"""和风天气 v7/weather/now 封装 + 进程内 TTL 缓存。"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 8.0


@dataclass
class WeatherResult:
    temperature: float = 22.0
    text: str = "晴"
    humidity: int = 50
    city: str = "未知"

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "text": self.text,
            "humidity": self.humidity,
            "city": self.city,
        }


_cache: dict[str, tuple[float, WeatherResult]] = {}
_CACHE_MAX_SIZE = 500


def _cleanup_cache() -> None:
    """主动清理过期天气缓存；若仍超过上限，删除最老的 20%。"""
    now = time.time()
    ttl = settings.qweather_cache_minutes * 60
    expired = [k for k, (ts, _) in _cache.items() if (now - ts) > ttl]
    for k in expired:
        _cache.pop(k, None)
    if len(_cache) > _CACHE_MAX_SIZE:
        sorted_items = sorted(_cache.items(), key=lambda x: x[1][0])
        to_remove = int(_CACHE_MAX_SIZE * 0.2)
        for k, _ in sorted_items[:to_remove]:
            _cache.pop(k, None)


def _cache_key(lng: float | None, lat: float | None, city: str | None) -> str:
    if lng is not None and lat is not None:
        return f"geo:{round(lng, 2)}:{round(lat, 2)}"
    return f"city:{(city or '').strip()}"


def _get_cached(key: str) -> WeatherResult | None:
    entry = _cache.get(key)
    if not entry:
        return None
    ts, value = entry
    if (time.time() - ts) > settings.qweather_cache_minutes * 60:
        _cache.pop(key, None)
        return None
    return value


def _set_cached(key: str, value: WeatherResult) -> None:
    _cleanup_cache()
    _cache[key] = (time.time(), value)


async def _lookup_city_via_geo(client: httpx.AsyncClient, lng: float, lat: float) -> tuple[str, str]:
    """经纬度 → 和风 location id + city name。"""
    url = f"{settings.qweather_host}/geo/v2/city/lookup"
    resp = await client.get(
        url,
        params={"location": f"{lng:.2f},{lat:.2f}", "key": settings.qweather_api_key},
    )
    resp.raise_for_status()
    data = resp.json()
    locations = data.get("location") or []
    if not locations:
        return "", ""
    top = locations[0]
    return str(top.get("id") or ""), str(top.get("name") or "")


async def _fetch_weather_now(client: httpx.AsyncClient, location_id: str) -> dict[str, Any]:
    url = f"{settings.qweather_host}/v7/weather/now"
    resp = await client.get(
        url,
        params={"location": location_id, "key": settings.qweather_api_key},
    )
    resp.raise_for_status()
    return resp.json()


async def get_weather(
    lng: float | None = None,
    lat: float | None = None,
    city: str | None = None,
) -> WeatherResult:
    """返回当前天气；未配置 KEY 或调用失败时返回默认。"""
    key = _cache_key(lng, lat, city)
    cached = _get_cached(key)
    if cached is not None:
        return cached

    if not settings.qweather_api_key:
        default = WeatherResult(city=city or "未知")
        _set_cached(key, default)
        return default

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            location_id = ""
            city_name = city or ""
            if lng is not None and lat is not None:
                location_id, resolved = await _lookup_city_via_geo(client, lng, lat)
                city_name = city_name or resolved
            if not location_id and city:
                url = f"{settings.qweather_host}/geo/v2/city/lookup"
                resp = await client.get(
                    url, params={"location": city, "key": settings.qweather_api_key}
                )
                resp.raise_for_status()
                data = resp.json()
                locs = data.get("location") or []
                if locs:
                    location_id = str(locs[0].get("id") or "")
                    city_name = city_name or str(locs[0].get("name") or "")

            if not location_id:
                fallback = WeatherResult(city=city_name or "未知")
                _set_cached(key, fallback)
                return fallback

            data = await _fetch_weather_now(client, location_id)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("qweather fetch failed: %s", exc)
        fallback = WeatherResult(city=city or "未知")
        _set_cached(key, fallback)
        return fallback

    now = data.get("now") or {}
    try:
        temp = float(now.get("temp", 22))
    except (TypeError, ValueError):
        temp = 22.0
    try:
        humidity = int(float(now.get("humidity", 50)))
    except (TypeError, ValueError):
        humidity = 50
    result = WeatherResult(
        temperature=temp,
        text=str(now.get("text") or "晴")[:20],
        humidity=humidity,
        city=city_name or (city or "未知"),
    )
    _set_cached(key, result)
    return result
