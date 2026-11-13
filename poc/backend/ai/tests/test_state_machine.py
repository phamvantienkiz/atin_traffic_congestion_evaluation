"""Unit tests for ai.decision.state_machine."""

from __future__ import annotations

from ai.config import AIConfig
from ai.decision.state_machine import StateMachine


def test_sustained_congested_emits_single_event() -> None:
    cfg = AIConfig(confirm_congested_s=60.0, cooldown_s=60.0)
    sm = StateMachine(cfg, has_traffic_light=False)

    events: list[str] = []
    for t in range(0, 71):
        _, ev = sm.update("CONGESTED", float(t), stream_ok=True, occ="NONE")
        if ev is not None:
            events.append(ev)

    assert events == ["CONGESTED"]


def test_traffic_light_cycle_no_false_event() -> None:
    cfg = AIConfig(confirm_congested_light_s=90.0, exit_clear_s=15.0)
    sm = StateMachine(cfg, has_traffic_light=True)

    events: list[str] = []
    # 50s CONGESTED (red light) followed by 30s CLEAR (green light)
    for t in range(0, 50):
        _, ev = sm.update("CONGESTED", float(t), stream_ok=True, occ="NONE")
        if ev:
            events.append(ev)
    for t in range(50, 80):
        _, ev = sm.update("CLEAR", float(t), stream_ok=True, occ="NONE")
        if ev:
            events.append(ev)

    assert events == []
    assert sm.display_state == "CLEAR"


def test_upgrade_congested_to_gridlocked_bypasses_cooldown() -> None:
    cfg = AIConfig(confirm_congested_s=20.0, confirm_gridlock_s=40.0, cooldown_s=60.0)
    sm = StateMachine(cfg, has_traffic_light=False)

    events: list[tuple[int, str]] = []
    for t in range(0, 25):
        _, ev = sm.update("CONGESTED", float(t), stream_ok=True, occ="NONE")
        if ev:
            events.append((t, ev))
    for t in range(25, 70):
        _, ev = sm.update("GRIDLOCKED", float(t), stream_ok=True, occ="NONE")
        if ev:
            events.append((t, ev))

    assert [e for _, e in events] == ["CONGESTED", "GRIDLOCKED"]


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
