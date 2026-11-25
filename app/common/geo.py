import math

from flask import request

from app.common.errors import APIError

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def location_args():
    """Optional ?lat=&lon= (customer GPS). Both or neither; returns (lat, lon) or (None, None)."""
    raw_lat, raw_lon = request.args.get("lat"), request.args.get("lon")
    if raw_lat is None and raw_lon is None:
        return None, None
    try:
        lat, lon = float(raw_lat), float(raw_lon)
    except (TypeError, ValueError):
        raise APIError("Provide both 'lat' and 'lon' as numbers", 422)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise APIError("'lat' must be within -90..90 and 'lon' within -180..180", 422)
    return lat, lon
