"""Pure 3-state traffic classifier fusing Option 1 and Option 2 metrics."""

from __future__ import annotations

from ai.config import AIConfig


def classify(m: dict[str, float | int | None], cfg: AIConfig) -> str:
    """Classify traffic state into CLEAR, CONGESTED, or GRIDLOCKED."""
    w = float(m["w_total"] or 0.0)
    o = float(m["o_vis"] or 0.0)
    v = float(m["v_flow"] or 0.0)
    t2 = m["t50_2w"]
    t4 = m["t50_4w"]
    d2 = m["d85_2w"]
    d4 = m["d85_4w"]
    n_2w = int(m["n_2w"] or 0)
    n_4w = int(m["n_4w"] or 0)

    def gt(x: float | int | None, th: float) -> bool:
        return x is not None and float(x) > th

    # 1. Empty / low-density road
    if w < cfg.w_clear and o < cfg.o_clear:
        return "CLEAR"

    # 2. GRIDLOCKED
    dense_g = w >= cfg.w_gridlock or o >= cfg.o_gridlock
    stall_4w = gt(t4, cfg.gridlock_t50_4w_s) or gt(d4, cfg.gridlock_d85_4w_s)
    stall_2w = gt(t2, cfg.gridlock_t50_2w_s) or gt(d2, cfg.gridlock_d85_2w_s)

    if n_4w < 2:
        time_ok = gt(t2, cfg.gridlock_t50_2w_only_s) or gt(d2, cfg.gridlock_d85_2w_only_s)
    else:
        time_ok = stall_4w and (stall_2w or n_2w == 0)

    macro_ok = v <= cfg.v_stall or o >= cfg.o_macro_stall
    if dense_g and time_ok and macro_ok:
        return "GRIDLOCKED"

    # Macro rescue when heavy occlusion breaks ByteTrack IDs
    if o >= cfg.o_rescue and v <= cfg.v_stall and w >= cfg.w_rescue:
        return "GRIDLOCKED"

    # 3. CONGESTED
    dense_c = w >= cfg.w_congested or o >= cfg.o_congested
    slow = (
        gt(t4, cfg.congested_t50_4w_s)
        or gt(d4, cfg.congested_d85_4w_s)
        or gt(t2, cfg.congested_t50_2w_s)
        or gt(d2, cfg.congested_d85_2w_s)
        or (cfg.v_stall < v < cfg.v_clear and o >= cfg.o_congested)
    )
    if dense_c and slow:
        return "CONGESTED"

    return "CLEAR"
