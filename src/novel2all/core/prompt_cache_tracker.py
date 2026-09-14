"""V0.30.6 C1：Prompt prefix cache 跟踪 + 成本节省量化。

与 V0.33 full response cache 的区别：
- **Response cache**（V0.33）：完整 (sys_hash, user_hash, model, temperature) 匹配 → 直接返回，不调 LLM
- **Prompt prefix cache**（V0.30.6 C1）：sys_hash 匹配 + user_hash 不同 → 仍需调 LLM，但 prefix 已缓存

为什么 prompt prefix cache 重要（基于 V0.36 实测）：
- DeepSeek flash：cache hit input=0.02 CNY/M, miss=1.00 CNY/M（50x 价差）
- 80% 命中率时：每 5 次请求 4 次命中（0.02）+ 1 次 miss（1.00）
  → 平均 input cost: (4×0.02 + 1×1.00) / 5 = 0.216 CNY/M
  → 无 cache: 1.00 CNY/M
  → **节省 78%**

典型 novel 写作工作负载的 sys_hash 复用率：
- 世界观/角色卡（系统提示）跨章节稳定 → sys_hash 100% 复用
- 用户消息（章节 prompt）每章不同 → user_hash 100% 不复用
- → prompt prefix hit rate 接近 100%（前提是 sys_hash 复用）

设计：
- PromptCacheTracker：纯 Python 跟踪器（无 IO），统计 sys_hash 复用
- 与 LLMProvider 集成：在 _make_cache_key() 之后判断 prefix hit/miss
- 暴露给 cache_stats() / 端点 / Web UI
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PromptCacheTracker:
    """V0.30.6 C1：跟踪 prompt prefix 命中统计。

    核心思路：sys_hash 是 prompt prefix（system prompt + 角色卡等）。
    相同 sys_hash 多次出现 → prompt prefix 复用机会。
    实际是否命中 prefix cache 取决于 LLM provider（DeepSeek/OpenAI 等），
    本 tracker 只负责统计 sys_hash 复用次数。

    V0.30.6 C1.1 增强：
    - cost_saved_cny 估算：基于 (prefix_hits / total) × avg_input_cost_per_call
    - 用户可通过 tracker.cost_saved_cny 直接看到 ¥ 节省金额
    """

    # === 核心计数器 ===
    prefix_hits: int = 0  # sys_hash 复用次数（prefix cache 命中机会）
    prefix_misses: int = 0  # 首次出现 sys_hash（无 prefix 复用）

    # === 节省估算（V0.30.6 C1.1）===
    # 假设：
    # - avg_input_tokens_per_call: 5000（典型章节 prompt input）
    # - cache_hit_ratio_in_provider: 1.00（sys_hash 复用时 provider 通常命中）
    # - cache_hit_price_cny_per_m: 0.02（DeepSeek flash hit）
    # - cache_miss_price_cny_per_m: 1.00（DeepSeek flash miss）
    avg_input_tokens_per_call: int = 5000
    cache_hit_price_cny_per_m: float = 0.02
    cache_miss_price_cny_per_m: float = 1.00

    # === 已知 sys_hashes（用于检测复用）===
    _seen_sys_hashes: set[str] = field(default_factory=set)

    def record(self, sys_hash: str) -> bool:
        """记录一次 prompt 调用，返回 True = prefix hit（sys_hash 复用）。

        Args:
            sys_hash: V0.24 _make_cache_key() 计算的 sys_h
                （sha256(system)[:16]）

        Returns:
            True = prefix hit（sys_hash 之前见过，LLM provider 可复用 prefix）
            False = prefix miss（sys_hash 首次出现）
        """
        if sys_hash in self._seen_sys_hashes:
            self.prefix_hits += 1
            return True
        self._seen_sys_hashes.add(sys_hash)
        self.prefix_misses += 1
        return False

    @property
    def total(self) -> int:
        """总调用次数 = prefix_hits + prefix_misses。"""
        return self.prefix_hits + self.prefix_misses

    @property
    def hit_rate(self) -> float:
        """Prefix 命中率（0.0-1.0）。"""
        if self.total == 0:
            return 0.0
        return round(self.prefix_hits / self.total, 4)

    @property
    def unique_sys_prompts(self) -> int:
        """唯一 sys_prompt 数量（实际 distinct system prompt 数）。"""
        return len(self._seen_sys_hashes)

    @property
    def cost_saved_cny(self) -> float:
        """估算节省的 ¥（基于 prefix hit rate + cache price 差）。

        每次 prefix hit 节省：(miss_price - hit_price) × input_tokens / 1M
        默认配置：(1.00 - 0.02) × 5000 / 1M = 0.0049 CNY/call

        V0.30.6 C1.1：返回节省总额。
        """
        saved_per_call = (
            (self.cache_miss_price_cny_per_m - self.cache_hit_price_cny_per_m)
            * self.avg_input_tokens_per_call
            / 1_000_000
        )
        return round(self.prefix_hits * saved_per_call, 6)

    @property
    def potential_savings_cny(self) -> float:
        """如果 100% prefix hit 时的总节省（理论上界）。

        用于计算"还有多少 ¥ 没赚到"（如果 prefix miss 多 → 还有节省空间）。
        """
        saved_per_call = (
            (self.cache_miss_price_cny_per_m - self.cache_hit_price_cny_per_m)
            * self.avg_input_tokens_per_call
            / 1_000_000
        )
        return round(self.total * saved_per_call, 6)

    def to_dict(self) -> dict[str, object]:
        """导出为 dict（用于 /api/cache/prompt-stats + Web UI）。"""
        return {
            "enabled": True,
            "prefix_hits": self.prefix_hits,
            "prefix_misses": self.prefix_misses,
            "total": self.total,
            "hit_rate": self.hit_rate,
            "unique_sys_prompts": self.unique_sys_prompts,
            "cost_saved_cny": self.cost_saved_cny,
            "potential_savings_cny": self.potential_savings_cny,
            "model": {
                "avg_input_tokens_per_call": self.avg_input_tokens_per_call,
                "cache_hit_price_cny_per_m": self.cache_hit_price_cny_per_m,
                "cache_miss_price_cny_per_m": self.cache_miss_price_cny_per_m,
            },
        }

    def reset(self) -> None:
        """重置所有计数器（V0.30.6 C1：用于测试或手动 reset）。"""
        self.prefix_hits = 0
        self.prefix_misses = 0
        self._seen_sys_hashes.clear()
