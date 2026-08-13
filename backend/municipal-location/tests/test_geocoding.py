"""Regression tests for district geocoding.

Origin: "Al-Olaya, Riyadh" resolved to Al Olaya in Al Quwayiyah — a different
governorate ~160 km away — and the competitor lookup then reported zero nearby
establishments. A wrong location producing a confident-looking count is worse
than an obvious failure, so the query is bounded to the city's viewbox and any
candidate outside it is discarded.

The deterministic tests always run. The live Nominatim checks are opt-in via
``--live`` because they depend on a third-party service and its rate limit
(1 request/second), and a flaky network should not fail the suite.
"""

import pytest

from app.competitor_lookup import (
    CITY_VIEWBOX,
    _match_quality,
    _match_rank,
    _viewbox_for,
    _within,
    geocode_district,
)

# The bug: this is where Al-Olaya used to land.
AL_QUWAYIYAH = (24.0700, 45.2800)
RIYADH_BOX = CITY_VIEWBOX["riyadh"]


class TestViewboxSelection:
    @pytest.mark.parametrize(
        "city", ["Riyadh", "riyadh", "RIYADH", "Al Riyadh", "Al-Riyadh"]
    )
    def test_riyadh_variants_resolve_to_a_box(self, city):
        assert _viewbox_for(city) == RIYADH_BOX

    def test_other_supported_cities(self):
        assert _viewbox_for("Jeddah") == CITY_VIEWBOX["jeddah"]
        assert _viewbox_for("Dammam") == CITY_VIEWBOX["dammam"]

    def test_unknown_city_has_no_box(self):
        assert _viewbox_for("Atlantis") is None

    def test_empty_city_has_no_box(self):
        assert _viewbox_for("") is None


class TestBoundsCheck:
    def test_al_quwayiyah_is_outside_the_riyadh_box(self):
        """The exact coordinates of the original bug must be rejected."""
        lat, lon = AL_QUWAYIYAH
        assert _within(lat, lon, RIYADH_BOX) is False

    def test_central_riyadh_is_inside(self):
        assert _within(24.6692, 46.6996, RIYADH_BOX) is True

    def test_north_riyadh_is_inside(self):
        assert _within(24.8341, 46.6802, RIYADH_BOX) is True

    def test_jeddah_is_not_inside_the_riyadh_box(self):
        assert _within(21.4858, 39.1925, RIYADH_BOX) is False


class TestMatchRanking:
    def test_district_polygon_outranks_a_street(self):
        district = {"class": "place", "type": "suburb"}
        street = {"class": "highway", "type": "residential"}
        assert _match_rank(district) < _match_rank(street)

    def test_boundary_outranks_a_street(self):
        assert _match_rank({"class": "boundary", "type": "administrative"}) < _match_rank(
            {"class": "highway", "type": "residential"}
        )

    def test_quality_labels(self):
        assert _match_quality({"class": "place", "type": "suburb"}) == "district"
        assert _match_quality({"class": "highway", "type": "residential"}) == "street"

    def test_street_matches_are_labelled_so_they_can_be_discounted(self):
        """Searching 'Al Malqa, Riyadh' returns only roads of that name."""
        assert _match_quality({"class": "highway", "type": "residential"}) == "street"


@pytest.mark.live
class TestLiveNominatim:
    """Opt in with: uv run pytest -m live

    Nominatim asks for <= 1 request/second, so these sleep between calls.
    """

    @pytest.mark.parametrize("district", ["Al-Olaya", "Al Malqa", "An Narjis"])
    def test_known_riyadh_districts_resolve_inside_riyadh(self, district):
        import time

        result = geocode_district(district, "Riyadh")
        time.sleep(1.2)
        assert result is not None, f"{district} did not resolve inside the Riyadh box"
        lat, lon, name, quality = result
        assert _within(lat, lon, RIYADH_BOX), (
            f"{district} resolved to {lat},{lon} ({name}) — outside Riyadh"
        )
        assert quality in ("district", "place", "street")

    def test_al_olaya_is_central_riyadh_not_al_quwayiyah(self):
        """The specific regression."""
        import time

        result = geocode_district("Al-Olaya", "Riyadh")
        time.sleep(1.2)
        assert result is not None
        lat, lon, _, _ = result
        # Central Riyadh, generously bounded.
        assert 24.55 <= lat <= 24.85, f"latitude {lat} is not central Riyadh"
        assert 46.55 <= lon <= 46.85, f"longitude {lon} is not central Riyadh"
        assert abs(lat - AL_QUWAYIYAH[0]) > 0.3 or abs(lon - AL_QUWAYIYAH[1]) > 0.3

    def test_nonsense_district_fails_rather_than_guessing(self):
        import time

        result = geocode_district("Zzzqqq Nonexistent District", "Riyadh")
        time.sleep(1.2)
        assert result is None
