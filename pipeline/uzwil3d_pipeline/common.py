import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]

session = requests.Session()
session.headers["User-Agent"] = "uzwil3d-pipeline (+https://github.com/sxwxbxr/uzwil3d)"


def load_config() -> dict:
    return json.loads((ROOT / "pipeline" / "config.json").read_text())


def get_json(url: str, params: dict | None = None) -> dict:
    for attempt in range(4):
        try:
            r = session.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")


def download(url: str, target: Path) -> Path:
    """Download url to target unless it is already cached."""
    if target.exists() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")
    for attempt in range(4):
        try:
            with session.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with tmp.open("wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            tmp.rename(target)
            return target
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    raise AssertionError("unreachable")


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
