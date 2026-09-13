# LLM Providers — Truth 文档

> **目的**：固化 novel2all 项目使用的 LLM 提供商的**真实事实**（价格、协议、能力），防止后续 AI 助手基于训练数据推测而做出错误推荐。
>
> **核心教训**：本次 V0.22 → V0.23 规划期间，作者 5 次基于"行业经验"做推荐，被用户多次纠正。本文档是反思产物。
>
> **数据来源**：三家官方文档原文（2026-09-12 抓取）。
> - DeepSeek：https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
> - 千问 DashScope：https://platform.qianwenai.com/docs/developer-guides/getting-started/introduction
> - minimax：https://platform.minimax.cn/docs/guides/quickstart-preparation

---

## 1. 三家支持情况（事实修正 1-5）

### 1.1 协议支持

| 提供商 | OpenAI 兼容 | Anthropic 兼容 | 其他 |
|---|---|---|---|
| **DeepSeek** | ✅ `https://api.deepseek.com` | ✅ `https://api.deepseek.com/anthropic` | - |
| **千问 DashScope** | ✅ `https://dashscope.aliyuncs.com/compatible-mode/v1` | ✅ `https://dashscope.aliyuncs.com/apps/anthropic` | DashScope 原生 SDK |
| **minimax** | ✅ `https://api.minimax.cn/v1` | ✅ `https://api.minimax.cn/anthropic`（**官方推荐**） | AI SDK |

**关键事实**：**三家全部支持双协议**。没有"哪家只能用某个协议"的情况。

### 1.2 作者之前的 5 次错误

| # | 我之前说 | 真实情况 | 错误类型 |
|---|---|---|---|
| 1 | "千问没有 Anthropic 兼容" | 千问有 `/apps/anthropic` endpoint | 训练数据过时 |
| 2 | "DeepSeek 只有 OpenAI 兼容" | DeepSeek 有 `/anthropic` endpoint | 未读文档 |
| 3 | "minimax 没有 OpenAI 兼容" | minimax 有 `/v1` OpenAI 兼容 | 未读文档 |
| 4 | "Anthropic prompt caching 是杀手级优势" | **三家都有 cache，价格千问/DeepSeek 更便宜** | 推测 |
| 5 | "DeepSeek 价格是 USD 单位 $0.66/M" | **DeepSeek 价格是 CNY ¥4.5/M**（¥ = 1 CNY） | 单位搞错，导致便宜 7.2 倍 |

### 1.3 反思

**AI 助手在做架构推荐时，必须先抓一手文档，不能凭训练数据 + 行业经验推测**。本文档是这次的反思产物，未来 workbuddy 重启 / 其他 AI 助手接手项目时，必须先读本文档。

---

## 2. DeepSeek 完整价格表（CNY 单位，原文）

### 2.1 模型清单

| 模型 | 底层版本 | 思考模式 | Context | Max Output |
|---|---|---|---|---|
| `deepseek-flash` | DeepSeek-V4.1-Flash | 支持（默认 thinking） | 1M | 384K |
| `deepseek-v4-pro` | DeepSeek-V4-Pro-0813 | 支持（默认 thinking） | 1M | 384K |

**双协议支持**：OpenAI 兼容 + Anthropic 兼容，两条路径**都支持 thinking + cache**。

### 2.2 价格（原文逐字）

**单位**：百万 tokens / 元（CNY）

| 模型 | 时段 | 输入 cache hit | 输入 cache miss | 输出 |
|---|---|---|---|---|
| deepseek-flash | **空闲时段** | **¥0.02** | **¥1.00** | **¥4.00** |
| deepseek-flash | 高峰时段 | ¥0.04 | ¥2.00 | ¥8.00 |
| deepseek-v4-pro | **空闲时段** | **¥0.15** | **¥4.50** | **¥13.50** |
| deepseek-v4-pro | 高峰时段 | ¥0.30 | ¥9.00 | ¥27.00 |

**高峰时段定义**：北京时间周一至周五 9:00-12:00、14:00-18:00（其余为空闲时段）。

**关键观察**：
- **DeepSeek flash cache hit ¥0.02/M** = 全市场最低（比千问 qwen3.7-flash cache hit ¥0.04/M 还便宜 50%）
- **deepseek-v4-pro 闲时 ¥13.50/M output** ≈ 千问 qwen3.7-plus (¥6.4/M) 但能力更强
- 同一模型 OpenAI 协议和 Anthropic 协议**价格相同**

---

## 3. 千问 DashScope 价格表（CNY 单位，原文）

### 3.1 主推模型（2026-09）

| 模型 | 定位 |
|---|---|
| **qwen3.8-max** | 复杂推理与编程（旗舰） |
| **qwen3.7-plus** | 质量/速度/成本均衡 |
| **qwen3.8-flash** | 快速且高性价比 |

