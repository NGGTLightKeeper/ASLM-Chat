# Copyright NEXTGGTECH. Elastic License 2.0.

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


# Return True when the response body looks like an anti-bot wall.
def is_antibot(text: str) -> bool:
    t = text[:2_000].lower()
    if any(m in t for m in _ANTIBOT_SINGLE):
        return True
    return sum(1 for m in _ANTIBOT_MARKERS if m in t) >= 2
