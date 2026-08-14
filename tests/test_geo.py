from logic.geo import resolve_live_location


CENTROIDS = {
    "Tirupur": (11.10, 77.34),
    "Salem": (11.66, 78.15),
}


def test_resolve_live_location_picks_nearest_territory_as_district():
    result = resolve_live_location(11.11, 77.35, CENTROIDS)
    assert result["district"] == "Tirupur"
    assert result["area"] in ("North-East", "North-West", "South-East", "South-West")


def test_resolve_live_location_missing_coords_returns_unknown():
    result = resolve_live_location(None, None, CENTROIDS)
    assert result == {"area": "Area unknown", "district": None}


def test_resolve_live_location_no_centroids_returns_unknown():
    result = resolve_live_location(11.11, 77.35, {})
    assert result == {"area": "Area unknown", "district": None}
