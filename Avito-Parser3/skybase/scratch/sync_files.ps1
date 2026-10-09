$src = "D:\ins\skybase\Avito-Parser3\skybase"
$targets = @("D:\ins\skybase\skybotparser\app", "C:\Program Files (x86)\SkyBotParser")

$fileList = @(
    "server.py",
    "gateway.py",
    "app_launcher.py",
    "avito_api_helper.py",
    "avito_sniper.py",
    "index.html",
    "manifest.json",
    "sw.js",
    "css\style.css",
    "js\app.js",
    "avito_bot\bot.py",
    "avito_bot\config.py",
    "avito_bot\database.py",
    "avito_bot\parser.py"
)

foreach ($target in $targets) {
    Write-Host "=== Syncing to $target ==="
    foreach ($rel in $fileList) {
        $sourcePath = Join-Path $src $rel
        $targetPath = Join-Path $target $rel
        $targetDir = Split-Path -Path $targetPath -Parent
        if (-not (Test-Path $targetDir)) {
            New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
        }
        Copy-Item -Path $sourcePath -Destination $targetPath -Force
        Write-Host "Copied $rel -> $targetPath"
    }
}

$pyds = @("server.cp311-win_amd64.pyd", "avito_api_helper.cp311-win_amd64.pyd")
foreach ($pyd in $pyds) {
    $p = "D:\ins\skybase\skybotparser\app\$pyd"
    if (Test-Path $p) {
        Move-Item -Path $p -Destination "$p.bak" -Force
        Write-Host "Renamed $pyd to $pyd.bak"
    }
}
Write-Host "Sync complete successfully!"
