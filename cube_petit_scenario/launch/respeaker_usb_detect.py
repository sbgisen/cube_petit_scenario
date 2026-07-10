#!/usr/bin/env python

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
"""Pure USB detection helper for the Seeed ReSpeaker mic array.

Intentionally has zero rclpy/launch imports so it can be unit tested without a
ROS environment, and imported from cube_petit_talk_demo.launch.py at launch
description generation time (before any node is started).
"""

import glob
import os
from typing import Optional

# Same idVendor/idProduct pair that respeaker_ros's RespeakerInterface
# (respeaker_ros/interface.py, VENDOR_ID/PRODUCT_ID) uses to open the device
# with pyusb, so detection here matches what respeaker_node would actually find.
RESPEAKER_VENDOR_ID = 0x2886
RESPEAKER_PRODUCT_ID = 0x0018

DEFAULT_USB_DEVICES_ROOT = '/sys/bus/usb/devices'


def _read_hex_id(path: str) -> Optional[int]:
    """Read a sysfs idVendor/idProduct file (bare hex digits, no '0x' prefix)."""
    try:
        with open(path, encoding='utf-8') as f:
            return int(f.read().strip(), 16)
    except (OSError, ValueError):
        return None


def is_respeaker_connected(usb_devices_root: str = DEFAULT_USB_DEVICES_ROOT) -> bool:
    """Return True if a ReSpeaker is attached over USB.

    Scans sysfs USB device entries directly (no pyusb dependency at launch
    description generation time) for the Seeed vendor/product ID.
    """
    for device_dir in glob.glob(os.path.join(usb_devices_root, '*')):
        vendor_id = _read_hex_id(os.path.join(device_dir, 'idVendor'))
        product_id = _read_hex_id(os.path.join(device_dir, 'idProduct'))
        if vendor_id == RESPEAKER_VENDOR_ID and product_id == RESPEAKER_PRODUCT_ID:
            return True
    return False
