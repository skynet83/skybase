$bytes = [System.IO.File]::ReadAllBytes('C:\ins\skybase\server.ps1')
$b0 = $bytes[0]; $b1 = $bytes[1]; $b2 = $bytes[2]
Write-Host ("BOM bytes: {0:X2} {1:X2} {2:X2}" -f $b0, $b1, $b2)
if ($b0 -eq 0xEF -and $b1 -eq 0xBB -and $b2 -eq 0xBF) {
    Write-Host "Encoding: UTF-8 WITH BOM" -ForegroundColor Green
} elseif ($b0 -eq 0xFF -and $b1 -eq 0xFE) {
    Write-Host "Encoding: UTF-16 LE" -ForegroundColor Yellow
} elseif ($b0 -eq 0xFE -and $b1 -eq 0xFF) {
    Write-Host "Encoding: UTF-16 BE" -ForegroundColor Yellow
} else {
    Write-Host "Encoding: UTF-8 WITHOUT BOM (or ANSI)" -ForegroundColor Red
    Write-Host "PowerShell 5.1 reads this as system ANSI (CP1251 on Russian Windows) - causes MOJIBAKE!" -ForegroundColor Red
}
