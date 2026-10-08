"""Outdoor Wet Bulb Globe Temperature from ordinary weather data.

A Python port of the Liljegren et al. (2008) model, "Modeling the Wet Bulb Globe
Temperature Using Standard Meteorological Measurements", J. Occup. Environ. Hyg.
5(10):645-655. It is the method the US Army, NWS and most heat-stress research
use to turn a weather forecast into WBGT, because WBGT needs a black globe and a
naturally ventilated wet bulb that no weather station has.

    WBGT = 0.7 * Tnwb + 0.2 * Tg + 0.1 * Ta

Units inside the solver: kelvin, hPa, m/s, W/m^2.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Physical constants (as in the reference implementation)
STEFANB = 5.6696e-8
CP = 1003.5  # J/(kg K), specific heat of dry air
M_AIR = 28.97
M_H2O = 18.015
RATIO = CP * M_AIR / M_H2O
R_GAS = 8314.34
R_AIR = R_GAS / M_AIR
PR = CP / (CP + 1.25 * R_AIR)  # Prandtl number

# Instrument / surface properties
EMIS_WICK, ALB_WICK, D_WICK, L_WICK = 0.95, 0.4, 0.007, 0.0254
EMIS_GLOBE, ALB_GLOBE, D_GLOBE = 0.95, 0.05, 0.0508
EMIS_SFC, ALB_SFC = 0.999, 0.45

CZA_MIN = 0.00873  # sun is below ~0.5 deg elevation
NORMSOLAR_MAX = 0.85
SOLAR_CONST = 1367.0
REF_HEIGHT = 2.0
MIN_SPEED = 0.13
CONVERGENCE = 0.02
MAX_ITER = 1000


def esat(tk: float) -> float:
    """Saturation vapour pressure over liquid water (hPa), Buck (1981) with moist-air factor."""
    y = (tk - 273.15) / (tk - 32.18)
    return 1.004 * 6.1121 * math.exp(17.502 * y)


def dew_point(e_hpa: float) -> float:
    z = math.log(e_hpa / (6.1121 * 1.004))
    return 273.15 + 240.97 * z / (17.502 - z)


def viscosity(tk: float) -> float:
    sigma, eps_kappa = 3.617, 97.0
    tr = tk / eps_kappa
    omega = (tr - 2.9) / 0.4 * (-0.034) + 1.048
    return 2.6693e-6 * math.sqrt(M_AIR * tk) / (sigma * sigma * omega)


def thermal_conductivity(tk: float) -> float:
    return (CP + 1.25 * R_AIR) * viscosity(tk)


def diffusivity(tk: float, p_hpa: float) -> float:
    pcrit_air, pcrit_h2o, tcrit_air, tcrit_h2o = 36.4, 218.0, 132.0, 647.3
    a, b = 3.640e-4, 2.334
    pcrit13 = (pcrit_air * pcrit_h2o) ** (1 / 3)
    tcrit512 = (tcrit_air * tcrit_h2o) ** (5 / 12)
    tcrit12 = math.sqrt(tcrit_air * tcrit_h2o)
    mmix = math.sqrt(1 / M_AIR + 1 / M_H2O)
    patm = p_hpa / 1013.25
    return a * (tk / tcrit12) ** b * pcrit13 * tcrit512 * mmix / patm * 1e-4


def evap_heat(tk: float) -> float:
    return (313.15 - tk) / 30.0 * (-71100.0) + 2.4073e6


def emis_atm(tk: float, rh: float) -> float:
    e = rh * esat(tk)
    return 0.575 * e**0.143


def h_sphere(diameter: float, tk: float, p_hpa: float, speed: float) -> float:
    density = p_hpa * 100 / (R_AIR * tk)
    speed = max(speed, MIN_SPEED)
    re = speed * density * diameter / viscosity(tk)
    nu = 2.0 + 0.6 * math.sqrt(re) * PR**0.3333
    return nu * thermal_conductivity(tk) / diameter


def h_cylinder(diameter: float, length: float, tk: float, p_hpa: float, speed: float) -> float:
    a, b, c = 0.56, 0.281, 0.4  # Bedingfield and Drew
    density = p_hpa * 100 / (R_AIR * tk)
    speed = max(speed, MIN_SPEED)
    re = speed * density * diameter / viscosity(tk)
    nu = b * re ** (1 - c) * PR ** (1 - a)
    return nu * thermal_conductivity(tk) / diameter


def globe_temperature(tk: float, rh: float, p_hpa: float, speed: float, solar: float, fdir: float, cza: float) -> float:
    tsfc = tk
    prev = tk
    cza = max(cza, CZA_MIN)
    for _ in range(MAX_ITER):
        tref = 0.5 * (prev + tk)
        h = h_sphere(D_GLOBE, tref, p_hpa, speed)
        new = (
            0.5 * (emis_atm(tk, rh) * tk**4 + EMIS_SFC * tsfc**4)
            - h / (STEFANB * EMIS_GLOBE) * (prev - tk)
            + solar / (2 * STEFANB * EMIS_GLOBE) * (1 - ALB_GLOBE) * (fdir * (1 / (2 * cza) - 1) + 1 + ALB_SFC)
        ) ** 0.25
        if abs(new - prev) < CONVERGENCE:
            return new - 273.15
        prev = 0.9 * prev + 0.1 * new
    raise ArithmeticError("globe temperature did not converge")


def wet_bulb(tk: float, rh: float, p_hpa: float, speed: float, solar: float, fdir: float, cza: float, radiative: bool) -> float:
    """Natural (radiative=True) or psychrometric (radiative=False) wet bulb, deg C."""
    a = 0.56
    tsfc = tk
    sza = math.acos(max(min(cza, 1.0), CZA_MIN))
    eair = rh * esat(tk)
    prev = dew_point(eair)
    for _ in range(MAX_ITER):
        tref = 0.5 * (prev + tk)
        h = h_cylinder(D_WICK, L_WICK, tref, p_hpa, speed)
        fatm = STEFANB * EMIS_WICK * (
            0.5 * (emis_atm(tk, rh) * tk**4 + EMIS_SFC * tsfc**4) - prev**4
        ) + (1 - ALB_WICK) * solar * (
            (1 - fdir) * (1 + 0.25 * D_WICK / L_WICK)
            + fdir * ((math.tan(sza) / math.pi) + 0.25 * D_WICK / L_WICK)
            + ALB_SFC
        )
        ewick = esat(prev)
        density = p_hpa * 100 / (R_AIR * tref)
        sc = viscosity(tref) / (density * diffusivity(tref, p_hpa))
        new = tk - evap_heat(tref) / RATIO * (ewick - eair) / (p_hpa - ewick) * (PR / sc) ** a + (
            fatm / h if radiative else 0.0
        )
        if abs(new - prev) < CONVERGENCE:
            return new - 273.15
        prev = 0.9 * prev + 0.1 * new
    raise ArithmeticError("wet bulb did not converge")


def stability_class(daytime: bool, speed: float, solar: float, dt: float = 0.0) -> int:
    table = [
        [1, 1, 2, 4, 0, 5, 6, 0],
        [1, 2, 3, 4, 0, 5, 6, 0],
        [2, 2, 3, 4, 0, 4, 4, 0],
        [3, 3, 4, 4, 0, 0, 0, 0],
        [3, 4, 4, 4, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ]
    if daytime:
        j = 0 if solar >= 925 else 1 if solar >= 675 else 2 if solar >= 175 else 3
        i = 4 if speed >= 6 else 3 if speed >= 5 else 2 if speed >= 3 else 1 if speed >= 2 else 0
    else:
        j = 6 if dt >= 0.111 else 5 if dt >= -0.175 else 4
        i = 2 if speed >= 2.5 else 1 if speed >= 2.0 else 0
    return table[i][j]


def wind_at_2m(speed: float, height: float, stab: int, urban: bool) -> float:
    urban_exp = [0.15, 0.15, 0.20, 0.25, 0.30, 0.30]
    rural_exp = [0.07, 0.07, 0.10, 0.15, 0.35, 0.55]
    exp = (urban_exp if urban else rural_exp)[max(stab, 1) - 1]
    return max(speed * (REF_HEIGHT / height) ** exp, MIN_SPEED)


def direct_fraction(solar: float, cza: float, distance_au: float) -> float:
    """Empirical direct-beam fraction (used when the forecast has no direct/diffuse split)."""
    toa = SOLAR_CONST * max(0.0, cza) / (distance_au * distance_au)
    if cza < CZA_MIN or toa <= 0:
        return 0.0
    norm = min(min(solar, toa) / toa, NORMSOLAR_MAX)
    if norm <= 0:
        return 0.0
    return max(0.0, min(math.exp(3 - 1.34 * norm - 1.65 / norm), 0.9))


@dataclass(frozen=True)
class WbgtResult:
    wbgt: float
    globe: float
    natural_wet_bulb: float
    psychrometric_wet_bulb: float
    wind_2m: float

    def as_dict(self) -> dict:
        return {
            "wbgt": round(self.wbgt, 1),
            "globe": round(self.globe, 1),
            "natural_wet_bulb": round(self.natural_wet_bulb, 1),
            "wet_bulb": round(self.psychrometric_wet_bulb, 1),
            "wind_2m": round(self.wind_2m, 2),
        }


def outdoor_wbgt(
    t_air_c: float,
    rh_pct: float,
    wind_ms: float,
    solar_wm2: float,
    pressure_hpa: float,
    cza: float,
    distance_au: float = 1.0,
    direct_wm2: float | None = None,
    wind_height_m: float = 10.0,
    urban: bool = True,
    shaded: bool = False,
) -> WbgtResult:
    """WBGT for a worker outdoors. `shaded=True` models work under a roof (no direct or diffuse sun)."""
    tk = t_air_c + 273.15
    rh = max(min(rh_pct, 100.0), 0.5) / 100.0
    solar = max(solar_wm2, 0.0)
    if cza < CZA_MIN:
        solar = 0.0
    else:
        toa = SOLAR_CONST * cza / (distance_au * distance_au)
        solar = min(solar, toa)
    if shaded:
        solar = 0.0

    if solar <= 0:
        fdir = 0.0
    elif direct_wm2 is not None:
        fdir = max(0.0, min(direct_wm2 / solar, 0.9))
    else:
        fdir = direct_fraction(solar, cza, distance_au)

    speed = wind_ms
    if wind_height_m != REF_HEIGHT:
        stab = stability_class(cza > 0, wind_ms, solar)
        speed = wind_at_2m(wind_ms, wind_height_m, stab, urban)

    tg = globe_temperature(tk, rh, pressure_hpa, speed, solar, fdir, cza)
    tnwb = wet_bulb(tk, rh, pressure_hpa, speed, solar, fdir, cza, radiative=True)
    tpsy = wet_bulb(tk, rh, pressure_hpa, speed, solar, fdir, cza, radiative=False)
    return WbgtResult(0.1 * t_air_c + 0.2 * tg + 0.7 * tnwb, tg, tnwb, tpsy, speed)
