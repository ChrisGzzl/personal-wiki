"""Configuration management - reads config.yaml from wiki root."""
import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = {
    "llm": {
        "provider": "anthropic",
        "model": "claude-3-5-sonnet-latest",
        "api_key_env": "ANTHROPIC_API_KEY",
        "max_tokens": 16000,
        "temperature": 0.3,
    },
    "paths": {
        "wiki_root": "~/wiki",
        "raw_dir": "raw",
        "wiki_dir": "wiki",
        "outputs_dir": "outputs",
        "schema_file": "schema.md",
        "state_file": ".wiki_state.json",
    },
    "behavior": {
        "lint_stale_days": 30,
        "max_raw_batch": 10,
        "language": "zh-CN",
    },
}


class Config:
    def __init__(self, wiki_root: Path | None = None):
        self._data = dict(DEFAULT_CONFIG)
        self.wiki_root = self._resolve_root(wiki_root)
        self._load()

    def _resolve_root(self, wiki_root: Path | None) -> Path:
        if wiki_root:
            return Path(wiki_root).expanduser().resolve()
        # Try config env var, then default
        env_root = os.environ.get("WIKI_ROOT")
        if env_root:
            return Path(env_root).expanduser().resolve()
        return Path("~/wiki").expanduser().resolve()

    def _load(self):
        config_path = self.wiki_root / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                user_config = yaml.safe_load(f) or {}
            self._deep_merge(self._data, user_config)

    def _deep_merge(self, base: dict, override: dict):
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_merge(base[k], v)
            else:
                base[k] = v

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-notation access e.g. 'llm.model'."""
        parts = key.split(".")
        cur = self._data
        for p in parts:
            if not isinstance(cur, dict) or p not in cur:
                return default
            cur = cur[p]
        return cur

    @property
    def raw_dir(self) -> Path:
        return self.wiki_root / self._data["paths"]["raw_dir"]

    @property
    def wiki_dir(self) -> Path:
        return self.wiki_root / self._data["paths"]["wiki_dir"]

    @property
    def outputs_dir(self) -> Path:
        return self.wiki_root / self._data["paths"]["outputs_dir"]

    @property
    def schema_file(self) -> Path:
        return self.wiki_root / self._data["paths"]["schema_file"]

    @property
    def state_file(self) -> Path:
        return self.wiki_root / self._data["paths"]["state_file"]

    @property
    def api_key(self) -> str:
        # Direct key in config takes precedence (for testing/non-Anthropic providers)
        direct = self._data["llm"].get("api_key", "")
        if direct:
            return direct
        # Otherwise read from environment variable
        env_var = self._data["llm"].get("api_key_env", "ANTHROPIC_API_KEY")
        key = os.environ.get(env_var, "")
        if not key:
            raise ValueError(
                f"API key not found. Set '{env_var}' env var or add 'api_key' to config.yaml."
            )
        return key

    @property
    def model(self) -> str:
        return self._data["llm"]["model"]

    def model_for(self, operation: str) -> str:
        """Get model for a specific operation, falling back to llm.model.

        Checks 'models.<operation>' in config before falling back to 'llm.model'.
        Example config:
            models:
              ingest: "strong-model"
              query: "fast-model"
              lint: "fast-model"
        """
        op_model = self.get(f"models.{operation}")
        return op_model if op_model else self.model

    @property
    def max_tokens(self) -> int:
        return self._data["llm"]["max_tokens"]

    @property
    def temperature(self) -> float:
        return self._data["llm"]["temperature"]
