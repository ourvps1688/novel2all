# novel2all LLM Benchmark 报告

**生成时间**：2026-09-13T02:38:35.918175
**高峰时段**：否（DeepSeek 空闲价）
**任务数**：5，**模型数**：5

## 汇总表

| Task | Model | 成功 | 延迟(s) | 输出(字) | 输出tok(估) | 成本(¥) |
|---|---|---|---|---|---|---|
| writing | deepseek/deepseek-v4-pro | ✓ | 12.48 | 1131 | 811 | 0.0114 |
| consistency | deepseek/deepseek-v4-pro | ✓ | 2.79 | 219 | 153 | 0.0026 |
| extraction | deepseek/deepseek-v4-pro | ✓ | 3.12 | 517 | 216 | 0.0033 |
| summarization | deepseek/deepseek-v4-pro | ✓ | 1.88 | 63 | 42 | 0.0010 |
| cover | deepseek/deepseek-v4-pro | ✓ | 2.66 | 528 | 107 | 0.0018 |
| writing | deepseek/deepseek-flash | ✓ | 5.49 | 1033 | 753 | 0.0031 |
| consistency | deepseek/deepseek-flash | ✓ | 1.86 | 421 | 279 | 0.0012 |
| extraction | deepseek/deepseek-flash | ✓ | 1.85 | 628 | 256 | 0.0011 |
| summarization | deepseek/deepseek-flash | ✓ | 0.78 | 75 | 51 | 0.0003 |
| cover | deepseek/deepseek-flash | ✓ | 1.72 | 1021 | 205 | 0.0009 |
| writing | anthropic/MiniMax-M3 | ✓ | 12.57 | 970 | 673 | 0.0059 |
| consistency | anthropic/MiniMax-M3 | ✓ | 6.59 | 982 | 577 | 0.0051 |
| extraction | anthropic/MiniMax-M3 | ✓ | 7.15 | 1369 | 567 | 0.0057 |
| summarization | anthropic/MiniMax-M3 | ✓ | 2.04 | 93 | 63 | 0.0015 |
| cover | anthropic/MiniMax-M3 | ✓ | 8.01 | 2257 | 524 | 0.0046 |
| writing | openai/qwen3.8-max | ✓ | 17.36 | 981 | 725 | 0.0275 |
| consistency | openai/qwen3.8-max | ✓ | 9.1 | 756 | 491 | 0.0191 |
| extraction | openai/qwen3.8-max | ✓ | 6.33 | 638 | 331 | 0.0131 |
| summarization | openai/qwen3.8-max | ✓ | 2.28 | 92 | 64 | 0.0036 |
| cover | openai/qwen3.8-max | ✓ | 9.04 | 1923 | 438 | 0.0167 |
| writing | openai/qwen3.8-flash | ✓ | 11.16 | 742 | 499 | 0.0014 |
| consistency | openai/qwen3.8-flash | ✓ | 16.41 | 1493 | 939 | 0.0026 |
| extraction | openai/qwen3.8-flash | ✓ | 6.56 | 713 | 346 | 0.0010 |
| summarization | openai/qwen3.8-flash | ✓ | 3.25 | 152 | 104 | 0.0004 |
| cover | openai/qwen3.8-flash | ✓ | 5.36 | 1084 | 246 | 0.0007 |

## 按 Task 分组对比

### writing

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-v4-pro | 12.48 | 1131 | ¥0.0114 |
| deepseek/deepseek-flash | 5.49 | 1033 | ¥0.0031 |
| anthropic/MiniMax-M3 | 12.57 | 970 | ¥0.0059 |
| openai/qwen3.8-max | 17.36 | 981 | ¥0.0275 |
| openai/qwen3.8-flash | 11.16 | 742 | ¥0.0014 |

