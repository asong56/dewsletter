import hashlib


def generate_item_id(source_id: str, run_id: str) -> str:
    payload = f"{source_id}|{run_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
