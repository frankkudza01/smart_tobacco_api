from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.access import can_view_farm
from apps.farms.models import Farm
from apps.weather.openweather_service import build_farmer_payload
from apps.weather.zimbabwe_regions import (
    ZIMBABWE_REGIONS,
    get_region,
    match_region_from_district,
    match_region_from_province,
)

# Rough bounding box for Zimbabwe (reject coordinates far outside).
_ZW_LAT_MIN, _ZW_LAT_MAX = -23.0, -15.0
_ZW_LON_MIN, _ZW_LON_MAX = 24.5, 34.0


class ZimbabweWeatherRegionsView(APIView):
    """List Zimbabwe provinces + districts/towns with coordinates for OpenWeatherMap queries."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        kind = (request.query_params.get("kind") or "").strip().lower()
        rows = ZIMBABWE_REGIONS
        if kind == "province":
            rows = [r for r in ZIMBABWE_REGIONS if r.get("kind") == "province"]
        elif kind == "district":
            rows = [r for r in ZIMBABWE_REGIONS if r.get("kind") == "district"]
        return Response({"regions": rows, "count": len(rows)})


class ZimbabweWeatherForecastView(APIView):
    """
    Current weather + 5-day/3-hour forecast (aggregated) with irrigation hints.

    Query (one of):
      - `region=<code>` — use provincial centroid (e.g. manicaland).
      - `lat=<float>&lon=<float>` — explicit coordinates within Zimbabwe.
      - `farm_id=<uuid>` — use farm GPS if set, else province → region centroid (must be viewable).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        region = (request.query_params.get("region") or "").strip().lower()
        lat_q = request.query_params.get("lat")
        lon_q = request.query_params.get("lon")
        farm_id = (request.query_params.get("farm_id") or "").strip()

        try:
            reg: dict | None = None
            if farm_id:
                farm = get_object_or_404(Farm, pk=farm_id)
                if not can_view_farm(request.user, farm):
                    return Response(
                        {"detail": "You cannot access weather for this farm."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
                reg = (
                    match_region_from_district(farm.district)
                    or match_region_from_province(farm.province)
                    or get_region("harare")
                )
                if reg is None:
                    reg = ZIMBABWE_REGIONS[0]
                if farm.latitude is not None and farm.longitude is not None:
                    lat = float(farm.latitude)
                    lon = float(farm.longitude)
                    if not (_ZW_LAT_MIN <= lat <= _ZW_LAT_MAX and _ZW_LON_MIN <= lon <= _ZW_LON_MAX):
                        lat, lon = float(reg["lat"]), float(reg["lon"])
                else:
                    lat, lon = float(reg["lat"]), float(reg["lon"])
                code, name = reg["code"], reg["name"]
            elif lat_q is not None and lon_q is not None:
                lat = float(lat_q)
                lon = float(lon_q)
                if not (_ZW_LAT_MIN <= lat <= _ZW_LAT_MAX and _ZW_LON_MIN <= lon <= _ZW_LON_MAX):
                    return Response(
                        {"detail": "Coordinates appear outside Zimbabwe; refused."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                reg = get_region(region) if region else None
                code = reg["code"] if reg else None
                name = reg["name"] if reg else "Custom coordinates"
            elif region:
                reg = get_region(region)
                if not reg:
                    return Response(
                        {"detail": f"Unknown region '{region}'. Use GET /api/v1/weather/zimbabwe/regions/."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                lat, lon = float(reg["lat"]), float(reg["lon"])
                code, name = reg["code"], reg["name"]
            else:
                return Response(
                    {
                        "detail": "Provide region=, lat&lon=, or farm_id=.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            payload = build_farmer_payload(
                region_code=code,
                region_name=name,
                lat=lat,
                lon=lon,
                location_kind=reg.get("kind") if reg else None,
                parent_region_code=reg.get("parent_code") if reg else None,
            )
            return Response(payload, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return Response(
                {"detail": f"Weather service error: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
