import math
import unittest
from datetime import datetime, timedelta, timezone

from chhaon import announce, limits, planner, protocol
from chhaon.solar import solar_position
from chhaon.wbgt import outdoor_wbgt

IST = timezone(timedelta(hours=5, minutes=30))


def synthetic_hourly(date: str, tmax: float, tmin: float, rh_min: float, rh_max: float, lat: float, lon: float, wind: float = 2.5):
    """Open-Meteo shaped hourly arrays for `date` and the next day, local time."""
    start = datetime.fromisoformat(f"{date}T00:00").replace(tzinfo=IST)
    out = {k: [] for k in ("time", "temperature_2m", "relative_humidity_2m", "wind_speed_10m", "shortwave_radiation", "direct_radiation", "surface_pressure")}
    for i in range(48):
        t = start + timedelta(hours=i)
        h = t.hour
        # temperature peaks at 15:00, minimum at 05:00
        phase = math.cos((h - 15) / 24 * 2 * math.pi)
        temp = (tmax + tmin) / 2 + (tmax - tmin) / 2 * phase
        rh = (rh_min + rh_max) / 2 - (rh_max - rh_min) / 2 * phase
        cza, _ = solar_position(t - timedelta(minutes=30), lat, lon)
        ghi = max(0.0, 1000 * cza * 0.85) if cza > 0 else 0.0
        out["time"].append(t.strftime("%Y-%m-%dT%H:%M"))
        out["temperature_2m"].append(round(temp, 1))
        out["relative_humidity_2m"].append(round(rh))
        out["wind_speed_10m"].append(wind)
        out["shortwave_radiation"].append(round(ghi))
        out["direct_radiation"].append(round(ghi * 0.75))
        out["surface_pressure"].append(1000.0)
    return out


class WbgtTests(unittest.TestCase):
    def test_shade_close_to_air_and_wet_bulb(self):
        r = outdoor_wbgt(30, 70, 2, 0, 1005, 0.0)
        self.assertAlmostEqual(r.psychrometric_wet_bulb, 25.6, delta=0.8)
        self.assertLess(abs(r.globe - 30), 2)

    def test_sun_raises_wbgt(self):
        shade = outdoor_wbgt(35, 40, 3, 900, 1005, 0.95, shaded=True)
        sun = outdoor_wbgt(35, 40, 3, 900, 1005, 0.95)
        self.assertGreater(sun.wbgt - shade.wbgt, 2.0)
        self.assertGreater(sun.globe, 45)

    def test_humidity_raises_wbgt(self):
        dry = outdoor_wbgt(38, 25, 2, 850, 1005, 0.95)
        humid = outdoor_wbgt(38, 60, 2, 850, 1005, 0.95)
        self.assertGreater(humid.wbgt, dry.wbgt + 3)

    def test_wind_cools(self):
        calm = outdoor_wbgt(36, 50, 0.5, 900, 1005, 0.9)
        windy = outdoor_wbgt(36, 50, 6, 900, 1005, 0.9)
        self.assertLess(windy.wbgt, calm.wbgt)


class SolarTests(unittest.TestCase):
    def test_noon_sun_high_in_kolkata_may(self):
        cza, dist = solar_position(datetime(2024, 5, 30, 11, 30, tzinfo=IST), 22.57, 88.36)
        self.assertGreater(cza, 0.95)
        self.assertAlmostEqual(dist, 1.014, delta=0.003)

    def test_night(self):
        cza, _ = solar_position(datetime(2024, 5, 30, 0, 0, tzinfo=IST), 22.57, 88.36)
        self.assertLess(cza, 0)


class LimitTests(unittest.TestCase):
    def test_table_values(self):
        self.assertEqual(limits.hour_limit(27.5, "heavy", True).work_minutes, 45)
        self.assertEqual(limits.hour_limit(27.6, "heavy", True).work_minutes, 30)
        self.assertEqual(limits.hour_limit(30.5, "heavy", True).work_minutes, 15)
        self.assertEqual(limits.hour_limit(30.6, "heavy", True).work_minutes, 0)
        self.assertEqual(limits.hour_limit(28.0, "moderate", True).work_minutes, 50)
        self.assertEqual(limits.hour_limit(25.0, "moderate", False).work_minutes, 50)
        self.assertEqual(limits.hour_limit(28.1, "heavy", False).work_minutes, 0)

    def test_heavy_never_full_hour(self):
        self.assertEqual(limits.hour_limit(15.0, "heavy", True).work_minutes, 45)

    def test_acclimatisation_ramp(self):
        self.assertEqual(limits.exposure_factor(1), 0.2)
        self.assertEqual(limits.exposure_factor(3), 0.6)
        self.assertEqual(limits.exposure_factor(9), 1.0)


