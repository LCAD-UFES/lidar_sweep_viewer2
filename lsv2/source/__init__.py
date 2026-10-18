from .base import Source, cache_path, available
from .gcs import GcsSource

__all__ = ["Source", "cache_path", "available", "make_source"]

def make_source(cfg: dict[str, str]) -> Source:
    kind, params = cfg.get("type", "gcs"), {k: v for k, v in cfg.items() if k != "type"}
    if kind == "gcs": return GcsSource(**params)
    raise ValueError(f"unknown source type {kind!r}")
