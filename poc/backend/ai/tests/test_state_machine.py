"""Unit tests for ai.decision.state_machine (V2 event lifecycle)."""

from __future__ import annotations

from ai.config import AIConfig
from ai.decision.state_machine import EventTrigger, StateMachine


def test_lifecycle_3m_5m_15m_and_recover() -> None:
    cfg = AIConfig(
        confirm_state_s=180.0,
        followup_after_confirm_s=120.0,
        periodic_reminder_s=900.0,
        exit_clear_s=15.0,
    )
    sm = StateMachine(cfg, has_traffic_light=False)

    emitted: list[tuple[int, EventTrigger]] = []
    # Continuous CONGESTED from t=0 to t=2110s
    for t in range(0, 2110):
        _, ev = sm.update("CONGESTED", float(t), stream_ok=True, occ="NONE")
        if ev is not None:
            emitted.append((t, ev))

    assert [(t, ev.state, ev.stage) for t, ev in emitted] == [
        (180, "CONGESTED", "CONFIRMED_3M"),
        (300, "CONGESTED", "FOLLOWUP_5M"),
        (1200, "CONGESTED", "PERIODIC_15M"),
        (2100, "CONGESTED", "PERIODIC_15M"),
    ]

    # Recover to CLEAR: display switches after exit_clear_s (15s), RECOVERED_CLEAR fires 180s after that
    rec: list[tuple[int, EventTrigger]] = []
    for t in range(2110, 2320):
        _, ev = sm.update("CLEAR", float(t), stream_ok=True, occ="NONE")
        if ev is not None:
            rec.append((t, ev))

    assert len(rec) == 1
    assert rec[0][1].state == "CLEAR"
    assert rec[0][1].stage == "RECOVERED_CLEAR"
    assert sm.confirmed_state == "CLEAR"


def test_traffic_light_cycle_no_false_event() -> None:
    cfg = AIConfig(red_light_hold_s=90.0, confirm_state_s=180.0, exit_clear_s=15.0)
    sm = StateMachine(cfg, has_traffic_light=True)

    events: list[EventTrigger] = []
    # 75s red light followed by 30s green light -> no event
    for t in range(0, 75):
        _, ev = sm.update("CONGESTED", float(t), stream_ok=True, occ="NONE")
        if ev:
            events.append(ev)
    for t in range(75, 105):
        _, ev = sm.update("CLEAR", float(t), stream_ok=True, occ="NONE")
        if ev:
            events.append(ev)

    assert events == []
    assert sm.display_state == "CLEAR"
    assert sm.confirmed_state == "CLEAR"


def test_transition_congested_to_gridlocked_fires_immediately_after_3m() -> None:
    cfg = AIConfig(
        confirm_state_s=180.0,
        followup_after_confirm_s=120.0,
        periodic_reminder_s=900.0,
    )
    sm = StateMachine(cfg, has_traffic_light=False)

    events: list[tuple[int, EventTrigger]] = []
    for t in range(0, 185):
        _, ev = sm.update("CONGESTED", float(t), stream_ok=True, occ="NONE")
        if ev:
            events.append((t, ev))
    for t in range(185, 500):
        _, ev = sm.update("GRIDLOCKED", float(t), stream_ok=True, occ="NONE")
        if ev:
            events.append((t, ev))

    # Expect CONFIRMED_3M at 180s, then TRANSITION to GRIDLOCKED around 188+180=368s,
    # then FOLLOWUP_5M for GRIDLOCKED 120s later (~488s)
    stages = [(ev.state, ev.stage) for _, ev in events]
    assert stages == [
        ("CONGESTED", "CONFIRMED_3M"),
        ("GRIDLOCKED", "TRANSITION"),
        ("GRIDLOCKED", "FOLLOWUP_5M"),
    ]


def test_stream_offline_and_occlusion_hold() -> None:
    cfg = AIConfig()
    sm = StateMachine(cfg, has_traffic_light=False)

    for t in range(0, 6):
        sm.update("CONGESTED", float(t), stream_ok=True, occ="NONE")
    assert sm.display_state == "CONGESTED"

    # Occlusion hold keeps previous display state
    disp, ev = sm.update("CLEAR", 6.0, stream_ok=True, occ="HOLD")
    assert disp == "CONGESTED"
    assert ev is None

    # Stream offline returns UNKNOWN
    disp, ev = sm.update("CLEAR", 7.0, stream_ok=False, occ="NONE")
    assert disp == "UNKNOWN"
    assert ev is None
