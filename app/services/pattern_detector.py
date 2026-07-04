from dataclasses import dataclass
from typing import List, Optional

SUSPICIOUS_PATTERNS: List[str] = [
    "ignore previous instructions",
    "forget everything",
    "show system prompt",
    "reveal password",
    "execute code",
    "admin mode",
    "override",
]


@dataclass
class PatternDetectionResult:
    is_suspicious: bool
    pattern: Optional[str] = None


def detect_suspicious_pattern(prompt: str) -> PatternDetectionResult:
    lowered = prompt.lower()
    for pattern in SUSPICIOUS_PATTERNS:
        if pattern in lowered:
            return PatternDetectionResult(is_suspicious=True, pattern=pattern)
    return PatternDetectionResult(is_suspicious=False)
