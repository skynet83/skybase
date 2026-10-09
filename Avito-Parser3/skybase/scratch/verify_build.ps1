$f = Get-Item 'C:\ins\skybase\dist\SkyBase.exe'
$sizeMB = [math]::Round($f.Length / 1MB, 2)
Write-Host "File:    $($f.Name)"
Write-Host "Size:    $sizeMB MB"
Write-Host "Created: $($f.LastWriteTime)"

# Скопируем в корень проекта (перезаписываем предыдущий)
Copy-Item 'C:\ins\skybase\dist\SkyBase.exe' 'C:\ins\skybase\SkyBase.exe' -Force
Write-Host "Copied to: C:\ins\skybase\SkyBase.exe" -ForegroundColor Green
