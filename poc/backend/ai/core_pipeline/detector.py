"""Batch YOLO detector supporting .pt, .onnx, and .engine models."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO

from ai.config import AIConfig

logger = logging.getLogger(__name__)


@dataclass
class Det:
    """Detections in 1280x720 frame coordinates."""

    xyxy: np.ndarray  # (N, 4) float32
    conf: np.ndarray  # (N,) float32
    cls_name: list[str]

    @classmethod
    def empty(cls) -> Det:
        return cls(
            xyxy=np.zeros((0, 4), dtype=np.float32),
            conf=np.zeros((0,), dtype=np.float32),
            cls_name=[],
        )


class Detector:
    """Wrapper around Ultralytics YOLO for batched ROI inference."""

    def __init__(self, cfg: AIConfig) -> None:
        self.cfg = cfg
        self.model = YOLO(cfg.model_path)
        self.half = cfg.device.startswith("cuda") and cfg.model_path.endswith(".pt")
        self.names: dict[int, str] = dict(self.model.names)

        # Validate that model classes map to both 2W and 4W groups
        mapped_groups = {
            cfg.class_groups[name]
            for name in self.names.values()
            if name in cfg.class_groups
        }
        if "2W" not in mapped_groups or "4W" not in mapped_groups:
            raise RuntimeError(
                f"Model classes {self.names} do not cover both 2W and 4W in class_groups"
            )

        # Warmup pass
        dummy = np.zeros((cfg.imgsz, cfg.imgsz, 3), dtype=np.uint8)
        self.model.predict(
            [dummy],
            imgsz=cfg.imgsz,
            conf=cfg.conf,
            iou=cfg.iou,
            half=self.half,
            device=cfg.device,
            verbose=False,
        )
        logger.info("Detector ready: model=%s device=%s half=%s", cfg.model_path, cfg.device, self.half)

    def detect_batch(
        self,
        crops: list[np.ndarray],
        offsets: list[tuple[int, int]],
    ) -> list[Det]:
        """Run single batched inference on ROI crops and shift boxes back to 1280x720."""
        if not crops:
            return []

        results = self.model.predict(
            crops,
            imgsz=self.cfg.imgsz,
            conf=self.cfg.conf,
            iou=self.cfg.iou,
            half=self.half,
            device=self.cfg.device,
            verbose=False,
        )

        out: list[Det] = []
        for res, (ox, oy) in zip(results, offsets):
            boxes = res.boxes
            if boxes is None or len(boxes) == 0:
                out.append(Det.empty())
                continue

            xyxy_raw = boxes.xyxy.cpu().numpy().astype(np.float32)
            conf_raw = boxes.conf.cpu().numpy().astype(np.float32)
            cls_ids = boxes.cls.cpu().numpy().astype(int)

            keep_idx: list[int] = []
            cls_names: list[str] = []
            for i, cid in enumerate(cls_ids):
                name = self.names.get(int(cid), "")
                if name in self.cfg.class_groups:
                    keep_idx.append(i)
                    cls_names.append(name)

            if not keep_idx:
                out.append(Det.empty())
                continue

            xyxy = xyxy_raw[keep_idx].copy()
            xyxy[:, [0, 2]] += float(ox)
            xyxy[:, [1, 3]] += float(oy)
            conf = conf_raw[keep_idx]
            out.append(Det(xyxy=xyxy, conf=conf, cls_name=cls_names))

        return out
