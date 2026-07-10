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
"""respeaker_usb_detect のテスト（実USBに依存しないよう擬似sysfsツリーを作る）."""

from pathlib import Path

from respeaker_usb_detect import is_respeaker_connected
from respeaker_usb_detect import RESPEAKER_PRODUCT_ID
from respeaker_usb_detect import RESPEAKER_VENDOR_ID


def _make_usb_device(root: Path, name: str, vendor_id: int, product_id: int) -> None:
    device_dir = root / name
    device_dir.mkdir(parents=True)
    (device_dir / 'idVendor').write_text(f'{vendor_id:04x}\n', encoding='utf-8')
    (device_dir / 'idProduct').write_text(f'{product_id:04x}\n', encoding='utf-8')


class TestIsRespeakerConnected:

    def test_no_devices(self, tmp_path: Path) -> None:
        assert is_respeaker_connected(str(tmp_path)) is False

    def test_unrelated_devices_only(self, tmp_path: Path) -> None:
        _make_usb_device(tmp_path, '1-1', 0x046d, 0xc52b)  # Logitech receiver
        _make_usb_device(tmp_path, '1-2', 0x1d6b, 0x0002)  # Linux Foundation root hub
        assert is_respeaker_connected(str(tmp_path)) is False

    def test_respeaker_present(self, tmp_path: Path) -> None:
        _make_usb_device(tmp_path, '1-1', 0x046d, 0xc52b)
        _make_usb_device(tmp_path, '1-2', RESPEAKER_VENDOR_ID, RESPEAKER_PRODUCT_ID)
        assert is_respeaker_connected(str(tmp_path)) is True

    def test_matching_vendor_but_different_product_is_not_detected(self, tmp_path: Path) -> None:
        # Seeed vendor ID reused by another product should not false-positive.
        _make_usb_device(tmp_path, '1-1', RESPEAKER_VENDOR_ID, 0x9999)
        assert is_respeaker_connected(str(tmp_path)) is False

    def test_device_dir_missing_id_files_is_ignored(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / 'usb1'
        empty_dir.mkdir()
        assert is_respeaker_connected(str(tmp_path)) is False

    def test_malformed_id_file_is_ignored(self, tmp_path: Path) -> None:
        device_dir = tmp_path / '1-1'
        device_dir.mkdir()
        (device_dir / 'idVendor').write_text('not-hex\n', encoding='utf-8')
        (device_dir / 'idProduct').write_text('0018\n', encoding='utf-8')
        assert is_respeaker_connected(str(tmp_path)) is False

    def test_nonexistent_root_returns_false(self, tmp_path: Path) -> None:
        assert is_respeaker_connected(str(tmp_path / 'does_not_exist')) is False