class PlannerTests(unittest.TestCase):
    lat, lon = 22.26, 84.85  # Rourkela

    def plan(self, hourly, **cfg):
        c = planner.SiteConfig(lat=self.lat, lon=self.lon, **cfg)
        return planner.plan_from_weather(hourly, 19800, c, "2024-05-30")

    def test_hot_day_moves_work_out_of_midday(self):
        hourly = synthetic_hourly("2024-05-30", 43, 30, 30, 70, self.lat, self.lon)
        slots, p = self.plan(hourly, workload="heavy")
        self.assertEqual(len(slots), 24)
        self.assertGreater(p.unsafe_hours_normal, 3)
        self.assertEqual(p.unsafe_hours_planned, 0)
        noon = next(h for h in p.crew.hours if h.hour == 13)
        self.assertEqual(noon.work_minutes, 0)
        self.assertTrue(p.crew.stop_windows)
        for h in p.crew.hours:
            self.assertLessEqual(h.work_minutes, h.safe_minutes)
        self.assertEqual(p.crew.first_start, "06:00")
        self.assertIn(p.verdict, ("stop_heavy", "stop_all"))

    def test_mild_day_keeps_normal_shift(self):
        hourly = synthetic_hourly("2024-05-30", 27, 20, 40, 60, self.lat, self.lon)
        _, p = self.plan(hourly, workload="moderate")
        self.assertEqual(p.verdict, "normal")
        self.assertEqual(p.unsafe_hours_normal, 0)
        worked = [h.hour for h in p.crew.hours if h.work_minutes]
        self.assertEqual(worked, [9, 10, 11, 12, 14, 15, 16, 17])
        self.assertEqual(p.crew.shortfall_minutes, 0)

    def test_cool_day_heavy_work_is_normal(self):
        # heavy work is never screened for a full hour, but that alone is not heat stress
        hourly = synthetic_hourly("2024-05-30", 22, 15, 40, 70, self.lat, self.lon)
        _, p = self.plan(hourly, workload="heavy", new_workers=3, new_worker_day=1)
        self.assertEqual(p.verdict, "normal")
        self.assertEqual(p.unsafe_hours_normal, 0)
        self.assertEqual(p.worker_hours_protected, 0)
        self.assertEqual(p.crew.first_start, "09:00")
        self.assertEqual(p.crew.target_minutes, 8 * 45)
        self.assertEqual(p.crew.shortfall_minutes, 0)
        self.assertIsNone(p.water_litres_total)
        # no heat, so no acclimatisation cut for new workers
        self.assertEqual(p.new_workers.planned_minutes, p.crew.planned_minutes)

    def test_impact_counts_only_heat(self):
        hourly = synthetic_hourly("2024-05-30", 39, 27, 30, 70, self.lat, self.lon)
        _, p = self.plan(hourly, workload="heavy", crew=20)
        normal = [h for h in p.crew.hours if h.in_normal_shift]
        self.assertEqual(p.unsafe_hours_normal, sum(1 for h in normal if h.safe_minutes < 45))
        self.assertAlmostEqual(p.worker_hours_protected, round(sum(45 - min(45, h.safe_minutes) for h in normal) * 20 / 60, 1))
        self.assertGreater(p.water_litres_total, 0)

    def test_new_workers_get_less_and_stricter(self):
        hourly = synthetic_hourly("2024-05-30", 40, 29, 35, 70, self.lat, self.lon)
        _, p = self.plan(hourly, workload="moderate", new_workers=4, new_worker_day=2)
        self.assertIsNotNone(p.new_workers)
        self.assertLessEqual(p.new_workers.planned_minutes, p.new_workers.target_minutes)
        self.assertEqual(p.new_workers.target_minutes, 160)
        for crew_h, new_h in zip(p.crew.hours, p.new_workers.hours):
            self.assertLessEqual(new_h.safe_minutes, crew_h.safe_minutes)

    def test_events_are_ordered_and_announceable(self):
        hourly = synthetic_hourly("2024-05-30", 39, 26, 25, 65, self.lat, self.lon)
        _, p = self.plan(hourly, workload="heavy")
        times = [e["at"] for e in p.events]
        self.assertEqual(times, sorted(times))
        kinds = [e["kind"] for e in p.events]
        self.assertEqual(kinds[0], "day_start")
        self.assertEqual(kinds[-1], "day_end")
        self.assertIn("pause", kinds)
        for e in p.events:
            for lang in ("hi", "en"):
                self.assertTrue(announce.text_for(e, lang))

    def test_night_window_recovers_work(self):
        hourly = synthetic_hourly("2024-05-30", 43, 30, 30, 70, self.lat, self.lon)
        _, day = self.plan(hourly, workload="heavy")
        _, night = self.plan(hourly, workload="heavy", window_start=5, window_end=23)
        self.assertGreater(night.crew.planned_minutes, day.crew.planned_minutes)
        self.assertEqual(night.unsafe_hours_planned, 0)

    def test_check_window_suggests_cooler_start(self):
        hourly = synthetic_hourly("2024-05-30", 43, 30, 30, 70, self.lat, self.lon)
        slots, _ = self.plan(hourly)
        c = planner.SiteConfig(lat=self.lat, lon=self.lon, workload="heavy")
        res = planner.check_window(slots, c, 14, 3)
        self.assertFalse(res["asked"]["ok"])
        self.assertLess(res["best"][0]["max_wbgt"], res["asked"]["max_wbgt"])

    def test_shaded_work_is_safer(self):
        hourly = synthetic_hourly("2024-05-30", 40, 29, 35, 70, self.lat, self.lon)
        _, sun = self.plan(hourly, workload="moderate")
        _, shade = self.plan(hourly, workload="moderate", shaded=True)
        self.assertLessEqual(shade.unsafe_hours_normal, sun.unsafe_hours_normal)
        noon_sun = next(h for h in sun.crew.hours if h.hour == 12)
        noon_shade = next(h for h in shade.crew.hours if h.hour == 12)
        self.assertLess(noon_shade.wbgt, noon_sun.wbgt - 2)