### consistency

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-v4-pro | 2.79 | 219 | ¥0.0026 |
| deepseek/deepseek-flash | 1.86 | 421 | ¥0.0012 |
| anthropic/MiniMax-M3 | 6.59 | 982 | ¥0.0051 |
| openai/qwen3.8-max | 9.1 | 756 | ¥0.0191 |
| openai/qwen3.8-flash | 16.41 | 1493 | ¥0.0026 |

### extraction

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-v4-pro | 3.12 | 517 | ¥0.0033 |
| deepseek/deepseek-flash | 1.85 | 628 | ¥0.0011 |
| anthropic/MiniMax-M3 | 7.15 | 1369 | ¥0.0057 |
| openai/qwen3.8-max | 6.33 | 638 | ¥0.0131 |
| openai/qwen3.8-flash | 6.56 | 713 | ¥0.0010 |

### summarization

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-v4-pro | 1.88 | 63 | ¥0.0010 |
| deepseek/deepseek-flash | 0.78 | 75 | ¥0.0003 |
| anthropic/MiniMax-M3 | 2.04 | 93 | ¥0.0015 |
| openai/qwen3.8-max | 2.28 | 92 | ¥0.0036 |
| openai/qwen3.8-flash | 3.25 | 152 | ¥0.0004 |

### cover

| Model | 延迟(s) | 字数 | 成本(¥) |
|---|---|---|---|
| deepseek/deepseek-v4-pro | 2.66 | 528 | ¥0.0018 |
| deepseek/deepseek-flash | 1.72 | 1021 | ¥0.0009 |
| anthropic/MiniMax-M3 | 8.01 | 2257 | ¥0.0046 |
| openai/qwen3.8-max | 9.04 | 1923 | ¥0.0167 |
| openai/qwen3.8-flash | 5.36 | 1084 | ¥0.0007 |

## 按 Model 总成本（本次 benchmark）

| Model | 总成本(¥) | 平均延迟(s) | 成功率 |
|---|---|---|---|
| deepseek/deepseek-v4-pro | ¥0.0200 | 4.59 | 100% |
| deepseek/deepseek-flash | ¥0.0066 | 2.34 | 100% |
| anthropic/MiniMax-M3 | ¥0.0228 | 7.27 | 100% |
| openai/qwen3.8-max | ¥0.0801 | 8.82 | 100% |
| openai/qwen3.8-flash | ¥0.0062 | 8.55 | 100% |

## 输出预览（抽样）

### writing × deepseek/deepseek-v4-pro
```
## 第一章 苍茫镇觉醒

苍茫镇逢五开集，青石长街两侧摊贩林立，叫卖声如沸水翻腾。林雷跟在父亲林远山身后，怀里揣着刚买的半斤桂花糕，油纸包还透着温热。

忽然，林远山脚步一顿。

长街尽头，五道黑影如墨滴入水，瞬间在人潮中散开，又同时收拢。他们身形飘忽，袖中寒光隐现，所过之处行人如被无形之手拨开，竟无一人发出声响。

“雷儿，退后。”林远山声音低沉，袍袖无风自动。

话音未落，当先一名黑衣人已欺...
```

### summarization × deepseek/deepseek-v4-pro
```
林雷在集市遇黑衣人围攻父亲，父亲重伤。危急时玉佩激发血脉力量，林雷一拳退敌。父亲临终嘱托他去找师叔玄清真人，告知林家尚有后人。
```

### writing × deepseek/deepseek-flash
```
## 第一章 苍茫镇觉醒

苍茫镇的天，常年是灰蒙蒙的，像蒙了一层擦不净的旧纱。镇口那棵老槐树歪着脖子，枝桠上挂着几串褪了色的红布条，风一吹，便簌簌地响，仿佛在数着镇子里有多少人出过远门，又有多少人再没回来。

林雷蹲在集市东头的石阶上，手里攥着半块硬得能砸核桃的炊饼，眼睛却盯着街对面那个卖糖人的老汉。老汉的手稳得很，一勺糖稀在他指间转来转去，便成了个活灵活现的兔子。林雷咽了口唾沫，正想着要不要用...
```

