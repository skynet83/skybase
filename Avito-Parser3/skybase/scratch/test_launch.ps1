$env:SERVER_PORT = "8091"
$env:PYTHON_EXE = "C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe"

$logFile = "C:\ins\skybase\scratch\test_server.log"
$null | Set-Content $logFile  # clear log

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "powershell.exe"
$psi.Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"C:\ins\skybase\server.ps1`" -Port 8091 -NoBrowser"
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.WorkingDirectory = "C:\ins\skybase"

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi

$sb = New-Object System.Text.StringBuilder
$proc.OutputDataReceived += { param($s,$e); if ($e.Data) { [void]$sb.AppendLine($e.Data) } }
$proc.ErrorDataReceived += { param($s,$e); if ($e.Data) { [void]$sb.AppendLine("ERR: " + $e.Data) } }

$proc.Start() | Out-Null
$proc.BeginOutputReadLine()
$proc.BeginErrorReadLine()

# Wait up to 10 seconds
$proc.WaitForExit(10000) | Out-Null
if (-not $proc.HasExited) {
    Write-Host "Process still running after 10s - killing test..."
    $proc.Kill()
} else {
    Write-Host ("Exit code: " + $proc.ExitCode)
}

$output = $sb.ToString()
$output | Set-Content $logFile -Encoding UTF8
Write-Host "=== OUTPUT (last 60 lines) ==="
($output -split "`n") | Select-Object -Last 60 | Write-Host
