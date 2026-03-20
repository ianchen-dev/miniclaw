# s09 弹性 - 三层重试洋葱

> 一次调用失败, 轮换重试。

## 概述

弹性组件提供了三层嵌套的重试机制，确保 Agent 在面对 API 调用失败时能够自动恢复：

- **Layer 1 (Auth Rotation)**: API Key 轮换，跳过冷却中的配置
- **Layer 2 (Overflow Recovery)**: 上下文溢出时压缩消息历史
- **Layer 3 (Tool-Use Loop)**: 标准的工具调用循环

## 架构

```
    Profiles: [main-key, backup-key, emergency-key]
         |
    for each non-cooldown profile:          LAYER 1: Auth Rotation
         |
    create client(profile.api_key)
         |
    for compact_attempt in 0..2:            LAYER 2: Overflow Recovery
         |
    _run_attempt(client, model, ...)        LAYER 3: Tool-Use Loop
         |              |
       success       exception
         |              |
    mark_success    classify_failure()
    return result       |
                   overflow? --> compact, retry Layer 2
                   auth/rate? -> mark_failure, break to Layer 1
                   timeout?  --> mark_failure(60s), break to Layer 1
                        |
                   all profiles exhausted?
                        |
                   try fallback models
                        |
                   all fallbacks failed?
                        |
                   raise RuntimeError
```

## 核心组件

### 1. FailoverReason - 失败原因分类

```python
from coder.components.resilience import FailoverReason, classify_failure

# 六种失败类型
class FailoverReason(Enum):
    rate_limit = "rate_limit"  # 速率限制
    auth = "auth"              # 认证失败
    timeout = "timeout"        # 请求超时
    billing = "billing"        # 计费问题
    overflow = "overflow"      # 上下文溢出
    unknown = "unknown"        # 未知错误

# 分类异常
try:
    # ... API 调用 ...
except Exception as exc:
    reason = classify_failure(exc)
    # 根据原因采取不同策略
```

分类驱动的冷却时长：

- `auth` / `billing`: 300s (坏 key, 不会很快自愈)
- `rate_limit`: 120s (等待速率限制窗口重置)
- `timeout`: 60s (瞬态故障, 短冷却)
- `overflow`: 不冷却配置 -- 改为压缩消息

### 2. AuthProfile - API Key 配置

```python
from coder.components.resilience import AuthProfile

profile = AuthProfile(
    name="main-key",
    provider="anthropic",
    api_key="sk-ant-xxxxx",
)
```

属性：

- `name`: 可读标签
- `provider`: LLM 提供商
- `api_key`: API 密钥
- `cooldown_until`: 冷却结束时间戳
- `failure_reason`: 上次失败原因
- `last_good_at`: 上次成功时间戳

### 3. ProfileManager - 配置管理器

```python
from coder.components.resilience import ProfileManager, AuthProfile

profiles = [
    AuthProfile(name="main-key", provider="anthropic", api_key=key1),
    AuthProfile(name="backup-key", provider="anthropic", api_key=key2),
    AuthProfile(name="emergency-key", provider="anthropic", api_key=key3),
]

manager = ProfileManager(profiles)

# 选择第一个可用配置
profile = manager.select_profile()

# 标记失败 (进入冷却)
manager.mark_failure(profile, FailoverReason.rate_limit, cooldown_seconds=120)

# 标记成功 (清除失败状态)
manager.mark_success(profile)

# 查看所有配置状态
status = manager.list_profiles()
```

### 4. SimulatedFailure - 模拟失败

用于测试三层重试洋葱的各类失败处理：

```python
from coder.components.resilience import SimulatedFailure

sim = SimulatedFailure()

# 装备一个模拟失败
sim.arm("rate_limit")  # 下次调用将模拟速率限制

# 在 API 调用前检查
sim.check_and_fire()  # 如果已装备，抛出模拟错误

# 查询状态
if sim.is_armed:
    print(f"已装备: {sim.pending_reason}")
```

支持的模拟类型：

- `rate_limit`: 速率限制
- `auth`: 认证失败
- `timeout`: 请求超时
- `billing`: 计费问题
- `overflow`: 上下文溢出
- `unknown`: 未知错误

### 5. ResilienceRunner - 三层重试洋葱

```python
from coder.components.resilience import (
    ResilienceRunner,
    ProfileManager,
    AuthProfile,
)

# 创建配置
profiles = [
    AuthProfile(name="main", provider="anthropic", api_key=key1),
    AuthProfile(name="backup", provider="anthropic", api_key=key2),
]

# 创建运行器
runner = ResilienceRunner(
    profile_manager=ProfileManager(profiles),
    model_id="claude-sonnet-4-20250514",
    fallback_models=["claude-haiku-4-20250514"],  # 备选模型
    max_tokens=8096,
)

# 执行请求 (三层重试自动处理)
response, messages = runner.run(
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "Hello!"}],
    tools=None,  # 可选
)

# 获取统计信息
stats = runner.get_stats()
print(f"尝试: {stats['total_attempts']}, 成功: {stats['total_successes']}")
```