### summarization × deepseek/deepseek-flash
```
林雷在苍茫镇集市采药时，目睹父亲被黑衣人围攻重伤。怀中玉佩突然发烫，激发血脉力量，一拳击退黑衣人。父亲临终前嘱托他去找师叔玄清真人，告知林家还有后人。
```

### writing × anthropic/MiniMax-M3
```
# 第一章 苍茫镇觉醒

苍茫镇，偏居北域边陲，地瘠人贫，却有一条贯穿东西的长街，每逢三六九日，便有四方商贾汇聚于此，换些盐铁皮货。

这一日恰逢集日，薄雾未散，街两旁的摊贩已支起油布棚子，吆喝声此起彼伏。林雷攥着几枚铜板，挤在人群里，望着案板上的糖人咽了咽口水，终是转身往镇西的药铺跑去。

"爹的药该抓了。"少年喃喃自语，脚步匆匆。

他父亲林远山，三月前外出采药归来，便一病不起，寻常郎中皆瞧不...
```

### summarization × anthropic/MiniMax-M3
```
林雷在苍茫镇集市采药时突遭黑衣人袭击，父亲为保护他身受重伤。危急关头，林雷怀中玉佩发烫激发血脉之力，他一拳击退黑衣人。父亲伤重垂危，临终遗言让他去寻找师叔玄清真人，告知林家仍有后人存活。
```

### writing × openai/qwen3.8-max
```
# 第一章 苍茫镇觉醒

苍茫镇的集市，向来是鱼龙混杂之地。

时值深秋，朔风卷着黄沙掠过青石板街，两旁摊贩的幌子被吹得猎猎作响。十五岁的林雷背着半捆柴薪，正穿过熙攘人群，忽听得一声闷响，如败革坠地。

他循声望去，瞳孔骤缩。

父亲林远山倒在肉铺前的血泊里，嘴角溢出的鲜血将灰布短衫洇透。三道黑影将他围在当中，皆着玄色劲装，面覆铁面，手中长刀映着惨白秋阳，杀气凛然。

“林远山，那东西藏了十五年，...
```

### summarization × openai/qwen3.8-max
```
林雷在苍茫镇集市采药时，突遇黑衣人围攻父亲。父亲重伤倒地之际，林雷怀中玉佩发烫，激发其血脉力量，一拳击退强敌。然而父亲伤势过重，临终前嘱托林雷去寻找师叔玄清真人，告知林家尚有后人存世。
```

### writing × openai/qwen3.8-flash
```
苍茫镇的集市，向来是鱼龙混杂之地。今日却不同，空气中弥漫着一股令人窒息的肃杀之气，原本喧闹的叫卖声戛然而止，唯有寒风卷着枯叶，在青石板上发出沙沙的哀鸣。

林雷缩在人群后方，目光死死锁住中央那几道黑影。只见父亲林震天单膝跪地，手中长剑已断，鲜血顺着他灰白的鬓角蜿蜒而下，染红了脚下斑驳的石砖。三名黑衣人呈品字形包围，为首者面覆青铜面具，眼中寒光凛冽，手中鬼头刀高举过顶，刀锋上隐隐有黑气缭绕，显然修习...
```

### summarization × openai/qwen3.8-flash
```
林雷在苍茫镇集市采药时，突遭黑衣人围攻父亲。危急关头，父亲重伤倒地，林雷怀中玉佩骤然发烫，激发其血脉潜能，助他一拳击退敌人。然而父亲伤势过重，生命垂危。临终前，父亲嘱托林雷务必寻找师叔玄清真人，并告知对方林家尚有后人存活。这一变故不仅让林雷初显非凡实力，更揭开了家族隐秘，为他踏上寻亲与复仇之路埋下伏笔。
```
