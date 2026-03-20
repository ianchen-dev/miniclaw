# 任务

## 每个路径都使用/code-simplifier skill进行 code simplification

## 1. 已知需要处理的路径

coder/
d-----         3/20/2026   2:25 PM                agent【已完成】
d-----         3/19/2026  10:36 PM                channels【已完成】
d-----         3/19/2026  10:43 PM                cli
d-----         3/20/2026   2:05 PM                common
d-----         3/19/2026  10:36 PM                concurrency
d-----         3/19/2026  10:36 PM                delivery
d-----         3/19/2026  10:36 PM                gateway
d-----         3/20/2026   2:13 PM                intelligence
d-----         3/20/2026   2:13 PM                prompts
d-----         3/19/2026  10:36 PM                resilience
d-----         3/19/2026  10:37 PM                scheduler
d-----         3/20/2026   2:29 PM                session 【已完成】
d-----         3/20/2026   2:13 PM                tools
2. 批量开终端执行命令：claude "/code-simplifier   @{路径} ,完成后提交"   --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip"
例如
claude "/code-simplifier   @coder\session ,完成后提交"   --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip"

所以请你编写一个window的脚本，批量开终端执行命令

## 并发注意

该脚本能批量打开cmd运行claude执行代码任务，而claude有并发限制数为5.所以可以        怎么解决？我提议写一个Python脚本，分批次打开，一次打开batch_num=5,interval
  time=60000后开启下一批。【上一批不关闭，因为不能确定任务是否完成】