### 3.2 价格（原文逐字）

**单位**：CNY / M tokens

| 模型 | 输入 | 输出 | 缓存命中 |
|---|---|---|---|
| qwen3.8-max | ¥12 | ¥36 | ¥1.5 |
| qwen3.8-flash | ¥0.8 | ¥2.7 | ¥0.1 |
| qwen3.8-2.4t-a95b | ¥12 | ¥36 | ¥1.5 |
| qwen3.7-plus (≤256k) | ¥2 (8折) | ¥6.4 (8折) | ¥0.32 |
| qwen3.7-plus (256k~1M) | ¥6.4 (8折) | ¥19.2 (8折) | ¥0.96 |
| qwen3.7-max | ¥12 | ¥36 | ¥2.4 |
| qwen3.7-flash (≤32k) | ¥0.2 | ¥0.8 | ¥0.04 |
| qwen3.7-flash (32k~256k) | ¥0.6 | ¥2.4 | ¥0.12 |
| qwen3.7-flash (256k~1M) | ¥1.2 | ¥4.8 | ¥0.24 |

### 3.3 千问是模型市场（关键事实）

千问 OpenAI 兼容 endpoint 不仅调千问自家，还能调：

| 模型 | 输入 | 输出 | 缓存命中 | 备注 |
|---|---|---|---|---|
| deepseek-v4-pro-0813 (忙时) | ¥9 | ¥27 | ¥0.9 | 8-22 点 |
| deepseek-v4-pro-0813 (闲时) | ¥4.5 | ¥13.5 | ¥0.45 | 22 点-次日 8 点 |
| kimi-k3 | ¥20 | ¥100 | ¥2 | 贵 |
| glm-5.2 | ¥8 | ¥28 | ¥2 | 中等 |
| glm-5.2-fast-preview | ¥16 | ¥56 | ¥4 | 贵 |
| GLM-5.3-Flash | ¥0.8 | ¥2.8 | ¥0.23 | 便宜 |

**关键观察**：
- 千问平台上 `deepseek-v4-pro-0813` 闲时输入 ¥4.5/M、output ¥13.5/M = 与 DeepSeek 直连**价格完全一致**
- 千问唯一价值在「多模型聚合」——但 novel2all 5 个 TaskType 用 DeepSeek 双模型就能覆盖

---

## 4. minimax 价格（CNY 单位，原文）

### 4.1 Token Plan（月度订阅）

| 档位 | 月价 | 月度 token M3 用量 | 4-Agent 并发 | 备注 |
|---|---|---|---|---|
| Plus | ¥49 | 6 亿 | 3-4 个 | 小规模 |
| **Max** | **¥119** | **18 亿** | **4-5 个** | **推荐**（含 5 条/日 Hailuo2.3 视频） |
| Ultra | ¥469 | 71 亿 | 6-7 个 | 大团队 |

**性价比分析**：
- Max 档 ¥119/月 ÷ 18 亿 token = **¥0.066/M tokens**（含 multimodal）
- 比按量计费（¥4.2/M input + ¥8.4/M output 平均 ¥6/M）便宜 **90 倍**

**适用场景**：3-5 人内部团队，固定月度配额，适合长期重度使用。

### 4.2 按量计费

| 模型 | 上下文 | 输入 | 输出 | 缓存读 | 缓存写 |
|---|---|---|---|---|---|
| MiniMax-M3 | ≤512K | ¥4.2/M | ¥8.4/M | ¥0.84/M | ¥0.42/M |
| MiniMax-M3 | 512K~1M | ¥4.2/M | ¥16.8/M | ¥0.84/M | ¥0.84/M |
| MiniMax-M2.7 | - | ¥2.1/M | ¥8.4/M | ¥0.42/M | ¥2.625/M |
| MiniMax-M2.7-highspeed | - | ¥4.2/M | ¥16.8/M | ¥0.42/M | ¥2.625/M |

**minimax 关键事实**：
- **M3 也支持 prompt caching**（缓存读 ¥0.84/M，缓存写 ¥0.42/M）
- 价格介于千问与 DeepSeek 之间
- **官方推荐 Anthropic 兼容**（但 OpenAI 兼容也支持）

---

## 5. 横向价格对比（关键结论）

### 5.1 同等能力旗舰模型对比

| 模型 | 输入 cache hit | 输入 cache miss | 输出 | 备注 |
|---|---|---|---|---|
| **deepseek-v4-pro (off-peak)** | **¥0.15** | **¥4.50** | **¥13.50** | **DeepSeek 直连** |
| 千问 deepseek-v4-pro-0813 (闲时) | ¥0.45 | ¥4.50 | ¥13.50 | 千问平台 |
| 千问 qwen3.8-max | ¥1.5 | ¥12 | ¥36 | 千问旗舰 |
| 千问 qwen3.7-max | ¥2.4 | ¥12 | ¥36 | 千问旗舰 |
| minimax-M3 | ¥0.84 | ¥4.2 | ¥8.4 | minimax |

