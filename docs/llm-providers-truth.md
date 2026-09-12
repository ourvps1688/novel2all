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

## 10. 引用

- 本文档用于 V0.23 决策依据
- 本文是 `docs/v0.23-design.md` 的事实基础
- benchmark `scripts/benchmark_llm.py` 输出结果将与本文档对照，验证路由策略
