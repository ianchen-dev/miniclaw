# 第 06 节: 智能层 - 工程化实现

> 系统提示词从磁盘上的文件组装. 换文件, 换性格.

## 架构

```
    Startup                              Per-Turn
    =======                              ========

    BootstrapLoader                      User Input
    load SOUL.md, IDENTITY.md, ...           |
    truncate per file (20k)                  v
    cap total (150k)                    _auto_recall(user_input)
         |                              search memory by TF-IDF
         v                                   |
    SkillsManager                            v
    scan directories for SKILL.md       build_system_prompt()
    parse frontmatter                   assemble 8 layers:
    deduplicate by name                     1. Identity
         |                                  2. Soul (personality)
         v                                  3. Tools guidance
    bootstrap_data + skills_block           4. Skills
    (cached for all turns)                  5. Memory (evergreen + recalled)
                                            6. Bootstrap (remaining files)
                                            7. Runtime context
                                            8. Channel hints
                                                |
                                                v
                                            LLM API call

    Earlier layers = stronger influence on behavior.
    SOUL.md is at layer 2 for exactly this reason.
```

## 工程化架构

教程中的单文件代码被拆分为模块化组件:

```
coder/components/
├── intelligence/            # 智能层组件 (新增)
│   ├── __init__.py          # 导出
│   ├── bootstrap.py         # BootstrapLoader - 文件加载
│   ├── skills.py            # SkillsManager - 技能发现
│   ├── memory.py            # MemoryStore - 记忆存储和搜索
│   └── prompt_builder.py    # build_system_prompt - 8 层组装
├── tools/                   # 工具组件 (更新)
│   ├── schema.py            # 新增 memory_write, memory_search
│   └── handlers.py          # 新增记忆工具处理器
├── prompts/                 # 提示词组件 (更新)
│   └── __init__.py          # 集成智能层
└── agent/                   # Agent 核心组件 (更新)
    └── loop.py              # AgentLoop - 新增智能层集成
```

## 核心文件说明

### 1. 配置扩展 (coder/settings.py)

添加了智能层相关配置:

```python
class Settings(BaseSettings):
    # ... 原有配置 ...

    # 智能层配置 (s06)
    workspace_dir: str = "workspace"  # 工作区目录
    max_file_chars: int = 20000  # 单个 Bootstrap 文件最大字符数
    max_total_chars: int = 150000  # Bootstrap 文件总字符数上限
    max_skills: int = 150  # 最大技能数量
    max_skills_prompt: int = 30000  # 技能提示词块最大字符数
    memory_top_k: int = 5  # 记忆搜索默认返回数量
    memory_decay_rate: float = 0.01  # 记忆时间衰减率
    mmr_lambda: float = 0.7  # MMR 重排序的 lambda 参数
```

### 2. Bootstrap 文件加载器 (coder/components/intelligence/bootstrap.py)

```python
class BootstrapLoader:
    """从工作区加载 Bootstrap 文件"""

    def __init__(self, workspace_dir: Optional[Path] = None) -> None:
        """初始化"""

    def load_file(self, name: str) -> str:
        """加载单个文件"""

    def truncate_file(self, content: str, max_chars: Optional[int] = None) -> str:
        """截断超长文件内容"""

    def load_all(self, mode: str = "full") -> Dict[str, str]:
        """加载所有 Bootstrap 文件"""
```

#### Bootstrap 文件列表

| 文件名 | 用途 | 层级 |
|--------|------|------|
| IDENTITY.md | Agent 身份定义 | 1 |
| SOUL.md | 人格/性格 | 2 |
| TOOLS.md | 工具使用指南 | 3 |
| MEMORY.md | 长期记忆 | 5 |
| USER.md | 用户信息 | 6 |
| HEARTBEAT.md | 心跳配置 | 6 |
| BOOTSTRAP.md | 引导上下文 | 6 |
| AGENTS.md | Agent 配置 | 6 |

### 3. 技能管理器 (coder/components/intelligence/skills.py)

