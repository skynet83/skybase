[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$serverPath = Join-Path $PSScriptRoot "server.ps1"
$content = Get-Content $serverPath -Raw -Encoding UTF8
$errors = $null
$tokens = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($content, [ref]$tokens, [ref]$errors)

if ($errors.Count -gt 0) {
    Write-Host "=== Найдены синтаксические ошибки ($($errors.Count)) ===" -ForegroundColor Red
    foreach ($err in $errors) {
        Write-Host "Строка $($err.Extent.StartLineNumber), Позиция $($err.Extent.StartColumnNumber): $($err.Message)" -ForegroundColor Yellow
    }
} else {
    Write-Host "Синтаксических ошибок не найдено." -ForegroundColor Green
}