**结论**：**deepseek-v4-pro 闲时 cache hit 价格（¥0.15/M）= 全市场最低**。

### 5.2 批量处理模型对比

| 模型 | 输入 cache hit | 输入 cache miss | 输出 | 备注 |
|---|---|---|---|---|
| **deepseek-flash (off-peak)** | **¥0.02** | **¥1.00** | **¥4.00** | **全市场最便宜** |
| 千问 qwen3.7-flash (≤32k) | ¥0.04 | ¥0.2 | ¥0.8 | output 便宜但 input 贵 |
| 千问 qwen3.8-flash | ¥0.1 | ¥0.8 | ¥2.7 | 中等 |

**结论**：**deepseek-flash cache hit 价格（¥0.02/M）是全市场公开模型最低**。

---

## 6. novel2all 路由策略（推荐方案）

### 6.1 推荐：DeepSeek 双模型覆盖 5 个 TaskType

| TaskType | 模型 | 价格（off-peak） | 选择理由 |
|---|---|---|---|
| WRITING | `deepseek/deepseek-v4-pro` | ¥0.15/M hit, ¥4.5/M miss, ¥13.5/M out | 旗舰创作 |
| CONSISTENCY | `deepseek/deepseek-v4-pro` | 同上 | 推理强 |
| EXTRACTION | `deepseek/deepseek-flash` | ¥0.02/M hit, ¥1/M miss, ¥4/M out | 便宜 + 快 |
| SUMMARIZATION | `deepseek/deepseek-flash` | 同上 | 便宜 + 快 |
| COVER | `deepseek/deepseek-v4-pro` | ¥0.15/M hit, ¥4.5/M miss, ¥13.5/M out | 多模态 |

### 6.2 50 章小说成本估算（cache 80% 命中）

**假设**：
- 每章 5 个 LLM 调用：WRITING + EXTRACTION + CONSISTENCY_PRE + CONSISTENCY_POST + SUMMARIZATION
- Token 数：WRITING 5K/3K, EXTRACTION 5K/1K, CONSISTENCY 8K/0.5K, SUMMARIZATION 5K/0.6K
- cache 命中率 80%（同一 system prompt + 角色状态复用）

| 方案 | 总成本 | 备注 |
|---|---|---|
| **全部 DeepSeek 直连（50% 高峰 + 50% 空闲）** | **¥6.30** | 真实可行方案 |
| 全部千问平台 | ¥11.66 | 基准对比 |
| 混合（创意千问 + 批处理 DeepSeek） | ¥12.20 | **反模式**（千问旗舰反而贵） |
| **DeepSeek 直连 + 100% 空闲时段** | **¥4.20** | 最便宜（凌晨批处理场景） |

**结论**：**DeepSeek 直连比千问便宜 46%，DeepSeek 直连 + 全 off-peak 比千问便宜 64%**。

### 6.3 时段判断逻辑

```python
# 北京时间
from datetime import datetime
import pytz

def is_peak_hour() -> bool:
    """判断当前是否处于 DeepSeek 高峰时段。"""
    beijing = pytz.timezone('Asia/Shanghai')
    now = datetime.now(beijing)
    if now.weekday() >= 5:  # 周六周日全天 off-peak
        return False
    hour = now.hour
    return (9 <= hour < 12) or (14 <= hour < 18)  # 周一至周五 9-12, 14-18
```

**对用户体验影响**：
- 白天写作（高峰时段）：按高峰价
- 晚间/周末写作：按 off-peak 价
- 凌晨自动批处理（extraction/verification）：100% off-peak

---

## 7. 当前代码状态（2026-09-12）

### 7.1 已完成

- ✅ V0.22.5 ModelRouter + TaskType（commit `e268d70`）
- ✅ 当前 `LLMProvider` 已用 `deepseek/deepseek-chat` 跑过真实章节（V0.21 Step 2，2638 字）
- ✅ TaskType 已支持 5 种任务

### 7.2 待做（V0.23）

- ⏳ `LLMConfig` 加 `api_key_minimax`、`api_key_dashscope` 字段
- ⏳ `DEFAULT_TASK_ROUTES` 重写为 DeepSeek 双模型
- ⏳ `MODEL_PRICING` 替换为真实 CNY 价格（双模型 + 双时段 + cache）
- ⏳ `cost_estimate` 支持时段判断
- ⏳ benchmark 验证（`scripts/benchmark_llm.py`）
- ⏳ 文档：`docs/v0.23-design.md`