```python
class SkillsManager:
    """发现和解析技能"""

    def __init__(self, workspace_dir: Optional[Path] = None) -> None:
        """初始化"""

    def _parse_frontmatter(self, text: str) -> Dict[str, str]:
        """解析 YAML frontmatter"""

    def _scan_dir(self, base: Path) -> List[Dict[str, str]]:
        """扫描单个目录下的技能"""

    def discover(self, extra_dirs: Optional[List[Path]] = None) -> None:
        """按优先级扫描技能目录"""

    def format_prompt_block(self) -> str:
        """将技能格式化为提示词块"""
```

#### 技能目录扫描顺序

1. `extra_dirs` (自定义目录)
2. `workspace/skills` (内置技能)
3. `workspace/.skills` (托管技能)
4. `workspace/.agents/skills` (个人 agent 技能)
5. `cwd/.agents/skills` (项目 agent 技能)
6. `cwd/skills` (工作区技能)

#### 技能文件格式 (SKILL.md)

```markdown
---
name: example-skill
description: An example skill
invocation: /example
---

Skill instructions here...
```

### 4. 记忆存储 (coder/components/intelligence/memory.py)

```python
class MemoryStore:
    """记忆存储和搜索"""

    def __init__(self, workspace_dir: Optional[Path] = None) -> None:
        """初始化"""

    def write_memory(self, content: str, category: str = "general") -> str:
        """写入记忆到每日 JSONL 文件"""

    def load_evergreen(self) -> str:
        """加载长期记忆 (MEMORY.md)"""

    def search_memory(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """TF-IDF + 余弦相似度搜索"""

    def hybrid_search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """完整混合搜索管道"""
```

#### 双层存储架构

```
workspace/
├── MEMORY.md           # 长期事实 (手动维护)
└── memory/
    └── daily/
        ├── 2024-01-15.jsonl
        └── 2024-01-16.jsonl
```

#### 混合搜索管道

1. **关键词搜索** (TF-IDF): 余弦相似度返回 top-10
2. **向量搜索** (哈希投影): 基于哈希的随机投影模拟嵌入向量
3. **合并**: 按文本前缀取并集, 加权组合 (`vector_weight=0.7, text_weight=0.3`)
4. **时间衰减**: `score *= exp(-decay_rate * age_days)`
5. **MMR 重排序**: 保证多样性

### 5. 系统提示词组装 (coder/components/intelligence/prompt_builder.py)

```python
def auto_recall(
    user_message: str,
    memory_store: Optional[MemoryStore] = None,
    top_k: Optional[int] = None
) -> str:
    """根据用户消息自动搜索相关记忆"""

def build_system_prompt(
    mode: str = "full",
    bootstrap: Optional[Dict[str, str]] = None,
    skills_block: str = "",
    memory_context: str = "",
    agent_id: str = "main",
    channel: str = "terminal",
    model_id: Optional[str] = None,
) -> str:
    """构建 8 层系统提示词"""
```

#### 8 层提示词结构

| 层级 | 名称 | 来源 | 影响力 |
|------|------|------|--------|
| 1 | Identity | IDENTITY.md | 最强 |
| 2 | Soul | SOUL.md | 很强 |
| 3 | Tools guidance | TOOLS.md | 强 |
| 4 | Skills | SKILL.md 文件 | 中 |
| 5 | Memory | MEMORY.md + 召回 | 中 |
| 6 | Bootstrap | 其他 .md 文件 | 弱 |
| 7 | Runtime context | 运行时生成 | 弱 |
| 8 | Channel hints | 通道类型 | 最弱 |

### 6. 记忆工具 (coder/components/tools/)

新增两个记忆工具:

#### memory_write

```python
{
    "name": "memory_write",
    "description": "Save an important fact or observation to long-term memory.",
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The fact to remember."},
            "category": {"type": "string", "description": "Category: preference, fact, context, etc."},
        },
        "required": ["content"],
    },
}
```

#### memory_search

