"""腾讯位置服务天气接口封装 + 进程内 TTL 缓存。

接口端点：GET {host}/ws/weather/v1?key=...&location=lat,lng
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# 避免 httpx 把完整 URL（含 key）打到日志
logging.getLogger("httpx").setLevel(logging.WARNING)

_TIMEOUT = 8.0


_KEY_REDACT_RE = re.compile(r"([?&]key=)[^&]*", re.IGNORECASE)


def _redact_url(url: str | httpx.URL) -> str:
    """把 URL 中的 key 参数脱敏后再打印。"""
    return _KEY_REDACT_RE.sub(r"\1***", str(url))


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
    ttl = settings.tencent_map_weather_cache_minutes * 60
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
    if (time.time() - ts) > settings.tencent_map_weather_cache_minutes * 60:
        _cache.pop(key, None)
        return None
    return value


def _set_cached(key: str, value: WeatherResult) -> None:
    _cleanup_cache()
    _cache[key] = (time.time(), value)


def _extract_number(value: Any) -> float | None:
    """从字符串/数字中提取数值。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _parse_tencent_now(data: dict[str, Any]) -> WeatherResult:
    """解析腾讯位置服务 /ws/weather/v1 响应。"""
    status = data.get("status")
    if status != 0:
        raise ValueError(f"tencent weather status={status}, message={data.get('message')}")

    result = data.get("result") or {}
    # realtime 可能是数组或对象
    realtime = result.get("realtime")
    if isinstance(realtime, list) and realtime:
        now = realtime[0]
    elif isinstance(realtime, dict):
        now = realtime
    else:
        now = result

    # 天气数值可能在 infos 子对象里
    info = now.get("infos") or now

    temp = (
        _extract_number(info.get("temperature"))
        or _extract_number(info.get("degree"))
        or _extract_number(info.get("temp"))
        or _extract_number(info.get("max_degree"))
        or 22.0
    )

    humidity = 50
    hum_val = info.get("humidity")
    if hum_val is not None:
        humidity = int(_extract_number(hum_val) or 50)

    text = str(
        info.get("weather")
        or info.get("weather_short")
        or info.get("text")
        or "晴"
    )[:20]

    city = str(now.get("city") or now.get("district") or "未知")[:20]

    return WeatherResult(
        temperature=temp,
        text=text,
        humidity=humidity,
        city=city,
    )


async def _fetch_weather_now(
    client: httpx.AsyncClient, location: str
) -> dict[str, Any]:
    url = f"{settings.tencent_map_host}/ws/weather/v1"
    resp = await client.get(
        url,
        params={"key": settings.tencent_map_key, "location": location},
    )
    logger.info("[tencent weather] request url=%s status=%s", _redact_url(resp.url), resp.status_code)
    resp.raise_for_status()
    data = resp.json()
    logger.info("[tencent weather] response=%s", data)
    return data


async def _geocode_address(
    client: httpx.AsyncClient, address: str
) -> tuple[float, float] | None:
    """用腾讯地理编码把城市/地址转成 lat,lng。"""
    url = f"{settings.tencent_map_host}/ws/geocoder/v1"
    resp = await client.get(
        url,
        params={"key": settings.tencent_map_key, "address": address},
    )
    logger.info("[tencent geocoder] request url=%s status=%s", _redact_url(resp.url), resp.status_code)
    resp.raise_for_status()
    data = resp.json()
    logger.info("[tencent geocoder] response=%s", data)
    if data.get("status") != 0:
        return None
    loc = data.get("result", {}).get("location")
    if not loc:
        return None
    lat = _extract_number(loc.get("lat"))
    lng = _extract_number(loc.get("lng"))
    if lat is None or lng is None:
        return None
    return lat, lng


async def get_weather(
    lng: float | None = None,
    lat: float | None = None,
    city: str | None = None,
) -> WeatherResult:
    """返回当前天气；未配置 KEY 或调用失败时返回默认，不阻断主流程。"""
    key = _cache_key(lng, lat, city)
    cached = _get_cached(key)
    if cached is not None:
        return cached

    if not settings.tencent_map_key:
        default = WeatherResult(city=city or "未知")
        _set_cached(key, default)
        return default

    city_name = city or "未知"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            # 腾讯天气接口只接受 lat,lng，城市名需要先地理编码
            if lat is not None and lng is not None:
                location = f"{lat:.6f},{lng:.6f}"
                display_city = ""
            elif city:
                geocoded = await _geocode_address(client, city)
                if geocoded is None:
                    fallback = WeatherResult(city=city_name)
                    _set_cached(key, fallback)
                    return fallback
                lat_gc, lng_gc = geocoded
                location = f"{lat_gc:.6f},{lng_gc:.6f}"
                display_city = city.strip()
            else:
                fallback = WeatherResult(city=city_name)
                _set_cached(key, fallback)
                return fallback

            logger.info("[get_weather] location=%s display_city=%s", location, display_city)
            data = await _fetch_weather_now(client, location)
            result = _parse_tencent_now(data)
            # 优先使用接口返回的城市名；经纬度查询时接口会返回 city/district
            result.city = result.city if result.city != "未知" else (display_city or city_name)
            _set_cached(key, result)
            logger.info("[get_weather] result=%s", result.to_dict())
            return result
    except (httpx.HTTPError, ValueError) as exc:
        response = getattr(exc, "response", None)
        detail = response.text[:200] if response is not None else ""
        logger.warning("tencent weather fetch failed: %s %s", type(exc).__name__, detail)
        fallback = WeatherResult(city=city_name)
        _set_cached(key, fallback)
        return fallback
