import os
from abc import ABC, abstractmethod

# Segment source interface (DESIGN.md "Segment source"): the cache dir is the only entry point of the pipeline.
# resolve(sid) -> (object, size): a provenance string of where the file comes from and its exact byte size
# fetch(object, dst): makes dst complete, atomically (write to dst + ".part", then rename)
# frames(object) -> frame count without fetching, when the source can tell cheaply (exact clip counts in the plan); None if it cannot
class Source(ABC):
    @abstractmethod
    def resolve(self, sid: str) -> tuple[str, int]: ...
    @abstractmethod
    def fetch(self, obj: str, dst: str) -> None: ...
    @abstractmethod
    def frames(self, obj: str) -> int | None: ...

def cache_path(cache_dir: str, sid: str) -> str: return os.path.join(cache_dir, f"{sid}.parquet")

def available(cache_dir: str, sid: str, size: int) -> bool:
    p = cache_path(cache_dir, sid)
    return os.path.exists(p) and os.path.getsize(p) == size
