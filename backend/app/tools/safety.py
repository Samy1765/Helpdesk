"""
Precision AI - Output safety filter.
Generated troubleshooting text is screened before it reaches a user: any step that would have the
user run destructive or security-weakening commands is removed and the event is flagged.
"""

import re

DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+-(rf|fr|r)\b", "recursive delete"),
    (r"\bdel\s+/[sq]", "recursive delete"),
    (r"\bformat\s+[a-z]:", "disk format"),
    (r"\b(diskpart|mkfs|dd\s+if=)", "disk tooling"),
    (r"\breg(\.exe)?\s+delete\b", "registry deletion"),
    (r"\bbcdedit\b", "boot configuration change"),
    (r"(disable|turn off|uninstall|stop)\s+(the\s+)?(windows\s+)?(defender|antivirus|anti-virus|firewall|edr|crowdstrike|endpoint protection|bitlocker)",
     "security control disable"),
    (r"set-mppreference\s+.*-disable", "security control disable"),
    (r"\bdrop\s+(table|database)\b|\btruncate\s+table\b|\bdelete\s+from\b", "destructive SQL"),
    (r"(curl|wget|iwr|invoke-webrequest)[^|\n]*\|\s*(sh|bash|iex|powershell)", "remote script execution"),
    (r"powershell(\.exe)?\s+-(e|enc|encodedcommand)\b", "encoded command"),
    (r"\bchmod\s+(-R\s+)?777\b", "unsafe permissions"),
    (r"(share|send|tell|give)\s+(us\s+|me\s+)?(your\s+)?(password|passcode|mfa code|otp)", "credential request"),
    (r"\bsudo\s+", "privileged command"),
    (r"run\s+as\s+administrator", "privileged command"),
]


def screen_text(text: str) -> list[str]:
    """Return the reasons a text is unsafe (empty list == safe)."""
    lowered = text.lower()
    return sorted({reason for pat, reason in DANGEROUS_PATTERNS if re.search(pat, lowered)})


def filter_steps(steps: list[str]) -> tuple[list[str], list[str]]:
    safe, flagged = [], []
    for step in steps:
        reasons = screen_text(step)
        if reasons:
            flagged.extend(reasons)
        else:
            safe.append(step)
    return safe, sorted(set(flagged))
