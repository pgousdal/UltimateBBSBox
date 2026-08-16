#!/usr/bin/env python3
"""Bounded, non-interactive FreeDOS/DOSEMU2 COM1 qualification harness."""
from __future__ import annotations

import argparse
import os
import re
import select
import subprocess
import termios
import time
from pathlib import Path
import pty

EXPECTED_RX = bytes.fromhex("41 42 43")
EXPECTED_TX = b"UBB-OK"


def raw_fd(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP |
                  termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON | termios.IXOFF)
    attrs[1] &= ~termios.OPOST
    attrs[2] &= ~(termios.CSIZE | termios.PARENB)
    attrs[2] |= termios.CS8
    attrs[3] &= ~(termios.ECHO | termios.ICANON | termios.ISIG | termios.IEXTEN)
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def read_exact(fd: int, size: int, deadline: float) -> bytes:
    data = bytearray()
    while len(data) < size and time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], max(0, deadline - time.monotonic()))
        if ready:
            data.extend(os.read(fd, size - len(data)))
    return bytes(data)


def parse_result(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if re.fullmatch(r"[A-Z0-9_]+", key):
                result[key] = value
    return result


def install_boot_files(drive_c: Path, serialtest: Path) -> None:
    (drive_c / "UBBQUAL").mkdir(parents=True, exist_ok=True)
    # The qualification binary is a tiny .COM image (NASM -f bin); retaining
    # the .COM suffix avoids DOS attempting to parse it as an MZ executable.
    (drive_c / "UBBQUAL" / "SERIALTEST.COM").write_bytes(serialtest.read_bytes())
    command = drive_c / "FREEDOS" / "BIN" / "COMMAND.COM"
    if not command.exists():
        raise RuntimeError("FreeDOS COMMAND.COM is missing from the disposable working tree")
    (drive_c / "COMMAND.COM").write_bytes(command.read_bytes())
    (drive_c / "FDCONFIG.SYS").write_text(
        "SHELL=\\COMMAND.COM /E:2048 /P=\\AUTOEXEC.BAT\n", encoding="ascii")
    (drive_c / "AUTOEXEC.BAT").write_text(
        "@echo off\r\nmd C:\\UBBQUAL > nul\r\n"
        "C:\\UBBQUAL\\SERIALTEST.COM EXCHANGE COM1\r\n", encoding="ascii")


def run(args: argparse.Namespace) -> int:
    drive_c = args.drive_c.resolve()
    install_boot_files(drive_c, args.serialtest.resolve())
    master, slave = pty.openpty()
    raw_fd(master)
    raw_fd(slave)
    slave_path = os.ttyname(slave)
    config = args.workdir / "dosemu-serial.conf"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        f'$_hdimage = "{drive_c}"\n'
        f'$_com1 = "{slave_path}"\n$_network = (off)\n', encoding="ascii")
    env = os.environ.copy()
    env.update({"HOME": str(args.home), "TERM": "xterm"})
    if args.library_path:
        env["LD_LIBRARY_PATH"] = args.library_path
    command = [str(args.dosemu), "-f", str(config)]
    process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result_path = drive_c / "UBBQUAL" / "SERIAL.RESULT"
    ready_path = drive_c / "UBBQUAL" / "SERIAL.READY"
    try:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline and not ready_path.exists():
            if process.poll() is not None:
                raise RuntimeError("DOSEMU2 exited before SERIAL.READY")
            time.sleep(0.05)
        if not ready_path.exists():
            raise RuntimeError("timeout waiting for guest SERIAL.READY")
        os.write(master, EXPECTED_RX)
        reply = read_exact(master, len(EXPECTED_TX), deadline)
        if reply != EXPECTED_TX:
            raise RuntimeError(f"guest reply mismatch: {reply.hex().upper()}")
        while time.monotonic() < deadline and not result_path.exists():
            time.sleep(0.05)
        if not result_path.exists():
            raise RuntimeError("guest result file was not produced")
        result = parse_result(result_path)
        if result.get("RESULT") != "PASS" or result.get("RX") != EXPECTED_RX.hex().upper():
            raise RuntimeError(f"guest reported failure: {result}")
        print("PASS")
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
        os.close(master)
        os.close(slave)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", nargs="?")
    parser.add_argument("--dosemu", type=Path, required=True)
    parser.add_argument("--drive-c", type=Path, required=True)
    parser.add_argument("--serialtest", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--workdir", type=Path, required=True)
    parser.add_argument("--library-path", default="")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
