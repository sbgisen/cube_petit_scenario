#!/usr/bin/env python

# Copyright (c) 2026 SoftBank Corp.
# 
# <<licensetext>>

import json
import yaml
import random
import subprocess
from pathlib import Path


class SEPlayer:

    def __init__(self, config_path):

        config_path = Path(config_path).expanduser()

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.base_dir = Path(config["se_parent_dir"]).expanduser()
        mapping_path = Path(config["mapping_file_path"]).expanduser()

        with open(mapping_path, "r") as f:
            self.mapping = json.load(f)

        self.state_map = {}
        for item in self.mapping:
            state = item["state"]
            self.state_map.setdefault(state, []).append(item)

    # ==========================================
    def _get_current_volume(self):
        try:
            result = subprocess.check_output(["amixer", "get", "Master"]).decode()
            for line in result.splitlines():
                if "%" in line:
                    start = line.find("[") + 1
                    end = line.find("%")
                    return int(line[start:end])
        except Exception:
            pass
        return 100

    # ==========================================
    def play(self, state_name):

        if state_name not in self.state_map:
            print(f"[SE] state not found: {state_name}")
            return

        candidate = random.choice(self.state_map[state_name])

        wav_path = self.base_dir / candidate["path"]
        volume = int(candidate.get("volume", 100))

        if not wav_path.exists():
            print(f"[SE] file not found: {wav_path}")
            return

        # 🔹 現在音量保存
        original_volume = self._get_current_volume()

        try:
            # 🔹 一時的に音量変更
            subprocess.run(
                ["amixer", "sset", "Master", f"{volume}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # 🔹 再生（ブロッキングで待つ）
            subprocess.run(
                ["aplay", str(wav_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        finally:
            # 🔹 元に戻す
            subprocess.run(
                ["amixer", "sset", "Master", f"{original_volume}%"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        print(f"[SE] {state_name} -> {wav_path.name} ({volume}%) restored to {original_volume}%")
