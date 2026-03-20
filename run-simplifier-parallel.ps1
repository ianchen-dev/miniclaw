$paths = @("cli", "common", "concurrency", "delivery", "gateway", "intelligence", "prompts", "resilience", "scheduler", "tools")

Write-Host "Starting code-simplifier in parallel..." -ForegroundColor Green

$workDir = $PWD.Path

foreach ($path in $paths) {
    $cmdArgs = "/k cd /d $workDir && claude `"/code-simplifier @coder\$path ,完成后提交`" --permission-mode acceptEdits --allowedTools `"Read,Write,Edit,Bash,Git,Npm,Pip`""
    Start-Process -FilePath "cmd.exe" -ArgumentList $cmdArgs
    Write-Host "Started: coder\$path" -ForegroundColor Cyan
    Start-Sleep -Milliseconds 500
}

Write-Host "`nAll terminals launched!" -ForegroundColor Green
