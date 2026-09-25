"""
Precision AI - Agent tool registry with permission levels.

  SAFE        read-only diagnostics, run automatically (DNS lookup, TCP/HTTP probe, ping,
              disk space, service status, client environment report)
  RESTRICTED  state-changing but low-risk, run only after the affected user authorises it
              (flush DNS cache, restart VPN client, clear app cache, password reset link)
  DANGEROUS   destructive or security-sensitive; never proposed automatically and executable
              only with administrator approval

There is deliberately NO tool that runs arbitrary shell commands, and the agent can only
invoke tools by registered name with schema-validated parameters. Anything else is blocked.
"""

import asyncio
import json
import platform
import re
import shutil
import socket
import sys
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable, Optional

import httpx

from app.core.config import get_settings

SAFE, RESTRICTED, DANGEROUS = "safe", "restricted", "dangerous"
HOST_RE = re.compile(r"^(?=.{1,253}$)([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$|^(\d{1,3}\.){3}\d{1,3}$")

ToolHandler = Callable[[dict], Awaitable[dict]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    permission: str
    label: str
    description: str
    handler: Optional[ToolHandler] = None  # None => executed through the action connector
    approver_role: Optional[str] = None     # requester | admin
    risk_note: str = ""
    params: tuple[str, ...] = ()


def _valid_host(host: str) -> str:
    host = (host or "").strip()
    if not HOST_RE.match(host):
        raise ValueError("invalid host")
    return host


# ---------------- SAFE diagnostic handlers ----------------
async def dns_lookup(params: dict) -> dict:
    host = _valid_host(params["host"])
    start = time.perf_counter()
    try:
        infos = await asyncio.wait_for(asyncio.to_thread(socket.getaddrinfo, host, None), timeout=4)
        addrs = sorted({i[4][0] for i in infos})[:4]
        return {"ok": True, "summary": f"{host} resolves to {', '.join(addrs)}",
                "addresses": addrs, "ms": round((time.perf_counter() - start) * 1000, 1)}
    except (socket.gaierror, asyncio.TimeoutError, OSError):
        return {"ok": False, "summary": f"{host} could not be resolved"}


async def tcp_check(params: dict) -> dict:
    host = _valid_host(params["host"])
    port = int(params["port"])
    if not 1 <= port <= 65535:
        raise ValueError("invalid port")
    start = time.perf_counter()
    try:
        _r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3)
        w.close()
        ms = round((time.perf_counter() - start) * 1000, 1)
        return {"ok": True, "summary": f"{host}:{port} reachable ({ms} ms)", "ms": ms}
    except (OSError, asyncio.TimeoutError):
        return {"ok": False, "summary": f"{host}:{port} unreachable"}


