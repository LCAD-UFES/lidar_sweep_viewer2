import os

# Segment getter interface (DESIGN.md "Segment source"): the cache dir is the only entry point of the pipeline.
# resolve(sid) -> (object, size): exact byte size and a provenance string of where the file comes from
# fetch(object, dst): makes dst complete, atomically (write to dst + ".part", then rename)
# frames(object) -> int or None: frame count without fetching, when the source can tell cheaply (exact clip counts in the plan)
class Source:
    def resolve(self, sid): raise NotImplementedError
    def fetch(self, obj, dst): raise NotImplementedError
    def frames(self, obj): return None

def cache_path(cache_dir, sid): return os.path.join(cache_dir, f"{sid}.parquet")

def available(cache_dir, sid, size):
    p = cache_path(cache_dir, sid)
    return os.path.exists(p) and os.path.getsize(p) == size

def make_source(cfg):
    kind, params = cfg.get("type", "gcs"), {k: v for k, v in cfg.items() if k != "type"}
    if kind == "gcs":
        from .gcs import GcsSource
        return GcsSource(**params)
    raise ValueError(f"unknown source type {kind!r}")
