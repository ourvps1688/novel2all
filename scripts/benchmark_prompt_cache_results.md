# V0.30.6 C1 Prompt Prefix Cache Benchmark

**Generated**: 2026-09-14T11:55:10.145716
**Elapsed**: 0.17 ms

## Configuration

- Chapters: 100
- Unique system prompts: 5
- Avg prompt tokens/chapter: 5000
- Avg output tokens/chapter: 3000

## Pricing (DeepSeek flash, V0.36 实测)

- Input cache miss: ¥1.0/M
- Input cache hit: ¥0.02/M
- Output: ¥4.0/M

## Results

| Metric | Value |
|--------|------:|
| Prefix hits | 95 |
| Prefix misses | 5 |
| Total chapters | 100 |
| **Hit rate** | **95.00%** |
| Unique sys prompts | 5 |

## Cost Analysis

| Scenario | Cost |
|----------|-----:|
| **WITHOUT cache** | ¥1.7000 |
| **WITH cache** | ¥1.2345 |
| **Savings** | **¥0.4655 (27.4%)** |

## Interpretation

- **Hit rate 95.00%** 意味着 95 章复用了 system prompt prefix，仅 5 章是首次生成 system prompt。
- **节省 ¥0.4655** (27.4%) 来自 input token 价格差：cache hit (¥0.02/M) vs cache miss (¥1.0/M)。
- **Hit rate 验证 V0.30.6 C1 设计假设**：典型 novel 写作工作负载（system prompt 跨章节稳定）的 prefix 命中率接近 80.0%。
