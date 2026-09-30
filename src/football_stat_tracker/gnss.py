"""Raw GNSS calculations."""

from __future__ import annotations

import math
from collections.abc import Iterable

from football_stat_tracker.data_model import GnssSample


EARTH_RADIUS_M = 6_371_000.0


def haversine_distance_m(
    latitude_1_deg: float,
    longitude_1_deg: float,
    latitude_2_deg: float,
    longitude_2_deg: float,
) -> float:
    """Return the great-circle distance in metres between two coordinates."""

    coordinates = (
        latitude_1_deg,
        longitude_1_deg,
        latitude_2_deg,
        longitude_2_deg,
    )
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("Coordinates must be finite numbers")
    if not -90.0 <= latitude_1_deg <= 90.0 or not -90.0 <= latitude_2_deg <= 90.0:
        raise ValueError("Latitude must be between -90 and 90 degrees")
    if not -180.0 <= longitude_1_deg <= 180.0 or not -180.0 <= longitude_2_deg <= 180.0:
        raise ValueError("Longitude must be between -180 and 180 degrees")

    latitude_1_rad = math.radians(latitude_1_deg)
    longitude_1_rad = math.radians(longitude_1_deg)
    latitude_2_rad = math.radians(latitude_2_deg)
    longitude_2_rad = math.radians(longitude_2_deg)

    delta_latitude = latitude_2_rad - latitude_1_rad
    delta_longitude = longitude_2_rad - longitude_1_rad
    a = (
        math.sin(delta_latitude / 2.0) ** 2
        + math.cos(latitude_1_rad)
        * math.cos(latitude_2_rad)
        * math.sin(delta_longitude / 2.0) ** 2
    )
    # Guard against a tiny floating-point overshoot outside [0, 1].
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def total_gnss_distance_m(samples: Iterable[GnssSample]) -> float:
    """Sum raw Haversine distances between successive valid GNSS positions.

    Samples without usable coordinates are skipped. The valid position before
    a missing sample is therefore connected directly to the next valid one;
    no coordinate is synthesized or interpolated.
    """

    total_distance = 0.0
    previous_coordinates: tuple[float, float] | None = None

    for sample in samples:
        latitude = sample.latitude_deg
        longitude = sample.longitude_deg
        if not _coordinates_are_valid(latitude, longitude):
            continue

        current_coordinates = (latitude, longitude)
        if previous_coordinates is not None:
            total_distance += haversine_distance_m(
                previous_coordinates[0],
                previous_coordinates[1],
                current_coordinates[0],
                current_coordinates[1],
            )
        previous_coordinates = current_coordinates

    return total_distance


def _coordinates_are_valid(
    latitude_deg: float | None, longitude_deg: float | None
) -> bool:
    return (
        latitude_deg is not None
        and longitude_deg is not None
        and math.isfinite(latitude_deg)
        and math.isfinite(longitude_deg)
        and -90.0 <= latitude_deg <= 90.0
        and -180.0 <= longitude_deg <= 180.0
    )
