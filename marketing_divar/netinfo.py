# -*- coding: utf-8 -*-
"""LAN listen addresses + public IP detection for quota reset on IP change."""

from __future__ import annotations

import socket
import time
from typing import List, Optional

from .brand import PORT


def get_public_ip(timeout: int = 8) -> Optional[str]:
    """گرفتن IP خارجی از چند سرویس — اگر اینترنت قطع باشد None."""
    # چند سرویس برای اطمینان
    services = [
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://icanhazip.com",
        "https://api.my-ip.io/ip",
    ]
    try:
        import urllib.request
        for url in services:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    ip = r.read().decode().strip()
                    # پاکسازی
                    ip = ip.split()[0] if ip else ""
                    # اعتبارسنجی ساده IPv4/IPv6
                    if ip and ("." in ip or ":" in ip) and len(ip) < 50:
                        return ip
            except Exception:
                continue
    except Exception:
        pass
    # fallback via socket trick — IP خصوصی را نمی‌دهد ولی لااقل تلاش
    return None


def get_current_ip_cached(cache_sec: int = 120) -> Optional[str]:
    """با کش کوتاه — هر 2 دقیقه یک بار IP واقعی را بگیر."""
    # از فایل temp کش بخوان
    import pathlib, json
    cache_path = pathlib.Path("data/last_public_ip.json")
    try:
        if cache_path.exists():
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            ts = float(data.get("ts") or 0)
            ip = data.get("ip") or ""
            if ip and (time.time() - ts) < cache_sec:
                return ip
    except Exception:
        pass
    ip = get_public_ip()
    if ip:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({"ip": ip, "ts": time.time()}, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return ip


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
