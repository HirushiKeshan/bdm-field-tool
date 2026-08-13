"""
outlets.csv has no locality/neighbourhood field, and Town collapses 1:1
onto a BDM's Territory (see docs/data-notes.md) -- so there is no source
column to filter a beat by "area" within a territory. This derives a
lightweight North/South/East/West quadrant from each outlet's coordinates
relative to its territory's centroid, purely so a BDM can plan a
realistic day without covering an entire district on foot. This is an
inferred grouping, not a real locality name -- labelled as such in the UI.
"""
from collections import defaultdict
from statistics import mean


def compute_centroids(outlets: list) -> dict:
    """outlets: list of dicts with 'territory', 'latitude', 'longitude'.
    Returns {territory: (centroid_lat, centroid_lon)}."""
    by_territory = defaultdict(list)
    for o in outlets:
        if o.get("latitude") is not None and o.get("longitude") is not None and o.get("territory"):
            by_territory[o["territory"]].append(o)
    return {
        territory: (mean(o["latitude"] for o in group), mean(o["longitude"] for o in group))
        for territory, group in by_territory.items()
    }


def assign_area(latitude, longitude, centroid: tuple) -> str:
    if latitude is None or longitude is None or centroid is None:
        return "Area unknown"
    clat, clon = centroid
    ns = "North" if latitude >= clat else "South"
    ew = "East" if longitude >= clon else "West"
    return f"{ns}-{ew}"
