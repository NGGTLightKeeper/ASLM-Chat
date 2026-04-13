# Copyright NGGT.LightKeeper and Di120078. All Rights Reserved.

_ANTIBOT_MARKERS = (
    "antibot", "challenge", "captcha", "cf-browser-verification",
    "ray id", "just a moment", "checking your browser", "please wait",
    "enable javascript", "ddos-guard", "robot or human",
)
_ANTIBOT_SINGLE = (
    "your browser does not support javascript",
    "javascript is required",
    "please enable javascript",
    "this site requires javascript",
    "you need to enable javascript",
)

def is_antibot(text: str) -> bool:
    """Return True when the response body looks like an anti-bot wall."""
    t = text[:2_000].lower()
    if any(m in t for m in _ANTIBOT_SINGLE):
        return True
    return sum(1 for m in _ANTIBOT_MARKERS if m in t) >= 2
