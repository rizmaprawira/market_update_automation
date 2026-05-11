"""Path resolution utilities using config/paths.yml and config/report_periods.yml."""
from pathlib import Path
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[4]


def load_current_period() -> str:
    cfg = yaml.safe_load((_REPO_ROOT / "config/report_periods.yml").read_text())
    return cfg["current_period"]


def resolve_path(key: str, period: str, segment: str, company: str) -> Path:
    """Resolve a paths.yml template key to an absolute company directory path."""
    paths = yaml.safe_load((_REPO_ROOT / "config/paths.yml").read_text())
    return _REPO_ROOT / paths[key].format(period=period, segment=segment) / company