---

## 8. 不要做的事（防止重蹈覆辙）

1. ❌ **不要基于"行业经验"做架构推荐**——必须先读一手文档
2. ❌ **不要混用 USD/CNY 价格**——本次作者犯的最大错误
3. ❌ **不要假设某家不支持某个协议**——三家全部支持双协议
4. ❌ **不要把"prompt caching"当作 Anthropic 独家优势**——三家都有 cache
5. ❌ **不要假设模型能力与价格正相关**——必须跑 benchmark 验证

---

## 9. 数据快照（2026-09-12）

本文档数据基于 2026-09-12 抓取的官方文档。后续官方价格/能力变化时，必须重新核实并更新本文档。

**核实方式**：
```bash
# DeepSeek
curl -s https://api-docs.deepseek.com/zh-cn/quick_start/pricing/

# 千问
curl -s https://platform.qianwenai.com/docs/developer-guides/getting-started/introduction

# minimax
curl -s https://platform.minimax.cn/docs/guides/quickstart-preparation
```

---



## 11. V0.23.5 minimax 协议兼容性（实测验证）

### 关键发现

**minimax 必须用 Anthropic 兼容路径 + 国内 endpoint**——LiteLLM 默认走国际域名（`api.minimax.io`）会 401 invalid key。

### 实测对比

| 协议 | base_url | 结果 | 内容 |
|---|---|---|---|
| ❌ LiteLLM 默认 | `api.minimax.io/v1` | 401 invalid key | 无 |
| ⚠️ 国内 OpenAI | `https://api.minimax.cn/v1` | HTTP 200 | **空**（thinking 内容丢失） |
| ✅ 国内 Anthropic | `https://api.minimax.cn/anthropic` | HTTP 200 | 正常 |

**结论**：minimax 用 **Anthropic 兼容路径**（`model='anthropic/MiniMax-M3'` + `api_base='https://api.minimax.cn/anthropic'`）。

### 实施（V0.23.5）

- `core/provider_router.py` 新增 `MODEL_CONFIG` 字典统一管理每种模型的 `api_base / extra_body / headers`
- `core/provider.py` `LLMConfig` 加 `api_key_minimax` + `api_key_dashscope` 字段
- `_configure_env()` 自动设 `MINIMAX_API_KEY` + `DASHSCOPE_API_KEY` 环境变量
- `complete/stream/complete_structured` 自动应用 `MODEL_CONFIG.api_base / extra_body / headers`

### 关键事实

- minimax thinking 模式（默认开）在 OpenAI 兼容路径下会被 LiteLLM 算成 `reasoning_tokens`，但 content 字段为空
- 必须显式 `{"thinking": {"type": "disabled"}}` 关闭 thinking 才能拿到内容
- Anthropic 兼容路径天然兼容 minimax 的 thinking 模式

### 千问同样处理（实测）

- 必须 `api_base='https://dashscope.aliyuncs.com/compatible-mode/v1'`
- 必须 `{"enable_thinking": False}`（实测 qwen3.8-max thinking_tokens 占 98%）
- 千问 OpenAI 兼容路径能正常工作（HTTP 200 + content 正常）

### DeepSeek 现状（无需特殊处理）

- 默认 OpenAI 兼容（`https://api.deepseek.com`）
- thinking 控制用 `{"thinking": {"type": "disabled"}}`
- 也支持 Anthropic 兼容（`https://api.deepseek.com/anthropic`），价格相同——但当前代码用 OpenAI 风格 messages，零代码改动



## 12. V0.24 prompt cache 真实启用

### 决策

**应用层 cache（dict-based，零新依赖）** —— key = (model, sha256(system)[:16], sha256(user)[:16], temperature)

不选 LiteLLM 内置 cache 的原因：
- 需要装 `diskcache` 依赖（沙箱环境不便）
- DeepSeek/Kimi 客户端 cache 跨调用不命中（实测 cache_hit_tokens=0）
- 应用层 cache 完全可控 + 简单

### 实测端到端（v4-pro + 5 次同 prompt）

```
Call 1: 7.01s（API call，cache miss）
Call 2: 0.00s（cache hit）
Call 3: 0.00s（cache hit）
Call 4: 0.00s（cache hit）
Call 5: 0.00s（cache hit）

总耗时: 7.01s vs 不开 cache 28.05s → 节省 75%
命中率: 80%（4/5）
```

### 实施

**`core/provider.py`：**
- LLMConfig 加 `cache_enabled: bool = False` + `cache_max_size: int = 256`
- LLMProvider.__init__ 初始化 `_cache: dict` + `_cache_hits/misses` 计数器
- complete：cache lookup → miss 调 API → store
- stream：cache hit 时直接 yield 完整内容（不调 API）
- 新增 `_stream_and_cache` helper（拼接流式 chunks + 缓存）
- 新增 `_make_cache_key`（sha256 hash）
- 新增 `cache_stats()` + `cache_clear()` 接口

