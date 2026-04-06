# Project Context

- Test command: `pytest`
- Package manager: `uv`/`pip`
- CLI composes a temporary orx YAML in `orxhestra_code/main.py` via `_build_orx_yaml`.
- Current installed `orxhestra` ComposeSpec requires `defaults.model` and `main_agent` (not legacy top-level `model`/`root`).
