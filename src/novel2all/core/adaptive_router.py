"""V0.30.6 C3：自适应路由（按历史表现自动切模型）。

设计：
1. 每次 LLM 调用后 record(task, model, success, latency_ms, quality_score)
2. select(task) 根据历史数据选最佳模型
3. 4 种策略：best_avg / best_quality / best_speed / best_success
4. 冷启动：样本数 < min_samples 时用 default 路由
5. 滑动窗口：只考虑最近 N 次（默认 50）

数据模型（SQLite）：
- model_runs(id, task_type, model, success, latency_ms, quality_score, ts)
- 索引：idx_runs_task_model(task_type, model, ts DESC)

与 V0.23 router 集成：
- select() 返回历史最佳模型（而非 config 指定的）
- fallback() 仍走 V0.23 逻辑
"""

from __future__ import annotations

import enum
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from novel2all.core.provider_router import TaskType

logger = logging.getLogger(__name__)


# === Constants ===

DEFAULT_DB_PATH: ClassVar[Path] = Path(".novel2all/adaptive_routing.db")
DEFAULT_MIN_SAMPLES = 5  # 冷启动：样本数 < N 用 default
DEFAULT_WINDOW_SIZE = 50  # 滑动窗口：只考虑最近 N 次


# === Strategy ===


class AdaptiveStrategy(str, enum.Enum):
    """V0.30.6 C3：自适应路由策略。"""

    BEST_AVG = "best_avg"  # 加权综合分（推荐）
    BEST_QUALITY = "best_quality"  # 优先质量（适合编辑/审校）
    BEST_SPEED = "best_speed"  # 优先速度（适合实时）
    BEST_SUCCESS = "best_success"  # 优先成功率（适合关键任务）


@dataclass
class ModelStats:
    """V0.30.6 C3：单模型在单任务上的统计数据。"""

    model: str
    task: TaskType
    samples: int
    success_rate: float  # 0.0-1.0
    avg_latency_ms: float  # 平均延迟
    avg_quality: float  # 平均质量分（0-10）
    score: float  # 综合分（策略加权）

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "task": self.task.value,
            "samples": self.samples,
            "success_rate": round(self.success_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "avg_quality": round(self.avg_quality, 2),
            "score": round(self.score, 4),
        }


# === Adaptive Router ===


