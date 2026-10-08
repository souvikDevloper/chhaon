"""Checks against real weather saved from Open-Meteo (data/fixtures)."""
import json
import statistics
import unittest
from pathlib import Path

from chhaon import planner
from chhaon.wbgt import outdoor_wbgt

FIX = Path(__file__).resolve().parents[2] / "data" / "fixtures"


def load(name):
    return json.loads((FIX / f"{name}.json").read_text())


@unittest.skipUnless((FIX / "forecast-howrah.json").exists(), "fixtures not present")
class RealData(unittest.TestCase):
    def test_wet_bulb_matches_open_meteo(self):
        h = load("forecast-howrah")["hourly"]
        diffs = []
        for i in range(len(h["time"])):
            vals = [h[k][i] for k in ("temperature_2m", "relative_humidity_2m", "wind_speed_10m", "surface_pressure", "wet_bulb_temperature_2m")]
            if None in vals:
                continue
            t, rh, w, p, wb = vals
            diffs.append(outdoor_wbgt(t, rh, w, 0, p, 0.0).psychrometric_wet_bulb - wb)
        self.assertGreater(len(diffs), 48)
        self.assertLess(abs(statistics.mean(diffs)), 0.3)
        self.assertLess(max(abs(d) for d in diffs), 1.0)

    def _replay(self, name, lat, lon, workload="heavy"):
        wx = load(name)
        cfg = planner.SiteConfig(lat=lat, lon=lon, workload=workload)
        return planner.plan_from_weather(wx["hourly"], wx["utc_offset_seconds"], cfg, "2024-05-30")

    def test_rourkela_heat_was_unsafe_before_the_official_ban(self):
        slots, p = self._replay("archive-rourkela-2024-05-30", 22.2604, 84.8536)
        self.assertEqual(p.unsafe_hours_normal, 8)
        start, end = p.crew.stop_windows[0]
        self.assertLessEqual(start, "07:00")  # Odisha's ban started at 11:00
        self.assertGreaterEqual(end, "16:00")
        self.assertGreater(p.peak_wbgt, 35)

    def test_aurangabad_most_dangerous_hour_is_not_the_hottest(self):
        slots, p = self._replay("archive-aurangabad-2024-05-30", 24.7522, 84.374)
        day = [s for s in slots if 6 <= s.hour < 19]
        hottest = max(day, key=lambda s: s.air_temp)
        worst = max(day, key=lambda s: s.wbgt)
        self.assertLess(worst.hour, hottest.hour)
        self.assertGreater(worst.wbgt - next(s for s in day if s.hour == hottest.hour).wbgt, 3)


if __name__ == "__main__":
    unittest.main()
