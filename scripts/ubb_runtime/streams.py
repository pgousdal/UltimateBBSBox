"""Raw PTY and TCP byte streams compatible with M4."""
from __future__ import annotations

import contextlib
import errno
import os
import socket
import struct
import termios
import threading

from .errors import RuntimeStreamError


class PTYStream:
    def __init__(self, fd: int):
        self.fd = fd
        self._closed = False
        self._lock = threading.Lock()

    def read(self, size=65536):
        try:
            return os.read(self.fd, size)
        except OSError as exc:
            if exc.errno in (errno.EIO, errno.EBADF):
                return b""
            raise

    def write(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("PTY writes require bytes")
        return os.write(self.fd, data)

    def resize(self, width: int, height: int):
        if width < 1 or height < 1:
            raise ValueError("PTY dimensions must be positive")
        import fcntl
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", height, width, 0, 0))

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            with contextlib.suppress(OSError):
                os.close(self.fd)


class TCPStream:
    def __init__(self, sock):
        self.socket = sock
        self._closed = False
        self._lock = threading.Lock()

    @classmethod
    def connect(cls, host, port, timeout):
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.settimeout(None)
            return cls(sock)
        except OSError as exc:
            raise RuntimeStreamError(f"runtime TCP stream connection failed: {exc}") from exc

    def read(self, size=65536): return self.socket.recv(size)
    def write(self, data): self.socket.sendall(data); return len(data)
    def close(self):
        with self._lock:
            if self._closed: return
            self._closed = True
            with contextlib.suppress(OSError): self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()


class PipeStream:
    def __init__(self, read_fd, write_fd):
        self.read_fd = read_fd; self.write_fd = write_fd
        self._closed = False; self._lock = threading.Lock()

    def read(self, size=65536): return os.read(self.read_fd, size)
    def write(self, data): return os.write(self.write_fd, data)
    def close(self):
        with self._lock:
            if self._closed: return
            self._closed = True
            for fd in (self.read_fd, self.write_fd):
                with contextlib.suppress(OSError): os.close(fd)
