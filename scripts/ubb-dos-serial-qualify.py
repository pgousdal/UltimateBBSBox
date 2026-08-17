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
MATRIX_BYTES = bytes.fromhex(
    "00 01 0A 0D 1B 20 41 7F 80 B3 C4 DA FF 1B 5B 33 31 6D 0D 0A B3 C4 DA"
)


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


def read_image_result(image: Path) -> dict[str, str]:
    """Read the mkfatimage16 partition through mtools after guest shutdown."""
    command = ["mtype", "-i", f"{image}@@8832", "::UBBQUAL/SERIAL.RST"]
    output = subprocess.check_output(command, text=True, env={**os.environ, "MTOOLS_SKIP_CHECK": "1"})
    result: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def print_exchange_evidence(host_tx: bytes, host_rx: bytes, result: dict[str, str]) -> None:
    """Emit byte-exact host observations alongside the guest result record."""
    print(f"HOST_TX_LENGTH={len(host_tx)}")
    print(f"HOST_TX_HEX={host_tx.hex().upper()}")
    print(f"HOST_RX_LENGTH={len(host_rx)}")
    print(f"HOST_RX_HEX={host_rx.hex().upper()}")
    for key in ("MODE", "RX", "TX", "RX_STATUS", "TX_STATUS", "RESULT"):
        if key in result:
            print(f"GUEST_{key}={result[key]}")


def install_boot_files(drive_c: Path, serialtest: Path, mode: str = "EXCHANGE", image: bool = False) -> None:
    (drive_c / "UBBQUAL").mkdir(parents=True, exist_ok=True)
    (drive_c / "UBBQUAL" / "UBBTEST.COM").write_bytes(serialtest.read_bytes())
    def replace_text(path: Path, content: str) -> None:
        # Preserved materialized files may be read-only; replacing within the
        # disposable directory is safe and avoids mutating the source tree.
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        path.write_text(content, encoding="ascii")

    command = drive_c / "FREEDOS" / "BIN" / "COMMAND.COM"
    if not command.exists():
        raise RuntimeError("FreeDOS COMMAND.COM is missing from the disposable working tree")
    root_command = drive_c / "COMMAND.COM"
    if not root_command.exists():
        root_command.write_bytes(command.read_bytes())
    replace_text(drive_c / "FDCONFIG.SYS",
        "SHELL=\\COMMAND.COM /E:2048 /P=\\AUTOEXEC.BAT\n")
    if image:
        autoexec = "@echo off\r\nmd D:\\UBBQUAL\r\n"
        autoexec += "copy C:\\UBBQUAL\\UBBTEST.COM D:\\UBBQUAL\\UBBTEST.COM > nul\r\n"
        autoexec += f"D:\\UBBQUAL\\UBBTEST.COM {mode}\r\n"
    else:
        autoexec = "@echo off\r\n" + f"C:\\UBBQUAL\\UBBTEST.COM {mode}\r\n"
    replace_text(drive_c / "AUTOEXEC.BAT", autoexec)


