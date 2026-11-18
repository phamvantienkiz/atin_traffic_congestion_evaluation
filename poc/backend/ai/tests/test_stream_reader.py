"""Unit tests for StreamReader FFmpeg binary resolution and command construction."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from ai.ingestion.stream_reader import StreamReader, _resolve_ffmpeg_bin


def test_resolve_ffmpeg_bin_prefers_venv_dir(tmp_path: Path) -> None:
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake_python = venv_bin / "python"
    fake_python.write_text("", encoding="utf-8")
    expected_ffmpeg = str(venv_bin / "ffmpeg")

    def fake_which(cmd: str, path: str | None = None) -> str | None:
        if cmd == "ffmpeg" and path == str(venv_bin):
            return expected_ffmpeg
        return "/usr/bin/ffmpeg"

    with patch.object(sys, "executable", str(fake_python)), patch("shutil.which", side_effect=fake_which):
        assert _resolve_ffmpeg_bin() == expected_ffmpeg


def test_resolve_ffmpeg_bin_falls_back_to_system_path(tmp_path: Path) -> None:
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    fake_python = venv_bin / "python"

    def fake_which(cmd: str, path: str | None = None) -> str | None:
        if cmd == "ffmpeg" and path is None:
            return "/usr/bin/ffmpeg"
        return None

    with patch.object(sys, "executable", str(fake_python)), patch("shutil.which", side_effect=fake_which):
        assert _resolve_ffmpeg_bin() == "/usr/bin/ffmpeg"


def test_build_ffmpeg_cmd_modes() -> None:
    reader = StreamReader("cam1", "rtsp://example/stream", w=1280, h=720)

    cuvid_cmd = reader._build_ffmpeg_cmd("h264_cuvid", "/venv/bin/ffmpeg")
    assert cuvid_cmd[0] == "/venv/bin/ffmpeg"
    assert "-hwaccel" in cuvid_cmd and "cuda" in cuvid_cmd
    assert "-c:v" in cuvid_cmd and "h264_cuvid" in cuvid_cmd
    assert "-resize" in cuvid_cmd and "1280x720" in cuvid_cmd

    hwaccel_cmd = reader._build_ffmpeg_cmd("cuda_hwaccel", "/venv/bin/ffmpeg")
    assert hwaccel_cmd[0] == "/venv/bin/ffmpeg"
    assert "-hwaccel" in hwaccel_cmd and "cuda" in hwaccel_cmd
    assert "-c:v" not in hwaccel_cmd
    assert "-vf" in hwaccel_cmd and "scale=1280:720:flags=fast_bilinear" in hwaccel_cmd
    assert hwaccel_cmd[hwaccel_cmd.index("-probesize") + 1] == "1000000"

    cpu_cmd = reader._build_ffmpeg_cmd("ffmpeg_cpu", "/usr/bin/ffmpeg")
    assert cpu_cmd[0] == "/usr/bin/ffmpeg"
    assert "-hwaccel" not in cpu_cmd
    assert "-c:v" not in cpu_cmd
    assert "-vf" in cpu_cmd
