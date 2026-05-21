import hashlib


def stable_hash(s: str, length: int = 10) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:length]


def doc_id_for(source_name: str, url: str) -> str:
    return f"{source_name.lower().replace(' ', '_')}_{stable_hash(url)}"
