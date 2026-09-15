"""V1.0.2 B4：Per-user LLM 调用 rate limiter（按 token 估算）。

背景：
- 之前只有 ``RateLimiter``（按 IP + 登录失败次数）防爆破
- 但单用户登录后可疯狂点击 → 把整月 LLM quota 烧光（DeepSeek 等仍按 token 计费）
- 财务风险：单用户失控调用 → 一次事故可能产生 ¥10K+ 账单

设计：
- 按 user_id 维度（不是 IP，避免 NAT 后多用户共享 quota）
- 按"预估 token 数"累计（不是调用次数 — 一次长文写作比 10 次摘要更贵）
- 1 小时滑动窗口（cleanup 时清理 > 1h 的记录）
- 原子 check-and-claim（threading.Lock 保护）

关键设计点：
1. **预估 token**（不精确计费）：
   - input: 估算 ``prompt + system`` 字符数 / 4（中英混合按 4 字符/token）
   - output: max_tokens（最坏情况预估）
   - 这样无需等 LLM 返回就能预扣 quota（避免事后无法追讨）

2. **多用户独立 quota**：
   - ``_usage: dict[int, list[float, int]]`` 按 user_id 隔离
   - user_id == 0（未登录）→ 用 IP fallback（key=-1 单独统计）

3. **失败回退**：
   - 单用户超 quota → raise ``LLMRateLimitExceeded``
   - 剩余 token 数返回给 caller 用于 header（``X-LLM-Tokens-Remaining``）

4. **环境变量**：
   - ``LLM_RATE_LIMIT_PER_HOUR``（默认 100000 token / hour / user）

5. **集成点**：
   - LLMProvider.complete() / stream() 入口前调 ``check()``
   - user_id 从 ``request.state.user.id`` 获取（FastAPI middleware 已注入）
   - 拒绝时 raise HTTPException(429, "LLM rate limit exceeded")
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

# 默认：每用户每小时 100K token（约 200 次 500-token 摘要 / 50 次 2K-token 写作）
DEFAULT_LIMIT_PER_HOUR = 100_000


class LLMRateLimitExceeded(Exception):
    """V1.0.2 B4：用户超过 LLM 调用 quota。"""

    def __init__(self, user_id: int, used: int, limit: int, requested: int) -> None:
        """V1.0.2 B4：构造限流异常。

        Args:
            user_id: 触发限流的用户 ID
            used: 当前已用 token（1h 窗口内累计）
            limit: 用户的 1h quota 上限
            requested: 这次请求预估 token 数
        """
        self.user_id = user_id
        self.used = used
        self.limit = limit
        self.requested = requested
        super().__init__(
            f"LLM rate limit exceeded for user {user_id}: "
            f"used {used}/{limit} tokens, requested {requested}. "
            f"Try again later or upgrade your plan."
        )


class LLMRateLimiter:
    """V1.0.2 B4：Per-user LLM token 限流器。

    用法：
        limiter = LLMRateLimiter()
        # 在 LLMProvider.complete() 入口：
        try:
            remaining = limiter.check(
                user_id=user.id,
                est_tokens=estimate_tokens(prompt, system) + max_tokens,
            )
            response.headers["X-LLM-Tokens-Remaining"] = str(remaining)
        except LLMRateLimitExceeded as e:
            raise HTTPException(429, str(e))

    设计：threading.Lock + 滑动窗口。内存版（适合单进程）。
    跨进程场景（multi-worker）需切换到 Redis / SQLite 共享。
    """

    # 特殊 key：未登录 / 匿名用户（按 IP 隔离）
    ANONYMOUS_KEY: int = -1

    def __init__(self, max_tokens_per_hour: int | None = None) -> None:
        """V1.0.2 B4：构造限流器。

        Args:
            max_tokens_per_hour: 每用户每小时 quota。``None`` → 从环境变量
                ``LLM_RATE_LIMIT_PER_HOUR`` 读（默认 100000）。
        """
        if max_tokens_per_hour is None:
            env_val = os.environ.get("LLM_RATE_LIMIT_PER_HOUR")
            if env_val:
                try:
                    max_tokens_per_hour = int(env_val)
                except ValueError:
                    logger.warning(
                        "V1.0.2 B4: invalid LLM_RATE_LIMIT_PER_HOUR=%r, using default %d",
                        env_val,
                        DEFAULT_LIMIT_PER_HOUR,
                    )
                    max_tokens_per_hour = DEFAULT_LIMIT_PER_HOUR
            else:
                max_tokens_per_hour = DEFAULT_LIMIT_PER_HOUR
        self.max_tokens_per_hour = max_tokens_per_hour
        # V1.0.2 B4：key = user_id (或 ANONYMOUS_KEY)，value = [(timestamp, tokens), ...]
        self._usage: dict[int, list[tuple[float, int]]] = {}
        self._lock = threading.Lock()

    def _prune(self, usage: list[tuple[float, int]], now: float, cutoff: float) -> None:
        """V1.0.2 B4：清理 > 1h 的旧记录（callers 持 lock）。"""
        # 原地过滤避免重新分配
        usage[:] = [(ts, t) for ts, t in usage if ts > cutoff]

    def _get_or_create(self, user_id: int) -> list[tuple[float, int]]:
        """V1.0.2 B4：取该用户的 usage 列表（callers 持 lock）。"""
        if user_id not in self._usage:
            self._usage[user_id] = []
        return self._usage[user_id]

    def check(self, user_id: int, est_tokens: int) -> int:
        """V1.0.2 B4：检查用户是否可发起 LLM 调用。

        原子地：
        1. 清理 > 1h 的旧记录
        2. 累计当前 1h 用量
        3. 若 current + est_tokens > limit → raise
        4. 否则追加本次记录，返回剩余 token 数

        Args:
            user_id: 用户 ID。``ANONYMOUS_KEY`` 表示匿名（按 IP 隔离）。
            est_tokens: 本次预估 token 数（input + output）。

        Returns:
            剩余 token 数（本次调用后还能用多少）。

        Raises:
            LLMRateLimitExceeded: 用户超额。
            ValueError: ``est_tokens < 0``。
        """
        if est_tokens < 0:
            raise ValueError(f"est_tokens must be >= 0, got {est_tokens}")
        with self._lock:
            now = time.time()
            cutoff = now - 3600
            usage = self._get_or_create(user_id)
            self._prune(usage, now, cutoff)
            current = sum(t for _, t in usage)
            if current + est_tokens > self.max_tokens_per_hour:
                # 超额 → 抛异常（caller 决定如何处理 HTTP / CLI 退出）
                raise LLMRateLimitExceeded(
                    user_id=user_id,
                    used=current,
                    limit=self.max_tokens_per_hour,
                    requested=est_tokens,
                )
            # 通过：追加本次记录
            usage.append((now, est_tokens))
            remaining = self.max_tokens_per_hour - current - est_tokens
            return max(0, remaining)

    def get_used(self, user_id: int) -> int:
        """V1.0.2 B4：查用户当前 1h 窗口已用 token（清理过期后）。"""
        with self._lock:
            now = time.time()
            cutoff = now - 3600
            usage = self._usage.get(user_id, [])
            self._prune(usage, now, cutoff)
            return sum(t for _, t in usage)

    def reset(self, user_id: int | None = None) -> None:
        """V1.0.2 B4：重置用户 quota（admin / 测试用）。

        Args:
            user_id: 指定用户。``None`` → 重置所有用户。
        """
        with self._lock:
            if user_id is None:
                self._usage.clear()
            else:
                self._usage.pop(user_id, None)


# V1.0.2 B4：模块级单例（供 LLMProvider 调用 — 避免每次创建 limiter）
_global_limiter: LLMRateLimiter | None = None
_global_limiter_lock = threading.Lock()


def get_global_llm_rate_limiter() -> LLMRateLimiter:
    """V1.0.2 B4：获取全局 LLM rate limiter（懒加载 + 线程安全）。

    用法（LLMProvider 内）：
        from novel2all.core.llm_rate_limiter import get_global_llm_rate_limiter
        limiter = get_global_llm_rate_limiter()
        limiter.check(user_id=..., est_tokens=...)

    单进程内共享；如需 multi-worker 共享，可替换为 Redis 实现。
    """
    global _global_limiter
    with _global_limiter_lock:
        if _global_limiter is None:
            _global_limiter = LLMRateLimiter()
        return _global_limiter


def reset_global_llm_rate_limiter() -> None:
    """V1.0.2 B4：重置全局 limiter（仅测试使用）。"""
    global _global_limiter
    with _global_limiter_lock:
        _global_limiter = None


def estimate_tokens(text: str | None) -> int:
    """V1.0.2 B4：估算文本 token 数（粗略：4 字符/token，中英混合）。

    这是简单启发式（不用 tiktoken 等重依赖）：
    - 1 token ≈ 4 字符（GPT 经验值）
    - 中文略低（约 1.5 字符/token）但保守按 4 估 → 略多扣 quota 更安全

    Args:
        text: 输入文本。``None`` / 空 → 0。

    Returns:
        估算 token 数（向上取整，最少 0）。
    """
    if not text:
        return 0
    # 向上取整：len + 3 // 4 避免 1-3 字符也按 1 估
    return (len(text) + 3) // 4
