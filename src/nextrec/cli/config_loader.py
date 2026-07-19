import json
from pathlib import Path
from typing import Any, Dict, Optional


def load_config(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML is required to load .yaml files. Install it with: pip install pyyaml")
        return yaml.safe_load(text) or {}
    elif path.suffix == ".json":
        return json.loads(text) or {}
    else:
        raise ValueError(f"Unsupported config file format: {path.suffix}. Use .json, .yaml, or .yml")


def merge_configs(cli_args: Dict[str, Any], file_config: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(file_config)
    for key, value in cli_args.items():
        if value is not None:
            merged[key] = value
    return merged
