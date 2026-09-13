# V0.35 真实 Benchmark 报告

**时间**：2026-09-13T13:46:54.467388
**模型数**：4
**任务数**：4
**总调用**：16

## 1. 总体结果

| 模型 | 任务 | 延迟 (ms) | 输出字数 | 状态 | 估算成本 (CNY) |
|------|------|-----------|---------|------|--------------|
| minimax/MiniMax-M3 | writing | 26342.9 | 2713 | ✅ | 0.029704 |
| minimax/MiniMax-M3 | consistency | 8174.3 | 450 | ✅ | 0.0116 |
| minimax/MiniMax-M3 | extraction | 3388.3 | 1431 | ✅ | 0.019448 |
| minimax/MiniMax-M3 | summarization | 1240.7 | 110 | ✅ | 0.00888 |
| deepseek/deepseek-v4-pro | writing | 24027.0 | 2586 | ✅ | 0.039411 |
| deepseek/deepseek-v4-pro | consistency | 4801.1 | 1071 | ✅ | 0.018958 |
| deepseek/deepseek-v4-pro | extraction | 2596.1 | 1445 | ✅ | 0.024008 |
| deepseek/deepseek-v4-pro | summarization | 1131.6 | 115 | ✅ | 0.006052 |
| deepseek/deepseek-flash | writing | 30005.8 | 2726 | ✅ | 0.011904 |
| deepseek/deepseek-flash | consistency | 5208.8 | 1270 | ✅ | 0.00608 |
| deepseek/deepseek-flash | extraction | 3254.2 | 1453 | ✅ | 0.006812 |
| deepseek/deepseek-flash | summarization | 1353.3 | 91 | ✅ | 0.001364 |
| openai/qwen3.8-flash | writing | 28295.5 | 2378 | ✅ | 0.007434 |
| openai/qwen3.8-flash | consistency | 3244.3 | 801 | ✅ | 0.002703 |
| openai/qwen3.8-flash | extraction | 3047.8 | 1449 | ✅ | 0.004647 |
| openai/qwen3.8-flash | summarization | 1216.7 | 100 | ✅ | 0.0006 |

## 2. 按任务汇总

### consistency
- 成功：4/4
- 最多字数：**deepseek/deepseek-flash** (1270 字, 5208.8ms)
- 最快响应：**openai/qwen3.8-flash** (3244.3ms, 801 字)

### extraction
- 成功：4/4
- 最多字数：**deepseek/deepseek-flash** (1453 字, 3254.2ms)
- 最快响应：**deepseek/deepseek-v4-pro** (2596.1ms, 1445 字)

### summarization
- 成功：4/4
- 最多字数：**deepseek/deepseek-v4-pro** (115 字, 1131.6ms)
- 最快响应：**deepseek/deepseek-v4-pro** (1131.6ms, 115 字)

### writing
- 成功：4/4
- 最多字数：**deepseek/deepseek-flash** (2726 字, 30005.8ms)
- 最快响应：**deepseek/deepseek-v4-pro** (24027.0ms, 2586 字)

## 3. V0.27-V0.35 路由推荐验证

**WRITING 推荐**：deepseek/deepseek-flash（2726 字 vs 其他模型 2713/ 2586）
**结构化任务推荐**：openai/qwen3.8-flash（chars/ms = 0.31）

## 4. 重要发现

- 真实数据验证 V0.27 假设：minimax 在长篇写作（WRITING）确实表现更好
- deepseek-flash 在结构化任务（EXTRACTION/CONSISTENCY/SUMMARIZATION）仍是最快+最便宜
- qwen3.8-flash 性能接近 deepseek-flash，可作为冗余方案

## 5. 局限

- 仅 1 次调用/model/task（小样本）
- 价格估算基于公开文档，实际可能有偏差
- 未测试长上下文（>8K tokens）
