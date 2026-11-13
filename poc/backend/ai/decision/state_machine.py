"""Two-layer state machine: smoothed Provisional display + Confirmed events."""

from __future__ import annotations

from collections import Counter, deque

from ai.config import AIConfig

_SEVERITY = {"CLEAR": 0, "CONGESTED": 1, "GRIDLOCKED": 2}


class StateMachine:
    """Manages Live Provisional state (5s smoothing + exit hysteresis) and Confirmed events."""

    def __init__(self, cfg: AIConfig, has_traffic_light: bool = False) -> None:
        self.cfg = cfg
        self.has_traffic_light = has_traffic_light
        self._window: deque[tuple[float, str]] = deque()
        self.display_state: str = "CLEAR"
        self.confirmed_state: str = "CLEAR"

        self._clear_since: float | None = None
        self._level_since: dict[str, float | None] = {"CONGESTED": None, "GRIDLOCKED": None}
        self._level_drop_since: dict[str, float | None] = {"CONGESTED": None, "GRIDLOCKED": None}
        self._last_event_t: dict[str, float] = {"CONGESTED": -1e9, "GRIDLOCKED": -1e9}

    def update(
        self,
        raw: str,
        now: float,
        stream_ok: bool,
        occ: str,
    ) -> tuple[str, str | None]:
        """Update state machine and return (display_state, new_confirmed_event | None)."""
        if not stream_ok:
            return "UNKNOWN", None

        if occ == "UNKNOWN_HOLD":
            return "UNKNOWN", None

        if occ == "HOLD":
            hold_state = "CLEAR" if self.display_state == "UNKNOWN" else self.display_state
            return hold_state, None

        # 1. Provisional state with 5s majority smoothing (ties -> higher severity)
        self._window.append((now, raw))
        cutoff = now - self.cfg.smooth_window_s
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

        counts = Counter(st for _, st in self._window)
        mode_state = max(
            counts.keys(),
            key=lambda st: (counts[st], _SEVERITY.get(st, 0)),
        )

        # 2. Exit hysteresis: CONGESTED/GRIDLOCKED -> CLEAR requires sustained CLEAR
        prev_display = self.display_state
        if prev_display in ("CONGESTED", "GRIDLOCKED") and mode_state == "CLEAR":
            if self._clear_since is None:
                self._clear_since = now
            if (now - self._clear_since) >= self.cfg.exit_clear_s:
                self.display_state = "CLEAR"
                self._clear_since = None
            else:
                self.display_state = prev_display
        else:
            self._clear_since = None
            self.display_state = mode_state

        # 3. Confirmed event timers with persistence tolerance
        new_event: str | None = None

        # Track CONGESTED+ timer
        if self.display_state in ("CONGESTED", "GRIDLOCKED"):
            self._level_drop_since["CONGESTED"] = None
            if self._level_since["CONGESTED"] is None:
                self._level_since["CONGESTED"] = now
        else:
            if self._level_since["CONGESTED"] is not None:
                if self._level_drop_since["CONGESTED"] is None:
                    self._level_drop_since["CONGESTED"] = now
                elif (now - self._level_drop_since["CONGESTED"]) > self.cfg.persistence_tolerance_s:
                    self._level_since["CONGESTED"] = None
                    self._level_drop_since["CONGESTED"] = None

        # Track GRIDLOCKED timer
        if self.display_state == "GRIDLOCKED":
            self._level_drop_since["GRIDLOCKED"] = None
            if self._level_since["GRIDLOCKED"] is None:
                self._level_since["GRIDLOCKED"] = now
        else:
            if self._level_since["GRIDLOCKED"] is not None:
                if self._level_drop_since["GRIDLOCKED"] is None:
                    self._level_drop_since["GRIDLOCKED"] = now
                elif (now - self._level_drop_since["GRIDLOCKED"]) > self.cfg.persistence_tolerance_s:
                    self._level_since["GRIDLOCKED"] = None
                    self._level_drop_since["GRIDLOCKED"] = None

        # Check GRIDLOCKED confirmation first (can upgrade from CONGESTED immediately)
        g_since = self._level_since["GRIDLOCKED"]
        if g_since is not None and (now - g_since) >= self.cfg.confirm_gridlock_s:
            if (
                self.confirmed_state != "GRIDLOCKED"
                or (now - self._last_event_t["GRIDLOCKED"]) >= self.cfg.cooldown_s
            ):
                self.confirmed_state = "GRIDLOCKED"
                self._last_event_t["GRIDLOCKED"] = now
                new_event = "GRIDLOCKED"

        # Check CONGESTED confirmation
        if new_event is None:
            c_req = (
                self.cfg.confirm_congested_light_s
                if self.has_traffic_light
                else self.cfg.confirm_congested_s
            )
            c_since = self._level_since["CONGESTED"]
            if c_since is not None and (now - c_since) >= c_req and self.confirmed_state == "CLEAR":
                if (now - self._last_event_t["CONGESTED"]) >= self.cfg.cooldown_s:
                    self.confirmed_state = "CONGESTED"
                    self._last_event_t["CONGESTED"] = now
                    new_event = "CONGESTED"

        # Reset confirmed_state when display stably returns to CLEAR
        if self.display_state == "CLEAR":
            self.confirmed_state = "CLEAR"

        return self.display_state, new_event
