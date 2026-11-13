"""Optional helper to export YOLO .pt model to dynamic ONNX."""

from __future__ import annotations

import argparse
from ultralytics import YOLO


def main() -> None:
    ap = argparse.ArgumentParser(description="Export YOLO .pt to dynamic FP32 ONNX.")
    ap.add_argument("--model", default="../../models/vehicle_n_best.pt")
    ap.add_argument("--imgsz", type=int, default=640)
    args = ap.parse_args()

    model = YOLO(args.model)
    out = model.export(
        format="onnx",
        dynamic=True,
        half=False,
        simplify=True,
        imgsz=args.imgsz,
    )
    print(f"Exported ONNX: {out}")


if __name__ == "__main__":
    main()