def run(args: argparse.Namespace) -> int:
    drive_c = args.drive_c.resolve()
    install_boot_files(drive_c, args.serialtest.resolve(), args.mode, bool(args.image))
    master, slave = pty.openpty()
    raw_fd(master)
    raw_fd(slave)
    slave_path = os.ttyname(slave)
    config = args.workdir / "dosemu-serial.conf"
    config.parent.mkdir(parents=True, exist_ok=True)
    image_spec = str(args.image) if args.image else ""
    hdimage = f'"{drive_c} {image_spec}"' if args.image else f'"{drive_c}"'
    config.write_text(
        f'$_hdimage = {hdimage}\n'
        f'$_com1 = "{slave_path}"\n$_network = (off)\n', encoding="ascii")
    env = os.environ.copy()
    env.update({"HOME": str(args.home), "TERM": "xterm"})
    if args.library_path:
        env["LD_LIBRARY_PATH"] = args.library_path
    command = [str(args.dosemu), "-f", str(config)]
    process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    result_path = drive_c / "UBBQUAL" / "SERIAL.RST"
    ready_path = drive_c / "UBBQUAL" / "READY.RST"
    try:
        deadline = time.monotonic() + args.timeout
        boot_seen = False
        boot_time = 0.0
        while time.monotonic() < deadline and not ready_path.exists():
            if process.poll() is not None:
                raise RuntimeError("DOSEMU2 exited before SERIAL.READY")
            if process.stdout is not None:
                ready, _, _ = select.select([process.stdout], [], [], 0.05)
                if ready:
                    text = os.read(process.stdout.fileno(), 4096).decode("ascii", "ignore")
                    if "FreeDOS kernel" in text:
                        boot_seen = True
                        boot_time = time.monotonic()
            else:
                time.sleep(0.05)
            # Some DOSEMU host-directory mappings are read-only to DOS.  The
            # banner is a bounded fallback readiness signal so COM diagnosis
            # can still proceed; result-file persistence remains independently
            # required and is reported if absent.
            if boot_seen and time.monotonic() - boot_time >= 1:
                break
        if not ready_path.exists() and not boot_seen:
            raise RuntimeError("timeout waiting for guest SERIAL.READY")
        if args.mode == "SELFTEST":
            while time.monotonic() < deadline and not result_path.exists():
                time.sleep(0.05)
            if args.image and not result_path.exists():
                # The FAT image is guest-owned until the process has stopped.
                # Stop the disposable guest, then inspect it with mtools.
                process.terminate()
                process.wait(timeout=3)
                result = read_image_result(args.image)
                if result.get("RESULT") == "PASS" and result.get("MODE") == "SELFTEST":
                    print("PASS")
                    return 0
            if not result_path.exists():
                raise RuntimeError("SELFTEST result file was not produced")
            result = parse_result(result_path)
            if result.get("RESULT") != "PASS" or result.get("MODE") != "SELFTEST":
                raise RuntimeError(f"SELFTEST reported failure: {result}")
            print("PASS")
            return 0
        if args.mode == "MATRIX":
            host_tx = MATRIX_BYTES
            os.write(master, host_tx)
            reply = read_exact(master, len(MATRIX_BYTES), deadline)
            if reply != MATRIX_BYTES:
                raise RuntimeError(f"matrix reply mismatch: {reply.hex().upper()}")
        else:
            host_tx = EXPECTED_RX
            os.write(master, host_tx)
            reply = read_exact(master, len(EXPECTED_TX), deadline)
            if reply != EXPECTED_TX:
                raise RuntimeError(f"guest reply mismatch: {reply.hex().upper()}")
        if args.image:
            # The guest sends its final byte immediately before writing the
            # result record. Give that DOS-local FAT write a bounded moment to
            # complete before stopping DOSEMU2 for offline mtools inspection.
            time.sleep(0.25)
            process.terminate()
            process.wait(timeout=3)
            result = read_image_result(args.image)
            expected = MATRIX_BYTES.hex().upper() if args.mode == "MATRIX" else EXPECTED_RX.hex().upper()
            expected_tx = (MATRIX_BYTES if args.mode == "MATRIX" else EXPECTED_TX).hex().upper()
            if (result.get("RESULT") == "PASS" and result.get("RX") == expected
                    and result.get("TX") == expected_tx):
                print_exchange_evidence(host_tx, reply, result)
                print("PASS")
                return 0
        while time.monotonic() < deadline and not result_path.exists():
            time.sleep(0.05)
        if not result_path.exists():
            raise RuntimeError("guest result file was not produced")
        result = parse_result(result_path)
        expected = MATRIX_BYTES.hex().upper() if args.mode == "MATRIX" else EXPECTED_RX.hex().upper()
        expected_tx = (MATRIX_BYTES if args.mode == "MATRIX" else EXPECTED_TX).hex().upper()
        if (result.get("RESULT") != "PASS" or result.get("RX") != expected
                or result.get("TX") != expected_tx):
            raise RuntimeError(f"guest reported failure: {result}")
        print_exchange_evidence(host_tx, reply, result)
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
    parser.add_argument("--mode", choices=("SELFTEST", "EXCHANGE", "MATRIX"), default="EXCHANGE")
    parser.add_argument("--image", type=Path, default=None)
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
