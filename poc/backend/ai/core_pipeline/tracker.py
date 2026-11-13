"""Per-camera ByteTrack wrapper with confidence-weighted majority class voting."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
import supervision as sv

from ai.config import AIConfig
from ai.core_pipeline.detector import Det


@dataclass
class Track:
    """Tracked vehicle in 1280x720 coordinates with voted class and bottom-center foot."""

    tid: int
    xyxy: np.ndarray
    conf: float
    cls_name: str
    group: str
    foot: tuple[float, float]


class CameraTracker:
    """ByteTrack instance with Majority Class Voting across track lifetime."""

    def __init__(self, cfg: AIConfig, fps: float = 15.0) -> None:
        self.cfg = cfg
        self.bt = sv.ByteTrack(
            track_activation_threshold=cfg.track_activation_conf,
            lost_track_buffer=max(1, round(cfg.track_buffer_s * fps)),
            minimum_matching_threshold=cfg.match_thresh,
            frame_rate=max(1, round(fps)),
        )
        self._cls_to_id: dict[str, int] = {}
        self._id_to_cls: dict[int, str] = {}
        self._votes: dict[int, Counter[str]] = {}
        self._last_seen: dict[int, float] = {}

    def _get_cls_id(self, name: str) -> int:
        if name not in self._cls_to_id:
            cid = len(self._cls_to_id)
            self._cls_to_id[name] = cid
            self._id_to_cls[cid] = name
        return self._cls_to_id[name]

    def update(self, det: Det, now: float) -> list[Track]:
        """Update ByteTrack with detections and return active tracks."""
        if len(det.xyxy) == 0:
            sv_dets = sv.Detections.empty()
        else:
            class_ids = np.array([self._get_cls_id(n) for n in det.cls_name], dtype=int)
            sv_dets = sv.Detections(
                xyxy=det.xyxy,
                confidence=det.conf,
                class_id=class_ids,
            )

        tracked = self.bt.update_with_detections(sv_dets)
        tracks: list[Track] = []

        if tracked.tracker_id is not None and len(tracked) > 0:
            for i in range(len(tracked)):
                tid = int(tracked.tracker_id[i])
                xyxy = tracked.xyxy[i].astype(np.float32)
                conf = float(tracked.confidence[i]) if tracked.confidence is not None else 0.5
                cid = int(tracked.class_id[i]) if tracked.class_id is not None else 0
                raw_cls = self._id_to_cls.get(cid, "car")

                votes = self._votes.setdefault(tid, Counter())
                votes[raw_cls] += max(conf, 0.01)
                self._last_seen[tid] = now

                voted_cls = votes.most_common(1)[0][0]
                group = self.cfg.class_groups.get(voted_cls, "4W")
                foot = (float(xyxy[0] + xyxy[2]) * 0.5, float(xyxy[3]))

                tracks.append(
                    Track(
                        tid=tid,
                        xyxy=xyxy,
                        conf=conf,
                        cls_name=voted_cls,
                        group=group,
                        foot=foot,
                    )
                )

        # Prune stale vote histories (> 10s unseen)
        stale = [tid for tid, t_seen in self._last_seen.items() if now - t_seen > 10.0]
        for tid in stale:
            self._last_seen.pop(tid, None)
            self._votes.pop(tid, None)

        return tracks