```python
{
    "name": "memory_search",
    "description": "Search stored memories for relevant information.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "top_k": {"type": "integer", "description": "Max results. Default: 5."},
        },
        "required": ["query"],
    },
}
```

### 7. Agent 循环更新 (coder/components/agent/loop.py)

```python
class AgentLoop:
    def __init__(
        self,
        ...,
        enable_intelligence: bool = False,  # 新增
        channel: str = "terminal",  # 新增
    ):
        """新增 enable_intelligence 和 channel 参数"""

        # 智能层组件 (s06)
        self._bootstrap_loader = None
        self._skills_manager = None
        self._memory_store = None
        self._bootstrap_data: Dict[str, str] = {}
        self._skills_block = ""

        if self.enable_intelligence:
            self._init_intelligence()

    def _init_intelligence(self) -> None:
        """初始化智能层组件"""

    def _build_system_prompt(self, user_input: str = "") -> str:
        """构建系统提示词 (8 层组装)"""

    def _handle_intelligence_command(self, command: str) -> Tuple[bool, bool]:
        """处理智能层相关的 REPL 命令"""
```

## REPL 命令

| 命令 | 功能 |
|------|------|
| `/soul` | 显示 SOUL.md 内容 |
| `/skills` | 列出已发现的技能 |
| `/memory` | 显示记忆统计 |
| `/search <query>` | 搜索记忆 |
| `/prompt` | 显示完整系统提示词 |
| `/bootstrap` | 显示已加载的 Bootstrap 文件 |
| `/help` | 显示帮助信息 |

## 使用方法

### 1. 配置环境变量

```bash
# .env
API_KEY=your-api-key-here
MODEL_ID=claude-sonnet-4-20250514

# 智能层配置
WORKSPACE_DIR=workspace
MAX_FILE_CHARS=20000
MAX_TOTAL_CHARS=150000
MEMORY_TOP_K=5
```

### 2. 创建工作区文件

```bash
mkdir -p workspace
cat > workspace/SOUL.md << 'EOF'
You are warm, curious, and encouraging.
You love helping users learn and grow.
EOF

cat > workspace/IDENTITY.md << 'EOF'
You are Luna, a personal AI companion.
Your goal is to be helpful, harmless, and honest.
EOF

cat > workspace/MEMORY.md << 'EOF'
User prefers Python over JavaScript.
User works on AI projects.
EOF
```

### 3. 运行带智能层的 Agent

```python
from coder.components.agent import AgentLoop, run_agent_loop
from coder.components.tools import TOOLS

# 方式1: 快速启动（带智能层）
run_agent_loop(tools=TOOLS, enable_intelligence=True)

# 方式2: 完整模式（智能层 + 会话）
run_agent_loop(
    tools=TOOLS,
    enable_session=True,
    enable_intelligence=True,
)

# 方式3: 自定义配置
loop = AgentLoop(
    model_id="claude-sonnet-4-20250514",
    tools=TOOLS,
    enable_intelligence=True,
    channel="terminal",
)
loop.run()
```

### 4. 直接使用智能层组件

```python
from coder.components.intelligence import (
    BootstrapLoader,
    SkillsManager,
    MemoryStore,
    build_system_prompt,
    auto_recall,
)

# 加载 Bootstrap 文件
loader = BootstrapLoader()
bootstrap = loader.load_all(mode="full")

# 发现技能
skills_mgr = SkillsManager()
skills_mgr.discover()
skills_block = skills_mgr.format_prompt_block()

# 记忆存储
memory_store = MemoryStore()
memory_store.write_memory("User likes Python", category="preference")

# 搜索记忆
results = memory_store.hybrid_search("python programming")

# 自动召回
memory_context = auto_recall("what language does user prefer", memory_store)

# 构建系统提示词
prompt = build_system_prompt(
    mode="full",
    bootstrap=bootstrap,
    skills_block=skills_block,
    memory_context=memory_context,
)
```

## 文件布局

