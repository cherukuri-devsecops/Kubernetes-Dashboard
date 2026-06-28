"""Shared parsing utilities used by routers and pollers."""


def parse_cpu(val: str) -> float:
    val = (val or "0").strip()
    if val.endswith("n"): return float(val[:-1]) / 1_000_000
    if val.endswith("u"): return float(val[:-1]) / 1_000
    if val.endswith("m"): return float(val[:-1])
    try:   return float(val) * 1000
    except: return 0.0


def parse_mem(val: str) -> int:
    val = (val or "0").strip()
    for sfx, mult in [("Ki", 1024), ("Mi", 1024**2), ("Gi", 1024**3), ("Ti", 1024**4),
                      ("K", 1000), ("M", 1000**2), ("G", 1000**3)]:
        if val.endswith(sfx):
            try: return int(float(val[:-len(sfx)]) * mult)
            except: return 0
    try: return int(val)
    except: return 0