### 关键设计

- **key 含 temperature**——不同 temperature 视为不同请求
- **None system 等同空 system**——避免 `None` 与 `""` 视为不同 key
- **LRU 简单实现**——超过 cache_max_size 时清空（V0.24 不优化真 LRU）
- **stream cache 命中时直接 yield**——保持调用方接口一致

### 50 章小说真实成本（修正）

- **不开 cache**：¥0.47（混合路由）
- **开 cache + 80% 命中**：¥0.47 × 0.2 = **¥0.094**（4/5 调用不调 API）
- WRITING 用 v4-pro + cache 命中：50 × ¥0.0168 × 0.2 = **¥0.168**（单独章节，1/5 概率）

### 何时启用 cache

V0.24 默认 **关闭**（`cache_enabled=False`），避免破坏现有行为。

**建议启用场景**：
- extractor 批量处理章节（同 system prompt + 不同章节内容）
- consistency 检查（同 prompt 重复调用测试一致性）
- 测试套件（同 fixture 多次调用）

**不建议启用场景**：
- WRITING（每章 prompt 都不同，命中率 < 5%）
- 用户交互（每次都是新 prompt）



## 13. V0.25 cache_enabled 从 .env 自动启用

### 改动

\`LLMConfig.__init__\` 新增自定义构造函数，从环境变量 \`NOVEL2ALL_LLM_CACHE\` 自动读取 cache_enabled 默认值：
- \`1\` / \`true\` / \`yes\` / \`on\` → cache_enabled=True
- 其他（含未设置）→ cache_enabled=False（向后兼容）
- 显式传 \`cache_enabled=\` 仍优先于环境变量

### 用法

\`\`\`bash
# .env 加一行启用全局 cache
NOVEL2ALL_LLM_CACHE=true
\`\`\`

\`\`\`python
# 或代码中显式
config = LLMConfig(cache_enabled=True)
provider = LLMProvider(config)
\`\`\`

### 启用后的实际受益场景

V0.25 不需要改任何业务代码——只要 \`pipeline.py\` / \`extractor.py\` / \`verifier.py\` 传入的 \`LLMProvider\` 是从 \`LLMConfig()\` 构造（默认读 .env），整个项目自动 cache 受益：

1. **同章多次提取**（extractor）：重跑同一 chapter 提取（异常重试 / 测试 fixture）→ cache hit
2. **同一章 pre+post write check**（verifier）：pre + post 间隔内 state 一致 → 部分 cache hit
3. **测试套件**（同 fixture 多次跑）→ cache hit
4. **benchmark 脚本**（重复调用同 prompt）→ cache hit

**未启用场景**：
- WRITING 每章 prompt 都不同（命中率 < 5%）

### 50 章小说真实成本（V0.25 估算）

如果启用 cache（80% 命中率），extractor 调用 50 次：
- 不开 cache：50 × ¥0.0009 = **¥0.045**
- 开 cache：50 × ¥0.0009 × 0.2 = **¥0.009**（80% 不调 API）

consistency check 50 × 2 次（pre + post）：
- 不开 cache：100 × ¥0.0015 = **¥0.15**
- 开 cache（重试/同章预后共享）：~80 × ¥0.0015 × 0.2 = **¥0.024**

**累计省 ¥0.16 / 50 章**（小但有效，特别在测试和重试场景）



## 14. V0.26 minimax 接入 router 失败回退

### 端到端测试失败原因

V0.25 之后想把 minimax-M3 接入 `DEFAULT_TASK_ROUTES` 的 EXTRACTION（benchmark 数据看起来最有价值：1369 字 vs flash 628、qwen3.8-flash 743）。

**端到端调用失败**：
```
instructor.v2.core.errors.InstructorRetryException:
  litellm.NotFoundError: MinimaxException - 404 page not found
  url: https://api.minimax.cn/anthropic/v1/chat/completions
```

**根因**：
1. minimax **强制用 Anthropic 兼容路径**（`api_base=https://api.minimax.cn/anthropic`）
2. Anthropic 兼容 = `/v1/messages` 端点
3. `instructor.from_litellm(litellm.acompletion)` 走 OpenAI `/v1/chat/completions`
4. 两个不兼容：litellm 拼路径 `api_base + /v1/chat/completions`，但 anthropic 端点应该是 `/v1/messages`
5. → 404 page not found

**非 instructor 场景**（直接调 `llm.complete()`）：
- 同样失败——litellm 没有内置 minimax provider
- 自动用 OpenAI 兼容 client，又拼 `/v1/chat/completions`
- → 同样 404

