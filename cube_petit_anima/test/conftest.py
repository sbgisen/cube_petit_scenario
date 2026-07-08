import sys
from pathlib import Path

# ソースツリーから直接 import できるようにする（install 不要）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
