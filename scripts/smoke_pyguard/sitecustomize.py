"""Outbound guard for the smoke run's Python processes (leadline/serve.py, scripts/seed_db.py).

scripts/smoke_app.py puts this folder on PYTHONPATH, so Python imports it at start-up. Any connection or DNS lookup
that is not for this machine is blocked (OSError) and written to $SMOKE_OUTBOUND_LOG, one line each, so the run can
prove nothing left the machine (no Cala, no Context.dev, no model API). Covers TCP connects and name lookups
(getaddrinfo, gethostbyname[_ex]); not raw UDP sends or direct `_socket` use, which nothing here makes.
"""
import os
import socket

_LOG = os.environ.get("SMOKE_OUTBOUND_LOG")
_LOCAL = {"127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1", "0.0.0.0", None, ""}


def _blocked(host, what):
    if _LOG:
        with open(_LOG, "a") as f:
            f.write(f"blocked {host} (python {what}, pid {os.getpid()})\n")
    raise OSError(f"smoke guard: outbound {what} to {host} blocked")


_connect, _connect_ex, _getaddrinfo = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
_by_name, _by_name_ex = socket.gethostbyname, socket.gethostbyname_ex


def _host(address):
    return address[0] if isinstance(address, tuple) else None  # a str address is a unix socket path


def connect(self, address):
    if _host(address) not in _LOCAL:
        _blocked(_host(address), "connect")
    return _connect(self, address)


def connect_ex(self, address):
    if _host(address) not in _LOCAL:
        _blocked(_host(address), "connect")
    return _connect_ex(self, address)


def getaddrinfo(host, *args, **kwargs):
    name = host.decode() if isinstance(host, bytes) else host
    if name not in _LOCAL:
        _blocked(name, "dns")
    return _getaddrinfo(host, *args, **kwargs)


def gethostbyname(host):
    if host not in _LOCAL:
        _blocked(host, "dns")
    return _by_name(host)


def gethostbyname_ex(host):
    if host not in _LOCAL:
        _blocked(host, "dns")
    return _by_name_ex(host)


socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo
socket.gethostbyname, socket.gethostbyname_ex = gethostbyname, gethostbyname_ex
