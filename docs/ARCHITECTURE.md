# novel2all 架构

## 顶层设计

```
novel2all/
├── core/                # 核心引擎（自研 runtime）
│   ├── memory/          # 5 层长记忆系统
│   ├── skill.py         # Skill 注册 + 调用
│   ├── role.py          # Role 注册 + 调用
│   ├── project.py       # 项目结构管理
│   └── provider.py      # LLM 抽象（LiteLLM）
├── skills/              # 13 个 Skill（markdown）
├── roles/               # 7 个 Role（markdown）
├── templates/           # 项目模板
├── cli/                 # CLI（Typer）
└── web/                 # Web UI（FastAPI + Jinja2 SPA）
```

## 长记忆系统（核心技术）

### 5 层记忆层级

```python
class MemoryLayer(str, Enum):
    CORE = "core"          # 永远加载
    CHARACTER = "character" # 按需加载
    RECENT = "recent"       # 滑动窗口
    EVENT = "event"         # 向量检索
    GRAPH = "graph"         # 知识图谱
```

**Token 预算**：3K + 4K + 6K + 5K = 18K（远低于 200K context window 上限）。

### 配套机制

#### pre-write 检查

```python
async def pre_write_check(chapter, outline) -> list[ConsistencyIssue]:
    # 1. 检查大纲与设定冲突
    # 2. 检查角色状态对得上
    # 3. 检查伏笔节奏（本章是否该揭示 / 是否破坏已埋伏笔）
    # 4. 检查时间线连续性
    # critical 级问题 → 阻断写作流
```

#### 写中流式校验

每生成 500 字调一次轻量校验（防止 LLM 长输出跑偏）。

#### post-write 自动提取

```python
async def update_after_writing(chapter, content):
    # 1. Extractor 自动提取关键信息（角色 / 伏笔 / 时间线）
    # 2. 自动 merge 到 _tracking-state.json
    # 3. Verifier 检查质量（critical 阻断回滚）
    # 4. 生成摘要，加入 recent_chapter_summaries
```

### 数据流

```
[用户输入]
   ↓
[load_for_writing(chapter, outline, characters)]
   ↓
[MemoryContext] = L1 + L2 + L3 + L4 + L5
   ↓
[pre-write check] → critical 阻断
   ↓
[LLM.generate(outline, memory_context)]
   ↓
[Verifier.post_write_check(content)]
   ↓
[Extractor.extract(content)] → merge 到 state
   ↓
[写入 正文/第NNN章.md]
```

## Skill 系统

### Skill 定义

```yaml
---
name: story-long-write
description: novel2all 长篇写作
---

# Skill prompt markdown
```

novel2all 沿用 Claude Skill 的 frontmatter 格式（兼容性最好）。

### Skill 注册

```python
class SkillRegistry:
    def discover(self) -> list[SkillDefinition]:
        # 扫描 skills/ 目录，读 SKILL.md 的 frontmatter
```

### Skill 调用（v0.21+ 完整实现）

```python
async def invoke_skill(name: str, ctx: SkillContext) -> SkillResult:
    skill = registry.get(name)
    
    # 1. 加载 memory context
    memory = await memory_manager.load_for_writing(...)
    
    # 2. pre-write check
    issues = await verifier.pre_write_check(...)
    if has_blocking_issues(issues):
        raise BlockingIssuesError(issues)
    
    # 3. 加载 references（按需）
    refs = await load_references(skill, ctx.task)
    
    # 4. 拼装 prompt
    prompt = build_prompt(skill.content, refs, memory, ctx)
    
    # 5. 调 LLM
    response = await llm.complete(prompt)
    
    # 6. post-write check + extract
    issues = await verifier.post_write_check(...)
    extracted = await extractor.extract(...)
    state = extractor.apply_to_state(state, extracted)
    
    # 7. 写文件
    save_chapter(ctx, response)
    
    return SkillResult(content=response, issues=issues)
```

## Role 系统

### Role 定义

```markdown
---
name: story-architect
description: 故事架构师
---

# Role system prompt
```

### Role 调用

```python
async def invoke_role(name: str, prompt: str, ctx: RoleContext) -> str:
    role = registry.get(name)
    
    return await llm.complete(
        system=role.system_prompt,
        messages=[{"role": "user", "content": prompt}],
        model=role.preferred_model or ctx.default_model,
    )
```

## 项目结构

```
{project_root}/
├── _tracking-state.json      # 机器可读的状态（TrackingState schema）
├── 创作设定.md                # 用户初始创作设定
├── 设定/
│   ├── 文风.md                # L1 永远加载
│   ├── 世界观/                # 力量体系 / 地理
│   └── 角色/                  # 每个角色一个文件
├── 大纲/
│   ├── 大纲.md                # 全书结构
│   ├── 卷纲_第N卷.md          # 每卷
│   └── 细纲_第NNN章.md        # 每章（pre-write 必查）
├── 正文/
│   └── 第NNN章.md            # 每章正文
├── 拆文库/                    # 对标参考书拆文
│   └── {书名}/
└── .novel2all/                # 元数据
```

## Provider 抽象

```python
class LLMProvider:
    async def complete(prompt, system=None, ...) -> str
    async def complete_structured(prompt, response_model, ...) -> T  # 用 instructor
    async def stream(prompt, ...) -> AsyncIterator[str]
```

底层用 LiteLLM，支持 100+ provider。结构化输出用 instructor + Pydantic。

## v0.20 实现状态

| 模块 | 状态 |
|---|---|
| `core/memory/types.py` | ✅ |
| `core/memory/tracker.py` | ✅ |
| `core/memory/extractor.py` | ✅ |
| `core/memory/verifier.py` | ✅ |
| `core/memory/manager.py` | ✅ |
| `core/skill.py` | ✅ |
| `core/role.py` | ✅ |
| `core/project.py` | ✅ |
| `core/provider.py` | ✅ |
| 13 skills | ✅ (markdown) |
| 7 roles | ✅ (markdown) |
| `cli/main.py` | ✅ (基础命令) |
| `web/app.py` | ✅ (基础 SPA) |

## v0.21+ 待实现

- 向量检索（chromadb）
- 完整 skill 调用流程
- 流式输出到 Web UI
- 多模型路由
- 知识图谱（NetworkX）
- 多 agent self-verification