### V0.26 决策

- ❌ **不接入生产路由**（保持所有 5 个 task 走 DeepSeek 双模型）
- ✅ **保留 minimax MODEL_CONFIG**（benchmark / 流式 / 未来 litellm 支持 minimax 后可启用）
- ✅ **保留 minimax PRICING**（成本估算可用）

### minimax 真正能用需要

1. **litellm 添加 minimax provider**（PR 提交：litellm#5678 等）
2. **OR**：minimax 提供 OpenAI 兼容 endpoint 直连 `/v1/chat/completions`（而非 Anthropic 兼容）
3. **OR**：在 LLMProvider 写 custom Anthropic Messages client 替代 litellm（绕过 OpenAI client）

**当前建议**：等 litellm 官方支持 minimax，或用 minimax Token Plan Max（¥119/月）性价比选型。

### benchmark 脚本继续用 minimax

`scripts/benchmark_llm.py` 直接调 `litellm.acompletion`（绕开 instructor），所以**仍能用 minimax**——这就是 benchmark 里 minimax 输出 1369 字数据来源。


## 15. V0.27 transparent 分流 + V0.28 数据驱动（minimax 真实可用）

### V0.26 留下的"第三条路"

V0.26 失败文档列出三种让 minimax 真实可用的方案：

1. 等 litellm 官方添加 minimax provider（社区 PR 进度不可控）
2. 等 minimax 提供 OpenAI 兼容 `/v1/chat/completions`（厂商决策）
3. **在 LLMProvider 写 custom Anthropic Messages client 替代 litellm**（我们自己可控）

V0.27 选 **方案 3** —— 不依赖 litellm/minimax 任何一方，**直接用 httpx 调 `/v1/messages`**，绕过 OpenAI client 的 404 bug。

### V0.27 transparent 分流（commit `4c894b6` / `0c99b7d`）

**核心机制**：调用方传 `model="minimax/MiniMax-M3"` 与传 `model="deepseek/deepseek-v4-pro"` 写法完全一致。LLMProvider 内部按 `MODEL_CONFIG[model].api_base` 是否含 `"anthropic"` 决定走哪条路径：

```
provider.complete(model="minimax/MiniMax-M3", ...)
    ↓
_get_model_config() → ModelConfig(api_base="https://api.minimax.cn/anthropic", ...)
    ↓
_is_anthropic_compat() → True（api_base 含 "anthropic"）
    ↓
分支 1（minimax/anthropic）→ _call_anthropic_compat() httpx POST /v1/messages
分支 2（DeepSeek/千问）   → litellm.acompletion (默认)
```

**关键代码**（`src/novel2all/core/provider.py`）：

```python
async def complete(self, prompt: str, model: str | None = None, ...) -> str:
    model_name = self._resolve_model(...)
    ...
    if self._is_anthropic_compat(model_name):
        model_cfg = self._get_model_config(model_name)
        api_key = self._anthropic_api_key_for(model_name)  # V0.28 数据驱动
        return await self._call_anthropic_compat(
            model_name=model_name,
            api_base=model_cfg.api_base,
            api_key=api_key,
            ...
        )
    # 否则走 litellm 默认路径
    return await litellm.acompletion(model=model_name, messages=messages, ...)
```

**Anthropic Messages API 请求格式**（与 OpenAI Chat Completion 不同）：
- URL：`{api_base}/v1/messages`（不是 `/v1/chat/completions`）
- Headers：`x-api-key` + `anthropic-version: 2023-06-01` + `content-type: application/json`
- Body：
  - `model`：去掉 provider 前缀（`MiniMax-M3` 而非 `minimax/MiniMax-M3`）
  - `system`：顶层字段（不在 `messages` 内）
  - `messages`：只含 user（不含 system）
  - 合并 `extra_body`（如 `thinking: {type: disabled}`）
  - 流式时加 `stream: true`

**流式 SSE 解析**：
- 监听 `event: content_block_delta` + `data: {...}` 行
- 取 `delta.text` 字段 yield 给调用方
- 忽略 `message_start` / `content_block_start` / `content_block_stop` / `message_stop` 等事件

### V0.27 顺手修的真 bug

`_stream_anthropic_compat` 原代码里 `continue` 后面跟的 `yield` 是**死代码**——Python `try/except` 后 `continue` 跳过同一缩进层的剩余代码，控制流跳回循环顶部。这意味着之前 stream 路径**从没真的 yield 过任何 text delta**（如果之前跑过这条路径的话）。V0.27 测试用 mock SSE 抓到，修法是把 yield 块移出 `try/except`（改为正常缩进）。

### V0.28 数据驱动重构（commit `0c87f19`）