class ProtocolTests(unittest.TestCase):
    def test_red_flags_win(self):
        self.assertEqual(protocol.classify(["dizzy", "confused"]), "red")
        self.assertEqual(protocol.classify(["hot_dry_skin"]), "red")

    def test_levels(self):
        self.assertEqual(protocol.classify(["vomiting"]), "amber")
        self.assertEqual(protocol.classify(["cramps"]), "yellow")
        self.assertEqual(protocol.classify(["rash"]), "green")
        with self.assertRaises(ValueError):
            protocol.classify(["unknown"])

    def test_escalation_is_conservative(self):
        self.assertEqual(protocol.after_recheck("amber", "better"), "resolved")
        self.assertEqual(protocol.after_recheck("amber", "same"), "red")
        self.assertEqual(protocol.after_recheck("yellow", "same"), "amber")

    def test_guidance_bilingual(self):
        for level in ("red", "amber", "yellow", "green"):
            en, hi = protocol.guidance(level, "en"), protocol.guidance(level, "hi")
            self.assertEqual(len(en["steps"]), len(hi["steps"]))
        self.assertTrue(protocol.guidance("red")["call_108"])


if __name__ == "__main__":
    unittest.main()


class OfflineProtocolTests(unittest.TestCase):
    def test_web_copy_matches_server(self):
        import json
        import re
        from pathlib import Path

        js = (Path(__file__).resolve().parents[2] / "web" / "protocol.js").read_text(encoding="utf-8")
        data = json.loads(re.search(r"export const PROTOCOL = (\{.*?\});\n", js, re.S).group(1))
        self.assertEqual(data["steps"], protocol.STEPS)
        self.assertEqual(data["titles"], protocol.TITLES)
        self.assertEqual(data["red"], list(protocol.RED_FLAGS))
        self.assertEqual(data["amber"], list(protocol.AMBER))
