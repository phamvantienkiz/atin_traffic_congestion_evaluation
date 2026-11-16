"""Two-layer state machine V2: smoothed display + 3m/5m/15m event lifecycle."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass

from ai.config import AIConfig

_SEVERITY = {"CLEAR": 0, "CONGESTED": 1, "GRIDLOCKED": 2}


@dataclass(frozen=True)
class EventTrigger:
    """Event emitted by StateMachine when a state is confirmed, reminded, or transitioned."""

    state: str
    stage: str  # CONFIRMED_3M | FOLLOWUP_5M | PERIODIC_15M | TRANSITION | RECOVERED_CLEAR
    duration_s: float


class StateMachine:
    """Manages Live Provisional state (5s smoothing + exit hysteresis) and V2 Event Lifecycle."""

    def __init__(self, cfg: AIConfig, has_traffic_light: bool = False) -> None:
        self.cfg = cfg
        self.has_traffic_light = has_traffic_light
        self._window: deque[tuple[float, str]] = deque()
        self.display_state: str = "CLEAR"
        self.confirmed_state: str = "CLEAR"

        self._clear_since: float | None = None
        self._confirmed_since: float | None = None
        self._next_reminder_at: float | None = None
        self._followup_sent: bool = False

        self._candidate_state: str | None = None
        self._candidate_since: float | None = None
        self._candidate_drop_since: float | None = None

    def _clear_candidate(self) -> None:
        self._candidate_state = None
        self._candidate_since = None
        self._candidate_drop_since = None

    def update(
        self,
        raw: str,
        now: float,
        stream_ok: bool,
        occ: str,
    ) -> tuple[str, EventTrigger | None]:
        """Update state machine and return (display_state, EventTrigger | None)."""
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

        # 3. Track candidate state differing from confirmed_state (with tolerance)
        if self.display_state != self.confirmed_state:
            self._candidate_drop_since = None
            if self._candidate_state != self.display_state:
                self._candidate_state = self.display_state
                self._candidate_since = now
        else:
            if self._candidate_state is not None:
                if self._candidate_drop_since is None:
                    self._candidate_drop_since = now
                elif (now - self._candidate_drop_since) > self.cfg.persistence_tolerance_s:
                    self._clear_candidate()

        # 4. Check confirmation / transition (3m = 180s; includes 90s red-light hold)
        if self._candidate_state is not None and self._candidate_since is not None:
            req_s = self.cfg.confirm_state_s
            if self.confirmed_state == "CLEAR" and self.has_traffic_light:
                req_s = max(req_s, self.cfg.red_light_hold_s)

            if (now - self._candidate_since) >= req_s:
                target = self._candidate_state
                if target == "CLEAR":
                    dur = (now - self._confirmed_since) if self._confirmed_since is not None else req_s
                    self.confirmed_state = "CLEAR"
                    self._confirmed_since = None
                    self._next_reminder_at = None
                    self._followup_sent = False
                    self._clear_candidate()
                    return self.display_state, EventTrigger(
                        state="CLEAR",
                        stage="RECOVERED_CLEAR",
                        duration_s=dur,
                    )

                stage = "CONFIRMED_3M" if self.confirmed_state == "CLEAR" else "TRANSITION"
                self.confirmed_state = target
                self._confirmed_since = self._candidate_since
                self._next_reminder_at = (
                    self._confirmed_since
                    + self.cfg.confirm_state_s
                    + self.cfg.followup_after_confirm_s
                )
                self._followup_sent = False
                self._clear_candidate()
                return self.display_state, EventTrigger(
                    state=self.confirmed_state,
                    stage=stage,
                    duration_s=now - self._confirmed_since,
                )

        # 5. Periodic reminders when confirmed CONGESTED / GRIDLOCKED persists
        if (
            self.confirmed_state in ("CONGESTED", "GRIDLOCKED")
            and self.display_state == self.confirmed_state
            and self._next_reminder_at is not None
            and now >= self._next_reminder_at
        ):
            stage = "PERIODIC_15M" if self._followup_sent else "FOLLOWUP_5M"
            self._followup_sent = True
            self._next_reminder_at += self.cfg.periodic_reminder_s
            dur = (now - self._confirmed_since) if self._confirmed_since is not None else 0.0
            return self.display_state, EventTrigger(
                state=self.confirmed_state,
                stage=stage,
                duration_s=dur,
            )

        return self.display_state, None
