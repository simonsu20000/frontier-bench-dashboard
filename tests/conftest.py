import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A throwaway project root with the real config/ directory copied in."""
    shutil.copytree(ROOT / "config", tmp_path / "config")
    (tmp_path / "data").mkdir()
    return tmp_path


MODEL_METADATA = [
    {"model_version": "gpt-5.2-2025-12-11_none", "model_group": "GPT-5.2", "date": "2025-12-11", "display_name": "GPT-5.2 (none)",
     "organization": "OpenAI", "country": "United States of America", "accessibility": "API access"},
    {"model_version": "gpt-5.2-2025-12-11_high", "model_group": "GPT-5.2", "date": "2025-12-11", "display_name": "GPT-5.2 (high)",
     "organization": "OpenAI", "country": "United States of America", "accessibility": "API access"},
    {"model_version": "claude-fable-5-1_xhigh", "model_group": "Claude Fable 5.1", "date": "2026-09-01", "display_name": "Fable 5.1 (xhigh)",
     "organization": "Anthropic", "country": "United States of America", "accessibility": "API access"},
    {"model_version": "qwen3.8-max-0902_xhigh", "model_group": "Qwen3.8 Max (0902)", "date": "2026-09-01", "display_name": "Qwen3.8 Max (0902) (XHigh)",
     "organization": "Alibaba", "country": "China", "accessibility": "Open weights (unrestricted)"},
    {"model_version": "gemini-2.5-pro-preview-03-25", "model_group": "Gemini 2.5 Pro (Mar 2025)", "date": "2025-03-25", "display_name": "",
     "organization": "Google DeepMind", "country": "United States of America", "accessibility": "API access"},
    {"model_version": "gemini-2.5-pro-06-05", "model_group": "Gemini 2.5 Pro (Jun 2025)", "date": "2025-06-05", "display_name": "",
     "organization": "Google DeepMind", "country": "United States of America", "accessibility": "API access"},
    {"model_version": "kimi-k2-thinking", "model_group": "Kimi K2 Thinking", "date": "2025-11-06", "display_name": "",
     "organization": "Moonshot", "country": "China", "accessibility": "Open weights (restricted use)"},
    {"model_version": "kimi-k2-0711", "model_group": "Kimi K2 (Jul 2025)", "date": "2025-07-11", "display_name": "",
     "organization": "Moonshot", "country": "China", "accessibility": "Open weights (restricted use)"},
]

ECI = [
    {"Model": "GPT-5.2", "eci": "155.4", "eci_ci_low": "153", "eci_ci_high": "158", "date": "2025-12-11", "Organization": "OpenAI", "Model accessibility": "API access"},
    {"Model": "Claude Fable 5.1", "eci": "164.5", "eci_ci_low": "162", "eci_ci_high": "167", "date": "2026-09-01", "Organization": "Anthropic", "Model accessibility": "API access"},
]


@pytest.fixture
def metadata():
    return MODEL_METADATA, ECI
