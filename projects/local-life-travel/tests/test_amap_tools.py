"""Offline contract tests for the optional Amap live adapter.

No network is used. The MockTransport asserts the adapter maps provider
results, errors and malformed payloads to the same ToolStatus contract as the
replay adapter.
"""
from __future__ import annotations

import httpx
import pytest

from app.amap_tools import AmapAdapter, AmapClient, normalize_city
from app.domain import ToolStatus


def client_with(handler) -> AmapClient:
    return AmapClient(key="test-key", transport=httpx.MockTransport(handler), timeout=1.0)


def poi(poi_id="B001", name="故宫博物院", location="116.397,39.918", city="北京市"):
    return {"id": poi_id, "name": name, "location": location, "cityname": city,
            "address": "景山前街4号", "adcode": "110101"}


def search_payload(pois):
    return {"status": "1", "info": "OK", "infocode": "10000", "count": str(len(pois)), "pois": pois}


def test_missing_key_is_explicit(monkeypatch):
    monkeypatch.delenv("AMAP_API_KEY", raising=False)
    with pytest.raises(ValueError, match="AMAP_API_KEY"):
        AmapClient()


def test_normalize_city_removes_suffix():
    assert normalize_city("北京市") == "北京"
    assert normalize_city("北京") == "北京"


def test_unique_poi_is_matched():
    def handler(request):
        assert request.url.path == "/v3/place/text"
        return httpx.Response(200, json=search_payload([poi()]))

    adapter = AmapAdapter(client_with(handler), city="北京")
    result = adapter.poi_lookup("故宫博物院")
    assert result.status == ToolStatus.VALID
    assert result.payload["match_status"] == "matched"
    assert result.payload["poi"]["coordinates"] == {"lon": 116.397, "lat": 39.918}


def test_duplicate_names_are_ambiguous_not_silently_chosen():
    def handler(request):
        return httpx.Response(200, json=search_payload([poi("B001"), poi("B002", location="116.4,39.9")]))

    adapter = AmapAdapter(client_with(handler), city="北京")
    result = adapter.poi_lookup("故宫博物院")
    assert result.status == ToolStatus.VALID
    assert result.payload["match_status"] == "ambiguous"
    assert len(result.payload["options"]) == 2


def test_empty_search_is_unmatched_not_provider_error():
    def handler(request):
        return httpx.Response(200, json=search_payload([]))

    adapter = AmapAdapter(client_with(handler), city="北京")
    result = adapter.poi_lookup("不存在的地点")
    assert result.status == ToolStatus.VALID
    assert result.payload["match_status"] == "unmatched"


def test_recycled_key_is_provider_error():
    def handler(request):
        return httpx.Response(200, json={"status": "0", "info": "USER_KEY_RECYCLED", "infocode": "10013"})

    adapter = AmapAdapter(client_with(handler), city="北京")
    result = adapter.poi_lookup("故宫博物院")
    assert result.status == ToolStatus.PROVIDER_ERROR
    assert result.error_code == "TOOL_PROVIDER_ERROR"
    assert "10013" in (result.message or "")


def test_timeout_is_timeout():
    def handler(request):
        raise httpx.TimeoutException("slow", request=request)

    adapter = AmapAdapter(client_with(handler), city="北京")
    result = adapter.poi_lookup("故宫博物院")
    assert result.status == ToolStatus.TIMEOUT
    assert result.error_code == "TOOL_TIMEOUT"


def test_malformed_location_is_not_reported_as_match():
    def handler(request):
        return httpx.Response(200, json=search_payload([poi(location="not-a-coordinate")]))

    adapter = AmapAdapter(client_with(handler), city="北京")
    result = adapter.poi_lookup("故宫博物院")
    assert result.status == ToolStatus.VALID
    assert result.payload["match_status"] == "unmatched"


