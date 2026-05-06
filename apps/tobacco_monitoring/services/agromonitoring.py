"""
AgroMonitoring Agro API client (polygons, NDVI history, soil history).

Docs: https://agromonitoring.com/api
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urljoin

from django.conf import settings

from apps.tobacco_monitoring.services.http_client import request_with_retries

logger = logging.getLogger(__name__)

# Polygon ids returned by POST /polygons are 24-char hex strings (Mongo-style).
_AGRO_POLYID_RE = re.compile(r"^[a-fA-F0-9]{24}$")


def _normalize_polyid(polyid: str) -> str:
    return (polyid or "").strip()


def looks_like_agromonitoring_polygon_id(polyid: str) -> bool:
    """True if [polyid] matches the hex string returned by AgroMonitoring POST /polygons."""
    return bool(_AGRO_POLYID_RE.match(_normalize_polyid(polyid)))


def _utc_day_range_timestamps_clamped(start: date, end: date) -> tuple[int, int] | None:
    """
    Return Unix ``start`` (UTC midnight) and ``end`` (UTC end-of-day), with ``end`` capped
    at the current instant so AgroMonitoring never sees ``end`` in the future.
    """
    now_ts = int(datetime.now(timezone.utc).timestamp())
    start_ts = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    end_ts = min(end_ts, now_ts)
    if start_ts > end_ts:
        return None
    return start_ts, end_ts


def _ndvi_payload_to_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        if "message" in data:
            raise AgroMonitoringError(str(data.get("message"))[:500])
        return [data] if "dt" in data else []
    if isinstance(data, list):
        return data
    return []


def agromonitoring_api_configured() -> bool:
    """True when Django settings has a non-empty AgroMonitoring API key."""
    return bool((getattr(settings, "AGROMONITORING_API_KEY", None) or "").strip())


class AgroMonitoringError(Exception):
    """Raised when AgroMonitoring returns an error or unexpected payload."""


class AgroMonitoringClient:
    """Thin wrapper around AgroMonitoring HTTP API with retries."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.AGROMONITORING_API_KEY
        self.base_url = (base_url or settings.AGROMONITORING_BASE_URL).rstrip("/") + "/"
        self.timeout = float(timeout if timeout is not None else settings.AGROMONITORING_TIMEOUT_SECONDS)
        self.max_retries = int(max_retries if max_retries is not None else settings.AGROMONITORING_MAX_RETRIES)

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def _params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        p = {"appid": self.api_key}
        if extra:
            p.update(extra)
        return p

    def list_polygons(self) -> list[dict[str, Any]]:
        """
        GET /polygons — list polygons for this API key (used for health checks).
        """
        if not self.api_key:
            raise AgroMonitoringError("AGROMONITORING_API_KEY is not configured.")
        url = self._url("polygons")
        resp = request_with_retries(
            "GET",
            url,
            params=self._params(),
            timeout=self.timeout,
            max_retries=self.max_retries,
            log_label="agromonitoring",
        )
        if resp.status_code == 401:
            raise AgroMonitoringError("Invalid or expired AgroMonitoring API key (HTTP 401).")
        if resp.status_code != 200:
            logger.warning("agromonitoring list polygons status=%s body=%s", resp.status_code, resp.text[:300])
            raise AgroMonitoringError(f"List polygons failed: HTTP {resp.status_code}")
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "message" in data:
            raise AgroMonitoringError(str(data.get("message"))[:500])
        return []

    def resolve_polygon_id_for_field_name(self, field_name: str) -> str | None:
        """
        Match ``GET /polygons`` row by ``name`` and return provider polygon id.

        Use when ``agromonitoring_poly_id`` is missing or not the AgroMonitoring hex id
        (e.g. polygon exists on the AgroMonitoring dashboard under the same API key).
        """
        target = (field_name or "").strip()
        if not target:
            return None
        try:
            rows = self.list_polygons()
        except AgroMonitoringError:
            return None
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("name") or "").strip() != target:
                continue
            for key in ("id", "_id", "polyid", "polygon_id"):
                v = row.get(key)
                if v is None:
                    continue
                rid = str(v).strip()
                if looks_like_agromonitoring_polygon_id(rid):
                    return rid
        return None

    def create_polygon(self, body: dict[str, Any], *, allow_duplicate: bool = False) -> dict[str, Any]:
        if not self.api_key:
            raise AgroMonitoringError("AGROMONITORING_API_KEY is not configured.")
        params = self._params()
        if allow_duplicate:
            params["duplicated"] = "true"
        url = self._url("polygons")
        logger.info("agromonitoring polygon create name=%s", body.get("name"))
        resp = request_with_retries(
            "POST",
            url,
            params=params,
            json=body,
            timeout=self.timeout,
            max_retries=self.max_retries,
            log_label="agromonitoring",
        )
        if resp.status_code not in (200, 201):
            logger.warning(
                "agromonitoring polygon create failed status=%s body=%s",
                resp.status_code,
                resp.text[:500],
            )
            raise AgroMonitoringError(f"Polygon create failed: HTTP {resp.status_code}")
        data = resp.json()
        logger.info("agromonitoring polygon created id=%s", data.get("id"))
        return data

    def _ndvi_history_chunk(self, polyid: str, start: date, end: date) -> list[dict[str, Any]]:
        bounds = _utc_day_range_timestamps_clamped(start, end)
        if bounds is None:
            return []
        start_ts, end_ts = bounds
        url = self._url("ndvi/history")
        # Docs list ``polygon_id``; many examples use ``polyid``. Retry with ``polyid`` on 400/404.
        params_primary = {"polygon_id": polyid, "start": start_ts, "end": end_ts}
        resp = request_with_retries(
            "GET",
            url,
            params=self._params(params_primary),
            timeout=self.timeout,
            max_retries=self.max_retries,
            log_label="agromonitoring",
        )
        # ``polygon_id`` is in the official parameter list; many deployments still expect ``polyid``.
        # Retry with ``polyid`` on 400 (bad request) or 404 (not found with ``polygon_id``).
        if resp.status_code in (400, 404):
            resp = request_with_retries(
                "GET",
                url,
                params=self._params({"polyid": polyid, "start": start_ts, "end": end_ts}),
                timeout=self.timeout,
                max_retries=self.max_retries,
                log_label="agromonitoring",
            )
        if resp.status_code == 401:
            raise AgroMonitoringError("Invalid or expired AgroMonitoring API key (HTTP 401).")
        if resp.status_code != 200:
            snippet = (resp.text or "")[:400].replace("\n", " ")
            logger.warning(
                "agromonitoring ndvi/history status=%s polyid=%s start=%s end=%s body=%s",
                resp.status_code,
                polyid,
                start_ts,
                end_ts,
                snippet,
            )
            raise AgroMonitoringError(f"NDVI history failed: HTTP {resp.status_code} ({snippet[:200]})")
        return _ndvi_payload_to_rows(resp.json())

    def ndvi_history(self, polyid: str, start: date, end: date) -> list[dict[str, Any]]:
        if not self.api_key:
            raise AgroMonitoringError("AGROMONITORING_API_KEY is not configured.")
        polyid = _normalize_polyid(polyid)
        if not polyid:
            raise AgroMonitoringError("AgroMonitoring polyid is empty.")
        if not _AGRO_POLYID_RE.match(polyid):
            logger.warning(
                "agromonitoring polyid=%r is not a 24-char hex id; "
                "use the id returned by POST /polygons (not the internal DB UUID).",
                polyid[:64],
            )
        if start > end:
            return []
        chunk_days = int(getattr(settings, "AGROMONITORING_HISTORY_CHUNK_DAYS", 30) or 30)
        chunk_days = max(1, min(chunk_days, 90))
        merged: list[dict[str, Any]] = []
        cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=chunk_days - 1))
            merged.extend(self._ndvi_history_chunk(polyid, cursor, chunk_end))
            cursor = chunk_end + timedelta(days=1)
        return merged

    def _soil_history_chunk(
        self, polyid: str, start: date, end: date
    ) -> tuple[list[dict[str, Any]], bool]:
        """Returns (rows, stop_remaining_chunks) — stop is True on 401/403."""
        bounds = _utc_day_range_timestamps_clamped(start, end)
        if bounds is None:
            return [], False
        start_ts, end_ts = bounds
        url = self._url("soil/history")
        resp = request_with_retries(
            "GET",
            url,
            params=self._params({"polyid": polyid, "start": start_ts, "end": end_ts}),
            timeout=self.timeout,
            max_retries=self.max_retries,
            log_label="agromonitoring",
        )
        if resp.status_code in (401, 403):
            body_snip = (resp.text or "")[:280].replace("\n", " ")
            low = body_snip.lower()
            if "invalid api key" in low:
                logger.info(
                    "agromonitoring soil/history HTTP %s: provider rejected the request (often "
                    "``soil/history`` is not enabled for this key or needs a different OpenWeather "
                    "product than NDVI). Free tier includes *current* soil, not historical ``/soil/history``. "
                    "body=%s",
                    resp.status_code,
                    body_snip,
                )
            else:
                logger.debug(
                    "agromonitoring soil/history status=%s; skipping remaining soil chunks. body=%s",
                    resp.status_code,
                    body_snip,
                )
            return [], True
        if resp.status_code != 200:
            logger.warning(
                "agromonitoring soil/history status=%s body=%s",
                resp.status_code,
                (resp.text or "")[:400].replace("\n", " "),
            )
            return [], False
        data = resp.json()
        if isinstance(data, list):
            return data, False
        return [], False

    def _soil_current(self, polyid: str) -> list[dict[str, Any]]:
        """GET ``/soil`` — latest soil (free tier); same payload keys as history rows."""
        if not self.api_key:
            return []
        polyid = _normalize_polyid(polyid)
        if not polyid:
            return []
        url = self._url("soil")
        resp = request_with_retries(
            "GET",
            url,
            params=self._params({"polyid": polyid}),
            timeout=self.timeout,
            max_retries=self.max_retries,
            log_label="agromonitoring",
        )
        if resp.status_code != 200:
            logger.debug(
                "agromonitoring soil (current) status=%s body=%s",
                resp.status_code,
                (resp.text or "")[:200].replace("\n", " "),
            )
            return []
        data = resp.json()
        if isinstance(data, dict) and data.get("dt") is not None:
            return [data]
        return []

    def soil_history(self, polyid: str, start: date, end: date) -> list[dict[str, Any]]:
        if not self.api_key:
            raise AgroMonitoringError("AGROMONITORING_API_KEY is not configured.")
        polyid = _normalize_polyid(polyid)
        if not polyid:
            return []
        if start > end:
            return []
        chunk_days = int(getattr(settings, "AGROMONITORING_HISTORY_CHUNK_DAYS", 30) or 30)
        chunk_days = max(1, min(chunk_days, 90))
        merged: list[dict[str, Any]] = []
        history_unauthorized = False
        cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + timedelta(days=chunk_days - 1))
            rows, stop = self._soil_history_chunk(polyid, cursor, chunk_end)
            merged.extend(rows)
            if stop:
                history_unauthorized = True
                break
            cursor = chunk_end + timedelta(days=1)
        if history_unauthorized:
            merged.extend(self._soil_current(polyid))
        return merged
