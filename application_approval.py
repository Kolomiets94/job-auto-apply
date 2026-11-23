"""Central fail-closed approval gate for all live application channels."""
import os


def live_applications_approved():
    return os.getenv("AUTO_APPLY_APPROVED", "0").strip().lower() in ("1", "true", "yes")
