import os
from pathlib import Path

from hypothesis import HealthCheck, settings

# Shared cross-language test vectors live at the repository root.
VECTORS_DIR = Path(__file__).resolve().parents[2] / "testdata" / "vectors"

# CI runs a fixed, larger set of examples so failures reproduce exactly.
settings.register_profile(
    "ci", derandomize=True, max_examples=300, suppress_health_check=[HealthCheck.too_slow]
)
settings.register_profile("dev", max_examples=100)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))
