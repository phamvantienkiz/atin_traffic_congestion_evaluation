#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RECORD_DIR="${RECORD_DIR:-${POC_DIR}/records}"
MEDIAMTX_BIN="${POC_DIR}/mediamtx/mediamtx"
MEDIAMTX_CFG="${SCRIPT_DIR}/mediamtx_fake.yml"
RTSP_PORT="${FAKE_RTSP_PORT:-28555}"

PDG_FILE="${RECORD_DIR}/8phandinhgiot_clip.mp4"
HVT_FILE_1="${RECORD_DIR}/tram-xe-buyt-247-duong-hoang-van-thu_clip.mp4"
HVT_FILE_2="${RECORD_DIR}/tram-xe-buyt-247-duong-hoang-van-thu_clip_2.mp4"

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[ERROR] ffmpeg is not installed. Install with: sudo apt-get update && sudo apt-get install -y ffmpeg"
    exit 1
fi

if [[ ! -x "${MEDIAMTX_BIN}" ]]; then
    echo "[ERROR] MediaMTX binary not found or not executable at: ${MEDIAMTX_BIN}"
    exit 1
fi

if [[ ! -f "${PDG_FILE}" && ! -f "${HVT_FILE_1}" && ! -f "${HVT_FILE_2}" ]]; then
    echo "[ERROR] No record MP4 files found in: ${RECORD_DIR}"
    echo "Expected files:"
    echo "  - 8phandinhgiot_clip.mp4"
    echo "  - tram-xe-buyt-247-duong-hoang-van-thu_clip.mp4"
    echo "  - tram-xe-buyt-247-duong-hoang-van-thu_clip_2.mp4"
    exit 1
fi

PIDS=()
CONCAT_LIST=""

cleanup() {
    echo ""
    echo "[fake_rtsp] Stopping all streams and MediaMTX..."
    for pid in "${PIDS[@]:-}"; do
        kill "${pid}" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    if [[ -n "${CONCAT_LIST}" && -f "${CONCAT_LIST}" ]]; then
        rm -f "${CONCAT_LIST}"
    fi
}
trap cleanup EXIT INT TERM

echo "[fake_rtsp] Starting fake MediaMTX on :${RTSP_PORT}..."
"${MEDIAMTX_BIN}" "${MEDIAMTX_CFG}" &
PIDS+=($!)
sleep 1.5

if [[ -f "${PDG_FILE}" ]]; then
    echo "[fake_rtsp] Publishing PDG -> rtsp://127.0.0.1:${RTSP_PORT}/pdg"
    ffmpeg -hide_banner -loglevel warning \
        -re -stream_loop -1 -i "${PDG_FILE}" \
        -c:v copy -an -f rtsp -rtsp_transport tcp \
        "rtsp://127.0.0.1:${RTSP_PORT}/pdg" &
    PIDS+=($!)
else
    echo "[WARN] Missing ${PDG_FILE}, skipping /pdg"
fi

if [[ -f "${HVT_FILE_1}" && -f "${HVT_FILE_2}" ]]; then
    CONCAT_LIST="/tmp/hvt_concat_$$.txt"
    printf "file '%s'\nfile '%s'\n" "${HVT_FILE_1}" "${HVT_FILE_2}" > "${CONCAT_LIST}"
    echo "[fake_rtsp] Publishing HVT (clip 1 + clip 2) -> rtsp://127.0.0.1:${RTSP_PORT}/hvt"
    ffmpeg -hide_banner -loglevel warning \
        -re -stream_loop -1 -f concat -safe 0 -i "${CONCAT_LIST}" \
        -c:v copy -an -f rtsp -rtsp_transport tcp \
        "rtsp://127.0.0.1:${RTSP_PORT}/hvt" &
    PIDS+=($!)
elif [[ -f "${HVT_FILE_1}" ]]; then
    echo "[fake_rtsp] Publishing HVT (clip 1) -> rtsp://127.0.0.1:${RTSP_PORT}/hvt"
    ffmpeg -hide_banner -loglevel warning \
        -re -stream_loop -1 -i "${HVT_FILE_1}" \
        -c:v copy -an -f rtsp -rtsp_transport tcp \
        "rtsp://127.0.0.1:${RTSP_PORT}/hvt" &
    PIDS+=($!)
elif [[ -f "${HVT_FILE_2}" ]]; then
    echo "[fake_rtsp] Publishing HVT (clip 2) -> rtsp://127.0.0.1:${RTSP_PORT}/hvt"
    ffmpeg -hide_banner -loglevel warning \
        -re -stream_loop -1 -i "${HVT_FILE_2}" \
        -c:v copy -an -f rtsp -rtsp_transport tcp \
        "rtsp://127.0.0.1:${RTSP_PORT}/hvt" &
    PIDS+=($!)
else
    echo "[WARN] Missing HVT video files, skipping /hvt"
fi

echo "[fake_rtsp] Streams are live. Press Ctrl+C to stop."
wait