async def ping(params: dict) -> dict:
    host = _valid_host(params["host"])
    count_flag = "-n" if sys.platform.startswith("win") else "-c"
    try:
        # Fixed argv, no shell: the host is validated and cannot inject options or commands
        proc = await asyncio.create_subprocess_exec("ping", count_flag, "2", host,
                                                    stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
        ok = proc.returncode == 0
        m = re.search(r"(?:Average|avg)[^=]*=\s*([\d.]+)", out.decode(errors="ignore"))
        return {"ok": ok, "summary": f"ping {host}: {'reply' if ok else 'no reply'}"
                + (f", avg {m.group(1)} ms" if ok and m else "")}
    except (OSError, asyncio.TimeoutError):
        return {"ok": False, "summary": f"ping {host}: unavailable"}


async def http_health(params: dict) -> dict:
    url = params["url"]
    if url not in _catalog_urls():
        raise ValueError("URL is not in the service catalog")
    try:
        async with httpx.AsyncClient(timeout=4, follow_redirects=True) as client:
            r = await client.get(url)
        return {"ok": r.status_code < 500, "summary": f"{url} -> HTTP {r.status_code}", "status": r.status_code}
    except httpx.HTTPError as exc:
        return {"ok": False, "summary": f"{url} -> {type(exc).__name__}"}


async def disk_space(params: dict) -> dict:
    usage = shutil.disk_usage(Path(get_settings().FAISS_INDEX_DIR).anchor or "/")
    pct = round(usage.used / usage.total * 100, 1)
    return {"ok": pct < 90, "summary": f"helpdesk host disk {pct}% used ({usage.free // 2**30} GB free)"}


async def client_environment(params: dict) -> dict:
    env = params.get("client") or {}
    parts = [f"{k}: {v}" for k, v in env.items() if k in ("platform", "user_agent", "language", "timezone", "online")]
    return {"ok": True, "summary": "; ".join(parts)[:300] or "no client environment reported", "client": env}


async def service_status(params: dict) -> dict:
    svc = next((s for s in load_service_catalog() if s["name"] == params["service"]), None)
    if svc is None:
        raise ValueError("unknown service")
    if svc.get("type") == "http":
        res = await http_health({"url": svc["url"]})
    elif svc.get("type") == "dns":
        res = await dns_lookup({"host": svc["host"]})
    else:
        res = await tcp_check({"host": svc["host"], "port": svc["port"]})
    res["summary"] = f"{svc['label']}: {'UP' if res['ok'] else 'DOWN'} ({res['summary']})"
    return res


async def system_info(params: dict) -> dict:
    return {"ok": True, "summary": f"helpdesk host {platform.system()} {platform.release()}, "
                                   f"Python {platform.python_version()}"}


TOOLS: dict[str, ToolSpec] = {t.name: t for t in [
    ToolSpec("dns_lookup", SAFE, "DNS lookup", "Resolve a hostname", dns_lookup, params=("host",)),
    ToolSpec("tcp_check", SAFE, "Connectivity check", "Open a TCP connection to host:port", tcp_check,
             params=("host", "port")),
    ToolSpec("ping", SAFE, "Ping", "ICMP echo to a host", ping, params=("host",)),
    ToolSpec("http_health", SAFE, "HTTP health check", "GET a catalogued health URL", http_health, params=("url",)),
    ToolSpec("service_status", SAFE, "Service status", "Probe a catalogued service", service_status,
             params=("service",)),
    ToolSpec("disk_space", SAFE, "Disk space", "Disk usage of the helpdesk host", disk_space),
    ToolSpec("system_info", SAFE, "System information", "Helpdesk host OS info", system_info),
    ToolSpec("client_environment", SAFE, "Client environment", "Browser-reported device environment",
             client_environment, params=("client",)),

    ToolSpec("flush_dns_cache", RESTRICTED, "Flush DNS cache", "Clear the resolver cache on the user's device",
             approver_role="requester", risk_note="Idempotent; no data loss"),
    ToolSpec("restart_vpn_client_service", RESTRICTED, "Restart VPN client service",
             "Restart the VPN agent on the user's device", approver_role="requester",
             risk_note="Drops any active VPN session for ~10 seconds"),
    ToolSpec("clear_application_cache", RESTRICTED, "Clear application cache",
             "Clear the cache of the affected application", approver_role="requester",
             risk_note="Signs the user out of the application", params=("application",)),
    ToolSpec("restart_print_spooler", RESTRICTED, "Restart print spooler",
             "Restart the print spooler on the user's device", approver_role="requester",
             risk_note="Cancels jobs currently queued on this device"),
    ToolSpec("send_password_reset_link", RESTRICTED, "Send password reset link",
             "Send a self-service reset link to the user's registered recovery channel",
             approver_role="requester", risk_note="Existing sessions stay active until reset"),
    ToolSpec("unlock_account", RESTRICTED, "Unlock account", "Clear an account lockout in the directory",
             approver_role="requester", risk_note="Only after identity is confirmed by SSO session"),

    ToolSpec("delete_user_profile", DANGEROUS, "Delete local user profile",
             "Remove the local profile from a device", approver_role="admin", risk_note="Irreversible data loss"),
    ToolSpec("modify_production_database", DANGEROUS, "Modify production database",
             "Change data or schema in production", approver_role="admin", risk_note="Production impact"),
    ToolSpec("disable_security_controls", DANGEROUS, "Disable security controls",
             "Turn off endpoint protection or firewall", approver_role="admin", risk_note="Security exposure"),
    ToolSpec("reimage_device", DANGEROUS, "Re-image device", "Wipe and reinstall the OS",
             approver_role="admin", risk_note="All local data is erased"),
]}


def get_tool(name: str) -> Optional[ToolSpec]:
    return TOOLS.get(name)


@lru_cache()
def load_service_catalog() -> list[dict]:
    path = Path(get_settings().SERVICE_CATALOG_FILE)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [s for s in data.get("services", []) if s.get("enabled", True)]


def _catalog_urls() -> set[str]:
    return {s["url"] for s in load_service_catalog() if s.get("type") == "http"}


def diagnostics_for(category: Optional[str]) -> list[tuple[str, dict]]:
    """SAFE checks the agent runs automatically for a category (from the service catalog)."""
    return [("service_status", {"service": s["name"]})
            for s in load_service_catalog() if category in s.get("categories", [])][:4]
