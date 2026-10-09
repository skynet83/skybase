Start-Sleep 2
$r = Test-NetConnection -ComputerName 127.0.0.1 -Port 8091 -InformationLevel Quiet -ErrorAction SilentlyContinue 2>$null
Write-Host ("Port 8091 open: $r")
$r2 = Test-NetConnection -ComputerName 127.0.0.1 -Port 8081 -InformationLevel Quiet -ErrorAction SilentlyContinue 2>$null
Write-Host ("Port 8081 open: $r2")