class AdaptiveRouter:
    """V0.30.6 C3：自适应路由器。

    用法：
        router = AdaptiveRouter(default_model="deepseek/deepseek-flash")
        # 1. LLM 调用后记录
        router.record_run(TaskType.WRITING, "deepseek/deepseek-flash",
                          success=True, latency_ms=3200, quality_score=8.5)
        # 2. 选择最佳模型
        model = router.select(TaskType.WRITING)
    """

    DEFAULT_WEIGHTS: ClassVar[dict[str, float]] = {
        # best_avg 策略的权重（success + speed + quality）
        "success": 0.5,
        "speed": 0.2,
        "quality": 0.3,
    }

    def __init__(
        self,
        *,
        default_model: str = "deepseek/deepseek-flash",
        strategy: AdaptiveStrategy = AdaptiveStrategy.BEST_AVG,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        window_size: int = DEFAULT_WINDOW_SIZE,
        db_path: Path | None = None,
    ) -> None:
        """V0.30.6 C3：初始化自适应路由器。

        Args:
            default_model: 冷启动 / 无数据时的默认模型
            strategy: 选择策略（best_avg 默认）
            min_samples: 触发自适应所需的最少样本数
            window_size: 滑动窗口大小（每个 task × model 只看最近 N 次）
            db_path: SQLite 路径（None 用 default）
        """
        self.default_model = default_model
        self.strategy = strategy
        self.min_samples = min_samples
        self.window_size = window_size
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """V0.30.6 C3：初始化 SQLite 表。

        V1.0.2 B3：增加 ``idx_model_runs_task_model`` UNIQUE INDEX — record_run 用
        ``INSERT ... ON CONFLICT DO UPDATE`` 原子聚合（task_type, model）维度的累计统计，
        避免原 read-modify-write 模式在多线程下丢计数。
        """
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS model_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT NOT NULL,
                    model TEXT NOT NULL,
                    samples INTEGER NOT NULL DEFAULT 0,
                    latency_sum_ms REAL NOT NULL DEFAULT 0,
                    quality_sum REAL NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    success INTEGER NOT NULL,
                    latency_ms REAL NOT NULL,
                    quality_score REAL,
                    ts REAL NOT NULL,
                    last_updated REAL
                );
                CREATE INDEX IF NOT EXISTS idx_runs_task_model
                    ON model_runs(task_type, model, ts DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_model_runs_task_model
                    ON model_runs(task_type, model);
            """)

    # === Recording ===

    def record_run(
        self,
        task: TaskType,
        model: str,
        *,
        success: bool,
        latency_ms: float,
        quality_score: float | None = None,
    ) -> None:
        """V0.30.6 C3：记录一次 LLM 调用结果。

        Args:
            task: 任务类型
            model: 使用的模型名
            success: 是否成功
            latency_ms: 端到端延迟
            quality_score: 质量分（0-10，可选，由 B1 review 提供）

        V1.0.2 B3：用 ``INSERT ... ON CONFLICT DO UPDATE`` 原子聚合累计统计列
        （samples / latency_sum_ms / quality_sum / success_count），避免 V0.30.6
        旧版 read-modify-write 模式在多线程并发下丢计数（race condition）。

        Schema 要求：``idx_model_runs_task_model`` UNIQUE INDEX on (task_type, model)
        —— 由 ``_init_db()`` 创建。
        """
        now = time.time()
        # V1.0.2 B3：用单条 SQL 原子聚合（threading.Lock 仍然保留，保护
        # SELECT 读取时的视图一致性；写入路径由 SQLite 内置锁 + UNIQUE INDEX
        # 提供原子性，多线程并发不会丢计数）。
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO model_runs
                    (task_type, model, samples, latency_sum_ms, quality_sum,
                     success_count, success, latency_ms, quality_score, ts, last_updated)
                    VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(task_type, model) DO UPDATE SET
                        samples = samples + 1,
                        latency_sum_ms = latency_sum_ms + excluded.latency_ms,
                        quality_sum = quality_sum + COALESCE(excluded.quality_score, 0),
                        success_count = success_count + excluded.success,
                        success = excluded.success,
                        latency_ms = excluded.latency_ms,
                        quality_score = excluded.quality_score,
                        ts = excluded.ts,
                        last_updated = excluded.last_updated""",
                (
                    task.value,
                    model,
                    float(latency_ms),
                    float(quality_score) if quality_score is not None else 0.0,
                    1 if success else 0,
                    1 if success else 0,
                    float(latency_ms),
                    quality_score,
                    now,
                    now,
                ),
            )

    # === Statistics ===

    def get_stats(self, task: TaskType, model: str) -> ModelStats | None:
        """V0.30.6 C3：查单 (task, model) 统计。

        V1.0.2 B3：改为读聚合列（samples / latency_sum_ms / success_count /
        quality_sum），与 record_run 的原子写入对齐。
        原 V0.30.6 实现用 ``ORDER BY ts DESC LIMIT window_size`` 取最近 N 条逐条聚合；
        新实现 record_run 只在 (task_type, model) 唯一行上累加聚合列，
        get_stats 直接读这行（O(1) vs 旧版 O(N)）。

        行为差异（旧 → 新）：
        - 旧：每次按窗口重算 stats（"最近 N 次平均"，窗口滑动语义）。
        - 新：累计所有历史记录（窗口语义移交给 ``cleanup_old_runs`` + 周期性 reset）。

        为保持 V0.30.6 测试的 ``avg_quality == 5.0`` 兜底语义：聚合列里 quality_sum
        为 0 时（说明所有 record_run 都没传 quality_score），仍返回 5.0 中位数。
        """
        with self._lock, sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """SELECT samples, latency_sum_ms, quality_sum, success_count
                   FROM model_runs
                   WHERE task_type = ? AND model = ?
                   LIMIT 1""",
                (task.value, model),
            )
            row = cur.fetchone()
        if not row:
            return None

        samples, latency_sum, quality_sum, success_count = row
        if samples == 0:
            return None
        # V1.0.2 B3：聚合列由 record_run 原子维护，直接除以 samples
        avg_latency = latency_sum / samples
        success_rate = success_count / samples
        # V0.30.6 兼容：无 quality 时仍返回 5.0 中位数
        avg_quality = quality_sum / samples if quality_sum > 0 else 5.0

        score = self._compute_score(success_rate, avg_latency, avg_quality)
        return ModelStats(
            model=model,
            task=task,
            samples=samples,
            success_rate=success_rate,
            avg_latency_ms=avg_latency,
            avg_quality=avg_quality,
            score=score,
        )

    def get_all_stats_for_task(self, task: TaskType) -> dict[str, ModelStats]:
        """V0.30.6 C3：查 task 下所有模型的统计。

        V1.0.2 B3：用 ``DISTINCT model`` 找所有模型 + 逐个 ``get_stats()``。
        聚合列已是 task+model 维度的一行，``get_stats()`` 直接读，无需 GROUP BY。
        """
        with self._lock, sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                """SELECT DISTINCT model FROM model_runs WHERE task_type = ?""",
                (task.value,),
            )
            models = [row[0] for row in cur.fetchall()]
        result: dict[str, ModelStats] = {}
        for m in models:
            stats = self.get_stats(task, m)
            if stats is not None:
                result[m] = stats
        return result

    # === Selection ===

    def select(self, task: TaskType) -> str:
        """V0.30.6 C3：根据历史数据选最佳模型。

        冷启动：样本 < min_samples → 返回 default_model
        否则：按 strategy 选最高分模型
        """
        stats = self.get_all_stats_for_task(task)
        if not stats:
            logger.debug("C3 cold-start: no data for %s → %s", task.value, self.default_model)
            return self.default_model

        # 过滤：只考虑有足够样本的模型
        qualified = {m: s for m, s in stats.items() if s.samples >= self.min_samples}
        if not qualified:
            # 样本数都 < min_samples → 全部按 default
            logger.debug(
                "C3 cold-start: insufficient samples for %s (have %d models) → %s",
                task.value,
                len(stats),
                self.default_model,
            )
            return self.default_model

        # 选最高分
        best_model = max(qualified, key=lambda m: qualified[m].score)
        logger.debug(
            "C3 select %s → %s (score=%.3f, %d samples)",
            task.value,
            best_model,
            qualified[best_model].score,
            qualified[best_model].samples,
        )
        return best_model

    # === Scoring ===

    def _compute_score(
        self,
        success_rate: float,
        avg_latency_ms: float,
        avg_quality: float,
    ) -> float:
        """V0.30.6 C3：根据策略计算综合分（0-1）。"""
        if self.strategy == AdaptiveStrategy.BEST_AVG:
            return self._score_avg(success_rate, avg_latency_ms, avg_quality)
        if self.strategy == AdaptiveStrategy.BEST_QUALITY:
            return avg_quality / 10.0
        if self.strategy == AdaptiveStrategy.BEST_SPEED:
            # 越快越高分（latency=0 → 1.0, latency=30s+ → 0.0）
            return max(0.0, 1.0 - avg_latency_ms / 30000.0)
        # BEST_SUCCESS
        return success_rate

    def _score_avg(
        self,
        success_rate: float,
        avg_latency_ms: float,
        avg_quality: float,
    ) -> float:
        """V0.30.6 C3：best_avg 加权综合分。

        公式：w1*success + w2*speed + w3*quality
        - success: 0-1
        - speed: 1 - min(latency/30s, 1.0)（30s+ 视为最低）
        - quality: avg_quality / 10
        """
        weights = self.DEFAULT_WEIGHTS
        speed_score = max(0.0, 1.0 - avg_latency_ms / 30000.0)
        quality_score = avg_quality / 10.0
        return (
            weights["success"] * success_rate
            + weights["speed"] * speed_score
            + weights["quality"] * quality_score
        )

    # === Maintenance ===

    def cleanup_old_runs(self, max_age_seconds: int = 90 * 24 * 3600) -> int:
        """V0.30.6 C3：清理 90 天前的旧 runs（防止 DB 无限增长）。

        Returns:
            删除的行数
        """
        cutoff = time.time() - max_age_seconds
        with self._lock, sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM model_runs WHERE ts < ?", (cutoff,))
            return cur.rowcount

    def clear(self) -> None:
        """V0.30.6 C3：清空所有历史（用于 reset）。"""
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM model_runs")
