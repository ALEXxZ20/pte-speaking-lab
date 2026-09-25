from uuid import uuid4


def plain(value):
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def evidence(sample_id: str, dimension: str, kind: str, source_type: str, source_ref: str,
             quality: str, algorithm_version: str, **details) -> dict:
    return {"id": f"ev_{uuid4().hex}", "sample_id": sample_id, "dimension": dimension,
            "kind": kind, "source_type": source_type, "source_ref": source_ref,
            "quality": quality, "algorithm_version": algorithm_version, **plain(details)}


def metric(value, unit: str, quality: str, reason: str | None = None, **details) -> dict:
    return {"value": plain(value), "unit": unit, "quality": quality, "reason": reason, "details": plain(details)}
