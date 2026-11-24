"""Đảm bảo `import core...` chạy được khi pytest gọi từ thư mục luyen_co/."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
