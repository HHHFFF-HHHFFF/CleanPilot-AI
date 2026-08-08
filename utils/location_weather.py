"""Browser location parsing and current-weather lookups."""

from __future__ import annotations

from typing import Any

import requests


NOMINATIM_HEADERS = {
    "User-Agent": "autonomous-cleaning-support-agent/1.0 (educational project)",
}

WEATHER_CODE_LABELS = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "强阵雨",
    82: "暴雨",
    95: "雷暴",
}


def extract_coordinates(raw_location: dict[str, Any] | None) -> tuple[float, float] | None:
    """Extract latitude and longitude from streamlit-js-eval output."""
    if not isinstance(raw_location, dict):
        return None

    coordinates = raw_location.get("coords", raw_location)
    if not isinstance(coordinates, dict):
        return None

    latitude = coordinates.get("latitude", coordinates.get("lat"))
    longitude = coordinates.get("longitude", coordinates.get("lon"))
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return None

    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    return latitude, longitude


def _request_json(url: str, *, params: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    response = requests.get(url, params=params, headers=headers, timeout=8)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("天气服务返回了无效数据")
    return payload


def _reverse_geocode_city(latitude: float, longitude: float) -> str:
    payload = _request_json(
        "https://nominatim.openstreetmap.org/reverse",
        params={
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "zoom": 10,
            "accept-language": "zh-CN,zh",
        },
        headers=NOMINATIM_HEADERS,
    )
    address = payload.get("address", {})
    if not isinstance(address, dict):
        return "当前位置"

    for key in ("city", "town", "village", "county", "state"):
        value = address.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "当前位置"


def _current_weather(latitude: float, longitude: float) -> dict[str, Any]:
    payload = _request_json(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            "timezone": "auto",
        },
    )
    current = payload.get("current")
    if not isinstance(current, dict):
        raise ValueError("天气服务未返回当前天气")
    return current


def _build_profile(city: str, latitude: float, longitude: float) -> dict[str, Any]:
    current = _current_weather(latitude, longitude)
    weather_code = current.get("weather_code")
    return {
        "city": city,
        "latitude": latitude,
        "longitude": longitude,
        "condition": WEATHER_CODE_LABELS.get(weather_code, "天气未知"),
        "temperature": current.get("temperature_2m"),
        "apparent_temperature": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "wind_speed": current.get("wind_speed_10m"),
        "observed_at": current.get("time"),
    }


def get_location_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """Resolve a browser coordinate to a city and current weather."""
    try:
        city = _reverse_geocode_city(latitude, longitude)
    except requests.RequestException:
        city = "当前位置"
    return _build_profile(city, latitude, longitude)


def get_city_weather(city: str) -> dict[str, Any]:
    """Resolve a city name and return its current weather."""
    normalized_city = city.strip()
    if not normalized_city:
        raise ValueError("请提供城市名称")

    payload = _request_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": normalized_city, "count": 1, "language": "zh", "format": "json"},
    )
    results = payload.get("results")
    if not isinstance(results, list) or not results:
        raise ValueError(f"未找到城市：{normalized_city}")

    result = results[0]
    if not isinstance(result, dict):
        raise ValueError("城市服务返回了无效数据")
    return _build_profile(
        str(result.get("name") or normalized_city),
        float(result["latitude"]),
        float(result["longitude"]),
    )


def format_weather(profile: dict[str, Any]) -> str:
    """Format weather data for the interface and Agent tools."""
    return (
        f"{profile['city']}当前{profile['condition']}，气温{profile['temperature']}°C，"
        f"体感{profile['apparent_temperature']}°C，湿度{profile['humidity']}%，"
        f"风速{profile['wind_speed']} km/h。"
    )
