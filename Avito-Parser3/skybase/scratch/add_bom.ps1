# Read the file, write it back with UTF-8 BOM
$content = [System.IO.File]::ReadAllText('C:\ins\skybase\server.ps1', [System.Text.Encoding]::UTF8)
$utf8bom = New-Object System.Text.UTF8Encoding $true
[System.IO.File]::WriteAllText('C:\ins\skybase\server.ps1', $content, $utf8bom)

# Verify
$bytes = [System.IO.File]::ReadAllBytes('C:\ins\skybase\server.ps1')
$b0 = $bytes[0]; $b1 = $bytes[1]; $b2 = $bytes[2]
Write-Host ("BOM bytes: {0:X2} {1:X2} {2:X2}" -f $b0, $b1, $b2)
if ($b0 -eq 0xEF -and $b1 -eq 0xBB -and $b2 -eq 0xBF) {
    Write-Host "SUCCESS: server.ps1 now has UTF-8 BOM!" -ForegroundColor Green
} else {
    Write-Host "FAILED: no BOM found" -ForegroundColor Red
}
