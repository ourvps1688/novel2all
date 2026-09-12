# novel2all LLM Benchmark 报告

**生成时间**：2026-09-13T03:07:52.377435
**高峰时段**：否（DeepSeek 空闲价）
**任务数**：5，**模型数**：4

## 汇总表

| Task | Model | 成功 | 延迟(s) | 输出(字) | 输出tok(估) | 成本(¥) |
|---|---|---|---|---|---|---|
| writing | deepseek/deepseek-v4-pro | ✓ | 11.69 | 835 | 646 | 0.0092 |
| consistency | deepseek/deepseek-v4-pro | ✓ | 3.85 | 254 | 175 | 0.0029 |
| extraction | deepseek/deepseek-v4-pro | ✓ | 4.33 | 533 | 224 | 0.0034 |
| summarization | deepseek/deepseek-v4-pro | ✓ | 2.23 | 75 | 53 | 0.0011 |
| cover | deepseek/deepseek-v4-pro | ✓ | 3.47 | 703 | 137 | 0.0022 |
| writing | deepseek/deepseek-flash | ✓ | 6.83 | 1194 | 877 | 0.0036 |
| consistency | deepseek/deepseek-flash | ✓ | 2.78 | 461 | 315 | 0.0014 |
| extraction | deepseek/deepseek-flash | ✓ | 1.7 | 476 | 202 | 0.0009 |
| summarization | deepseek/deepseek-flash | ✓ | 1.04 | 75 | 51 | 0.0003 |
| cover | deepseek/deepseek-flash | ✓ | 1.81 | 912 | 185 | 0.0008 |
| writing | anthropic/MiniMax-M3 | ✓ | 8.98 | 836 | 609 | 0.0053 |
| consistency | anthropic/MiniMax-M3 | ✓ | 7.24 | 1025 | 611 | 0.0062 |
| extraction | anthropic/MiniMax-M3 | ✓ | 5.58 | 997 | 413 | 0.0045 |
| summarization | anthropic/MiniMax-M3 | ✓ | 2.18 | 119 | 84 | 0.0017 |
| cover | anthropic/MiniMax-M3 | ✓ | 9.62 | 2487 | 609 | 0.0053 |
| writing | openai/qwen3.8-flash | ✓ | 13.5 | 675 | 479 | 0.0014 |
| consistency | openai/qwen3.8-flash | ✓ | 18.13 | 1542 | 936 | 0.0026 |
| extraction | openai/qwen3.8-flash | ✓ | 5.5 | 743 | 324 | 0.0010 |
| summarization | openai/qwen3.8-flash | ✓ | 2.22 | 131 | 90 | 0.0003 |
| cover | openai/qwen3.8-flash | ✓ | 6.64 | 1995 | 446 | 0.0013 |

## 按 Task 分组对比

### writing

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-v4-pro | 11.69 | 835 | ¥0.0092 |
| deepseek/deepseek-flash | 6.83 | 1194 | ¥0.0036 |
| anthropic/MiniMax-M3 | 8.98 | 836 | ¥0.0053 |
| openai/qwen3.8-flash | 13.5 | 675 | ¥0.0014 |

### consistency

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-v4-pro | 3.85 | 254 | ¥0.0029 |
| deepseek/deepseek-flash | 2.78 | 461 | ¥0.0014 |
| anthropic/MiniMax-M3 | 7.24 | 1025 | ¥0.0062 |
| openai/qwen3.8-flash | 18.13 | 1542 | ¥0.0026 |

### extraction

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-v4-pro | 4.33 | 533 | ¥0.0034 |
| deepseek/deepseek-flash | 1.7 | 476 | ¥0.0009 |
| anthropic/MiniMax-M3 | 5.58 | 997 | ¥0.0045 |
| openai/qwen3.8-flash | 5.5 | 743 | ¥0.0010 |

### summarization

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-v4-pro | 2.23 | 75 | ¥0.0011 |
| deepseek/deepseek-flash | 1.04 | 75 | ¥0.0003 |
| anthropic/MiniMax-M3 | 2.18 | 119 | ¥0.0017 |
| openai/qwen3.8-flash | 2.22 | 131 | ¥0.0003 |

### cover

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-v4-pro | 3.47 | 703 | ¥0.0022 |
| deepseek/deepseek-flash | 1.81 | 912 | ¥0.0008 |
| anthropic/MiniMax-M3 | 9.62 | 2487 | ¥0.0053 |
| openai/qwen3.8-flash | 6.64 | 1995 | ¥0.0013 |

## 按 Model 总成本（本次 benchmark）

