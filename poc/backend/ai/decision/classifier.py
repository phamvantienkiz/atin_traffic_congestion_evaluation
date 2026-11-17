"""Pure 3-state traffic classifier V2 fusing O_vis, Flow, and T50/D85 with confidence."""

from __future__ import annotations

from ai.config import AIConfig


def classify(m: dict[str, float | int | None], cfg: AIConfig) -> tuple[str, float]:
    """Classify traffic state into (CLEAR|CONGESTED|GRIDLOCKED, state_conf)."""
    w = float(m["w_total"] or 0.0)
    o = float(m["o_vis"] or 0.0)
    v = float(m["v_flow"] or 0.0)
    t2 = m["t50_2w"]
    t4 = m["t50_4w"]
    d2 = m["d85_2w"]
    d4 = m["d85_4w"]

    def gt(x: float | int | None, th: float) -> bool:
        return x is not None and float(x) > th

    has_time = any(x is not None for x in (t2, t4, d2, d4))
    has_vehicles = (w >= cfg.w_sanity_min) or has_time

    time_clear = has_time and all(
        x is None or float(x) <= th
        for x, th in (
            (t4, cfg.congested_t50_4w_s),
            (d4, cfg.congested_d85_4w_s),
            (t2, cfg.congested_t50_2w_s),
            (d2, cfg.congested_d85_2w_s),
        )
    )
    has_t50_congested = gt(t4, cfg.congested_t50_4w_s) or gt(t2, cfg.congested_t50_2w_s)
    has_d85_congested = (
        (t4 is None and gt(d4, cfg.congested_d85_4w_s))
        or (t2 is None and gt(d2, cfg.congested_d85_2w_s))
    )
    time_congested = has_t50_congested or (has_d85_congested and v <= cfg.v_gridlock_max)
    time_gridlock = (
        gt(t4, cfg.gridlock_t50_4w_s)
        or gt(d4, cfg.gridlock_d85_4w_s)
        or gt(t2, cfg.gridlock_t50_2w_s)
        or gt(d2, cfg.gridlock_d85_2w_s)
    )

    # 1. Empty / clear road or no real vehicles (blocks night rain headlight glare)
    if o < cfg.o_clear or not has_vehicles:
        conf = 0.85 + (0.10 if v > cfg.v_clear_min else 0.0)
        return "CLEAR", round(min(0.98, conf), 2)

    # 1b. High-flow override: dense traffic actively discharging is CLEAR, not congested
    if v > cfg.v_congested_max:
        conf = 0.84 + (0.12 if time_clear else 0.0)
        return "CLEAR", round(min(0.98, conf), 2)

    # 2. GRIDLOCKED: O_vis >= 85% and (Flow <= 15 with time_gridlock, or macro-only Flow <= 6)
    if o >= cfg.o_gridlock:
        if (time_gridlock and v <= cfg.v_gridlock_max) or (not has_time and v <= cfg.v_stall):
            conf = 0.75 + (0.13 if time_gridlock else 0.0) + (0.10 if w >= 24.0 else 0.0)
            return "GRIDLOCKED", round(min(0.98, conf), 2)

    # 3. CONGESTED: O_vis >= 70% and (Flow <= 25 with time_congested, or macro-only Flow <= 18)
    #    Also handle 40% <= O_vis < 70% when T50/D85 strongly indicate stall
    if o >= cfg.o_congested:
        if (time_congested and v <= cfg.v_congested_max) or (not has_time and v <= cfg.v_congested_macro):
            conf = 0.72 + (0.14 if time_congested else 0.0) + (0.10 if w >= 15.0 else 0.0)
            return "CONGESTED", round(min(0.98, conf), 2)
    elif time_gridlock and v <= cfg.v_gridlock_max:
        return "CONGESTED", 0.82

    # 4. CLEAR (busy road 40% <= O_vis < 70% moving smoothly, or high flow)
    conf = 0.75 + (0.12 if time_clear else 0.0) + (0.08 if v >= cfg.v_clear_min else 0.0)
    return "CLEAR", round(min(0.98, conf), 2)
