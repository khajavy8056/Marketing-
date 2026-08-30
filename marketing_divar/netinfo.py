# -*- coding: utf-8 -*-
"""LAN listen addresses so a phone on the same Wi-Fi can open the panel."""

from __future__ import annotations

import socket
from typing import List

from .brand import PORT


def lan_ipv4() -> List[str]:
    ips: List[str] = []
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.4)
        s.connect(("1.1.1.1", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127.") and ip not in ips:
            ips.insert(0, ip)
    except Exception:
        pass
    return ips


def listen_urls(port: int = PORT) -> dict:
    lan = [f"http://{ip}:{port}" for ip in lan_ipv4()]
    return {
        "port": port,
        "bind": "0.0.0.0",
        "local": f"http://127.0.0.1:{port}",
        "lan": lan,
    }
