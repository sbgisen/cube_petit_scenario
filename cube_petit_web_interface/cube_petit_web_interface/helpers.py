"""api_server.py の純粋ヘルパー関数群。

rclpy / FastAPI に依存しないため、素の Python 環境で単体テストできる。
パスは引数で受け取り、api_server.py 側のモジュール定数を渡して使う。
"""

import io
import re
from pathlib import Path
from typing import Optional

import yaml
from PIL import Image


# --- 音量制御 ---

def _parse_amixer_volume(output: str) -> int:
    m = re.search(r'\[(\d+)%\]', output)
    return int(m.group(1)) if m else -1


# --- ポイント (places.yaml) ---

def _load_places(places_file: Path) -> dict:
    if places_file.exists():
        with places_file.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_places(places_file: Path, data: dict) -> None:
    with places_file.open('w') as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


# --- プロンプト ---

def _active_prompt_name(prompt_dir: Path, active_marker: Path, default_name: str) -> str:
    if active_marker.exists():
        name = active_marker.read_text(encoding='utf-8').strip()
        if (prompt_dir / name).exists():
            return name
    return default_name


# --- マップディレクトリ探索 ---

def _find_map_dir(map_name: str, base_dirs: list) -> Optional[Path]:
    for base in base_dirs:
        d = Path(base) / map_name
        if d.is_dir():
            return d
    return None


# --- マップ別 places.yaml ---

def _map_places_path(map_name: str, base_dirs: list) -> Optional[Path]:
    d = _find_map_dir(map_name, base_dirs)
    return d / 'places.yaml' if d else None


def _load_map_places(map_name: str, base_dirs: list) -> list:
    p = _map_places_path(map_name, base_dirs)
    if p and p.exists():
        data = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        return data.get('places', [])
    return []


def _save_map_places(map_name: str, places: list, base_dirs: list) -> None:
    p = _map_places_path(map_name, base_dirs)
    if p is None:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump({'places': places}, allow_unicode=True, sort_keys=False), encoding='utf-8')


# --- マップ別 rooms.yaml ---

def _map_rooms_path(map_name: str, base_dirs: list) -> Optional[Path]:
    d = _find_map_dir(map_name, base_dirs)
    return d / 'rooms.yaml' if d else None


def _load_map_rooms(map_name: str, base_dirs: list) -> list:
    p = _map_rooms_path(map_name, base_dirs)
    if p and p.exists():
        data = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        return data.get('rooms', [])
    return []


def _save_map_rooms(map_name: str, rooms: list, base_dirs: list) -> None:
    p = _map_rooms_path(map_name, base_dirs)
    if p is None:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump({'rooms': rooms}, allow_unicode=True, sort_keys=False), encoding='utf-8')


# --- 画像変換 (PGM <-> PNG) ---

def _pgm_to_png_bytes(pgm_path: Path) -> bytes:
    img = Image.open(pgm_path).convert('L')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def _png_bytes_to_pgm(png_data: bytes, pgm_path: Path) -> None:
    img = Image.open(io.BytesIO(png_data)).convert('L')
    img.save(str(pgm_path), format='PPM')
    # PPM → PGM: rewrite header
    pgm_path.write_bytes(_pil_to_pgm_bytes(img))


def _pil_to_pgm_bytes(img: Image.Image) -> bytes:
    w, h = img.size
    header = f'P5\n{w} {h}\n255\n'.encode()
    return header + img.tobytes()