| Model | 总成本(¥) | 平均延迟(s) | 成功率 |
|---|---|---|---|
| deepseek/deepseek-v4-pro | ¥0.0187 | 5.11 | 100% |
| deepseek/deepseek-flash | ¥0.0070 | 2.83 | 100% |
| anthropic/MiniMax-M3 | ¥0.0230 | 6.72 | 100% |
| openai/qwen3.8-flash | ¥0.0066 | 9.20 | 100% |

## 输出预览（抽样）

### writing × deepseek/deepseek-v4-pro
```
## 九霄问道
> 第一章 苍茫镇觉醒

苍茫镇，逢三集。

天蒙蒙亮，长街两侧已支起竹棚布幌，油煎豆腐的焦香混着土腥气，在晨雾里滚作一团。林雷挑着两筐新摘的山枣，跟在父亲林远山身后，扁担吱呀吱呀地响。他今年十五，身量尚未长足，一件洗得发白的青布短衫，袖口磨出了毛边。

“雷儿，把枣子送到刘家铺子，便去西街寻你娘。”林远山低声嘱咐，目光却扫过街角几个生面孔。

那几个汉子披着灰褐斗篷，斗笠压得极低...
```

### summarization × deepseek/deepseek-v4-pro
```
林雷在苍茫镇集市采药时，突遇黑衣人围攻父亲。父亲重伤倒地，林雷怀中玉佩发烫，激发血脉力量击退敌人。父亲临终前嘱托他去找师叔玄清真人，告知林家仍有后人。
```

### writing × deepseek/deepseek-flash
```
## 第一章 苍茫镇觉醒

苍茫镇集市，午时三刻，日头正毒。

林雷蹲在药铺檐下，双手抱膝，百无聊赖地望着街面。今日赶集的人不多，三三两两的乡农挑着空担子往家走，几个顽童在土墙根下弹石子。他爹林远山进了药铺，说是要抓两副药，让他外头等着。

林雷今年十四岁，生得瘦瘦小小，一双眼睛倒是极亮，像两汪深不见底的寒潭。镇上人都说这孩子邪性，三岁才会说话，可一开口就能背出整篇《千字文》，镇上私塾先生听了直摇...
```

### summarization × deepseek/deepseek-flash
```
林雷在苍茫镇集市采药时，目睹父亲遭黑衣人围攻重伤。怀中玉佩突然发烫，激发血脉力量，一拳击退黑衣人。父亲临终前嘱托他去找师叔玄清真人，告知林家还有后人。
```

### writing × anthropic/MiniMax-M3
```
# 九霄问道

## 第一章 苍茫镇觉醒

天色晦暗，铅云压城。

苍茫镇东市正值旬集，人声鼎沸间，忽闻一声厉叱划破喧嚣——

"林崇，交出那物，饶你不死！"

七道黑影自屋脊掠下，将林雷之父围在当中。为首之人面覆青铜鬼面，手中弯刀泛着幽绿寒芒。

林雷挤进人群，恰见父亲林崇单臂护胸，执剑的右手微微发颤。那柄"断云剑"在父亲掌中嗡鸣不止，似有灵性。

"爹——！"林雷嘶声高呼，却被人潮阻在外围。
...
```

### summarization × anthropic/MiniMax-M3
```
林雷在苍茫镇集市采药时突遭黑衣人袭击，其父重伤倒地。危急关头，林雷怀中玉佩骤然发烫，激发血脉力量，他一拳击退强敌，但父亲伤势过重，无力回天。临终前，父亲遗言告知林雷去找师叔玄清真人，并传达"林家还有后人"的信息，为后续身世与复仇埋下伏笔。
```

### writing × openai/qwen3.8-flash
```
大梁历三百二十年，暮春。苍茫镇的集市上，人声鼎沸，叫卖声夹杂着尘土气息，熏得人有些昏沉。

少年林雷正蹲在街角，手里攥着半块冷硬的胡饼，目光却死死锁住不远处那个佝偻的身影——那是他的父亲，林震。往日里沉默寡言、只会低头修剑的父亲，此刻竟被四名黑衣蒙面人团团围住。那几人步伐诡异，袖中寒光吞吐，显然不是寻常江湖草莽，而是带着必杀之意来的死士。

“老东西，交出《九霄残卷》，留你全尸。”为首黑衣人声音沙...
```

### summarization × openai/qwen3.8-flash
```
林雷在苍茫镇集市采药时，突遭黑衣人围攻父亲。危急关头，林雷怀中玉佩发烫，激发血脉之力，一拳击退敌人。然而父亲伤势过重，临终前嘱托林雷前往寻找师叔玄清真人，并告知其林家尚有后人。这一变故不仅让林雷初显异能，更揭开了家族隐秘与身世之谜的序幕，指引他踏上寻亲复仇之路。
```
