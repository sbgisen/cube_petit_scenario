# Copyright (c) 2026 SoftBank Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""api_server.py の純粋ヘルパー関数群.

rclpy / FastAPI に依存しないため、素の Python 環境で単体テストできる。
パスは引数で受け取り、api_server.py 側のモジュール定数を渡して使う。
"""

import io
from pathlib import Path
import re
import socket
from typing import Optional

from PIL import Image
import yaml

# --- 音量制御 ---


def parse_amixer_volume(output: str) -> int:
    m = re.search(r'\[(\d+)%\]', output)
    return int(m.group(1)) if m else -1


# --- 名前空間 (hostname -> cube_petit_<color>) ---

DEFAULT_NAMESPACE = 'cube_petit_orange'


def resolve_namespace(hostname: Optional[str] = None) -> str:
    """ホスト名から ROS 名前空間 (例: 'cube_petit_pink') を導く.

    各個体は cube_petit_<color> という hostname を持つ運用のため、そのまま
    名前空間として使える（cube_petit_bringup.launch.py の face_color 導出と
    同じ発想だが、こちらは色名を剥がさず完全な名前空間文字列を返す）。
    その命名規則に沿わないホスト（開発機など）では DEFAULT_NAMESPACE にフォールバックする。
    """
    hostname = hostname if hostname is not None else socket.gethostname()
    namespace = hostname.replace('-', '_')
    return namespace if namespace.startswith('cube_petit_') else DEFAULT_NAMESPACE


# --- ポイント (places.yaml) ---


def load_places(places_file: Path) -> dict:
    if places_file.exists():
        with places_file.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def save_places(places_file: Path, data: dict) -> None:
    with places_file.open('w') as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


# --- プロンプト ---


def active_prompt_name(prompt_dir: Path, active_marker: Path, default_name: str) -> str:
    if active_marker.exists():
        name = active_marker.read_text(encoding='utf-8').strip()
        if (prompt_dir / name).exists():
            return name
    return default_name


# --- マップディレクトリ探索 ---


def find_map_dir(map_name: str, base_dirs: list) -> Optional[Path]:
    for base in base_dirs:
        d = Path(base) / map_name
        if d.is_dir():
            return d
    return None


# --- マップ別 places.yaml ---


def map_places_path(map_name: str, base_dirs: list) -> Optional[Path]:
    d = find_map_dir(map_name, base_dirs)
    return d / 'places.yaml' if d else None


def load_map_places(map_name: str, base_dirs: list) -> list:
    p = map_places_path(map_name, base_dirs)
    if p and p.exists():
        data = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        return data.get('places', [])
    return []


def save_map_places(map_name: str, places: list, base_dirs: list) -> None:
    p = map_places_path(map_name, base_dirs)
    if p is None:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump({'places': places}, allow_unicode=True, sort_keys=False), encoding='utf-8')


# --- マップ別 rooms.yaml ---


def map_rooms_path(map_name: str, base_dirs: list) -> Optional[Path]:
    d = find_map_dir(map_name, base_dirs)
    return d / 'rooms.yaml' if d else None


def load_map_rooms(map_name: str, base_dirs: list) -> list:
    p = map_rooms_path(map_name, base_dirs)
    if p and p.exists():
        data = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
        return data.get('rooms', [])
    return []


def save_map_rooms(map_name: str, rooms: list, base_dirs: list) -> None:
    p = map_rooms_path(map_name, base_dirs)
    if p is None:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.dump({'rooms': rooms}, allow_unicode=True, sort_keys=False), encoding='utf-8')


# --- 画像変換 (PGM <-> PNG) ---


def pgm_to_png_bytes(pgm_path: Path) -> bytes:
    img = Image.open(pgm_path).convert('L')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def png_bytes_to_pgm(png_data: bytes, pgm_path: Path) -> None:
    img = Image.open(io.BytesIO(png_data)).convert('L')
    img.save(str(pgm_path), format='PPM')
    # PPM → PGM: rewrite header
    pgm_path.write_bytes(pil_to_pgm_bytes(img))


def pil_to_pgm_bytes(img: Image.Image) -> bytes:
    w, h = img.size
    header = f'P5\n{w} {h}\n255\n'.encode()
    return header + img.tobytes()
