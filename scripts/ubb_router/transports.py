"""Minimal bidirectional byte streams and endpoint connectors."""
from __future__ import annotations

import collections
import contextlib
import socket
import threading
from typing import Protocol

from .errors import TransportError, UnsupportedTransportError


class ByteStream(Protocol):
    def read(self, size: int = 65536) -> bytes: ...
    def write(self, data: bytes) -> int: ...
    def close(self) -> None: ...


class Connector(Protocol):
    def connect(self, endpoint: dict, timeout: float) -> ByteStream: ...


class SocketStream:
    def __init__(self, sock: socket.socket):
        self.socket = sock
        self._closed = False
        self._close_lock = threading.Lock()

    def read(self, size=65536):
        return self.socket.recv(size)

    def write(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("stream writes require bytes")
        self.socket.sendall(data)
        return len(data)

    def close(self):
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            with contextlib.suppress(OSError):
                self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()


class TCPConnector:
    def connect(self, endpoint, timeout):
        try:
            sock = socket.create_connection((endpoint["host"], endpoint["port"]), timeout=timeout)
            sock.settimeout(None)
            return SocketStream(sock)
        except (OSError, ValueError) as exc:
            raise TransportError(f"TCP connection failed: {exc}") from exc


class MemoryStream:
    """Thread-safe fake raw stream with explicit inbound EOF."""
    def __init__(self, incoming=()):
        self._incoming = collections.deque(incoming)
        self.written = bytearray()
        self.closed = False
        self._lock = threading.Lock()

    def read(self, size=65536):
        with self._lock:
            if self.closed or not self._incoming:
                return b""
            value = self._incoming.popleft()
            if len(value) > size:
                self._incoming.appendleft(value[size:])
                return value[:size]
            return value

    def write(self, data):
        with self._lock:
            if self.closed:
                raise OSError("stream is closed")
            self.written.extend(data)
            return len(data)

    def close(self):
        with self._lock:
            self.closed = True


class MemoryConnector:
    def __init__(self, stream=None, error=None):
        self.stream = stream or MemoryStream()
        self.error = error
        self.calls = 0

    def connect(self, endpoint, timeout):
        self.calls += 1
        if self.error:
            raise self.error
        return self.stream


class UnsupportedConnector:
    def __init__(self, endpoint_type):
        self.endpoint_type = endpoint_type

    def connect(self, endpoint, timeout):
        raise UnsupportedTransportError(f"transport {self.endpoint_type!r} is declared but not implemented in M4")
