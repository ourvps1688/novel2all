"""novel2all - novel-to-all 创作工具集。

V0.29.2：模块日志约定
- 库不主动配 logger（"don't configure the root logger"）
- 添加 NullHandler 防止 "No handlers could be found" warning
- 应用方（CLI/Web）按需要 basicConfig(level=...)
"""

import logging

__version__ = "0.20.0"

# V0.29.2：库级 NullHandler（避免 "No handlers" warning）
logging.getLogger(__name__).addHandler(logging.NullHandler())
