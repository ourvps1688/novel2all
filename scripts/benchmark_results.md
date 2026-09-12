# novel2all LLM Benchmark 报告

**生成时间**：2026-09-13T01:18:31.207538
**高峰时段**：否（DeepSeek 空闲价）
**任务数**：5，**模型数**：2

## 汇总表

| Task | Model | 成功 | 延迟(s) | 输出(字) | 输出tok(估) | 成本(¥) |
|---|---|---|---|---|---|---|
| writing | deepseek/deepseek-flash | ✓ | 7.65 | 1232 | 869 | 0.0036 |
| consistency | deepseek/deepseek-flash | ✓ | 3.7 | 532 | 354 | 0.0015 |
| extraction | deepseek/deepseek-flash | ✓ | 1.62 | 471 | 196 | 0.0009 |
| summarization | deepseek/deepseek-flash | ✓ | 1.21 | 97 | 63 | 0.0003 |
| cover | deepseek/deepseek-flash | ✓ | 1.56 | 778 | 142 | 0.0006 |
| writing | deepseek/deepseek-v4-pro | ✓ | 20.5 | 1662 | 1212 | 0.0168 |
| consistency | deepseek/deepseek-v4-pro | ✓ | 3.67 | 234 | 164 | 0.0027 |
| extraction | deepseek/deepseek-v4-pro | ✓ | 3.28 | 417 | 180 | 0.0028 |
| summarization | deepseek/deepseek-v4-pro | ✓ | 1.41 | 63 | 42 | 0.0010 |
| cover | deepseek/deepseek-v4-pro | ✓ | 3.25 | 515 | 101 | 0.0017 |

## 按 Task 分组对比

### writing

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-flash | 7.65 | 1232 | ¥0.0036 |
| deepseek/deepseek-v4-pro | 20.5 | 1662 | ¥0.0168 |

### consistency

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-flash | 3.7 | 532 | ¥0.0015 |
| deepseek/deepseek-v4-pro | 3.67 | 234 | ¥0.0027 |

### extraction

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-flash | 1.62 | 471 | ¥0.0009 |
| deepseek/deepseek-v4-pro | 3.28 | 417 | ¥0.0028 |

### summarization

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-flash | 1.21 | 97 | ¥0.0003 |
| deepseek/deepseek-v4-pro | 1.41 | 63 | ¥0.0010 |

### cover

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-flash | 1.56 | 778 | ¥0.0006 |
| deepseek/deepseek-v4-pro | 3.25 | 515 | ¥0.0017 |

## 按 Model 总成本（本次 benchmark）

| Model | 总成本(¥) | 平均延迟(s) | 成功率 |
|---|---|---|---|
| deepseek/deepseek-flash | ¥0.0070 | 3.15 | 100% |
| deepseek/deepseek-v4-pro | ¥0.0250 | 6.42 | 100% |

## 输出预览（抽样）

### writing × deepseek/deepseek-flash
```
## 第一章 苍茫镇觉醒

苍茫镇这名字，取得倒是贴切。镇子夹在两山之间，终年云雾缭绕，连集市上贩夫走卒的吆喝声，都像是被雾气吞了半截，闷沉沉地传不远。

林雷蹲在药铺檐下，百无聊赖地翻弄着面前几捆晒干的柴胡。他今年十六，生得肩宽腰窄，一双眼睛倒是亮堂，只是此刻被雾气熏得有些发涩。父亲林远山一早便去了镇东的茶楼，说是见个故人，临走前嘱咐他看好药摊，莫要与人争执。

可这世道，你不寻事，事却寻你。
...
```

### summarization × deepseek/deepseek-flash
```
林雷在苍茫镇集市采药时，遭遇黑衣人围攻父亲。父亲重伤倒地，林雷怀中玉佩突然发烫，激发血脉力量，一拳击退黑衣人。但父亲伤势过重，临终前告知林雷：“去找你师叔玄清真人……告诉他……林家还有后人……”
```

### writing × deepseek/deepseek-v4-pro
```
## 九霄问道
> 第一章 苍茫镇觉醒

苍茫镇逢三六九，四方乡民皆来赶集。青石长街两侧，布幌招摇，叫卖声、讨价声、骡马嘶鸣声搅作一团。蒸笼掀开，白雾腾起，混着油饼香与牲畜膻气，在日头下翻涌。

林雷抱着一摞草药，跟在父亲林远山身后。他年方十五，身形尚未长足，眉宇间却已透着一股子倔劲。林远山是镇上有名的跌打郎中，今日带他来认几味新到的南疆药材。

“雷儿，你看这‘赤炎草’，叶背有朱砂纹，断口处会渗...
```

### summarization × deepseek/deepseek-v4-pro
```
林雷在集市遇黑衣人围攻父亲，父亲重伤。危急时玉佩激发血脉力量，林雷击退敌人。父亲临终嘱托他寻找师叔玄清真人，告知林家尚有后人。
```