def test_weather_uses_only_target_date_forecast():
    def handler(request):
        if request.url.path == "/v3/geocode/geo":
            return httpx.Response(200, json={"status": "1", "geocodes": [{"adcode": "110000"}]})
        assert request.url.path == "/v3/weather/weatherInfo"
        return httpx.Response(200, json={"status": "1", "forecasts": [{"casts": [
            {"date": "2026-11-09", "dayweather": "晴", "nightweather": "多云"},
            {"date": "2026-11-10", "dayweather": "雨", "nightweather": "阴"},
        ]}]})

    adapter = AmapAdapter(client_with(handler), city="北京")
    result = adapter.weather("2026-11-09")
    assert result.status == ToolStatus.VALID
    assert result.payload["summary"] == "晴 / 多云"
    assert result.payload["date"] == "2026-11-09"


def test_weather_outside_window_is_unavailable_not_current_weather():
    def handler(request):
        if request.url.path == "/v3/geocode/geo":
            return httpx.Response(200, json={"status": "1", "geocodes": [{"adcode": "110000"}]})
        return httpx.Response(200, json={"status": "1", "forecasts": [{"casts": [
            {"date": "2026-11-09", "dayweather": "晴", "nightweather": "多云"},
        ]}]})

    adapter = AmapAdapter(client_with(handler), city="北京")
    result = adapter.weather("2026-12-01")
    assert result.status == ToolStatus.UNAVAILABLE
    assert result.error_code == "WEATHER_DATE_NOT_COVERED"


def test_route_duration_and_distance_are_parsed():
    def handler(request):
        if request.url.path == "/v3/place/text":
            name = request.url.params["keywords"]
            return httpx.Response(200, json=search_payload([poi("B001" if name == "A" else "B002", name=name)]))
        assert request.url.path == "/v3/direction/walking"
        return httpx.Response(200, json={"status": "1", "route": {"paths": [
            {"duration": "600", "distance": "1200"}
        ]}})

    adapter = AmapAdapter(client_with(handler), city="北京", transport="walking")
    assert adapter.poi_lookup("A").payload["match_status"] == "matched"
    assert adapter.poi_lookup("B").payload["match_status"] == "matched"
    result = adapter.leg("A", "B")
    assert result.status == ToolStatus.VALID
    assert result.payload["duration_seconds"] == 600
    assert result.payload["distance_meters"] == 1200


def test_opening_hours_are_parsed_when_present():
    def handler(request):
        if request.url.path == "/v3/place/text":
            return httpx.Response(200, json=search_payload([poi()]))
        assert request.url.path == "/v3/place/detail"
        return httpx.Response(200, json={"status": "1", "pois": [
            {**poi(), "biz_ext": {"open_time": "09:00-17:00"}}
        ]})

    adapter = AmapAdapter(client_with(handler), city="北京")
    adapter.poi_lookup("故宫博物院")
    result = adapter.hours()
    assert result.status == ToolStatus.VALID
    assert result.payload["windows"]["故宫博物院"] == ["09:00", "17:00"]


def test_hours_does_not_query_origin_pseudo_poi():
    detail_ids = []

    def handler(request):
        if request.url.path == "/v3/geocode/geo":
            return httpx.Response(200, json={"status": "1", "geocodes": [
                {"location": "116.4,39.9", "adcode": "110000"}]})
        if request.url.path == "/v3/place/text":
            return httpx.Response(200, json=search_payload([poi()]))
        assert request.url.path == "/v3/place/detail"
        detail_ids.append(request.url.params["id"])
        return httpx.Response(200, json={"status": "1", "pois": [
            {**poi(), "biz_ext": {"open_time": "09:00-17:00"}}]})

    adapter = AmapAdapter(client_with(handler), city="北京")
    assert adapter.resolve_origin("北京站").status == ToolStatus.VALID
    assert adapter.poi_lookup("故宫博物院").payload["match_status"] == "matched"
    result = adapter.hours()
    assert result.status == ToolStatus.VALID
    assert detail_ids == ["B001"]


def test_missing_opening_hours_stays_unknown():
    def handler(request):
        if request.url.path == "/v3/place/text":
            return httpx.Response(200, json=search_payload([poi()]))
        return httpx.Response(200, json={"status": "1", "pois": [{**poi(), "biz_ext": {}}]})

    adapter = AmapAdapter(client_with(handler), city="北京")
    adapter.poi_lookup("故宫博物院")
    result = adapter.hours()
    assert result.status == ToolStatus.EMPTY
    assert result.payload["windows"] == {}
