"""
Precision AI - Output safety filter.
Generated troubleshooting text is screened before it reaches a user: any step that would have the
user run destructive or security-weakening commands, hand over credentials, or follow a link or phone
number that did not come from our own documentation is removed and the event is flagged.
"""

import re

_SECRET = (r"(password|passcode|passphrase|pin\b|mfa code|2fa code|otp\b|one[- ]time (?:pass)?code|"
           r"verification code|security code|recovery code|backup code|authenticator code)")

DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+-(rf|fr|r)\b", "recursive delete"),
    (r"\bdel\s+/[sq]", "recursive delete"),
    (r"\bformat\s+[a-z]:", "disk format"),
    (r"\b(diskpart|mkfs|dd\s+if=)", "disk tooling"),
    (r"\breg(\.exe)?\s+delete\b", "registry deletion"),
    (r"\bbcdedit\b", "boot configuration change"),
    (r"(disable|turn off|uninstall|stop|pause)\s+(the\s+)?(windows\s+)?(defender|antivirus|anti-virus|firewall|edr|"
     r"crowdstrike|endpoint protection|bitlocker|tamper protection|smartscreen|uac|user account control)",
     "security control disable"),
    (r"set-mppreference\s+.*-disable", "security control disable"),
    (r"\benablelua\b", "security control disable"),
    # exclusions make the antivirus ignore a file or folder
    (r"add-mppreference\s+.*-exclusion", "antivirus exclusion"),
    (r"\b(add|create|set up)\s+(an?\s+)?(exclusion|exception)\b.{0,60}\b(defender|antivirus|anti-virus|edr|scan)",
     "antivirus exclusion"),
    (r"\bexclu(de|sion)\b.{0,40}\bfrom\s+(windows\s+)?(defender|antivirus|anti-virus|edr|scanning)", "antivirus exclusion"),
    (r"(remove|disable|turn off|bypass|skip)\s+(\w+\s+){0,2}(mfa|2fa|two[- ]factor|multi[- ]factor|authenticator)",
     "MFA removal"),
    (r"\bdrop\s+(table|database)\b|\btruncate\s+table\b|\bdelete\s+from\b", "destructive SQL"),
    (r"(curl|wget|iwr|invoke-webrequest)[^|\n]*\|\s*(sh|bash|iex|powershell)", "remote script execution"),
    (r"\bcertutil(\.exe)?\b.*-urlcache", "download cradle"),
    (r"\bbitsadmin(\.exe)?\b.*/transfer", "download cradle"),
    (r"\bmshta(\.exe)?\b", "download cradle"),
    (r"\bregsvr32(\.exe)?\b.*/i:\s*https?", "download cradle"),
    (r"\b(downloadstring|downloadfile|invoke-expression)\b|\biex\s*\(", "download cradle"),
    (r"powershell(\.exe)?\s+-(e|enc|encodedcommand)\b", "encoded command"),
    (r"-(executionpolicy|ep)\s+(bypass|unrestricted)|set-executionpolicy\s+(bypass|unrestricted)",
     "execution policy bypass"),
    (r"\bvssadmin(\.exe)?\s+delete\s+shadows|\bwmic\s+shadowcopy\s+delete|\bwbadmin\s+delete", "shadow copy deletion"),
    (r"\bwevtutil(\.exe)?\s+(cl|clear-log)\b|\bclear-eventlog\b|(clear|delete|wipe|erase)\s+(the\s+)?(windows\s+)?"
     r"(event|security|audit|system)\s+logs?", "log clearing"),
    (r"\bnet\s+user\s+\S+\s+\S+\s+/add\b|\bnet\s+localgroup\s+administrators\s+.*/add\b|"
     r"\badd-localgroupmember\b.*administrators", "local admin creation"),
    (r"(make|add)\s+(yourself|me|the user|your account)\s+(\w+\s+){0,2}(local\s+)?admin(istrator)?", "local admin creation"),
    (r"\bnetsh\s+(adv)?firewall\s+set\s+.*\b(state\s+off|opmode\s+disable)", "firewall disable"),
    (r"set-netfirewallprofile\b.*-enabled\s+(false|0)", "firewall disable"),
    (r"\bchmod\s+(-R\s+)?(777|666|a\+w|o\+w)\b", "unsafe permissions"),
    (r"\bicacls\b.*\b(everyone|\*s-1-1-0|users)\s*:\s*\(?(f|m)\)?", "unsafe permissions"),
    (r"grant\s+everyone\s+(full|write|modify)", "unsafe permissions"),
    (r"(share|send|tell|give|provide|disclose|email|e-mail|post|paste|reply with|read out|forward)\s+(\w+\s+){0,3}"
     + _SECRET, "credential request"),
    (_SECRET + r"\s+(\w+\s+){0,4}(in|into|to|via)\s+(this|the|our)\s+(chat|ticket|conversation|reply|message)",
     "credential request"),
    (r"(what is|what's|confirm)\s+your\s+(current\s+)?" + _SECRET, "credential request"),
    (r"\bsudo\s+", "privileged command"),
    (r"run\s+as\s+administrator", "privileged command"),
]

_URL = re.compile(r"\b(?:https?://|www\.)[^\s)>\]]+", re.I)
_PHONE = re.compile(r"(?<![\w-])\+?\d[\d\s().-]{7,}\d(?![\w-])")


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


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _phones(text: str) -> list[str]:
    return [p for p in _PHONE.findall(text) if len(_digits(p)) >= 9]  # dates and short codes are not phone numbers


def unverified_references(text: str, context: str) -> list[str]:
    """Links and phone numbers in model output that do not appear in the supplied context (i.e. invented)."""
    known_urls = {u.lower().rstrip(".,;") for u in _URL.findall(context)}
    known_phones = {_digits(p) for p in _phones(context)}
    out = [f"unverified link: {u}" for u in _URL.findall(text) if u.lower().rstrip(".,;") not in known_urls]
    out += [f"unverified phone number: {p.strip()}" for p in _phones(text) if _digits(p) not in known_phones]
    return out


def filter_generated_steps(steps: list[str], context: str) -> tuple[list[str], list[str]]:
    """filter_steps plus removal of steps that cite links or phone numbers not present in `context`."""
    safe, flags = filter_steps(steps)
    kept = []
    for step in safe:
        refs = unverified_references(step, context)
        if refs:
            flags.append("invented link or phone number")
        else:
            kept.append(step)
    return kept, sorted(set(flags))