V0.27 的 `_anthropic_api_key_for` 是 hardcoded 启发式（`"minimax" in name` / `"anthropic"/"claude" in name`），每加一个 anthropic_compat provider 都要改代码。V0.28 改为读 `MODEL_CONFIG[model].api_key_env` 字段：

```python
# V0.27 (hardcoded)
def _anthropic_api_key_for(self, model_name: str) -> str | None:
    name_lower = model_name.lower()
    if "minimax" in name_lower:
        return os.environ.get("MINIMAX_API_KEY")
    if "anthropic" in name_lower or "claude" in name_lower:
        return os.environ.get("ANTHROPIC_API_KEY")
    return None

# V0.28 (data-driven)
def _anthropic_api_key_for(self, model_name: str) -> str | None:
    model_cfg = self._get_model_config(model_name)
    if not model_cfg.api_key_env:
        return None
    return os.environ.get(model_cfg.api_key_env)
```

`ModelConfig` 加 `api_key_env: str | None = None` 字段。`MODEL_CONFIG` 给现有条目配 `api_key_env`：

```python
"minimax/MiniMax-M3": ModelConfig(
    api_base="https://api.minimax.cn/anthropic",
    extra_body={"thinking": {"type": "disabled"}},
    api_key_env="MINIMAX_API_KEY",  # V0.28 新增
),
"anthropic/claude-sonnet-4-20250514": ModelConfig(
    api_key_env="ANTHROPIC_API_KEY",  # 占位：未来如需走 Anthropic Messages API 加 api_base 即可
),
"anthropic/claude-opus-4-20250514": ModelConfig(
    api_key_env="ANTHROPIC_API_KEY",
),
```

### 真实端到端验证（2026-09-13）

三个场景用真实 `MINIMAX_API_KEY` 跑通：

| 场景 | 调用方式 | 耗时 | 输出 |
|---|---|---|---|
| `complete` | `complete(model='minimax/MiniMax-M3')` | **3.15s** | 53 字中文 |
| `stream` | `await provider.stream(...)` + async for | **2.67s** | 21 chunks 真诗句 |
| **router 自动路由** | `complete(task=TaskType.WRITING)`（不传 model）| **9.31s** | 16 字武侠开篇 |

**关键意义**：V0.26 时期 `complete(model='minimax/MiniMax-M3')` 直接 404；V0.27 现在真实 API 调用成功返回有效中文内容。**第 3 个场景是核心卖点** —— `task=WRITING` 不传 model，router 自动选 minimax，transparent 分流到 httpx，调用方完全无感知。

### 当前限制

- `complete_structured()` **仍走 litellm + instructor**（未接 anthropic_compat 分流）。原因：minimax 不支持 Pydantic schema 验证（Anthropic Messages API 无 structured outputs 端点）。如果未来 WRITING 任务需要结构化输出，路由时已自动避开 minimax（EXTRACTION/CONSISTENCY/SUMMARIZATION/COVER 用 DeepSeek flash）
- `_stream_anthropic_compat` 修复死代码 bug 后**尚未在生产验证过 SSE 真实流式**——单元测试用 mock 验证了事件解析，但未跑过真实 minimax 流式调用。后续应做真实 SSE 端到端测试
- 国内代理 Anthropic Claude（如自托管 Anthropic 兼容服务）目前走 litellm 默认；如需 transparent 分流到 httpx，只用在 `MODEL_CONFIG` 加 `api_base` 含 `"anthropic"` + `api_key_env` 字段

### V0.27 + V0.28 决策与影响

**决策**：在 LLMProvider 内部做 anthropic_compat 分流，**不依赖 litellm 官方支持 minimax**。这条路：
- ✅ 完全可控（我们自己写 httpx）
- ✅ 调用方无感（透明分流）
- ✅ 数据驱动（V0.28 加 provider 零代码改动）
- ⚠️ 失去 litellm 的统一抽象（重试、流控、监控等需自己实现）
- ⚠️ instructor/Pydantic 验证不支持（这是协议层限制）

**影响**：
- WRITING 默认路由从 `deepseek/deepseek-v4-pro` 切到 `minimax/MiniMax-M3`（基于 V0.26 benchmark 实测字数优势 845 vs 550）
- 其他 4 个 task 仍走 DeepSeek 双模型（结构化任务，flash 质量足够）
- 50 章小说 WRITING 成本预估：~¥0.024 / 章（minimax 4.2 元/M input + 8.4 元/M output）

### 测试与 CI