## 使用示例

### 基础用法

```python
from coder.components.resilience import (
    ResilienceRunner,
    ProfileManager,
    AuthProfile,
)
from coder.settings import settings

# 从配置创建 profiles
api_key = settings.api_key
profiles = [
    AuthProfile(name="main-key", provider="anthropic", api_key=api_key),
]

runner = ResilienceRunner(
    profile_manager=ProfileManager(profiles),
    model_id=settings.model_id,
    api_base_url=settings.api_base_url,
)

# 执行请求
response, messages = runner.run(
    system="You are helpful.",
    messages=[{"role": "user", "content": "Hello"}],
)
```

### 多 Key 轮换

```python
profiles = [
    AuthProfile(name="key-1", provider="anthropic", api_key=key1),
    AuthProfile(name="key-2", provider="anthropic", api_key=key2),
    AuthProfile(name="key-3", provider="anthropic", api_key=key3),
]

runner = ResilienceRunner(
    profile_manager=ProfileManager(profiles),
    model_id="claude-sonnet-4-20250514",
)

# 当 key-1 因速率限制失败时，自动切换到 key-2
response, messages = runner.run(system, messages, tools)
```

### 备选模型链

```python
from coder.settings import settings

# 从配置读取备选模型
fallback_str = settings.resilience_fallback_models
fallback_models = [m.strip() for m in fallback_str.split(",") if m.strip()]

runner = ResilienceRunner(
    profile_manager=ProfileManager(profiles),
    model_id=settings.model_id,
    fallback_models=fallback_models,  # 主模型失败时尝试这些
)
```

### 集成到 AgentLoop

```python
from coder.components.agent import AgentLoop
from coder.components.resilience import (
    ResilienceRunner,
    ProfileManager,
    AuthProfile,
)

# 创建弹性运行器
profiles = [AuthProfile(name="main", provider="anthropic", api_key=key)]
runner = ResilienceRunner(
    profile_manager=ProfileManager(profiles),
    model_id="claude-sonnet-4-20250514",
)

# 在自定义循环中使用
messages = []
while True:
    user_input = input("You > ")
    messages.append({"role": "user", "content": user_input})

    response, messages = runner.run(
        system="You are helpful.",
        messages=messages,
    )
```

## 配置项

在 `.env` 中配置：

```env
# 弹性配置 (s09)
# 备选模型链，逗号分隔
RESILIENCE_FALLBACK_MODELS=claude-haiku-4-20250514,gpt-4o-mini
# 最大溢出压缩尝试次数
RESILIENCE_MAX_OVERFLOW_COMPACTION=3
```

## 重试限制

公式: `min(max(BASE_RETRY + PER_PROFILE * N, 32), 160)`

- `BASE_RETRY = 24`
- `PER_PROFILE = 8`
- `N` = 配置数量

例如 3 个配置: `min(max(24 + 8*3, 32), 160) = min(48, 160) = 48`

## 文件结构

```
coder/components/resilience/
├── __init__.py      # 组件导出
├── failure.py       # FailoverReason, classify_failure, SimulatedFailure
├── profile.py       # AuthProfile, ProfileManager
└── runner.py        # ResilienceRunner
```

## 与 OpenClaw 的对比

| 方面             | Miniclaw (本项目)                      | OpenClaw 生产代码                          |
|------------------|------------------------------------------|----------------------------------------------|
| 配置轮换         | 支持多配置演示                          | 跨提供商的多个真实 key                       |
| 失败分类器       | 异常文本字符串匹配                       | 相同模式, 加 HTTP 状态码检查                 |
| 溢出恢复         | 截断工具结果 + LLM 摘要                  | 相同的两阶段压缩                             |
| 冷却追踪         | 内存中的浮点时间戳                       | 相同的每配置内存追踪                         |
| 备选模型         | 可配置的备选链                           | 相同链, 通常为更小/更便宜的模型              |
| 重试限制         | BASE_RETRY=24, PER_PROFILE=8, 上限=160  | 相同公式                                     |
| 模拟失败         | SimulatedFailure 用于测试               | 集成测试工具带故障注入                       |

## REPL 命令

当使用集成 REPL 时：

```
/profiles               显示所有配置状态
/cooldowns              显示活跃的冷却
/simulate-failure <r>   装备模拟失败 (测试用)
/fallback               显示备选模型链
/stats                  显示弹性统计
```