```
workspace/
├── SOUL.md              # 人格定义
├── IDENTITY.md          # 身份定义
├── TOOLS.md             # 工具使用指南
├── MEMORY.md            # 长期记忆
├── USER.md              # 用户信息
├── HEARTBEAT.md         # 心跳配置
├── BOOTSTRAP.md         # 引导上下文
├── AGENTS.md            # Agent 配置
├── memory/
│   └── daily/
│       ├── 2024-01-15.jsonl
│       └── 2024-01-16.jsonl
└── skills/
    └── example-skill/
        └── SKILL.md
```

## 与教程代码的对比

| 方面 | 教程 (s06_intelligence.py) | 工程化实现 |
|------|---------------------------|-----------|
| Bootstrap 加载 | 单文件内联 | 独立 bootstrap.py 模块 |
| 技能发现 | 单文件内联 | 独立 skills.py 模块 |
| 记忆存储 | 单文件内联 | 独立 memory.py 模块 |
| 提示词组装 | 单文件内联 | 独立 prompt_builder.py 模块 |
| API 客户端 | Anthropic SDK | LiteLLM（兼容多模型） |
| 配置管理 | 直接读取环境变量 | Pydantic Settings |
| REPL 命令 | 内联函数 | AgentLoop 方法 |

## 搜索算法详解

### TF-IDF + 余弦相似度

```python
def search_memory(self, query: str, top_k: int = 5) -> list[dict]:
    chunks = self._load_all_chunks()  # MEMORY.md 段落 + 每日 JSONL 条目
    query_tokens = self._tokenize(query)
    chunk_tokens = [self._tokenize(c["text"]) for c in chunks]

    # 所有片段的文档频率
    df: dict[str, int] = {}
    for tokens in chunk_tokens:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1

    def tfidf(tokens):
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        return {t: c * (math.log((n + 1) / (df.get(t, 0) + 1)) + 1)
                for t, c in tf.items()}

    def cosine(a, b):
        common = set(a) & set(b)
        if not common:
            return 0.0
        dot = sum(a[k] * b[k] for k in common)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        return dot / (na * nb) if na and nb else 0.0

    qvec = tfidf(query_tokens)
    scored = []
    for i, tokens in enumerate(chunk_tokens):
        score = cosine(qvec, tfidf(tokens))
        if score > 0.0:
            scored.append({"path": chunks[i]["path"], "score": score,
                           "snippet": chunks[i]["text"][:200]})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
```

### MMR 重排序

```python
def _mmr_rerank(results, lambda_param=0.7):
    """
    Maximal Marginal Relevance
    MMR = lambda * relevance - (1-lambda) * max_similarity_to_selected
    """
    tokenized = [tokenize(r["chunk"]["text"]) for r in results]
    selected = []
    remaining = list(range(len(results)))
    reranked = []

    while remaining:
        best_idx = -1
        best_mmr = float("-inf")
        for idx in remaining:
            relevance = results[idx]["score"]
            max_sim = max(
                jaccard_similarity(tokenized[idx], tokenized[sel_idx])
                for sel_idx in selected
            ) if selected else 0.0
            mmr = lambda_param * relevance - (1 - lambda_param) * max_sim
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = idx
        selected.append(best_idx)
        remaining.remove(best_idx)
        reranked.append(results[best_idx])

    return reranked
```

## 试一试

```bash
# 启动 Agent（需要配置 .env 和创建工作区文件）
python -c "from coder.components.agent import run_agent_loop; from coder.components.tools import TOOLS; run_agent_loop(tools=TOOLS, enable_intelligence=True)"

# 查看组装好的提示词
# You > /prompt

# 检查加载了哪些引导文件
# You > /bootstrap

# 搜索记忆
# You > /search python

# 告诉它一些信息, 然后过一会再问
# You > 我最喜欢的颜色是蓝色.
# You > 你知道我的偏好吗?
# (auto-recall 找到颜色记忆并注入提示词)
```

## 后续扩展

- **s07**: 添加心跳和 Cron 调度
- **s08**: 添加消息投递队列
- **s09**: 添加弹性重试机制
- **s10**: 添加并发支持