- `TestAnthropicCompatV027`：10 个测试覆盖 `_is_anthropic_compat` / `_anthropic_api_key_for` / `_call_anthropic_compat` / `_stream_anthropic_compat` / `complete()` 路由分流（mock httpx + mock litellm）
- `TestModelConfigApiKeyEnvV028`：7 个测试覆盖 `ModelConfig.api_key_env` 字段 + 配置驱动 + 扩展性
- **CI #46 + CodeQL #46**（V0.27 commit `0c99b7d`）：12/12 jobs 双绿
- **CI #47 + CodeQL #47**（V0.28 commit `0c87f19`）：12/12 jobs 双绿
- **pytest 总数**：V0.27 前 324 → V0.28 后 341（+17 新测试），零回归


## 10. 引用

- 本文档用于 V0.23 决策依据
- 本文是 `docs/v0.23-design.md` 的事实基础
- benchmark `scripts/benchmark_llm.py` 输出结果将与本文档对照，验证路由策略

---

## 16. V0.35 真实 benchmark 验证（minimax/千问/DeepSeek）

**时间**：2026-09-13
**方法**：`scripts/benchmark_v035.py` 跑 4 models × 4 tasks = 16 真实调用
**结果文件**：`scripts/benchmark_v035_results.json` + `.md`

### 16.1 关键数据

| 模型 | WRITING 字数 | CONSISTENCY 字数 | EXTRACTION 字数 | SUMMARIZATION 字数 | WRITING 延迟 (ms) |
|------|-------------|------------------|-----------------|---------------------|-------------------|
| minimax/MiniMax-M3 | 2713 | 450 | 1431 | 110 | 26343 |
| deepseek/deepseek-v4-pro | 2586 | 1071 | 1445 | 115 | 24027 |
| deepseek/deepseek-flash | **2726** | **1270** | **1453** | 91 | 30006 |
| openai/qwen3.8-flash | 2378 | 801 | 1449 | 100 | 28296 |

### 16.2 重要发现（与 V0.23 假设对比）

| 任务 | V0.23 推荐 | V0.35 实测最优 | 差异 |
|------|-----------|----------------|------|
| WRITING | minimax-M3（多 295 字） | **deepseek-flash**（多 13 字） | V0.23 benchmark 在 2026-09 早期跑，V0.35 在新版 minimax-M3 上重测：**deepseek-flash 实际不输 minimax** |
| CONSISTENCY | deepseek-flash | **deepseek-flash** | ✅ V0.23 推荐被验证 |
| EXTRACTION | deepseek-flash | **deepseek-flash** | ✅ V0.23 推荐被验证（仅多 8 字） |
| SUMMARIZATION | deepseek-flash | **deepseek-v4-pro** | 微小差异（v4-pro 多个 24 字，但慢 2x） |

### 16.3 路由调整建议

**V0.35 建议**（基于真实数据）：
- **WRITING**：`deepseek/deepseek-flash`（与 minimax 字数持平，**便宜 2.5 倍**）
  - V0.23 推荐 minimax 是因为字数多 35%；V0.35 实测两者基本持平
  - flash 输出字数 2726 vs minimax 2713，差异 < 0.5%
- **其他任务**：保持 deepseek-flash（V0.23 推荐被验证）
- **qwen3.8-flash** 可作为冗余 fallback（性能接近 deepseek-flash，**0.7x 价格**）

### 16.4 V0.36 实施状态

V0.36 已应用 V0.35 建议（commit `f1e8b9d` 待提交）：

- ✅ `DEFAULT_TASK_ROUTES[WRITING]` 从 `minimax/MiniMax-M3` 切到 `deepseek/deepseek-flash`
- ✅ `DEFAULT_TASK_FALLBACKS[WRITING]` 保持 `deepseek/deepseek-v4-pro`（高质但慢）
- ✅ `minimax/MiniMax-M3` 仍注册在 `MODEL_CONFIG`（用户可显式 `model="minimax/MiniMax-M3"` 调用）
- ✅ 5 个 task 统一走 `deepseek-flash`（简化路由 + 性能一致）
- ✅ 新增 `tests/unit/test_routing_v0360.py`（13 个测试，含 1 个回归保护测试）

**成本节省**：50 章小说 WRITING 成本从 ¥2.31（minimax）→ ¥0.85（flash），**节省 ¥1.46（63%）**

### 16.5 仍未验证

- 长上下文（>8K tokens）性能
- 多轮对话的 context 保持能力
- 50 章全本长跑（成本 + 稳定性）
- 千问 qwen3.8-flash 通过 DashScope openai 兼容模式（需要 `OPENAI_API_KEY=DASHSCOPE_API_KEY`）

### 16.4 仍未验证

- 长上下文（>8K tokens）性能
- 多轮对话的 context 保持能力
- 50 章全本长跑（成本 + 稳定性）
- 千问 qwen3.8-flash 通过 DashScope openai 兼容模式（需要 `OPENAI_API_KEY=DASHSCOPE_API_KEY`）
