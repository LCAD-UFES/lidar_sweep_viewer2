import types
from collections.abc import Callable
from dataclasses import MISSING, fields, is_dataclass
from typing import TYPE_CHECKING, cast, get_args, get_origin, get_type_hints
if TYPE_CHECKING: from _typeshed import DataclassInstance

# The JSON boundary of the package (job, plan and state files): every value is checked against the dataclass field
# annotation, so nothing typed Any enters the program and a malformed file fails with the offending key named.
# Supported annotations: str, int, float, bool, None, X | Y, list[X], dict[K, V] and nested dataclasses.

def from_dict[T: DataclassInstance](cls: type[T], data: object, where: str = "") -> T:
    where = where or cls.__name__
    if not isinstance(data, dict): raise ValueError(f"{where}: expected an object, got {type(data).__name__}")
    d, hints, kwargs = cast(dict[object, object], data), cast(dict[str, object], get_type_hints(cls)), {}
    names = {f.name for f in fields(cls)}
    extra = set(d) - names
    if extra: raise ValueError(f"{where}: unknown keys {sorted(str(k) for k in extra)}")
    for f in fields(cls):
        if f.name not in d:
            if f.default is MISSING and f.default_factory is MISSING: raise ValueError(f"{where}: missing key {f.name!r}")
            continue
        kwargs[f.name] = conforms(d[f.name], hints[f.name], f"{where}.{f.name}")
    return cast(Callable[..., T], cls)(**kwargs)

def conforms(v: object, t: object, where: str) -> object:
    origin, args = get_origin(t), cast(tuple[object, ...], get_args(t))
    if origin is types.UnionType:
        for a in args:
            try: return conforms(v, a, where)
            except ValueError: pass
        raise ValueError(f"{where}: expected {t}, got {type(v).__name__}")
    if origin is list:
        if not isinstance(v, list): raise ValueError(f"{where}: expected a list, got {type(v).__name__}")
        return [conforms(x, args[0], f"{where}[{i}]") for i, x in enumerate(cast(list[object], v))]
    if origin is dict:
        if not isinstance(v, dict): raise ValueError(f"{where}: expected an object, got {type(v).__name__}")
        return {conforms(k, args[0], where): conforms(x, args[1], f"{where}[{k!r}]") for k, x in cast(dict[object, object], v).items()}
    if t is type(None):
        if v is not None: raise ValueError(f"{where}: expected null, got {type(v).__name__}")
        return None
    if isinstance(t, type) and is_dataclass(t): return from_dict(t, v, where)
    if isinstance(t, type):
        if t is float and isinstance(v, int) and not isinstance(v, bool): return float(v)   # JSON integers are valid floats
        if not isinstance(v, t) or (t is int and isinstance(v, bool)): raise ValueError(f"{where}: expected {t.__name__}, got {type(v).__name__}")
        return v
    raise TypeError(f"{where}: unsupported annotation {t!r}")
