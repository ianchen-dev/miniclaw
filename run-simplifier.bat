@echo off
echo Starting code-simplifier for all coder modules...
echo.

for %%p in (cli common concurrency delivery gateway intelligence prompts resilience scheduler tools) do (
    echo ========================================
    echo Processing: coder\%%p
    echo ========================================
    claude "/code-simplifier @coder\%%p ,完成后提交" --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Bash,Git,Npm,Pip"
    echo.
)

echo ========================================
echo All modules processed!
echo ========================================
pause
