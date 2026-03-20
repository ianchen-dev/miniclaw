# 批量打开 CMD 运行 Claude 命令指南

## 核心要点

1. **用 `os.system`，不用 `subprocess`** - 避免引号嵌套问题
2. **引号格式** - 外层双引号包裹整个命令，内层双引号保持不变
3. **分批执行** - 控制并发数，批次间等待

## 正确写法

```python
import os
from pathlib import Path

work_dir = Path.cwd()
task = "cli"

# 核心命令格式
cmd = (
    f'start "{task}" cmd /k "cd /d {work_dir} && claude '
    f'"/code-simplifier @coder\\{task} ,done then commit" '
    f"--permission-mode acceptEdits --allowedTools "
    f'"Read,Write,Edit,Bash,Git,Npm,Pip""'
)

os.system(cmd)
```

## 命令结构解析

```
start "窗口标题" cmd /k "完整命令"
                         └── cd /d 路径 && claude "参数" --选项 "值"
```

## 完整脚本模板

```python
import os
import time
from pathlib import Path

BATCH_NUM = 1      # 每批并发数
INTERVAL_TIME = 60  # 批次间隔(秒)
TASKS = ["cli", "common", "gateway"]  # 任务列表

def launch_batch(tasks: list[str], batch_num: int) -> None:
    work_dir = Path.cwd()
    for task in tasks:
        cmd = (
            f'start "{task}" cmd /k "cd /d {work_dir} && claude '
            f'"/code-simplifier @coder\\{task} ,done then commit" '
            f'--permission-mode acceptEdits --allowedTools '
            f'"Read,Write,Edit,Bash,Git,Npm,Pip""'
        )
        print(f"[Batch {batch_num}] Launching: {task}")
        os.system(cmd)
        time.sleep(1)

def main():
    batch_count = 0
    for i in range(0, len(TASKS), BATCH_NUM):
        batch_count += 1
        batch_tasks = TASKS[i : i + BATCH_NUM]
        launch_batch(batch_tasks, batch_count)
        if i + BATCH_NUM < len(TASKS):
            print(f"Waiting {INTERVAL_TIME}s...")
            time.sleep(INTERVAL_TIME)

if __name__ == "__main__":
    main()
```

## 使用

```bash
python run-batch.py           # 默认配置
python run-batch.py 3 120     # 每批3个，间隔120秒
```
