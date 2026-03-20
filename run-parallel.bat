@echo off
start "cli" cmd /k "cd /d %~dp0 && claude "/code-simplifier @coder\cli ,done then commit" --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip""
timeout /t 1 >nul
start "common" cmd /k "cd /d %~dp0 && claude "/code-simplifier @coder\common ,done then commit" --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip""
timeout /t 1 >nul
start "concurrency" cmd /k "cd /d %~dp0 && claude "/code-simplifier @coder\concurrency ,done then commit" --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip""
timeout /t 1 >nul
start "delivery" cmd /k "cd /d %~dp0 && claude "/code-simplifier @coder\delivery ,done then commit" --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip""
timeout /t 1 >nul
start "gateway" cmd /k "cd /d %~dp0 && claude "/code-simplifier @coder\gateway ,done then commit" --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip""
timeout /t 1 >nul
start "intelligence" cmd /k "cd /d %~dp0 && claude "/code-simplifier @coder\intelligence ,done then commit" --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip""
timeout /t 1 >nul
start "prompts" cmd /k "cd /d %~dp0 && claude "/code-simplifier @coder\prompts ,done then commit" --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip""
timeout /t 1 >nul
start "resilience" cmd /k "cd /d %~dp0 && claude "/code-simplifier @coder\resilience ,done then commit" --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip""
timeout /t 1 >nul
start "scheduler" cmd /k "cd /d %~dp0 && claude "/code-simplifier @coder\scheduler ,done then commit" --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip""
timeout /t 1 >nul
start "tools" cmd /k "cd /d %~dp0 && claude "/code-simplifier @coder\tools ,done then commit" --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip""
echo All terminals launched!
