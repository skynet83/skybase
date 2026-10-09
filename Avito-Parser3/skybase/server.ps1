param(
    [Parameter(Position=0, Mandatory=$false)][object]$Port = 0,
    [switch]$NoBrowser
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
try { $host.UI.RawUI.WindowTitle = "SkyBase Server" } catch {}

[int]$parsedPort = 0
if ($Port -is [int] -and $Port -gt 0) {
    $parsedPort = $Port
} elseif ($Port -and $Port.ToString() -match '^\d+$') {
    $parsedPort = [int]$Port.ToString()
}
if ($parsedPort -le 0 -and $args) {
    for ($i = 0; $i -lt $args.Count; $i++) {
        if ($args[$i] -eq "-Port" -and ($i + 1) -lt $args.Count -and $args[$i+1] -match '^\d+$') {
            $parsedPort = [int]$args[$i+1]
            break
        } elseif ($args[$i] -match '^\d+$') {
            $parsedPort = [int]$args[$i]
            break
        }
    }
}
$port = if ($parsedPort -gt 0) { $parsedPort } elseif ($env:SERVER_PORT -and $env:SERVER_PORT -match '^\d+$') { [int]$env:SERVER_PORT } else { 8080 }
$path = $PSScriptRoot
if ([string]::IsNullOrEmpty($path)) {
    $path = $PWD.Path
}
# Защита от искажения кодировки пути (UTF-8 -> CP1251 mojibake)
if (-not (Test-Path $path)) {
    try {
        $repaired = [System.Text.Encoding]::UTF8.GetString([System.Text.Encoding]::GetEncoding(1251).GetBytes($path))
        if (Test-Path $repaired) { $path = $repaired }
    } catch {}
}

$pidFile = Join-Path $path "server.pid"
# Динамическое определение пути к интерпретатору Python (без жестких привязок к диску или пользователю)
function Test-ValidPython($cmdPath) {
    if (-not $cmdPath) { return $false }
    $s = "$cmdPath".Trim()
    if ($s -eq "") { return $false }
    if ($s -match '(?i)WindowsApps') { return $false }
    if ($s -match '(?i)(skybase|electrobase|keymanager)\.exe$') { return $false }
    if ($s -ne "python" -and $s -ne "python3" -and $s -ne "py") {
        if (-not (Test-Path $s -ErrorAction SilentlyContinue)) { return $false }
    }
    try {
        $p = Start-Process -FilePath $s -ArgumentList '-c "import sys; sys.exit(0 if sys.version_info[0] == 3 and sys.version_info[1] >= 10 else 1)"' -WindowStyle Hidden -Wait -PassThru -ErrorAction Stop
        return ($p.ExitCode -eq 0)
    } catch {
        return $false
    }
}

function Install-SkyBasePython($baseDir) {
    Write-Host "===================================================================" -ForegroundColor Yellow
    Write-Host "  [!] В системе не обнаружен рабочий Python 3.11 (чистая Windows)." -ForegroundColor Yellow
    Write-Host "  [*] Поиск локального установщика Python 3.11..." -ForegroundColor Yellow
    
    $installerCandidates = @(
        (Join-Path $baseDir "installer\python-installer.exe"),
        (Join-Path $baseDir "avito_bot\installer\python-installer.exe"),
        "C:\ins\skybase\installer\python-installer.exe",
        "C:\ins\Avito-Parser\skybase\installer\python-installer.exe",
        "D:\TEMP\SITE\avito_bot\installer\python-installer.exe"
    )
    $installerPath = $null
    foreach ($cand in $installerCandidates) {
        if ($cand -and (Test-Path $cand) -and ((Get-Item $cand).Length -gt 5000000)) {
            $installerPath = $cand
            break
        }
    }
    
    if (-not $installerPath) {
        $instDir = Join-Path $baseDir "installer"
        if (-not (Test-Path $instDir)) {
            New-Item -ItemType Directory -Path $instDir -Force | Out-Null
        }
        $installerPath = Join-Path $instDir "python-installer.exe"
        Write-Host "  [*] Локальный установщик не найден. Скачивание с python.org..." -ForegroundColor Cyan
        $downloadUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        $downloadOk = $false
        
        # Попытка через curl.exe
        try {
            $curl = Get-Command "curl.exe" -ErrorAction SilentlyContinue
            if ($curl) {
                & $curl.Source -fSL --connect-timeout 20 --retry 3 -o $installerPath $downloadUrl 2>&1 | Out-Null
                if ((Test-Path $installerPath) -and ((Get-Item $installerPath).Length -gt 5000000)) {
                    $downloadOk = $true
                }
            }
        } catch {}
        
        # Попытка через WebClient
        if (-not $downloadOk) {
            try {
                [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
                $wc = New-Object System.Net.WebClient
                $wc.Headers.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SkyBaseInstaller/1.0")
                $wc.DownloadFile($downloadUrl, $installerPath)
                if ((Test-Path $installerPath) -and ((Get-Item $installerPath).Length -gt 5000000)) {
                    $downloadOk = $true
                }
            } catch {}
        }
        
        if (-not $downloadOk -or -not (Test-Path $installerPath) -or ((Get-Item $installerPath).Length -lt 5000000)) {
            Write-Host "  [ОШИБКА] Не удалось скачать python-installer.exe. Проверьте интернет-соединение!" -ForegroundColor Red
            return $null
        }
    }
    
    Write-Host "  [*] Запуск тихой установки Python 3.11 в фоновом режиме..." -ForegroundColor Cyan
    Write-Host "  [*] Источник: $installerPath" -ForegroundColor Gray
    Write-Host "  [*] Пожалуйста, подождите 20-40 секунд..." -ForegroundColor Cyan
    
    $instArgs = "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0 SimpleInstall=1"
    Start-Process -FilePath $installerPath -ArgumentList $instArgs -Wait
    Start-Sleep -Seconds 2
    
    $checkPaths = @(
        (Join-Path $env:LocalAppData "Programs\Python\Python311\python.exe"),
        (Join-Path $env:ProgramFiles "Python311\python.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Python311\python.exe")
    )
    foreach ($cp in $checkPaths) {
        if ($cp -and (Test-Path $cp) -and (Test-ValidPython $cp)) {
            $pyDir = Split-Path $cp -Parent
            $env:PATH = "$pyDir;$pyDir\Scripts;" + $env:PATH
            Write-Host "  [+] Python 3.11 успешно установлен: $cp" -ForegroundColor Green
            Write-Host "===================================================================" -ForegroundColor Green
            return $cp
        }
    }
    return $null
}

$global:pythonCmd = $null
if ($env:PYTHON_EXE -and (Test-ValidPython $env:PYTHON_EXE)) {
    $global:pythonCmd = $env:PYTHON_EXE
} else {
    $candidates = @(
        (Join-Path $env:LocalAppData "Programs\Python\Python311\python.exe"),
        (Join-Path $env:ProgramFiles "Python311\python.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Python311\python.exe"),
        (Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"),
        (Join-Path $env:ProgramFiles "Python312\python.exe"),
        (Join-Path $env:LocalAppData "Programs\Python\Python310\python.exe"),
        (Join-Path $env:ProgramFiles "Python310\python.exe"),
        "C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe"
    )
    foreach ($cand in $candidates) {
        if ($cand -and (Test-Path $cand -ErrorAction SilentlyContinue) -and (Test-ValidPython $cand)) {
            $global:pythonCmd = $cand
            break
        }
    }
    if (-not $global:pythonCmd) {
        foreach ($name in @("python", "python3", "py")) {
            $cmd = Get-Command $name -ErrorAction SilentlyContinue
            if ($cmd -and $cmd.Source -notmatch '(?i)WindowsApps' -and (Test-ValidPython $cmd.Source)) {
                $global:pythonCmd = $cmd.Source
                break
            }
        }
    }
}

if (-not $global:pythonCmd) {
    $global:pythonCmd = Install-SkyBasePython -baseDir $path
}

if ($global:pythonCmd -and ($global:pythonCmd -match 'pythonw(\.exe)?$')) {
    $nonGuiPy = $global:pythonCmd -replace 'pythonw(\.exe)?$', 'python$1'
    if (Test-Path $nonGuiPy) {
        $global:pythonCmd = $nonGuiPy
    }
}

if (-not $global:pythonCmd -or -not (Test-ValidPython $global:pythonCmd)) {
    Write-Host "[КРИТИЧЕСКАЯ ОШИБКА] Интерпретатор Python 3.11 не найден и не может быть установлен!" -ForegroundColor Red
    Write-Host "Пожалуйста, скачайте и установите Python 3.11 вручную с https://www.python.org/downloads/" -ForegroundColor Red
} else {
    $env:PYTHON_EXE = $global:pythonCmd
    $pyDir = Split-Path $global:pythonCmd -Parent
    $env:PATH = "$pyDir;$pyDir\Scripts;" + $env:PATH
}

# 1. Автоматическое освобождение порта: завершение старого сервера по PID-файлу
if (Test-Path $pidFile) {
    try {
        $oldPidStr = (Get-Content $pidFile -ErrorAction SilentlyContinue | Out-String).Trim()
        if ($oldPidStr -match '^\d+$') {
            $oldPid = [int]$oldPidStr
            if ($oldPid -ne $PID) {
                $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
                if ($proc -and $proc.ProcessName -like "*powershell*") {
                    Write-Host "Остановка предыдущего экземпляра сервера (PID $oldPid)..." -ForegroundColor Yellow
                    Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Milliseconds 600
                }
            }
        }
    } catch {}
}

# Очистка предыдущего процесса LAN-прокси при перезапуске
$proxyPidFile = Join-Path $path "lan_proxy.pid"
if (Test-Path $proxyPidFile) {
    try {
        $oldPPid = (Get-Content $proxyPidFile -ErrorAction SilentlyContinue | Out-String).Trim()
        if ($oldPPid -match '^\d+$') {
            Stop-Process -Id [int]$oldPPid -Force -ErrorAction SilentlyContinue
        }
        Remove-Item $proxyPidFile -Force -ErrorAction SilentlyContinue
    } catch {}
}

# Запись текущего PID в файл
$PID | Out-File -FilePath $pidFile -Encoding ASCII

# 2. Инициализация HTTP Listener с поддержкой локальной сети и защитой от конфликтов портов
$localIp = ""
try {
    # Определение IP сетевого интерфейса со стандартным сетевым шлюзом (активная сеть / Wi-Fi / Ethernet)
    $defaultRoute = Get-NetRoute -DestinationPrefix "0.0.0.0/0" -AddressFamily IPv4 -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1
    if ($defaultRoute) {
        $candidate = Get-NetIPAddress -InterfaceIndex $defaultRoute.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254*" } | Select-Object -First 1 -ExpandProperty IPAddress
        if ($candidate) { $localIp = $candidate }
    }
} catch {}

if (-not $localIp -or $localIp -eq "127.0.0.1") {
    $localIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.InterfaceAlias -notlike "*vEthernet*" -and $_.InterfaceAlias -notlike "*VirtualBox*" -and $_.InterfaceAlias -notlike "*VMware*" -and $_.IPAddress -notlike "169.254*" -and $_.IPAddress -notlike "127.*" } | Select-Object -First 1 -ExpandProperty IPAddress)
}
if (-not $localIp -or $localIp -eq "127.0.0.1") {
    try {
        $dnsIps = @([System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) | Where-Object { $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and $_.IPAddressToString -notlike "127.*" -and $_.IPAddressToString -notlike "169.254*" } | Select-Object -ExpandProperty IPAddressToString)
        if ($dnsIps.Count -gt 0) { $localIp = $dnsIps[0] }
    } catch {}
}
if (-not $localIp) { $localIp = "127.0.0.1" }

function Get-PasswordHash([string]$plain) {
    if ([string]::IsNullOrEmpty($plain)) { return "" }
    $salt = "SkyBase_2026_Salt!"
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($plain + $salt)
    $hash = $sha.ComputeHash($bytes)
    return [System.BitConverter]::ToString($hash).Replace("-", "").ToLower()
}

function New-SessionToken {
    return [System.Guid]::NewGuid().ToString("N")
}

function Get-CleanJsonOutput($rawOutput) {
    if ($null -ne $rawOutput) {
        $str = ($rawOutput | Out-String).Trim()
        if ($str.StartsWith("{") -and $str.EndsWith("}")) {
            return $str
        }
        $first = $str.IndexOf('{')
        $last = $str.LastIndexOf('}')
        if ($first -ge 0 -and $last -gt $first) {
            return $str.Substring($first, $last - $first + 1)
        }
    }
    $errStr = if ($rawOutput) { ($rawOutput | Out-String).Trim() } else { "Empty response" }
    return (@{ success = $false; error = $errStr } | ConvertTo-Json -Compress)
}

function Test-And-Start-Listener($targetPort) {
    # 1. Сначала пробуем слушать на всех сетевых интерфейсах (http://+:$port/) для прямого доступа без прокси
    try {
        $l = New-Object System.Net.HttpListener
        $l.Prefixes.Add("http://+:$targetPort/")
        $l.Start()
        return @{ Listener = $l; NetworkAccess = $true; Port = $targetPort; IsProxied = $false }
    } catch {}

    # 1.1 Попытка авто-регистрации URLACL если запущено от администратора
    try {
        Start-Process netsh -ArgumentList "http add urlacl url=http://+:$targetPort/ sddl=`"D:(A;;GX;;;WD)`"" -WindowStyle Hidden -Wait -ErrorAction SilentlyContinue
        $l = New-Object System.Net.HttpListener
        $l.Prefixes.Add("http://+:$targetPort/")
        $l.Start()
        return @{ Listener = $l; NetworkAccess = $true; Port = $targetPort; IsProxied = $false }
    } catch {}

    # 1.2 Пробуем с локальным IP (если есть urlacl на конкретный IP)
    if ($localIp -and $localIp -ne "127.0.0.1") {
        try {
            $l = New-Object System.Net.HttpListener
            $l.Prefixes.Add("http://localhost:$targetPort/")
            $l.Prefixes.Add("http://127.0.0.1:$targetPort/")
            $l.Prefixes.Add("http://$localIp`:$targetPort/")
            $l.Start()
            return @{ Listener = $l; NetworkAccess = $true; Port = $targetPort; IsProxied = $false }
        } catch {}
    }

    # 2. Если прав администратора/URLACL для прямого бинда http://+: нет:
    # Запускаем встроенный сетевой LAN-прокси на 0.0.0.0:$targetPort!
    # Он принимает все внешние подключения (включая http://$localIp:$targetPort и любые телефоны в Wi-Fi),
    # пересылая их на внутренний порт бэкенда без каких-либо ошибок 400!
    $backendPort = $targetPort + 10000
    $proxyScript = Join-Path $path "lan_proxy.py"
    if (Test-Path $proxyScript) {
        try {
            $l = New-Object System.Net.HttpListener
            $l.Prefixes.Add("http://127.0.0.1:$backendPort/")
            $l.Prefixes.Add("http://localhost:$backendPort/")
            $l.Start()

            # Освобождаем внешний порт $targetPort если он еще кем-то занят
            try {
                $conns = Get-NetTCPConnection -LocalPort $targetPort -State Listen -ErrorAction SilentlyContinue
                foreach ($c in $conns) {
                    if ($c.OwningProcess -and $c.OwningProcess -ne $PID) {
                        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
                    }
                }
                Start-Sleep -Milliseconds 400
            } catch {}

            $proxyProc = Start-Process -FilePath $global:pythonCmd -ArgumentList "`"$proxyScript`" $targetPort $backendPort" -WindowStyle Hidden -PassThru
            $global:proxyProcess = $proxyProc
            Start-Sleep -Milliseconds 500
            return @{ Listener = $l; NetworkAccess = $true; Port = $targetPort; BackendPort = $backendPort; IsProxied = $true }
        } catch {}
    }

    # 3. Финальный fallback на localhost и 127.0.0.1 если Python недоступен
    try {
        $l = New-Object System.Net.HttpListener
        $l.Prefixes.Add("http://localhost:$targetPort/")
        $l.Prefixes.Add("http://127.0.0.1:$targetPort/")
        $l.Start()
        return @{ Listener = $l; NetworkAccess = $false; Port = $targetPort; IsProxied = $false }
    } catch {
        return $null
    }
}

$bindResult = Test-And-Start-Listener $port
if (-not $bindResult) {
    Write-Host "Порт $port занят. Освобождаем порт $port..." -ForegroundColor Yellow
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            if ($c.OwningProcess -and $c.OwningProcess -ne $PID) {
                Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Milliseconds 800
        $bindResult = Test-And-Start-Listener $port
    } catch {}
}

if (-not $bindResult) {
    Write-Host "Критическая ошибка: не удалось запустить сервер на порту $port." -ForegroundColor Red
    if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }
    exit 1
}

$listener = $bindResult.Listener
$networkAccess = $bindResult.NetworkAccess
$port = $bindResult.Port
$global:serverPowerState = "running"

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  Сервер SkyBase запущен успешно!                      " -ForegroundColor Green
Write-Host "  На этом ПК:      http://localhost:$port/             " -ForegroundColor Yellow
if ($networkAccess) {
    if ($bindResult.IsProxied) {
        Write-Host "  В локальной сети: http://$localIp`:$port/ (LAN-прокси активен)" -ForegroundColor Green
    } else {
        Write-Host "  В локальной сети: http://$localIp`:$port/             " -ForegroundColor Cyan
    }
} else {
    Write-Host "  Сеть (другие ПК): http://$localIp`:$port/ (запустите от Администратора)" -ForegroundColor Gray
}
Write-Host "  Нажмите Ctrl+C для остановки сервера.               " -ForegroundColor Gray
Write-Host "=======================================================" -ForegroundColor Cyan



# Автоматическое открытие сайта в браузере по умолчанию (только для прямого ручного запуска start_server.bat на публичном порту)
try {
    if (-not $NoBrowser -and $port -ne 8081 -and -not $env:SERVER_PORT -and -not $env:GATEWAY_PORT) {
        if ($Host.Name -eq "ConsoleHost" -and [Environment]::UserInteractive) {
            Start-Process "http://localhost:$port/"
        }
    }
} catch {}

$global:recentVisitors = [System.Collections.Generic.Dictionary[string, object]]::new()
$global:ipToMacCache = @{}
$global:blacklistCache = $null
$global:blacklistLastRead = [DateTime]::MinValue

function Get-ClientMacAddress($ip) {
    if (-not $ip -or $ip -eq "127.0.0.1" -or $ip -eq "::1" -or ($localIp -and $ip -eq $localIp)) { return "" }
    if ($global:ipToMacCache.ContainsKey($ip)) {
        return $global:ipToMacCache[$ip]
    }
    $mac = ""
    try {
        $neighbor = Get-NetNeighbor -IPAddress $ip -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($neighbor -and $neighbor.LinkLayerAddress) {
            $mac = $neighbor.LinkLayerAddress.ToUpper().Replace("-", ":")
        }
    } catch {}

    if (-not $mac) {
        try {
            $arpLines = arp -a $ip 2>$null
            foreach ($line in $arpLines) {
                if ($line -match "([0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2})") {
                    $mac = $matches[1].ToUpper().Replace("-", ":")
                    break
                }
            }
        } catch {}
    }

    # Кэшируем результат (включая пустую строку), чтобы не вызывать медленный Get-NetNeighbor повторно
    $global:ipToMacCache[$ip] = $mac
    return $mac
}

function Get-BlacklistEntries {
    $blFile = Join-Path $path "data\blacklist.json"
    try {
        if ([System.IO.File]::Exists($blFile)) {
            $fInfo = New-Object System.IO.FileInfo($blFile)
            if ($global:blacklistCache -eq $null -or $fInfo.LastWriteTimeUtc -gt $global:blacklistLastRead) {
                $raw = [System.IO.File]::ReadAllText($blFile, [System.Text.Encoding]::UTF8).Trim().Trim([char]0xfeff)
                if ([string]::IsNullOrWhiteSpace($raw)) {
                    $global:blacklistCache = @()
                } else {
                    $parsed = $raw | ConvertFrom-Json
                    if ($parsed -isnot [System.Collections.IEnumerable]) { $parsed = @($parsed) }
                    $global:blacklistCache = @($parsed)
                }
                $global:blacklistLastRead = $fInfo.LastWriteTimeUtc
            }
            return $global:blacklistCache
        }
    } catch {}
    return @()
}

function Save-BlacklistEntries($list) {
    $blFile = Join-Path $path "data\blacklist.json"
    try {
        $json = if (-not $list -or @($list).Count -eq 0) { "[]" } else { ($list | ConvertTo-Json -Depth 5) }
        [System.IO.File]::WriteAllText($blFile, $json, [System.Text.Encoding]::UTF8)
        $global:blacklistCache = @($list)
        $global:blacklistLastRead = [DateTime]::UtcNow
    } catch {}
}

function Get-UsersList {
    $uFile = Join-Path $path "data\users.json"
    try {
        if ([System.IO.File]::Exists($uFile)) {
            $fInfo = New-Object System.IO.FileInfo($uFile)
            if ($global:usersCache -eq $null -or $fInfo.LastWriteTimeUtc -gt $global:usersLastRead) {
                $raw = [System.IO.File]::ReadAllText($uFile, [System.Text.Encoding]::UTF8).Trim().Trim([char]0xfeff)
                if ([string]::IsNullOrWhiteSpace($raw)) {
                    $global:usersCache = @()
                } else {
                    $parsed = $raw | ConvertFrom-Json
                    if ($parsed -isnot [System.Collections.IEnumerable]) { $parsed = @($parsed) }
                    $global:usersCache = @($parsed)
                }
                $global:usersLastRead = $fInfo.LastWriteTimeUtc
            }
            return $global:usersCache
        }
    } catch {}
    return @()
}

function Save-UsersList($list) {
    $uFile = Join-Path $path "data\users.json"
    try {
        $json = if (-not $list -or @($list).Count -eq 0) { "[]" } else { ($list | ConvertTo-Json -Depth 6) }
        [System.IO.File]::WriteAllText($uFile, $json, [System.Text.Encoding]::UTF8)
        $global:usersCache = @($list)
        $global:usersLastRead = [DateTime]::UtcNow
    } catch {}
}

function Get-ChatMessagesList {
    $cFile = Join-Path $path "data\chat_messages.json"
    try {
        if ([System.IO.File]::Exists($cFile)) {
            $fInfo = New-Object System.IO.FileInfo($cFile)
            if ($global:chatCache -eq $null -or $fInfo.LastWriteTimeUtc -gt $global:chatLastRead) {
                $raw = [System.IO.File]::ReadAllText($cFile, [System.Text.Encoding]::UTF8).Trim().Trim([char]0xfeff)
                if ([string]::IsNullOrWhiteSpace($raw)) {
                    $global:chatCache = @()
                } else {
                    $parsed = $raw | ConvertFrom-Json
                    if ($parsed -isnot [System.Collections.IEnumerable]) { $parsed = @($parsed) }
                    $global:chatCache = @($parsed)
                }
                $global:chatLastRead = $fInfo.LastWriteTimeUtc
            }
            return $global:chatCache
        }
    } catch {}
    return @()
}

function Test-IsBlacklisted($mac, $ip, $username) {
    if ($username -and $username.ToString().ToLower() -eq "skynet83") { return $false }

    $entries = Get-BlacklistEntries
    if (-not $entries -or $entries.Count -eq 0) { return $false }

    $normMac = if ($mac) { $mac.ToString().ToUpper().Replace("-", ":").Trim() } else { "" }
    $normIp = if ($ip) { $ip.ToString().Trim() } else { "" }
    $normUser = if ($username) { $username.ToString().ToLower().Trim() } else { "" }
    $isLoopbackIp = ($normIp -in @("127.0.0.1", "::1", "localhost"))

    foreach ($b in $entries) {
        $bMac = if ($b.mac) { $b.mac.ToString().ToUpper().Replace("-", ":").Trim() } else { "" }
        $bIp = if ($b.ip) { $b.ip.ToString().Trim() } else { "" }
        $bUser = if ($b.username) { $b.username.ToString().ToLower().Trim() } else { "" }

        if ($normUser -and $bUser -and $normUser -eq $bUser) { return $true }
        if ($normMac -and $bMac -and $normMac -eq $bMac) { return $true }
        if (-not $isLoopbackIp -and $normIp -and $bIp -and $normIp -eq $bIp) { return $true }
    }
    return $false
}

function Get-UrlParam($req, [string]$name) {
    try {
        $raw = $req.RawUrl
        $qIdx = $raw.IndexOf('?')
        if ($qIdx -ge 0) {
            $qs = $raw.Substring($qIdx + 1)
            $pairs = $qs.Split('&')
            foreach ($pair in $pairs) {
                $kv = $pair.Split('=')
                if ($kv.Length -ge 1) {
                    $k = [System.Uri]::UnescapeDataString($kv[0]).Trim()
                    if ($k.ToLower() -eq $name.ToLower()) {
                        $v = if ($kv.Length -ge 2) { [System.Uri]::UnescapeDataString($kv[1]).Trim() } else { "" }
                        return $v
                    }
                }
            }
        }
    } catch {}
    try {
        if ($req.QueryString -and $req.QueryString[$name]) {
            return $req.QueryString[$name].Trim()
        }
    } catch {}
    return ""
}

# Автозапуск и поддержание Telegram-бота как неотъемлемой части сервера
try {
    $pyScript = Join-Path $path "avito_api_helper.py"
    if (Test-Path $pyScript) {
        Write-Host " [ТГ-БОТ] Проверка и автозапуск встроенного Telegram-бота..." -ForegroundColor Cyan
        & $global:pythonCmd -X utf8 $pyScript "bot-toggle" "start" 2>&1 | Out-Null
    }
} catch {}

try {
    while ($listener.IsListening) {
        $context = $null
        try {
            $context = $listener.GetContext()
        } catch {
            if (-not $listener.IsListening) { break }
            Write-Host "GetContext warning: $_" -ForegroundColor DarkYellow
            Start-Sleep -Milliseconds 100
            continue
        }
        try {
            $request = $context.Request
            $response = $context.Response

            $rawUrl = $request.Url.LocalPath
            $localPath = [System.Uri]::UnescapeDataString($rawUrl)

            # Определение реального IP клиента с учетом шлюза / reverse proxy (gateway.py)
            $clientIpHeader = $request.Headers["X-Forwarded-For"]
            if (-not $clientIpHeader) { $clientIpHeader = $request.Headers["X-Real-IP"] }
            if (-not $clientIpHeader) { $clientIpHeader = $request.Headers["CF-Connecting-IP"] }
            if ($clientIpHeader) {
                $remoteIp = $clientIpHeader.Split(',')[0].Trim()
            } else {
                $remoteIp = $request.RemoteEndPoint.Address.ToString()
            }
            if ($remoteIp -eq "::1" -or $remoteIp -eq "127.0.0.1") {
                if ($localIp -and $localIp -ne "127.0.0.1") {
                    $remoteIp = $localIp
                }
            }
            $ua = $request.UserAgent
            $dev = "ПК 💻"
            if ($ua -match "iPhone") { $dev = "iPhone 📱" }
            elseif ($ua -match "iPad") { $dev = "iPad 📱" }
            elseif ($ua -match "Android") { $dev = "Android 📱" }
            elseif ($ua -match "Mobile|webOS|BlackBerry|Opera Mini") { $dev = "Телефон 📱" }

            $clientMac = Get-ClientMacAddress $remoteIp

            $global:recentVisitors[$remoteIp] = @{
                ip = $remoteIp
                mac = $clientMac
                device = $dev
                last_seen = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                last_path = $localPath
            }

            if ($remoteIp -ne "127.0.0.1" -and $remoteIp -ne "::1") {
                $macLog = if ($clientMac) { " (MAC: $clientMac)" } else { "" }
                Write-Host " [СЕТЬ] $($request.HttpMethod) $localPath от $remoteIp$macLog ($dev)" -ForegroundColor Magenta
            }

            # CORS
            $response.AddHeader("Access-Control-Allow-Origin", "*")
            $response.AddHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            $response.AddHeader("Access-Control-Allow-Headers", "Content-Type, Access-Control-Request-Private-Network")
            $response.AddHeader("Access-Control-Allow-Private-Network", "true")

            if ($request.HttpMethod -eq "OPTIONS") {
                $response.StatusCode = 200
                $response.Close()
                continue
            }

            # Проверка Черного Списка (ЧС): по MAC, IP и имени пользователя
            $checkUser = if ($request.QueryString["username"]) { $request.QueryString["username"] } else { "" }
            $isBlocked = Test-IsBlacklisted -mac $clientMac -ip $remoteIp -username $checkUser
            if ($isBlocked) {
                Write-Host " [ЧС БЛОКИРОВКА] Отклонен запрос $localPath от $remoteIp (MAC: $clientMac, User: $checkUser)" -ForegroundColor Red
                $response.StatusCode = 403
                if ($localPath.StartsWith("/api/")) {
                    $errObj = @{ success = $false; error = "Доступ заблокирован администратором (ЧС)"; blocked = $true; mac = $clientMac; ip = $remoteIp }
                    $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                    $response.ContentType = "application/json; charset=utf-8"
                    $response.ContentLength64 = $bytes.Length
                    $response.OutputStream.Write($bytes, 0, $bytes.Length)
                } else {
                    $htmlBlocked = "<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'><title>Доступ заблокирован</title><meta name='viewport' content='width=device-width, initial-scale=1.0'><style>body{background:#0f172a;color:#f8fafc;font-family:system-ui,-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:1rem;box-sizing:border-box;}.card{background:#1e293b;border:1px solid #ef4444;border-radius:16px;padding:2.5rem 2rem;max-width:480px;text-align:center;box-shadow:0 10px 25px rgba(239,68,68,0.2);}.icon{font-size:3.5rem;margin-bottom:1rem;}.title{color:#ef4444;font-size:1.5rem;margin-bottom:0.75rem;font-weight:700;}.desc{color:#94a3b8;font-size:0.95rem;line-height:1.6;margin-bottom:1.5rem;}.details{background:#0f172a;padding:0.75rem 1rem;border-radius:8px;font-family:monospace;font-size:0.82rem;color:#cbd5e1;display:flex;flex-direction:column;gap:0.4rem;text-align:left;}</style></head><body><div class='card'><div class='icon'>🚫</div><div class='title'>Доступ заблокирован</div><div class='desc'>Ваше устройство или учетная запись внесены администратором сервера в черный список (ЧС). Обратитесь к администратору для разблокировки.</div><div class='details'><div>🌐 IP: $remoteIp</div><div>🏷️ MAC: $(if ($clientMac) { $clientMac } else { 'не определен' })</div></div></div></body></html>"
                    $bytes = [System.Text.Encoding]::UTF8.GetBytes($htmlBlocked)
                    $response.ContentType = "text/html; charset=utf-8"
                    $response.ContentLength64 = $bytes.Length
                    $response.OutputStream.Write($bytes, 0, $bytes.Length)
                }
                $response.Close()
                continue
            }

        # API: Состояние питания сервера (GET /api/server/power-state)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/server/power-state") {
            try {
                $curState = if ($global:serverPowerState) { $global:serverPowerState } else { "running" }
                $stateObj = @{ success = $true; state = $curState }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($stateObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
                $response.Close()
            } catch {}
            continue
        }

        # API: Включение сервера из режима ожидания (POST /api/server/start)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/server/start") {
            $global:serverPowerState = "running"
            Write-Host " [ЗАПУСК] Включение сервера из дежурного режима..." -ForegroundColor Green
            try {
                $pyScript = Join-Path $path "avito_api_helper.py"
                if (Test-Path $pyScript) {
                    & $global:pythonCmd -X utf8 $pyScript "bot-toggle" "start" 2>&1 | Out-Null
                    & $global:pythonCmd -X utf8 $pyScript "fetch-proxies" "start" "auto" 2>&1 | Out-Null
                }
            } catch {}
            Write-Host " [ЗАПУСК] Сервер и Telegram-бот успешно запущены!" -ForegroundColor Green
            try {
                $msgObj = @{ success = $true; state = "running"; message = "Сервер и Telegram-бот успешно запущены!" }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($msgObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
                $response.Close()
            } catch {}
            continue
        }

        # Если сервер в режиме ожидания (выключен), блокируем тяжелые API (запросы к /data/ разрешены)
        if ($global:serverPowerState -eq "off" -and $localPath.StartsWith("/api/") -and $localPath -ne "/api/server/power-state" -and $localPath -ne "/api/server/start" -and $localPath -ne "/api/server/network-info" -and $localPath -ne "/api/me" -and $localPath -ne "/api/login" -and $localPath -ne "/api/logout") {
            try {
                $response.StatusCode = 503
                $errObj = @{ success = $false; error = "server_off"; message = "Сервер выключен (нажмите кнопку START для включения)"; state = "off" }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
                $response.Close()
            } catch {}
            continue
        }

        # API: Перезапуск сервера (POST/GET /api/server/restart)
        if (($request.HttpMethod -eq "POST" -or $request.HttpMethod -eq "GET") -and ($localPath -eq "/api/server/restart" -or $localPath -eq "/api/restart")) {
            try {
                $msgObj = @{ success = $true; message = "Сервер SkyBase перезапускается..." }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($msgObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
                $response.Close()
            } catch {}

            try {
                if ($global:proxyProcess -and -not $global:proxyProcess.HasExited) {
                    $global:proxyProcess.Kill()
                }
                $proxyPidFile = Join-Path $path "lan_proxy.pid"
                if (Test-Path $proxyPidFile) {
                    $pPid = (Get-Content $proxyPidFile -ErrorAction SilentlyContinue | Out-String).Trim()
                    if ($pPid -match '^\d+$') { Stop-Process -Id [int]$pPid -Force -ErrorAction SilentlyContinue }
                    Remove-Item $proxyPidFile -Force -ErrorAction SilentlyContinue
                }
            } catch {}

            try {
                $pyScript = Join-Path $path "avito_api_helper.py"
                if (Test-Path $pyScript) {
                    & $global:pythonCmd -X utf8 $pyScript "bot-toggle" "stop" 2>&1 | Out-Null
                    & $global:pythonCmd -X utf8 $pyScript "fetch-proxies" "stop" 2>&1 | Out-Null
                }
            } catch {}

            # Запускаем новый процесс сервера через start_server.bat
            $batFile = Join-Path $path "start_server.bat"
            if (Test-Path $batFile) {
                Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$batFile`"" -WindowStyle Normal
            }

            try { Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue } catch {}
            try { $listener.Stop() } catch {}
            try { $listener.Close() } catch {}
            Write-Host "Перезапуск сервера SkyBase..." -ForegroundColor Yellow

            Start-Sleep -Milliseconds 500
            try {
                $parentProcId = (Get-CimInstance Win32_Process -Filter "ProcessId = $PID").ParentProcessId
                if ($parentProcId) {
                    $parent = Get-Process -Id $parentProcId -ErrorAction SilentlyContinue
                    if ($parent -and ($parent.ProcessName -like "*cmd*" -or $parent.ProcessName -like "*conhost*")) {
                        Stop-Process -Id $parentProcId -Force -ErrorAction SilentlyContinue
                    }
                }
            } catch {}
            Stop-Process -Id $PID -Force
        }

        # API: Завершение работы сервера / спящий режим (POST/GET /api/server/shutdown)
        if (($request.HttpMethod -eq "POST" -or $request.HttpMethod -eq "GET") -and ($localPath -eq "/api/server/shutdown" -or $localPath -eq "/api/shutdown")) {
            $global:serverPowerState = "off"
            try {
                $pyScript = Join-Path $path "avito_api_helper.py"
                if (Test-Path $pyScript) {
                    & $global:pythonCmd -X utf8 $pyScript "bot-toggle" "stop" 2>&1 | Out-Null
                    & $global:pythonCmd -X utf8 $pyScript "fetch-proxies" "stop" 2>&1 | Out-Null
                }
            } catch {}

            try {
                $msgObj = @{ success = $true; state = "off"; message = "Сервер переведен в режим ожидания (выключен)" }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($msgObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
                $response.Close()
            } catch {}

            Write-Host " [ДЕЖУРНЫЙ РЕЖИМ] Сервер SkyBase переведен в спящий режим (ожидание включения с кнопки)..." -ForegroundColor Yellow

            # Если сервер запущен как бэкенд под управлением дежурного диспетчера (gateway.py):
            # освобождаем внутренний порт 8081, пока gateway.py держит публичный порт 8080.
            if ($env:SERVER_PORT) {
                Start-Sleep -Milliseconds 400
                try { Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue } catch {}
                try { $listener.Stop() } catch {}
                try { $listener.Close() } catch {}
                Stop-Process -Id $PID -Force
            }

            # Если сервер запущен автономно напрямую на порту 8080 (без gateway.py):
            # слушатель $listener продолжает работать в дежурном режиме, отдавая статику и ожидая /api/server/start.
            continue
        }

        # API: Информация о сервере и локальном IP (GET /api/server/network-info)
        if ($request.HttpMethod -eq "GET" -and ($localPath -eq "/api/server/network-info" -or $localPath -eq "/api/server/info" -or $localPath -eq "/api/server/visitors")) {
            try {
                $visitorsList = @($global:recentVisitors.Values)
                $publicPort = if ($env:GATEWAY_PORT) { [int]$env:GATEWAY_PORT } elseif ($port) { [int]$port } else { 8080 }
                $infoObj = @{
                    success = $true
                    port = $publicPort
                    local_ip = $localIp
                    network_url = "http://$localIp`:$publicPort"
                    network_access = [bool]$networkAccess
                    visitors = $visitorsList
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($infoObj | ConvertTo-Json -Depth 4 -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Статус ngrok туннеля (GET /api/server/ngrok)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/server/ngrok") {
            try {
                $pyNgrok = Join-Path $path "tools\ngrok_service.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyNgrok "status" 2>&1 | Out-String
                $response.ContentType = "application/json; charset=utf-8"
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Переключение ngrok туннеля (POST/GET /api/server/ngrok/toggle)
        if (($request.HttpMethod -eq "POST" -or $request.HttpMethod -eq "GET") -and $localPath -eq "/api/server/ngrok/toggle") {
            try {
                $actionParam = $request.QueryString["action"]
                if (-not $actionParam -and $request.HasEntityBody) {
                    $reader = [System.IO.StreamReader]::new($request.InputStream, [System.Text.Encoding]::UTF8)
                    $bText = $reader.ReadToEnd()
                    if ($bText) {
                        try {
                            $bObj = $bText | ConvertFrom-Json
                            if ($bObj.action) { $actionParam = $bObj.action }
                        } catch {}
                    }
                }
                if (-not $actionParam) { $actionParam = "toggle" }
                $pyNgrok = Join-Path $path "tools\ngrok_service.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyNgrok $actionParam 2>&1 | Out-String
                $response.ContentType = "application/json; charset=utf-8"
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Получение конфигурации WAN туннеля (GET /api/server/wan/config)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/server/wan/config") {
            try {
                $pyNgrok = Join-Path $path "tools\ngrok_service.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyNgrok "get-config" 2>&1 | Out-String
                $response.ContentType = "application/json; charset=utf-8"
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Сохранение конфигурации WAN туннеля (POST /api/server/wan/config)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/server/wan/config") {
            try {
                $bText = ""
                if ($request.HasEntityBody) {
                    $reader = [System.IO.StreamReader]::new($request.InputStream, [System.Text.Encoding]::UTF8)
                    $bText = $reader.ReadToEnd()
                }
                $pyNgrok = Join-Path $path "tools\ngrok_service.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $psi = [System.Diagnostics.ProcessStartInfo]::new()
                $psi.FileName = $pCmd
                $psi.Arguments = "-X utf8 `"$pyNgrok`" save-config"
                $psi.RedirectStandardInput = $true
                $psi.RedirectStandardOutput = $true
                $psi.RedirectStandardError = $true
                $psi.UseShellExecute = $false
                $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
                $pProc = [System.Diagnostics.Process]::Start($psi)
                if ($bText) {
                    $pProc.StandardInput.Write($bText)
                }
                $pProc.StandardInput.Close()
                $rawJson = $pProc.StandardOutput.ReadToEnd()
                $pProc.WaitForExit(5000)

                $response.ContentType = "application/json; charset=utf-8"
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Статистика и последние объявления (GET /api/avito/stats?username=...)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/avito/stats") {
            try {
                $qUsername = Get-UrlParam $request "username"
                $nowUtc = [DateTime]::UtcNow
                if (-not $global:lastStatsTime -or ($nowUtc - $global:lastStatsTime).TotalMilliseconds -ge 4000 -or -not $global:cachedRawStatsJson) {
                    $pyScript = Join-Path $path "avito_api_helper.py"
                    $rawJson = & $global:pythonCmd -X utf8 $pyScript "get-stats" 2>&1 | Out-String
                    $global:cachedRawStatsJson = $rawJson
                    $global:lastStatsTime = $nowUtc
                } else {
                    $rawJson = $global:cachedRawStatsJson
                }
                $statObj = $rawJson.Trim() | ConvertFrom-Json

                # Персонализируем searches под конкретного пользователя
                $allUsers = Get-UsersList
                if (@($allUsers).Count -ge 0) {
                    $targetU = if ($qUsername) { $allUsers | Where-Object { $_ -and $_.username -and $_.username.ToString().ToLower() -eq $qUsername.ToLower() } | Select-Object -First 1 } else { $null }
                    if ($targetU) {
                        $targetUid = if ($targetU.telegram_chat_id) {
                            [int64]$targetU.telegram_chat_id
                        } else {
                            try {
                                $uClean = if ($targetU.username) { $targetU.username.Trim().ToLower() } else { "user" }
                                $md5Inst = [System.Security.Cryptography.MD5]::Create()
                                $hBytes = $md5Inst.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("usr_" + $uClean))
                                $hHex = ([System.BitConverter]::ToString($hBytes)).Replace("-", "").Substring(0, 8)
                                [Convert]::ToInt64($hHex, 16)
                            } catch {
                                [int64]0
                            }
                        }
                        $userSearches = if ($targetU.avito_searches) { [object[]]@($targetU.avito_searches) } else { [object[]]@() }
                        if (($targetU.role -eq "admin" -or ($targetU.username -and $targetU.username.ToLower() -eq "skynet83")) -and (@($userSearches).Count -eq 0) -and $statObj.searches) {
                            $userSearches = [object[]]@($statObj.searches)
                        }
                        if (@($userSearches).Count -gt 0 -and $statObj.searches) {
                            $needSaveUsers = $false
                            foreach ($us in $userSearches) {
                                $usCleanUrl = if ($us.url) { $us.url.ToString().Trim().TrimEnd('/') } else { "" }
                                $matched = @($statObj.searches) | Where-Object { 
                                    ($_.user_id -and [int64]$_.user_id -eq $targetUid -and (($_.url -and $_.url.ToString().Trim().TrimEnd('/') -eq $usCleanUrl) -or ($us.id -and $_.id -eq $us.id)))
                                } | Select-Object -First 1
                                if (-not $matched) {
                                    $matched = @($statObj.searches) | Where-Object { 
                                        ($_.url -and $_.url.ToString().Trim().TrimEnd('/') -eq $usCleanUrl) -or ($us.id -and $_.id -eq $us.id) 
                                    } | Select-Object -First 1
                                }
                                if ($matched -and $matched.last_polled_at) {
                                    $prevPolled = if ($us.last_polled_at) { $us.last_polled_at.ToString() } else { "" }
                                    if ($prevPolled -ne $matched.last_polled_at.ToString()) {
                                        $us | Add-Member -NotePropertyName "last_polled_at" -NotePropertyValue $matched.last_polled_at -Force
                                        $needSaveUsers = $true
                                    }
                                }
                                $initVal = if ($matched -and $null -ne $matched.is_initialized) { [int]$matched.is_initialized } elseif ($null -ne $us.is_initialized) { [int]$us.is_initialized } else { 0 }
                                $prevInit = if ($null -ne $us.is_initialized) { [int]$us.is_initialized } else { 0 }
                                if ($prevInit -ne $initVal) {
                                    $us | Add-Member -NotePropertyName "is_initialized" -NotePropertyValue $initVal -Force
                                    $needSaveUsers = $true
                                }
                            }
                            if ($needSaveUsers -and $targetU.avito_searches -and $allUsers -and @($allUsers).Count -gt 0) {
                                try {
                                    $safeJson = ($allUsers | ConvertTo-Json -Depth 6)
                                    if ($safeJson -and $safeJson.Trim().Length -gt 15) {
                                        [System.IO.File]::WriteAllText($usersFile, $safeJson, [System.Text.Encoding]::UTF8)
                                    }
                                } catch {}
                            }
                        }
                        $statObj | Add-Member -NotePropertyName "searches" -NotePropertyValue ([object[]]@($userSearches)) -Force
                        if (-not $statObj.stats) {
                            $statObj | Add-Member -NotePropertyName "stats" -NotePropertyValue ([PSCustomObject]@{}) -Force
                        }
                        $statObj.stats | Add-Member -NotePropertyName "total_searches" -NotePropertyValue (@($userSearches).Count) -Force
                        $maxVal = if ($targetU.permissions -and $targetU.permissions.max_searches) { [int]$targetU.permissions.max_searches } elseif ($targetU.role -eq "admin") { 999 } else { 1 }
                        $statObj.stats | Add-Member -NotePropertyName "max_searches" -NotePropertyValue $maxVal -Force
                        $statObj.stats | Add-Member -NotePropertyName "telegram_chat_id" -NotePropertyValue $targetU.telegram_chat_id -Force
                        $statObj.stats | Add-Member -NotePropertyName "telegram_username" -NotePropertyValue $targetU.telegram_username -Force
                        $statObj.stats | Add-Member -NotePropertyName "telegram_pending" -NotePropertyValue $targetU.telegram_pending -Force

                        $isUserMon = if ($targetU.permissions -and $targetU.permissions.monitoring -ne $null) { [bool]$targetU.permissions.monitoring } else { $true }
                        $isUserTg = if ($targetU.permissions -and $targetU.permissions.tg_bot -ne $null) { [bool]$targetU.permissions.tg_bot } else { $true }
                        $statObj.stats | Add-Member -NotePropertyName "user_monitoring" -NotePropertyValue $isUserMon -Force
                        $statObj.stats | Add-Member -NotePropertyName "user_tg_bot" -NotePropertyValue $isUserTg -Force
                        if (-not $isUserTg) {
                            $statObj.stats | Add-Member -NotePropertyName "bot_paused" -NotePropertyValue $true -Force
                        }
                        if ($isUserMon -or $isUserTg) {
                            $statObj.stats | Add-Member -NotePropertyName "monitor_enabled" -NotePropertyValue $true -Force
                        } else {
                            $statObj.stats | Add-Member -NotePropertyName "monitor_enabled" -NotePropertyValue $false -Force
                        }

                        # Индивидуальный интервал опроса пользователя (сохраняем выбор пользователя, дефолт 60с)
                        $uTargetInterval = if ($targetU.active_interval) { [string]$targetU.active_interval } elseif ($targetU.target_interval) { [string]$targetU.target_interval } else { "60" }
                        if ($uTargetInterval.ToLower().StartsWith("rand")) { $uTargetInterval = "60" }
                        $statObj.stats | Add-Member -NotePropertyName "target_interval" -NotePropertyValue $uTargetInterval -Force

                        # Изолируем объявления строго по персональным поисковым ссылкам пользователя
                        $myNames = if ($userSearches) { @($userSearches | ForEach-Object { [string]$_.name.Trim().ToLower() }) } else { @() }
                        $myUrls = if ($userSearches) { @($userSearches | ForEach-Object { [string]$_.url.Trim().ToLower() }) } else { @() }
                        if ($statObj.searches) {
                            foreach ($s in $statObj.searches) {
                                if ($s.url -and $myUrls -contains $s.url.Trim().ToLower()) {
                                    if ($s.name) { $myNames += $s.name.Trim().ToLower() }
                                }
                            }
                        }
                        $myNames = @($myNames | Select-Object -Unique)
                        if ($targetU.role -ne "admin" -and @($userSearches).Count -eq 0) {
                            $statObj.items = @()
                        } elseif ($statObj.items) {
                            $statObj.items = @($statObj.items | Where-Object { 
                                ($_.user_id -and [int64]$_.user_id -eq $targetUid) -or 
                                ($myNames.Count -gt 0 -and $myNames -contains [string]$_.search_name.Trim().ToLower())
                            })
                        } else {
                            $statObj.items = @()
                        }
                        $statObj.stats | Add-Member -NotePropertyName "total_items" -NotePropertyValue ($statObj.items.Count) -Force

                        # Индивидуальный расчет безопасного интервала под пул прокси
                        $userProxiesCount = if ($targetU.proxies) { @($targetU.proxies).Count } else { 0 }
                        $sharedProxyCount = if ($statObj.stats.proxy_count) { [int]$statObj.stats.proxy_count } else { 0 }
                        $effectiveProxyCount = if ($userProxiesCount -gt 0) { $userProxiesCount } else { $sharedProxyCount }
                        $statObj.stats | Add-Member -NotePropertyName "user_proxies_count" -NotePropertyValue $userProxiesCount -Force
                        $statObj.stats | Add-Member -NotePropertyName "shared_proxies_count" -NotePropertyValue $sharedProxyCount -Force
                        $statObj.stats | Add-Member -NotePropertyName "is_custom_proxies" -NotePropertyValue ($userProxiesCount -gt 0) -Force
                        $statObj.stats | Add-Member -NotePropertyName "proxy_count" -NotePropertyValue $effectiveProxyCount -Force

                        $pCount = $effectiveProxyCount
                        if ($uTargetInterval -match "^\d+$") {
                            $tSec = [int]$uTargetInterval
                            $needed = [Math]::Min(360, [Math]::Max(15, [int][Math]::Ceiling(30.0 / [Math]::Max(1, $tSec)) * 10))
                            $safe = if ($pCount -ge $needed) { $tSec } else { [Math]::Max($tSec, [int][Math]::Ceiling(30.0 / [Math]::Max(1, $pCount))) }
                            $statObj.stats | Add-Member -NotePropertyName "needed_proxies" -NotePropertyValue $needed -Force
                            $statObj.stats | Add-Member -NotePropertyName "safe_interval" -NotePropertyValue $safe -Force
                        } else {
                            $statObj.stats | Add-Member -NotePropertyName "needed_proxies" -NotePropertyValue 15 -Force
                            $statObj.stats | Add-Member -NotePropertyName "safe_interval" -NotePropertyValue 30 -Force
                        }
                    } else {
                        $statObj | Add-Member -NotePropertyName "searches" -NotePropertyValue ([object[]]@()) -Force
                        $statObj.items = @()
                        if (-not $statObj.stats) {
                            $statObj | Add-Member -NotePropertyName "stats" -NotePropertyValue ([PSCustomObject]@{}) -Force
                        }
                        $statObj.stats | Add-Member -NotePropertyName "total_searches" -NotePropertyValue 0 -Force
                        $statObj.stats | Add-Member -NotePropertyName "total_items" -NotePropertyValue 0 -Force
                        $statObj.stats | Add-Member -NotePropertyName "max_searches" -NotePropertyValue 1 -Force
                    }
                }

                $jsonOutput = ($statObj | ConvertTo-Json -Depth 6 -Compress)
                if ($jsonOutput -match '"searches":\s*\{') {
                    $jsonOutput = $jsonOutput -replace '"searches":\s*(\{.*?\})([,\}])', '"searches":[$1]$2'
                }
                if (-not $targetU -or @($userSearches).Count -eq 0) {
                    $jsonOutput = $jsonOutput -replace '"searches":\s*(\{\}|null)', '"searches":[]'
                }
                if (-not $targetU -or $statObj.items.Count -eq 0) {
                    $jsonOutput = $jsonOutput -replace '"items":\s*(\{\}|null)', '"items":[]'
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonOutput)
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Список ссылок поиска (GET /api/avito/searches?username=...)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/avito/searches") {
            try {
                $qUsername = Get-UrlParam $request "username"
                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                    if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                }
                $u = if ($qUsername) { $users | Where-Object { $_.username.ToLower() -eq $qUsername.ToLower() } | Select-Object -First 1 } else { $null }
                $isExpired = $false
                if ($u -and $u.role -ne "admin" -and $u.permissions -and $u.permissions.avito_expires_at) {
                    try {
                        $expDate = [DateTime]::Parse($u.permissions.avito_expires_at)
                        if ((Get-Date) -gt $expDate) { $isExpired = $true }
                    } catch {}
                }
                $userSearches = if ($u -and $u.avito_searches) { @($u.avito_searches) } else { @() }
                if ($userSearches.Count -gt 0) {
                    try {
                        $pyScript = Join-Path $path "avito_api_helper.py"
                        $uParam = if ($u.username) { $u.username } else { "skynet83" }
                        $dbRaw = & $global:pythonCmd -X utf8 $pyScript "get-searches" $uParam 2>&1 | Out-String
                        $dbObj = $dbRaw.Trim() | ConvertFrom-Json
                            $needSaveSearches = $false
                            foreach ($us in $userSearches) {
                                $usCleanUrl = if ($us.url) { $us.url.ToString().Trim().TrimEnd('/') } else { "" }
                                $matched = @($dbObj.searches) | Where-Object { 
                                    ($_.url -and $_.url.ToString().Trim().TrimEnd('/') -eq $usCleanUrl) -or ($us.id -and $_.id -eq $us.id) 
                                } | Select-Object -First 1
                                if ($matched -and $matched.last_polled_at) {
                                    $prevPolled = if ($us.last_polled_at) { $us.last_polled_at.ToString() } else { "" }
                                    if ($prevPolled -ne $matched.last_polled_at.ToString()) {
                                        $us | Add-Member -NotePropertyName "last_polled_at" -NotePropertyValue $matched.last_polled_at -Force
                                        $needSaveSearches = $true
                                    }
                                }
                                $initVal = if ($matched -and $null -ne $matched.is_initialized) { [int]$matched.is_initialized } elseif ($null -ne $us.is_initialized) { [int]$us.is_initialized } else { 0 }
                                $prevInit = if ($null -ne $us.is_initialized) { [int]$us.is_initialized } else { 0 }
                                if ($prevInit -ne $initVal) {
                                    $us | Add-Member -NotePropertyName "is_initialized" -NotePropertyValue $initVal -Force
                                    $needSaveSearches = $true
                                }
                            }
                            if ($needSaveSearches) {
                                try {
                                    [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                                } catch {}
                            }
                    } catch {}
                }
                $maxS = if ($u -and $u.permissions -and $u.permissions.max_searches) { [int]$u.permissions.max_searches } elseif ($u -and $u.role -eq "admin") { 999 } else { 1 }
                $resObj = @{
                    success = $true
                    searches = [object[]]@($userSearches)
                    max_searches = $maxS
                    count = $userSearches.Count
                    is_expired = $isExpired
                    username = if ($u) { $u.username } else { "" }
                }
                $jsonOutput = ($resObj | ConvertTo-Json -Depth 5 -Compress)
                if ($userSearches.Count -eq 0) {
                    $jsonOutput = $jsonOutput -replace '"searches":\s*(\{\}|null)', '"searches":[]'
                } elseif ($userSearches.Count -eq 1 -or $jsonOutput -match '"searches":\s*\{') {
                    $jsonOutput = [System.Text.RegularExpressions.Regex]::Replace($jsonOutput, '"searches":\s*(\{.*?\})\s*,\s*"max_searches"', '"searches":[$1],"max_searches"')
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonOutput)
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        if ($request.HttpMethod -eq "POST" -and $localPath.StartsWith("/api/avito/")) {
            $global:lastStatsTime = $null
        }

        # API: Мониторинг Avito - Добавить поисковую ссылку (POST /api/avito/add-search)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/add-search") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $qUsername = if ($json.username) { $json.username.ToString().Trim() } else { "" }
                $url = if ($json.url) { $json.url.ToString().Trim() } else { "" }
                $name = if ($json.name) { $json.name.ToString().Trim() } else { "" }

                if (-not $url) {
                    $resObj = @{ success = $false; error = "Ссылка не может быть пустой" }
                } elseif ($url -notmatch '^https?://') {
                    $resObj = @{ success = $false; error = "Ссылка должна начинаться с http:// или https://" }
                } else {
                    $usersFile = Join-Path $path "data\users.json"
                    $users = @()
                    if ([System.IO.File]::Exists($usersFile)) {
                        $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                        if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                    }
                    $u = if ($qUsername) { $users | Where-Object { $_.username.ToLower() -eq $qUsername.ToLower() } | Select-Object -First 1 } else { $null }
                    if (-not $u) {
                        $u = $users | Where-Object { $_.role -eq "admin" } | Select-Object -First 1
                    }

                    # Проверка срока действия тарифа
                    $isExpired = $false
                    if ($u) {
                        if ($u.permissions -and $u.permissions.is_expired) {
                            $isExpired = $true
                        } elseif ($u.permissions -and $u.permissions.avito_expires_at) {
                            try {
                                $expDate = [DateTime]::Parse($u.permissions.avito_expires_at)
                                if ((Get-Date) -gt $expDate) { $isExpired = $true }
                            } catch {}
                        } elseif ($u.permissions -and -not $u.permissions.unlimited -and -not $u.permissions.active_key) {
                            $isExpired = $true
                        }
                        if (-not $u.permissions -or (-not $u.permissions.avito_bot -and -not $u.permissions.avito)) {
                            $isExpired = $true
                        }
                    }

                    if ($isExpired) {
                        $resObj = @{ success = $false; error = "Срок действия вашего тарифа истёк или доступ отключен. Обратитесь к администратору для продления." }
                    } else {
                        $existingSearches = if ($u.avito_searches) { @($u.avito_searches) } else { @() }
                        $maxS = if ($u.permissions -and $u.permissions.max_searches) { [int]$u.permissions.max_searches } elseif ($u.role -eq "admin") { 999 } else { 1 }
                        if ($u.role -ne "admin" -and $existingSearches.Count -ge $maxS) {
                            $resObj = @{ success = $false; error = "Достигнут лимит поисковых ссылок вашего тарифа (максимум $maxS). Удалите ненужные ссылки или обратитесь к администратору для расширения тарифа." }
                        } elseif ($existingSearches | Where-Object { $_.url.Trim().ToLower() -eq $url.ToLower() }) {
                            $resObj = @{ success = $false; error = "duplicate"; message = "Такая ссылка уже добавлена." }
                        } else {
                            if (-not $name) {
                                if ($url -match '[?&]q=([^&]+)') {
                                    $qVal = [System.Uri]::UnescapeDataString($Matches[1]).Replace('+', ' ')
                                    $name = "$qVal"
                                } elseif ($url -match 'videokarty') {
                                    $name = "Видеокарты"
                                } elseif ($url -match 'protsessory') {
                                    $name = "Процессоры"
                                } elseif ($url -match 'telefony') {
                                    $name = "Телефоны"
                                } elseif ($url -match 'noutbuki') {
                                    $name = "Ноутбуки"
                                } elseif ($url -match 'komplektuyuschie') {
                                    $name = "Комплектующие"
                                } else {
                                    $name = "Поиск Avito"
                                }
                            }
                            # Приписка фильтра цен из URL (pmin, pmax или base64 f=...)
                            $pminVal = $null
                            $pmaxVal = $null
                            if ($url -match '[?&]pmin=(\d+)') { $pminVal = $Matches[1] }
                            if ($url -match '[?&]pmax=(\d+)') { $pmaxVal = $Matches[1] }
                            if ((-not $pminVal -or -not $pmaxVal) -and $url -match '[?&]f=([^&]+)') {
                                try {
                                    $fVal = [System.Uri]::UnescapeDataString($Matches[1]).Replace('-', '+').Replace('~', '/')
                                    while ($fVal.Length % 4 -ne 0) { $fVal += '=' }
                                    $fBytes = [System.Convert]::FromBase64String($fVal)
                                    $fStr = [System.Text.Encoding]::UTF8.GetString($fBytes)
                                    if ($fStr -match '"from"\s*:\s*(\d+)' -and -not $pminVal) { $pminVal = $Matches[1] }
                                    if ($fStr -match '"to"\s*:\s*(\d+)' -and -not $pmaxVal) { $pmaxVal = $Matches[1] }
                                } catch {}
                            }
                            $pSuffix = ""
                            if ($pminVal -and $pmaxVal) { $pSuffix = "($pminVal-$pmaxVal)" }
                            elseif ($pminVal) { $pSuffix = "(от $pminVal)" }
                            elseif ($pmaxVal) { $pSuffix = "(до $pmaxVal)" }
                            if ($pSuffix -and $name -notmatch '\(\s*(?:от|до|\d+)\s*[\d\-–\s]*\)') {
                                $name = "$name $pSuffix"
                            }
                            $newId = [int][DateTimeOffset]::UtcNow.ToUnixTimeSeconds() + (Get-Random -Minimum 10 -Maximum 99)
                            $newSearch = [PSCustomObject]@{
                                id = $newId
                                name = $name
                                url = $url
                                created_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                                is_active = 1
                                is_initialized = 0
                            }
                            $u.avito_searches = @($u.avito_searches) + $newSearch
                            [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)

                            # Добавляем в SQLite бота с прямой привязкой к владельцу ссылки
                            try {
                                $pyScript = Join-Path $path "avito_api_helper.py"
                                $targetOwner = if ($u.username) { $u.username } else { "admin" }
                                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                                $b64Url = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($url))
                                $b64Name = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($name))
                                $b64Owner = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($targetOwner))
                                & $pCmd -X utf8 $pyScript "add-search" $b64Url $b64Name $b64Owner 2>&1 | Out-Null
                            } catch {}

                            $global:lastStatsTime = $null
                            $global:cachedRawStatsJson = $null

                            $resObj = @{ success = $true; id = $newId; name = $name; url = $url; searches = $u.avito_searches }
                        }
                    }
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Depth 5 -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Удалить поисковую ссылку (POST /api/avito/delete-search)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/delete-search") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $qUsername = if ($json.username) { $json.username.ToString().Trim() } else { "" }
                $searchId = [int]$json.id

                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                    if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                }

                $retSearches = @()
                if ($qUsername) {
                    $u = $users | Where-Object { $_.username.ToLower() -eq $qUsername.ToLower() } | Select-Object -First 1
                    if ($u -and $u.avito_searches) {
                        $u.avito_searches = @($u.avito_searches | Where-Object { $_.id -ne $searchId })
                        $retSearches = $u.avito_searches
                    }
                } else {
                    foreach ($user in $users) {
                        if ($user.avito_searches) {
                            $user.avito_searches = @($user.avito_searches | Where-Object { $_.id -ne $searchId })
                        }
                    }
                }
                [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)

                # Также удаляем из sqlite бота если есть
                try {
                    $pyScript = Join-Path $path "avito_api_helper.py"
                    & $global:pythonCmd -X utf8 $pyScript "del-search" $searchId 2>&1 | Out-Null
                } catch {}

                $global:lastStatsTime = $null
                $global:cachedRawStatsJson = $null

                $resObj = @{ success = $true; searches = $retSearches }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Depth 5 -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Включение/Выключение ссылки в поиске (POST /api/avito/toggle-search)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/toggle-search") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $qUsername = if ($json.username) { $json.username.ToString().Trim() } else { "" }
                $searchId = [int]$json.id
                $newActive = if ($json.is_active -ne $null) { [int]$json.is_active } else { $null }

                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                    if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                }

                $retActive = 1
                $retSearches = @()
                $targetUsers = if ($qUsername) { @($users | Where-Object { $_.username.ToLower() -eq $qUsername.ToLower() }) } else { @($users) }
                foreach ($u in $targetUsers) {
                    if ($u.avito_searches) {
                        foreach ($s in $u.avito_searches) {
                            if ([int]$s.id -eq $searchId) {
                                if ($newActive -ne $null) {
                                    $s.is_active = $newActive
                                } else {
                                    $cur = if ($s.is_active -ne $null) { [int]$s.is_active } else { 1 }
                                    $s.is_active = if ($cur -eq 1) { 0 } else { 1 }
                                }
                                $retActive = [int]$s.is_active
                            }
                        }
                    }
                    if ($qUsername -and $u.username.ToLower() -eq $qUsername.ToLower()) {
                        $retSearches = $u.avito_searches
                    }
                }
                [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)

                # Также обновляем статус в sqlite tracked_urls
                try {
                    $pyScript = Join-Path $path "avito_api_helper.py"
                    $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                    & $pCmd -X utf8 $pyScript "toggle-search" $searchId $retActive 2>&1 | Out-Null
                } catch {}

                $resObj = @{ success = $true; id = $searchId; is_active = $retActive; searches = $retSearches }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Depth 5 -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Редактировать поисковую ссылку (POST /api/avito/edit-search)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/edit-search") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $qUsername = if ($json.username) { $json.username.ToString().Trim() } else { "" }
                $searchId = [int]$json.id
                $newName = if ($json.name) { $json.name.ToString().Trim() } else { "" }
                $newUrl = if ($json.url) { $json.url.ToString().Trim() } else { "" }

                if (-not $newUrl -or $newUrl -notmatch '^https?://') {
                    $resObj = @{ success = $false; error = "Ссылка должна начинаться с http:// или https://" }
                } else {
                    $usersFile = Join-Path $path "data\users.json"
                    $users = @()
                    if ([System.IO.File]::Exists($usersFile)) {
                        $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                        if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                    }

                    $retSearches = @()
                    $targetUsers = if ($qUsername) { @($users | Where-Object { $_.username.ToLower() -eq $qUsername.ToLower() }) } else { @($users) }
                    foreach ($u in $targetUsers) {
                        if ($u.avito_searches) {
                            foreach ($s in $u.avito_searches) {
                                if ([int]$s.id -eq $searchId) {
                                    if ($newName) { $s.name = $newName }
                                    $s.url = $newUrl
                                    $s.is_initialized = 0
                                }
                            }
                        }
                        if ($qUsername -and $u.username.ToLower() -eq $qUsername.ToLower()) {
                            $retSearches = [object[]]@($u.avito_searches)
                        }
                    }
                    if ($retSearches.Count -eq 0 -and $targetUsers.Count -gt 0) {
                        $retSearches = [object[]]@($targetUsers[0].avito_searches)
                    }
                    [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)

                    # Синхронизируем с sqlite
                    try {
                        $pyScript = Join-Path $path "avito_api_helper.py"
                        $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                        $uOwner = if ($qUsername) { $qUsername } else { "skynet83" }
                        $b64Url = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($newUrl))
                        $b64Name = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($newName))
                        $b64Owner = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($uOwner))
                        & $pCmd -X utf8 $pyScript "edit-search" $searchId $b64Url $b64Name $b64Owner 2>&1 | Out-Null
                    } catch {}

                    $resObj = @{ success = $true; id = $searchId; name = $newName; url = $newUrl; searches = $retSearches }
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Depth 5 -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Просмотр ссылок пользователя Администратором (GET /api/users/avito-searches?username=...)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/users/avito-searches") {
            try {
                $qUsername = $request.QueryString["username"]
                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                    if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                }
                $u = $users | Where-Object { $_.username.ToLower() -eq $qUsername.ToLower() } | Select-Object -First 1
                if ($u) {
                    $searches = [object[]]@($u.avito_searches)
                    $maxS = if ($u.permissions -and $u.permissions.max_searches) { [int]$u.permissions.max_searches } elseif ($u.role -eq "admin") { 999 } else { 1 }
                    $resObj = @{
                        success = $true
                        username = $u.username
                        name = $u.name
                        searches = $searches
                        max_searches = $maxS
                        avito_duration = if ($u.permissions) { $u.permissions.avito_duration } else { "none" }
                        avito_expires_at = if ($u.permissions) { $u.permissions.avito_expires_at } else { $null }
                    }
                } else {
                    $resObj = @{ success = $false; error = "Пользователь не найден" }
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Depth 5 -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Запустить сканирование (POST /api/avito/check)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/check") {
            try {
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyScript "run-check" 2>&1 | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Загрузить все актуальные объявления по ссылкам (POST /api/avito/fetch-all)
        if (($request.HttpMethod -eq "POST" -or $request.HttpMethod -eq "GET") -and $localPath -eq "/api/avito/fetch-all") {
            try {
                $qUsername = ""
                $qSearchName = ""
                $qSearchUrl = ""
                if ($request.QueryString["username"]) {
                    $qUsername = $request.QueryString["username"].Trim()
                }
                if ($request.QueryString["search_name"]) {
                    $qSearchName = $request.QueryString["search_name"].Trim()
                }
                if ($request.QueryString["search_url"]) {
                    $qSearchUrl = $request.QueryString["search_url"].Trim()
                } elseif ($request.QueryString["url"]) {
                    $qSearchUrl = $request.QueryString["url"].Trim()
                }
                if ($request.HttpMethod -eq "POST" -and $request.HasEntityBody) {
                    try {
                        $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                        $reqBody = $reader.ReadToEnd()
                        if ($reqBody) {
                            $jsonObj = $reqBody | ConvertFrom-Json
                            if ($jsonObj.username) { $qUsername = $jsonObj.username.ToString().Trim() }
                            if ($jsonObj.search_name) { $qSearchName = $jsonObj.search_name.ToString().Trim() }
                            if ($jsonObj.search_url) { $qSearchUrl = $jsonObj.search_url.ToString().Trim() }
                            elseif ($jsonObj.url) { $qSearchUrl = $jsonObj.url.ToString().Trim() }
                        }
                    } catch {}
                }
                if (-not $qUsername) {
                    $qUsername = "skynet83"
                }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $b64User = [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($qUsername))
                $b64Search = if ($qSearchName) { [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($qSearchName)) } else { "" }
                $b64Url = if ($qSearchUrl) { [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($qSearchUrl)) } else { "" }
                $rawJson = & $pCmd -X utf8 $pyScript "fetch-all" $b64User $b64Search $b64Url 2>$null | Out-String
                $global:lastStatsTime = $null
                $global:cachedRawStatsJson = $null
                $cleanJson = if ($rawJson) { $rawJson.Trim() } else { "" }
                if ($cleanJson -match '(?s)(\{.*\})') {
                    $cleanJson = $Matches[1]
                }
                if (-not $cleanJson) {
                    $cleanJson = '{"success":false,"error":"Не удалось получить ответ от парсера объявлений"}'
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($cleanJson)
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Управление ботом ТГ (POST /api/avito/bot-toggle)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/bot-toggle") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $actionArg = if ($json.action) { $json.action } else { "start" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "bot-toggle" $actionArg 2>&1 | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Общий переключатель монитора (POST /api/avito/monitor-toggle)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/monitor-toggle") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $actionArg = if ($json.action) { $json.action } else { "toggle" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "set-monitor" $actionArg 2>&1 | Out-String
                $global:lastStatsTime = $null
                $global:cachedRawStatsJson = $null
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Получить настройки интервала и прокси (GET /api/avito/interval?username=...)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/avito/interval") {
            try {
                $qUsername = $request.QueryString["username"]
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "get-interval" 2>&1 | Out-String
                $intObj = $rawJson.Trim() | ConvertFrom-Json

                # Накладываем персональные настройки пользователя из users.json
                $usersFile = Join-Path $path "data\users.json"
                if ([System.IO.File]::Exists($usersFile)) {
                    $allUsers = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                    if ($allUsers -isnot [System.Collections.IEnumerable]) { $allUsers = @($allUsers) }
                    $targetU = if ($qUsername) { $allUsers | Where-Object { $_.username.ToLower() -eq $qUsername.ToLower() } | Select-Object -First 1 } else { $null }
                    if (-not $targetU) { $targetU = $allUsers | Where-Object { $_.role -eq "admin" } | Select-Object -First 1 }
                    if ($targetU) {
                        $sysTargetInterval = if ($intObj -and $null -ne $intObj.target_interval) { [string]$intObj.target_interval } else { "60" }
                        if ($sysTargetInterval.ToLower().StartsWith("rand")) { $sysTargetInterval = "60" }
                        $uTargetInterval = if ($targetU.active_interval) { [string]$targetU.active_interval } elseif ($targetU.target_interval) { [string]$targetU.target_interval } else { "60" }
                        if ($uTargetInterval.ToLower().StartsWith("rand")) { $uTargetInterval = "60" }
                        $intObj | Add-Member -NotePropertyName "target_interval" -NotePropertyValue $uTargetInterval -Force
                        $pCount = if ($intObj.proxy_count) { [int]$intObj.proxy_count } else { 0 }
                        if ($uTargetInterval -match "^\d+$") {
                            $tSec = [int]$uTargetInterval
                            $needed = [int][Math]::Ceiling(30.0 / [Math]::Max(1, $tSec))
                            $safe = if ($pCount -ge $needed) { $tSec } else { [Math]::Max($tSec, [int][Math]::Ceiling(30.0 / [Math]::Max(1, $pCount))) }
                            $intObj | Add-Member -NotePropertyName "needed_proxies" -NotePropertyValue $needed -Force
                            $intObj | Add-Member -NotePropertyName "safe_interval" -NotePropertyValue $safe -Force
                            $intObj | Add-Member -NotePropertyName "is_random" -NotePropertyValue $false -Force
                        } else {
                            $intObj | Add-Member -NotePropertyName "needed_proxies" -NotePropertyValue 0 -Force
                            $intObj | Add-Member -NotePropertyName "safe_interval" -NotePropertyValue "30-60" -Force
                            $intObj | Add-Member -NotePropertyName "is_random" -NotePropertyValue $true -Force
                        }
                    }
                }

                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($intObj | ConvertTo-Json -Depth 5 -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Установить целевую скорость опроса (POST /api/avito/interval)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/interval") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $secArg = if ($json.interval) { [string]$json.interval } else { "60" }
                if ($secArg.ToLower().StartsWith("rand")) { $secArg = "60" }
                $reqUser = if ($json.username) { [string]$json.username } else { "" }

                # Сохраняем индивидуально в users.json как активный выбранный интервал
                $usersFile = Join-Path $path "data\users.json"
                $allUsers = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $allUsers = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                    if ($allUsers -isnot [System.Collections.IEnumerable]) { $allUsers = @($allUsers) }
                }
                
                $targetU = if ($reqUser) { $allUsers | Where-Object { $_.username.ToLower() -eq $reqUser.ToLower() } | Select-Object -First 1 } else { $null }
                if (-not $targetU) {
                    $targetU = $allUsers | Where-Object { $_.role -eq "admin" } | Select-Object -First 1
                }

                if ($targetU) {
                    $uMin = if ($targetU.target_interval) { [int]$targetU.target_interval } else { 60 }
                    $reqSec = if ($secArg -match "^\d+$") { [int]$secArg } else { 60 }
                    if ($targetU.role -ne "admin" -and $targetU.username.ToLower() -ne "skynet83" -and $reqSec -lt $uMin) {
                        $secArg = [string]$uMin
                    }
                    if ($targetU.PSObject.Properties["active_interval"]) {
                        $targetU.active_interval = $secArg
                    } else {
                        $targetU | Add-Member -NotePropertyName "active_interval" -NotePropertyValue $secArg -Force
                    }
                    [System.IO.File]::WriteAllText($usersFile, ($allUsers | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                }

                # Обновляем глобальный monitor_state.json для синхронизации с Telegram-ботом (для админа)
                if ($targetU -and ($targetU.role -eq "admin" -or $targetU.username.ToLower() -eq "skynet83" -or -not $reqUser)) {
                    $pyScript = Join-Path $path "avito_api_helper.py"
                    $null = & $global:pythonCmd -X utf8 $pyScript "set-interval" $secArg 2>&1
                }

                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "get-interval" 2>&1 | Out-String
                $intObj = $rawJson.Trim() | ConvertFrom-Json
                $intObj | Add-Member -NotePropertyName "target_interval" -NotePropertyValue $secArg -Force
                $pCount = if ($intObj.proxy_count) { [int]$intObj.proxy_count } else { 0 }
                if ($secArg -match "^\d+$") {
                    $tSec = [int]$secArg
                    $needed = [Math]::Min(360, [Math]::Max(15, [int][Math]::Ceiling(30.0 / [Math]::Max(1, $tSec)) * 10))
                    $safe = if ($pCount -ge $needed) { $tSec } else { [Math]::Max($tSec, [int][Math]::Ceiling(30.0 / [Math]::Max(1, $pCount))) }
                    $intObj | Add-Member -NotePropertyName "needed_proxies" -NotePropertyValue $needed -Force
                    $intObj | Add-Member -NotePropertyName "safe_interval" -NotePropertyValue $safe -Force
                    $intObj | Add-Member -NotePropertyName "is_random" -NotePropertyValue $false -Force
                } else {
                    $intObj | Add-Member -NotePropertyName "needed_proxies" -NotePropertyValue 15 -Force
                    $intObj | Add-Member -NotePropertyName "safe_interval" -NotePropertyValue "30-60" -Force
                    $intObj | Add-Member -NotePropertyName "is_random" -NotePropertyValue $true -Force
                }

                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($intObj | ConvertTo-Json -Depth 5 -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Получить список прокси (GET /api/avito/proxies)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/avito/proxies") {
            try {
                $qUsername = Get-UrlParam $request "username"
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = if ($qUsername) {
                    & $global:pythonCmd -X utf8 $pyScript "get-proxies" $qUsername 2>&1 | Out-String
                } else {
                    & $global:pythonCmd -X utf8 $pyScript "get-proxies" 2>&1 | Out-String
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Поиск бесплатных прокси (POST /api/avito/proxies/fetch) - НЕБЛОКИРУЮЩИЙ РЕЖИМ
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/proxies/fetch") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $actionArg = if ($json.action) { $json.action } else { "start" }
                $sourceArg = if ($json.source) { $json.source } else { "manual" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "fetch-proxies" $actionArg $sourceArg 2>&1 | Out-String

                # Дополнительно гарантируем непрерывность фонового воркера прокси через Start-Process
                if ($actionArg -eq "start") {
                    $botDir = Join-Path $path "avito_bot"
                    $workerScript = Join-Path $botDir "proxy_worker.py"
                    $pidFile = Join-Path $botDir "proxy_worker.pid"
                    $isWorkerRunning = $false
                    if (Test-Path $pidFile) {
                        try {
                            $wPid = [int](Get-Content $pidFile -ErrorAction SilentlyContinue).Trim()
                            $wProc = Get-Process -Id $wPid -ErrorAction SilentlyContinue
                            if ($wProc -and -not $wProc.HasExited) { $isWorkerRunning = $true }
                        } catch {}
                    }
                    if (-not $isWorkerRunning) {
                        $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                        $wProc = Start-Process -FilePath $pCmd -ArgumentList "-X utf8 `"$workerScript`" fetch 300" -WorkingDirectory $botDir -WindowStyle Hidden -PassThru
                        if ($wProc) {
                            $wProc.Id | Out-File -FilePath $pidFile -Encoding ASCII
                        }
                    }
                }

                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Правила автоматизации бот + прокси (POST /api/avito/apply-rules)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/apply-rules") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $mon = if ($null -ne $json.monitoring) { [bool]$json.monitoring } else { $false }
                $tg  = if ($null -ne $json.tg_bot) { [bool]$json.tg_bot } else { $false }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "apply-rules" ($mon.ToString().ToLower()) ($tg.ToString().ToLower()) 2>&1 | Out-String

                if (-not ($mon -or $tg)) {
                    $botDir = Join-Path $path "avito_bot"
                    $pidFile = Join-Path $botDir "proxy_worker.pid"
                    if (Test-Path $pidFile) {
                        try {
                            $wPid = [int](Get-Content $pidFile -ErrorAction SilentlyContinue).Trim()
                            Stop-Process -Id $wPid -Force -ErrorAction SilentlyContinue
                            Remove-Item -Path $pidFile -Force -ErrorAction SilentlyContinue
                        } catch {}
                    }
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Добавить пользовательские прокси (POST /api/avito/proxies/add)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/proxies/add") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $proxiesText = if ($json.proxies) { $json.proxies } else { "" }
                $uName = if ($json.username) { $json.username.ToString().Trim() } else { Get-UrlParam $request "username" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = if ($uName) {
                    & $global:pythonCmd -X utf8 $pyScript "add-proxies" $proxiesText $uName 2>&1 | Out-String
                } else {
                    & $global:pythonCmd -X utf8 $pyScript "add-proxies" $proxiesText 2>&1 | Out-String
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Удалить прокси (POST /api/avito/proxies/delete)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/proxies/delete") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $proxyText = if ($json.proxy) { $json.proxy.ToString().Trim() } else { "" }
                $uName = if ($json.username) { $json.username.ToString().Trim() } else { Get-UrlParam $request "username" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = if ($uName) {
                    & $global:pythonCmd -X utf8 $pyScript "del-proxy" $proxyText $uName 2>&1 | Out-String
                } else {
                    & $global:pythonCmd -X utf8 $pyScript "del-proxy" $proxyText 2>&1 | Out-String
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Очистить все прокси (POST /api/avito/proxies/clear)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/proxies/clear") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $bodyStr = $reader.ReadToEnd()
                $json = if ($bodyStr) { $bodyStr | ConvertFrom-Json } else { $null }
                $uName = if ($json -and $json.username) { $json.username.ToString().Trim() } else { Get-UrlParam $request "username" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = if ($uName) {
                    & $global:pythonCmd -X utf8 $pyScript "clear-proxies" $uName 2>&1 | Out-String
                } else {
                    & $global:pythonCmd -X utf8 $pyScript "clear-proxies" 2>&1 | Out-String
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Проверить все прокси (POST /api/avito/proxies/check)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/proxies/check") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $bodyStr = $reader.ReadToEnd()
                $json = if ($bodyStr) { $bodyStr | ConvertFrom-Json } else { $null }
                $uName = if ($json -and $json.username) { $json.username.ToString().Trim() } else { Get-UrlParam $request "username" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = if ($uName) {
                    & $global:pythonCmd -X utf8 $pyScript "check-proxies" $uName 2>&1 | Out-String
                } else {
                    & $global:pythonCmd -X utf8 $pyScript "check-proxies" 2>&1 | Out-String
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Список клиентов (GET /api/avito/users)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/avito/users") {
            try {
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "get-users" 2>&1 | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Изменить статус клиента / Удалить (POST /api/avito/users/status)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/users/status") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $userIdArg = if ($json.user_id) { $json.user_id } else { 0 }
                $statusArg = if ($json.status) { $json.status } else { "approved" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "set-user-status" $userIdArg $statusArg 2>&1 | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Синхронизация пачки объявлений / проверка статуса и фото (POST /api/avito/items/sync-batch)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/items/sync-batch") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $reqBody = $reader.ReadToEnd()
                if (-not $reqBody) { $reqBody = "{}" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "sync-items" $reqBody 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Очистка устаревших тестовых объявлений (POST /api/avito/items/cleanup)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/items/cleanup") {
            try {
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "cleanup-legacy" 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Удалить карточки объявлений (все или по ссылке) (POST /api/avito/items/clear)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/items/clear") {
            try {
                $qSearchName = ""
                $qKeepIds = ""
                if ($request.QueryString["search_name"]) {
                    $qSearchName = $request.QueryString["search_name"].Trim()
                }
                if ($request.HasEntityBody) {
                    try {
                        $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                        $reqBody = $reader.ReadToEnd()
                        if ($reqBody) {
                            $jsonObj = $reqBody | ConvertFrom-Json
                            if ($jsonObj.search_name) { $qSearchName = $jsonObj.search_name.ToString().Trim() }
                            if ($jsonObj.keep_ids) {
                                if ($jsonObj.keep_ids -is [Array]) {
                                    $qKeepIds = ($jsonObj.keep_ids -join ",")
                                } else {
                                    $qKeepIds = $jsonObj.keep_ids.ToString().Trim()
                                }
                            }
                        }
                    } catch {}
                }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $b64Search = if ($qSearchName) { [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($qSearchName)) } else { "" }
                $b64Keep = if ($qKeepIds) { [System.Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($qKeepIds)) } else { "" }
                $rawJson = & $pCmd -X utf8 $pyScript "clear-all-items" $b64Search $b64Keep 2>$null | Out-String
                $global:lastStatsTime = $null
                $global:cachedRawStatsJson = $null
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Добавить/удалить из избранного (POST /api/avito/favorites/toggle)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/favorites/toggle") {
            try {
                $qItemId = ""
                if ($request.HasEntityBody) {
                    try {
                        $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                        $reqBody = $reader.ReadToEnd()
                        if ($reqBody) {
                            $jsonObj = $reqBody | ConvertFrom-Json
                            if ($jsonObj.item_id) { $qItemId = $jsonObj.item_id.ToString().Trim() }
                        }
                    } catch {}
                }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyScript "toggle-favorite" $qItemId 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Удалить одну карточку объявления (POST /api/avito/items/delete)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/items/delete") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $itemIdArg = if ($json.item_id) { [string]$json.item_id } else { "" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "delete-item" "$itemIdArg" 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Добавить в Черный Список (POST /api/avito/blacklist/add)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/blacklist/add") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $sellerArg = if ($json.seller) { [string]$json.seller } else { "" }
                $sellerB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($sellerArg))
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "add-blacklist" "$sellerB64" 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Получить Черный Список (GET /api/avito/blacklist)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/avito/blacklist") {
            try {
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "get-blacklist" 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Мониторинг Avito - Удалить из Черного Списка (POST /api/avito/blacklist/delete)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/blacklist/delete") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $sellerArg = if ($json.seller) { [string]$json.seller } else { "" }
                $sellerB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($sellerArg))
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawJson = & $global:pythonCmd -X utf8 $pyScript "del-blacklist" "$sellerB64" 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Снайпер Avito - Статус авторизации и конфигурация (GET /api/avito/sniper/status)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/avito/sniper/status") {
            try {
                $nowTicks = [System.DateTime]::UtcNow.Ticks
                $isNegativeCache = ($global:lastSniperStatusJson -and $global:lastSniperStatusJson -match '"authenticated":\s*false')
                $forceCheck = ($request.QueryString -and $request.QueryString["force"] -eq "1") -or ($nowTicks - $global:lastSniperStatusTime) -ge 12000000 -or $isNegativeCache
                if (-not $forceCheck -and $global:lastSniperStatusJson) {
                    $rawJson = $global:lastSniperStatusJson
                } else {
                    $pyScript = Join-Path $path "avito_api_helper.py"
                    $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                    $rawJson = (& $pCmd -X utf8 $pyScript "sniper-status" 2>$null | Out-String).Trim()
                    if ($rawJson -and $rawJson.StartsWith("{")) {
                        $global:lastSniperStatusJson = $rawJson
                        $global:lastSniperStatusTime = $nowTicks
                    }
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson)
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Снайпер Avito - Открыть окно браузера для входа (POST /api/avito/sniper/login)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/sniper/login") {
            try {
                $global:lastSniperStatusJson = $null
                $global:lastSniperStatusTime = 0
                $isReauth = ($request.QueryString -and $request.QueryString["reauth"] -eq "1")
                $reauthArg = if ($isReauth) { "reauth" } else { "normal" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyScript "sniper-login" $reauthArg 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Снайпер Avito - Получить / Сохранить настройки (GET / POST /api/avito/sniper/config)
        if ($localPath -eq "/api/avito/sniper/config") {
            try {
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }

                if ($request.HttpMethod -eq "POST") {
                    $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                    $jsonStr = $reader.ReadToEnd()
                    $cfgB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($jsonStr))
                    $global:lastSniperStatusJson = $null
                    $rawJson = (& $pCmd -X utf8 $pyScript "sniper-save-config" "$cfgB64" 2>$null | Out-String).Trim()
                } else {
                    $rawJson = (& $pCmd -X utf8 $pyScript "sniper-get-config" 2>$null | Out-String).Trim()
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Снайпер Avito - Быстрый чекаут (POST /api/avito/sniper/checkout)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/sniper/checkout") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $itemId = if ($json.item_id) { [string]$json.item_id } else { "" }
                $itemUrl = if ($json.url) { [string]$json.url } else { "" }
                $autoPay = if ($null -ne $json.auto_pay) { if ($json.auto_pay) { "true" } else { "false" } } else { "" }
                $headless = if ($null -ne $json.headless) { if ($json.headless) { "true" } else { "false" } } else { "" }
                $idB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($itemId))
                $urlB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($itemUrl))
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyScript "sniper-checkout" "$idB64" "$urlB64" "$autoPay" "$headless" 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Снайпер Avito - Получить предпросмотр чекаута для сайта (POST /api/avito/sniper/checkout-preview)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/sniper/checkout-preview") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $itemId = if ($json.item_id) { [string]$json.item_id } else { "" }
                $itemUrl = if ($json.url) { [string]$json.url } else { "" }
                $idB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($itemId))
                $urlB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($itemUrl))
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyScript "sniper-checkout-preview" "$idB64" "$urlB64" 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Снайпер Avito - Подтвердить и выполнить заказ роботом (POST /api/avito/sniper/checkout-confirm)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/sniper/checkout-confirm") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $itemId = if ($json.item_id) { [string]$json.item_id } else { "" }
                $itemUrl = if ($json.url) { [string]$json.url } else { "" }
                $pm = if ($json.payment_method) { [string]$json.payment_method } else { "card" }
                $sms = if ($json.sms_code) { [string]$json.sms_code } else { "" }
                $idB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($itemId))
                $urlB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($itemUrl))
                $pmB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($pm))
                $smsB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($sms))
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyScript "sniper-checkout-confirm" "$idB64" "$urlB64" "$pmB64" "$smsB64" 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Снайпер Avito - Отправка сообщения продавцу (POST /api/avito/sniper/message)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/sniper/message") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $itemId = if ($json.item_id) { [string]$json.item_id } else { "" }
                $itemUrl = if ($json.url) { [string]$json.url } else { "" }
                $msgText = if ($json.message) { [string]$json.message } else { "Здравствуйте! Товар в наличии?" }
                $idB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($itemId))
                $urlB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($itemUrl))
                $msgB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($msgText))
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyScript "sniper-message" "$idB64" "$urlB64" "$msgB64" 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Снайпер Avito - Отмена заказа на Авито (POST /api/avito/sniper/cancel-order)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/sniper/cancel-order") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $itemId = if ($json.item_id) { [string]$json.item_id } else { "" }
                $itemUrl = if ($json.url) { [string]$json.url } else { "" }
                $orderUrl = if ($json.order_url) { [string]$json.order_url } else { "" }
                $idB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($itemId))
                $urlB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($itemUrl))
                $orderB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($orderUrl))
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyScript "sniper-cancel-order" "$idB64" "$urlB64" "$orderB64" 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Снайпер Avito - Проверка статуса отправки заказов в корзине (POST /api/avito/sniper/check-cart-orders)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/avito/sniper/check-cart-orders") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $rawBody = $reader.ReadToEnd()
                $json = if ($rawBody) { $rawBody | ConvertFrom-Json } else { $null }
                $itemsJson = "[]"
                if ($json -and $json.items) {
                    $itemsJson = ($json.items | ConvertTo-Json -Compress -Depth 5)
                }
                $itemsB64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($itemsJson))
                $pyScript = Join-Path $path "avito_api_helper.py"
                $pCmd = if ($global:pythonCmd) { $global:pythonCmd } else { "python" }
                $rawJson = & $pCmd -X utf8 $pyScript "sniper-check-cart-orders" "$itemsB64" 2>$null | Out-String
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Синхронизация профиля (GET /api/me?username=...&token=...)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/me") {
            try {
                $qUsername = Get-UrlParam $request "username"
                $qToken = Get-UrlParam $request "token"
                if (-not $qToken) {
                    $qToken = $request.Headers["X-Session-Token"]
                }
                $cleanUser = if ($qUsername) { ($qUsername.ToLower().Trim() -replace '\s*\(.*?\)', '') } else { "" }
                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8).Trim().Trim([char]0xfeff) | ConvertFrom-Json
                    if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                }
                $u = $null
                if ($cleanUser) {
                    $u = $users | Where-Object {
                        $uName = if ($_.username) { $_.username.ToString().ToLower().Trim() } else { "" }
                        $uDisplayName = if ($_.name) { ($_.name.ToString().ToLower().Trim() -replace '\s*\(.*?\)', '') } else { "" }
                        ($uName -eq $cleanUser) -or ($uDisplayName -eq $cleanUser) -or ($cleanUser -in @("admin", "skynet") -and ($_.role -eq "admin" -or $uName -eq "skynet83"))
                    } | Select-Object -First 1
                }
                if (-not $u -and $qToken) {
                    $u = $users | Where-Object {
                        ($_.sessions -and ($_.sessions.desktop.token -eq $qToken -or $_.sessions.mobile.token -eq $qToken)) -or
                        ($_.session_token -and $_.session_token -eq $qToken)
                    } | Select-Object -First 1
                }
                if (-not $u -and ($remoteIp -in @("127.0.0.1", "::1", "localhost") -and ($cleanUser -in @("admin", "skynet", "skynet83") -or -not $cleanUser))) {
                    $u = $users | Where-Object { $_.role -eq "admin" -or ($_.username -and $_.username.ToLower() -eq "skynet83") } | Select-Object -First 1
                }
                if ($u) {
                    # Проверка правила «1 компьютер и 1 телефон»:
                    if ($qToken) {
                        $desktopToken = if ($u.sessions -and $u.sessions.desktop) { $u.sessions.desktop.token } else { $null }
                        $mobileToken = if ($u.sessions -and $u.sessions.mobile) { $u.sessions.mobile.token } else { $null }
                        $legacyToken = if ($u.session_token) { $u.session_token } else { $null }

                        # Автоматическая миграция старых сессий без объекта sessions
                        if (-not $desktopToken -and -not $mobileToken -and $legacyToken) {
                            $ua = $request.UserAgent
                            $isMob = ($ua -and ($ua -match "Mobile|Android|iPhone|iPad|iPod|webOS|BlackBerry|IEMobile|Opera Mini"))
                            $slotName = if ($isMob) { "mobile" } else { "desktop" }
                            if (-not ($u | Get-Member -Name "sessions")) {
                                $u | Add-Member -NotePropertyName "sessions" -NotePropertyValue ([PSCustomObject]@{}) -Force
                            }
                            $u.sessions | Add-Member -NotePropertyName $slotName -NotePropertyValue ([PSCustomObject]@{
                                token = $legacyToken
                                last_ip = $remoteIp
                                last_seen = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                                device_type = $slotName
                            }) -Force
                            $desktopToken = if ($u.sessions.desktop) { $u.sessions.desktop.token } else { $null }
                            $mobileToken = if ($u.sessions.mobile) { $u.sessions.mobile.token } else { $null }
                        }

                        $isTokenValid = ($qToken -eq $desktopToken) -or ($qToken -eq $mobileToken) -or ($qToken -eq $legacyToken)
                        if (-not $isTokenValid) {
                            $ua = $request.UserAgent
                            $isMob = ($ua -and ($ua -match "Mobile|Android|iPhone|iPad|iPod|webOS|BlackBerry|IEMobile|Opera Mini"))
                            $devText = if ($isMob) { "другого телефона" } else { "другого компьютера" }
                            $resObj = @{
                                success = $false
                                error = "session_expired"
                                message = "⚠️ Доступ прекращен: выполнен вход с $devText (разрешен 1 компьютер и 1 телефон)"
                            }
                            $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                            $response.StatusCode = 401
                            $response.ContentType = "application/json; charset=utf-8"
                            $response.ContentLength64 = $bytes.Length
                            $response.OutputStream.Write($bytes, 0, $bytes.Length)
                            $response.Close()
                            continue
                        }

                        if ($qToken -eq $desktopToken -and $u.sessions.desktop) {
                            $u.sessions.desktop.last_seen = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                            $u.sessions.desktop.last_ip = $remoteIp
                        } elseif ($qToken -eq $mobileToken -and $u.sessions.mobile) {
                            $u.sessions.mobile.last_seen = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                            $u.sessions.mobile.last_ip = $remoteIp
                        }
                    }

                    if (-not $u.session_token) {
                        $initToken = New-SessionToken
                        $u | Add-Member -NotePropertyName "session_token" -NotePropertyValue $initToken -Force
                        try {
                            [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                        } catch {}
                    }

                    $u.last_seen = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                    $u.last_ip = $remoteIp
                    if ($clientMac) { $u | Add-Member -NotePropertyName "last_mac" -NotePropertyValue $clientMac -Force }

                    $isExpired = $false
                    if ($u.role -ne "admin" -and $u.permissions -and $u.permissions.avito_expires_at) {
                        try {
                            $expDate = [DateTime]::Parse($u.permissions.avito_expires_at)
                            if ((Get-Date) -gt $expDate) { $isExpired = $true }
                        } catch {}
                    }
                    $hasAvitoBot = if ($u.role -eq "admin" -or $u.username.ToLower() -eq "skynet83") {
                        $true
                    } elseif ($isExpired) {
                        $false
                    } elseif ($u.permissions) {
                        [bool]($u.permissions.avito_bot -or $u.permissions.avito)
                    } else {
                        $false
                    }
                    $uPerms = [PSCustomObject]@{
                        avito_bot        = $hasAvitoBot
                        avito            = $hasAvitoBot
                        tg_bot           = if ($isExpired) { $false } elseif ($u.permissions -and $u.permissions.tg_bot -ne $null) { [bool]$u.permissions.tg_bot } else { $hasAvitoBot }
                        monitoring       = if ($isExpired) { $false } elseif ($u.permissions -and $u.permissions.monitoring -ne $null) { [bool]$u.permissions.monitoring } else { $true }
                        avito_duration   = if ($u.permissions -and $u.permissions.avito_duration) { $u.permissions.avito_duration } else { "none" }
                        avito_expires_at = if ($u.permissions) { $u.permissions.avito_expires_at } else { $null }
                        is_expired       = $isExpired
                        max_searches     = if ($u.permissions -and $u.permissions.max_searches) { [int]$u.permissions.max_searches } elseif ($u.role -eq "admin") { 999 } else { 1 }
                    }
                    $resObj = @{
                        success = $true
                        user = @{
                            username      = if ($u.username -match '(?i)deev|деев') { "skynet83" } else { $u.username }
                            name          = if ($u.name -match '(?i)deev|деев') { "skynet83" } else { $u.name }
                            role          = $u.role
                            last_ip       = $u.last_ip
                            last_seen     = $u.last_seen
                            session_token = $u.session_token
                            permissions   = $uPerms
                            telegram_chat_id  = if ($u.telegram_chat_id) { $u.telegram_chat_id } else { $null }
                            telegram_username = if ($u.telegram_username) { $u.telegram_username } else { $null }
                            telegram_pending  = if ($u.telegram_pending) { $u.telegram_pending } else { $null }
                            target_interval   = if ($u.target_interval) { $u.target_interval } else { "60" }
                            active_interval   = if ($u.active_interval) { $u.active_interval } elseif ($u.target_interval) { $u.target_interval } else { "60" }
                            avito_searches    = if ($u.avito_searches) { [object[]]@($u.avito_searches) } else { @() }
                            plain_password    = if ($u.plain_password) { $u.plain_password } else { "" }
                        }
                    }
                } else {
                    $resObj = @{ success = $false; error = "Пользователь не найден" }
                }
                $jsonOutput = ($resObj | ConvertTo-Json -Depth 6 -Compress)
                if ($jsonOutput -match '"avito_searches":\s*\{') {
                    $jsonOutput = $jsonOutput -replace '"avito_searches":\s*(\{.*?\})([,\}])', '"avito_searches":[$1]$2'
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonOutput)
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                try {
                    $errBytes = [System.Text.Encoding]::UTF8.GetBytes((@{ success = $false; error = ("Ошибка сервера: " + $_.Exception.Message) } | ConvertTo-Json -Compress))
                    $response.ContentType = "application/json; charset=utf-8"
                    $response.ContentLength64 = $errBytes.Length
                    $response.OutputStream.Write($errBytes, 0, $errBytes.Length)
                } catch {}
            }
            $response.Close()
            continue
        }

        # API: Вход (POST /api/login)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/login") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8).Trim().Trim([char]0xfeff) | ConvertFrom-Json
                    if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                }
                $targetUser = if ($json.username) { $json.username.ToString().Trim() } else { "" }
                $targetPass = if ($json.password) { $json.password.ToString().Trim() } else { "" }
                $targetHash = Get-PasswordHash $targetPass
                $user = $users | Where-Object {
                    $uName = if ($_.username) { $_.username.ToString().Trim() } else { "" }
                    ($uName.ToLower() -eq $targetUser.ToLower()) -and
                    ($_.password -eq $targetHash -or $_.password -eq $targetPass -or $_.password -eq $json.password)
                } | Select-Object -First 1
                if ($user) {
                    if ($user.password -eq $json.password) {
                        $user.password = $targetHash
                    }
                    $ua = $request.UserAgent
                    $isMobile = $false
                    if ($json.device_type) {
                        $dt = $json.device_type.ToString().ToLower()
                        $isMobile = ($dt -eq "mobile" -or $dt -eq "phone")
                    } elseif ($ua -and ($ua -match "Mobile|Android|iPhone|iPad|iPod|webOS|BlackBerry|IEMobile|Opera Mini")) {
                        $isMobile = $true
                    }
                    $slot = if ($isMobile) { "mobile" } else { "desktop" }

                    $sessionToken = New-SessionToken
                    if (-not ($user | Get-Member -Name "sessions")) {
                        $user | Add-Member -NotePropertyName "sessions" -NotePropertyValue ([PSCustomObject]@{}) -Force
                    }
                    $slotData = [PSCustomObject]@{
                        token = $sessionToken
                        last_ip = $remoteIp
                        last_seen = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                        device_type = $slot
                        user_agent = if ($ua) { $ua } else { "" }
                    }
                    if (-not ($user.sessions | Get-Member -Name $slot)) {
                        $user.sessions | Add-Member -NotePropertyName $slot -NotePropertyValue $slotData -Force
                    } else {
                        $user.sessions.$slot = $slotData
                    }
                    if ($targetPass) {
                        if (-not ($user | Get-Member -Name "plain_password")) {
                            $user | Add-Member -NotePropertyName "plain_password" -NotePropertyValue $targetPass -Force
                        } else {
                            $user.plain_password = $targetPass
                        }
                    }
                    $user.session_token = $sessionToken
                    $user.last_ip = $remoteIp
                    if ($clientMac) { $user | Add-Member -NotePropertyName "last_mac" -NotePropertyValue $clientMac -Force }
                    $user.last_seen = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                    try {
                        [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                    } catch {}
                    $isExpired = $false
                    if ($user.role -ne "admin" -and $user.permissions -and $user.permissions.avito_expires_at) {
                        try {
                            $expDate = [DateTime]::Parse($user.permissions.avito_expires_at)
                            if ((Get-Date) -gt $expDate) { $isExpired = $true }
                        } catch {}
                    }
                    $hasAvitoBot = if ($user.role -eq "admin" -or $user.username.ToLower() -eq "skynet83") {
                        $true
                    } elseif ($isExpired) {
                        $false
                    } elseif ($user.permissions) {
                        [bool]($user.permissions.avito_bot -or $user.permissions.avito)
                    } else {
                        $false
                    }
                    $userPerms = [PSCustomObject]@{
                        avito_bot        = $hasAvitoBot
                        avito            = $hasAvitoBot
                        tg_bot           = if ($isExpired) { $false } elseif ($user.permissions -and $user.permissions.tg_bot -ne $null) { [bool]$user.permissions.tg_bot } else { $hasAvitoBot }
                        monitoring       = if ($isExpired) { $false } elseif ($user.permissions -and $user.permissions.monitoring -ne $null) { [bool]$user.permissions.monitoring } else { $true }
                        avito_duration   = if ($user.permissions -and $user.permissions.avito_duration) { $user.permissions.avito_duration } else { "none" }
                        avito_expires_at = if ($user.permissions) { $user.permissions.avito_expires_at } else { $null }
                        is_expired       = $isExpired
                        max_searches     = if ($user.permissions -and $user.permissions.max_searches) { [int]$user.permissions.max_searches } elseif ($user.role -eq "admin") { 999 } else { 1 }
                    }
                    $resObj = @{
                        success = $true
                        session_token = $sessionToken
                        user = @{
                            username          = $user.username
                            name              = $user.name
                            role              = $user.role
                            last_ip           = $user.last_ip
                            last_seen         = $user.last_seen
                            session_token     = $sessionToken
                            permissions       = $userPerms
                            telegram_chat_id  = if ($user.telegram_chat_id) { $user.telegram_chat_id } else { $null }
                            telegram_username = if ($user.telegram_username) { $user.telegram_username } else { $null }
                            telegram_pending  = if ($user.telegram_pending) { $user.telegram_pending } else { $null }
                            target_interval   = if ($user.target_interval) { $user.target_interval } else { "60" }
                            active_interval   = if ($user.active_interval) { $user.active_interval } elseif ($user.target_interval) { $user.target_interval } else { "60" }
                            avito_searches    = if ($user.avito_searches) { [object[]]@($user.avito_searches) } else { @() }
                            plain_password    = if ($user.plain_password) { $user.plain_password } else { $targetPass }
                        }
                    }
                } else {
                    $resObj = @{ success = $false; error = "Неверный логин или пароль" }
                }
                $jsonOutput = ($resObj | ConvertTo-Json -Depth 6 -Compress)
                if ($jsonOutput -match '"avito_searches":\s*\{') {
                    $jsonOutput = $jsonOutput -replace '"avito_searches":\s*(\{.*?\})([,\}])', '"avito_searches":[$1]$2'
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonOutput)
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                try {
                    $errBytes = [System.Text.Encoding]::UTF8.GetBytes((@{ success = $false; error = ("Ошибка сервера: " + $_.Exception.Message) } | ConvertTo-Json -Compress))
                    $response.ContentType = "application/json; charset=utf-8"
                    $response.ContentLength64 = $errBytes.Length
                    $response.OutputStream.Write($errBytes, 0, $errBytes.Length)
                } catch {}
            }
            $response.Close()
            continue
        }

        # API: Регистрация (POST /api/register)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/register") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8).Trim().Trim([char]0xfeff) | ConvertFrom-Json
                    if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                }

                $targetRegUser = if ($json.username) { $json.username.ToString().Trim() } else { "" }
                $exists = $users | Where-Object {
                    $uName = if ($_.username) { $_.username.ToString().Trim() } else { "" }
                    $uName.ToLower() -eq $targetRegUser.ToLower()
                }
                if ($exists) {
                    $resObj = @{ success = $false; error = "Пользователь с таким логином уже существует" }
                } else {
                    $newPerms = [PSCustomObject]@{
                        avito = $false
                        avito_bot = $false
                        tg_bot = $false
                        monitoring = $true
                        avito_duration = "none"
                        avito_expires_at = $null
                        max_searches = 1
                    }
                    $ua = $request.UserAgent
                    $isMobile = $false
                    if ($json.device_type) {
                        $dt = $json.device_type.ToString().ToLower()
                        $isMobile = ($dt -eq "mobile" -or $dt -eq "phone")
                    } elseif ($ua -and ($ua -match "Mobile|Android|iPhone|iPad|iPod|webOS|BlackBerry|IEMobile|Opera Mini")) {
                        $isMobile = $true
                    }
                    $slot = if ($isMobile) { "mobile" } else { "desktop" }

                    $sessionToken = New-SessionToken
                    $sessionsObj = [PSCustomObject]@{
                        $slot = [PSCustomObject]@{
                            token = $sessionToken
                            last_ip = $remoteIp
                            last_seen = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                            device_type = $slot
                            user_agent = if ($ua) { $ua } else { "" }
                        }
                    }
                    $plainPass = $json.password.ToString().Trim()
                    $newUser = [PSCustomObject]@{
                        username = $targetRegUser
                        password = (Get-PasswordHash $plainPass)
                        plain_password = $plainPass
                        name = if ($json.name -and $json.name.ToString().Trim()) { $json.name.ToString().Trim() } else { $targetRegUser }
                        role = "user"
                        last_ip = $remoteIp
                        last_mac = if ($clientMac) { $clientMac } else { "" }
                        last_seen = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                        session_token = $sessionToken
                        sessions = $sessionsObj
                        target_interval = "60"
                        active_interval = "60"
                        permissions = $newPerms
                        avito_searches = @()
                        telegram_chat_id = $null
                        telegram_username = $null
                        telegram_pending = $null
                    }
                    $users += $newUser
                    [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                    $resObj = @{
                        success = $true
                        session_token = $sessionToken
                        user = @{
                            username          = $newUser.username
                            name              = $newUser.name
                            role              = $newUser.role
                            last_ip           = $newUser.last_ip
                            last_seen         = $newUser.last_seen
                            session_token     = $sessionToken
                            permissions       = $newPerms
                            telegram_chat_id  = $null
                            telegram_username = $null
                            telegram_pending  = $null
                            target_interval   = "60"
                            active_interval   = "60"
                            avito_searches    = @()
                            plain_password    = $plainPass
                        }
                    }
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Список пользователей и гостей (GET /api/users)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/users") {
            try {
                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                    if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                }
                $safeUsers = @()
                $needsSave = $false
                $cleanedUsers = @()
                foreach ($u in $users) {
                    $uNameStr = if ($u.username) { $u.username.ToString() } else { "" }
                    $dNameStr = if ($u.name) { $u.name.ToString() } else { "" }
                    if ($uNameStr -match '(?i)deev|деев' -or $dNameStr -match '(?i)deev|деев') {
                        $needsSave = $true
                        continue
                    }
                    $cleanedUsers += $u
                }
                if ($needsSave) {
                    $users = $cleanedUsers
                    try { [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8) } catch {}
                }
                foreach ($u in $cleanedUsers) {
                    $hasAvitoBot = if ($u.role -eq "admin" -or $u.username.ToLower() -eq "skynet83") {
                        $true
                    } elseif ($u.permissions) {
                        [bool]($u.permissions.avito_bot -or $u.permissions.avito)
                    } else {
                        $false
                    }
                    $uPerms = if ($u.permissions) { $u.permissions } else { [PSCustomObject]@{} }
                    if (-not $uPerms.PSObject.Properties["avito_bot"]) {
                        $uPerms | Add-Member -NotePropertyName "avito_bot" -NotePropertyValue $hasAvitoBot -Force
                    }
                    if (-not $uPerms.PSObject.Properties["tg_bot"]) {
                        $uPerms | Add-Member -NotePropertyName "tg_bot" -NotePropertyValue $hasAvitoBot -Force
                    }
                    if (-not $uPerms.PSObject.Properties["monitoring"]) {
                        $uPerms | Add-Member -NotePropertyName "monitoring" -NotePropertyValue $true -Force
                    }
                    $uMac = if ($u.last_mac) { $u.last_mac.ToString().Trim() } else { "" }
                    $isBlockedUser = Test-IsBlacklisted -mac $uMac -ip $u.last_ip -username $u.username
                    if ($u.PSObject.Properties["is_blocked"] -and [bool]$u.is_blocked -eq $true) { $isBlockedUser = $true }
                    $uTargetInt = if ($u.target_interval) { [string]$u.target_interval } elseif ($uPerms -and $uPerms.PSObject.Properties["target_interval"]) { [string]$uPerms.target_interval } else { "60" }
                    $uActiveInt = if ($u.active_interval) { [string]$u.active_interval } else { $uTargetInt }
                    if (-not $uPerms.PSObject.Properties["target_interval"]) {
                        $uPerms | Add-Member -NotePropertyName "target_interval" -NotePropertyValue $uTargetInt -Force
                    }
                    $safeUsers += [PSCustomObject]@{
                        username = $u.username
                        name = $u.name
                        role = $u.role
                        last_ip = if ($u.last_ip) { $u.last_ip } else { "—" }
                        last_mac = if ($uMac) { $uMac } else { "—" }
                        last_seen = if ($u.last_seen) { $u.last_seen } else { "—" }
                        is_blocked = $isBlockedUser
                        permissions = $uPerms
                        target_interval = $uTargetInt
                        active_interval = $uActiveInt
                        avito_searches = [object[]]@($u.avito_searches)
                        telegram_chat_id = if ($u.telegram_chat_id) { $u.telegram_chat_id } else { $null }
                        telegram_username = if ($u.telegram_username) { $u.telegram_username } else { $null }
                        plain_password = if ($u.plain_password) { $u.plain_password } else { "" }
                        password = if ($u.password) { $u.password } else { "" }
                    }
                }
                $visitorsList = @()
                foreach ($v in $global:recentVisitors.Values) {
                    $vMac = if ($v.mac) { $v.mac } else { (Get-ClientMacAddress $v.ip) }
                    $vObj = [PSCustomObject]@{
                        ip = $v.ip
                        mac = if ($vMac) { $vMac } else { "—" }
                        device = $v.device
                        last_seen = $v.last_seen
                        last_path = $v.last_path
                    }
                    $visitorsList += $vObj
                }
                $blEntries = @(Get-BlacklistEntries)
                $resObj = @{
                    success = $true
                    users = [object[]]@($safeUsers)
                    visitors = [object[]]@($visitorsList)
                    blacklist = [object[]]@($blEntries)
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Depth 6 -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Удаление пользователя (POST /api/users/delete)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/users/delete") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $delUsername = if ($json.username) { $json.username.ToString().Trim() } else { "" }
                if ($delUsername.ToLower() -eq "skynet83") {
                    $resObj = @{ success = $false; error = "Нельзя удалить главного администратора skynet83" }
                } else {
                    $usersFile = Join-Path $path "data\users.json"
                    $users = @()
                    if ([System.IO.File]::Exists($usersFile)) {
                        $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                        if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                    }
                    $users = @($users | Where-Object { $_.username.ToLower() -ne $delUsername.ToLower() })
                    [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                    $resObj = @{ success = $true }
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Добавление в Черный Список (POST /api/users/blacklist/add)
        if ($request.HttpMethod -eq "POST" -and ($localPath -eq "/api/users/blacklist/add" -or $localPath -eq "/api/blacklist/add")) {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $targetUsername = if ($json.username) { $json.username.ToString().Trim() } else { "" }
                $targetIp = if ($json.ip) { $json.ip.ToString().Trim() } else { "" }
                $targetMac = if ($json.mac) { $json.mac.ToString().Trim() } else { "" }
                $reason = if ($json.reason) { $json.reason.ToString().Trim() } else { "Заблокирован администратором" }

                if ($targetUsername -and $targetUsername.ToLower() -eq "skynet83") {
                    $resObj = @{ success = $false; error = "Нельзя заблокировать главного администратора skynet83" }
                } elseif (-not $targetUsername -and ($targetIp -in @("127.0.0.1", "::1", "localhost") -or ($localIp -and $targetIp -eq $localIp))) {
                    $resObj = @{ success = $false; error = "Нельзя заблокировать локальный IP-адрес сервера!" }
                } else {
                    $usersFile = Join-Path $path "data\users.json"
                    $users = @()
                    if ([System.IO.File]::Exists($usersFile)) {
                        $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8).Trim().Trim([char]0xfeff) | ConvertFrom-Json
                        if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                    }

                    if ($targetUsername) {
                        foreach ($u in $users) {
                            if ($u.username -and $u.username.ToLower() -eq $targetUsername.ToLower()) {
                                if (-not $targetIp -and $u.last_ip -and $u.last_ip -ne "—") { $targetIp = $u.last_ip }
                                if (-not $targetMac -and $u.last_mac -and $u.last_mac -ne "—") { $targetMac = $u.last_mac }
                                $u | Add-Member -NotePropertyName "is_blocked" -NotePropertyValue $true -Force
                                $u | Add-Member -NotePropertyName "session_token" -NotePropertyValue "" -Force
                            }
                        }
                        [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                    }

                    # Защита: не блокируем локальный IP целиком при блокировке учетной записи пользователя
                    if ($targetIp -in @("127.0.0.1", "::1", "localhost") -or ($localIp -and $targetIp -eq $localIp)) {
                        $targetIp = ""
                    }

                    $blEntries = @(Get-BlacklistEntries)
                    $exists = $false
                    foreach ($b in $blEntries) {
                        $bU = if ($b.username) { $b.username.ToString().ToLower().Trim() } else { "" }
                        $bI = if ($b.ip) { $b.ip.ToString().Trim() } else { "" }
                        if (($targetUsername -and $bU -eq $targetUsername.ToLower()) -or ($targetIp -and $bI -eq $targetIp)) {
                            $exists = $true
                            break
                        }
                    }

                    if (-not $exists) {
                        $newEntry = [PSCustomObject]@{
                            username = $targetUsername
                            ip = $targetIp
                            mac = $targetMac
                            reason = $reason
                            blocked_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
                        }
                        $blEntries += $newEntry
                        Save-BlacklistEntries $blEntries
                    }

                    $resObj = @{ success = $true; message = "Добавлено в черный список"; is_blocked = $true; blacklist = $blEntries }
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Depth 5 -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Удаление из Черного Списка (POST /api/users/blacklist/remove)
        if ($request.HttpMethod -eq "POST" -and ($localPath -eq "/api/users/blacklist/remove" -or $localPath -eq "/api/blacklist/remove")) {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $targetUsername = if ($json.username) { $json.username.ToString().Trim() } else { "" }
                $targetIp = if ($json.ip) { $json.ip.ToString().Trim() } else { "" }
                $targetMac = if ($json.mac) { $json.mac.ToString().Trim() } else { "" }

                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $users = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                    if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                }

                if ($targetUsername) {
                    foreach ($u in $users) {
                        if ($u.username -and $u.username.ToLower() -eq $targetUsername.ToLower()) {
                            $u | Add-Member -NotePropertyName "is_blocked" -NotePropertyValue $false -Force
                        }
                    }
                    [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                }

                $blEntries = @(Get-BlacklistEntries)
                $newEntries = @()
                foreach ($b in $blEntries) {
                    $bU = if ($b.username) { $b.username.ToString().ToLower().Trim() } else { "" }
                    $bI = if ($b.ip) { $b.ip.ToString().Trim() } else { "" }
                    $bM = if ($b.mac) { $b.mac.ToString().ToUpper().Replace("-", ":").Trim() } else { "" }

                    $match = $false
                    if ($targetUsername -and $bU -eq $targetUsername.ToLower()) { $match = $true }
                    if ($targetIp -and $targetIp -ne "—" -and $bI -eq $targetIp) { $match = $true }
                    if ($targetMac -and $targetMac -ne "—" -and $bM -eq $targetMac.ToUpper().Replace("-", ":")) { $match = $true }

                    if (-not $match) {
                        $newEntries += $b
                    }
                }
                Save-BlacklistEntries $newEntries

                $resObj = @{ success = $true; message = "Удалено из черного списка"; is_blocked = $false; blacklist = $newEntries }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Depth 5 -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Изменение разрешений пользователя (POST /api/users/permission)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/users/permission") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $targetUser = if ($json.username) { $json.username.ToString().Trim() } else { "" }
                $cleanTarget = if ($targetUser) { ($targetUser.ToLower().Trim() -replace '\s*\(.*?\)', '') } else { "" }
                $permKey = if ($json.permission) { $json.permission.ToString().Trim() } else { "" }
                $hasExplicitValue = ($null -ne $json.value)
                $permVal = if ($hasExplicitValue) { [bool]$json.value } else { $true }

                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    for ($i = 0; $i -lt 3; $i++) {
                        try {
                            $rawText = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8)
                            if ($rawText -and $rawText.Trim()) {
                                $users = $rawText | ConvertFrom-Json
                                if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                                if ($users.Count -gt 0) { break }
                            }
                        } catch { Start-Sleep -Milliseconds 60 }
                    }
                }

                $clientToken = if ($json.session_token) { $json.session_token.ToString().Trim() } else { $request.Headers["X-Session-Token"] }
                $duration = if ($json.duration) { $json.duration.ToString().Trim() } else { "" }
                $found = $false
                foreach ($u in $users) {
                    $uName = if ($u.username) { $u.username.ToString().ToLower().Trim() } else { "" }
                    $uDisplayName = if ($u.name) { ($u.name.ToString().ToLower().Trim() -replace '\s*\(.*?\)', '') } else { "" }
                    $uTgName = if ($u.telegram_username) { $u.telegram_username.ToString().ToLower().Trim().TrimStart('@') } else { "" }
                    $uTgId = if ($u.telegram_chat_id) { $u.telegram_chat_id.ToString().Trim() } else { "" }

                    $matchByName = ($cleanTarget -and (
                        $uName -eq $cleanTarget -or
                        $uDisplayName -eq $cleanTarget -or
                        ($cleanTarget -in @("admin", "skynet") -and ($u.role -eq "admin" -or $uName -eq "skynet83")) -or
                        ($uTgName -and $cleanTarget -eq $uTgName) -or
                        ($uTgId -and $cleanTarget -eq $uTgId)
                    ))

                    $tokens = @()
                    if ($u.session_token) { $tokens += $u.session_token }
                    if ($u.sessions -and $u.sessions.desktop -and $u.sessions.desktop.token) { $tokens += $u.sessions.desktop.token }
                    if ($u.sessions -and $u.sessions.mobile -and $u.sessions.mobile.token) { $tokens += $u.sessions.mobile.token }
                    $matchByToken = (-not $cleanTarget -and $clientToken -and ($tokens -contains $clientToken))

                    if ($matchByName -or $matchByToken) {
                        $found = $true
                        if (-not $u.permissions) {
                            $u | Add-Member -NotePropertyName "permissions" -NotePropertyValue ([PSCustomObject]@{}) -Force
                        }
                        # Индивидуальное переключение Telegram-бота для пользователя (tg_bot)
                        if ($permKey -eq "tg_bot" -or ($null -ne $json.tg_bot)) {
                            $tgVal = if ($null -ne $json.tg_bot) { [bool]$json.tg_bot } else { [bool]$json.value }
                            $u.permissions | Add-Member -NotePropertyName "tg_bot" -NotePropertyValue $tgVal -Force
                        }

                        # Индивидуальное переключение персонального мониторинга (monitoring)
                        if ($permKey -eq "monitoring" -or ($null -ne $json.monitoring)) {
                            $monVal = if ($null -ne $json.monitoring) { [bool]$json.monitoring } else { [bool]$json.value }
                            $u.permissions | Add-Member -NotePropertyName "monitoring" -NotePropertyValue $monVal -Force
                        }

                        # Обработка лимита ссылок (max_searches: 1..10, default 1)
                        if ($permKey -eq "max_searches" -or ($null -ne $json.max_searches)) {
                            $maxValRaw = if ($null -ne $json.max_searches) { [int]$json.max_searches } else { [int]$json.value }
                            if ($u.role -eq "admin" -or $u.username.ToLower() -eq "skynet83") {
                                $maxValRaw = 999
                            } else {
                                if ($maxValRaw -lt 1) { $maxValRaw = 1 }
                                if ($maxValRaw -gt 10) { $maxValRaw = 10 }
                            }
                            $u.permissions | Add-Member -NotePropertyName "max_searches" -NotePropertyValue $maxValRaw -Force
                        }

                        # Обработка целевой скорости опроса (target_interval)
                        if ($permKey -eq "target_interval" -or $permKey -eq "interval" -or ($null -ne $json.target_interval) -or ($null -ne $json.interval)) {
                            $intervalVal = if ($null -ne $json.target_interval) { [string]$json.target_interval } elseif ($null -ne $json.interval) { [string]$json.interval } else { [string]$json.value }
                            if ($intervalVal.ToLower().StartsWith("rand")) { $intervalVal = "60" }
                            if ($u.PSObject.Properties["target_interval"]) {
                                $u.target_interval = $intervalVal
                            } else {
                                $u | Add-Member -NotePropertyName "target_interval" -NotePropertyValue $intervalVal -Force
                            }
                            if ($u.permissions) {
                                if ($u.permissions.PSObject.Properties["target_interval"]) {
                                    $u.permissions.target_interval = $intervalVal
                                } else {
                                    $u.permissions | Add-Member -NotePropertyName "target_interval" -NotePropertyValue $intervalVal -Force
                                }
                            }
                            $uActive = if ($u.active_interval) { [int]$u.active_interval } else { 0 }
                            $uBase = [int]$intervalVal
                            if ($uActive -lt $uBase -or $uActive -eq 60 -or $uActive -eq 0 -or $uBase -ge 60) {
                                if ($u.PSObject.Properties["active_interval"]) {
                                    $u.active_interval = $intervalVal
                                } else {
                                    $u | Add-Member -NotePropertyName "active_interval" -NotePropertyValue $intervalVal -Force
                                }
                            }
                            if ($u.role -eq "admin" -or $u.username.ToLower() -eq "skynet83") {
                                $pyScript = Join-Path $path "avito_api_helper.py"
                                $null = & $global:pythonCmd -X utf8 $pyScript "set-interval" $intervalVal 2>&1
                            }
                        }

                        # Обработка срока действия тарифа (продление: 1..12 месяцев, 1 месяц = 30 дней)
                        if ($permKey -in @("avito_bot", "avito", "avito_duration", "duration") -or $duration -or $json.action -eq "extend" -or $json.extend) {
                            $durationVal = "none"
                            $expiresAt = $null
                            $hasAccess = $false

                            $isExtend = ($json.action -eq "extend" -or $json.extend -eq $true -or $permKey -eq "extend")
                            $rawMonths = 0
                            if ($json.months -and $json.months -ne "unlimited") {
                                $rawMonths = [int]$json.months
                            } elseif ($duration -match '^(\d+)m$') {
                                $rawMonths = [int]$Matches[1]
                            }

                            if ($duration -eq "unlimited" -or $json.months -eq "unlimited" -or ($hasExplicitValue -and $json.value -eq "unlimited")) {
                                $hasAccess = $true
                                $durationVal = "unlimited"
                                $expiresAt = $null
                            } elseif ($duration -eq "none" -or ($hasExplicitValue -and -not $duration -and $permVal -eq $false)) {
                                $hasAccess = $false
                                $durationVal = "none"
                                $expiresAt = $null
                            } elseif ($rawMonths -gt 0 -or $isExtend -or $duration -or ($hasExplicitValue -and $permVal -eq $true)) {
                                $monthsCount = if ($rawMonths -gt 0) { $rawMonths } else { 1 }
                                if ($monthsCount -lt 1) { $monthsCount = 1 }
                                if ($monthsCount -gt 12) { $monthsCount = 12 }
                                $daysToAdd = $monthsCount * 30
                                $hasAccess = $true
                                $durationVal = "${monthsCount}m"

                                # Прибавление к существующему тарифу (только если это явное продление):
                                $baseDate = (Get-Date)
                                if ($isExtend -and $u.permissions -and $u.permissions.avito_expires_at) {
                                    try {
                                        $parsedExp = [DateTime]::Parse($u.permissions.avito_expires_at)
                                        if ($parsedExp -gt (Get-Date)) {
                                            $baseDate = $parsedExp
                                        }
                                    } catch {}
                                }
                                $expiresAt = $baseDate.AddDays($daysToAdd).ToString("yyyy-MM-dd HH:mm:ss")
                            }

                            if ($u.username.ToLower() -eq "skynet83") {
                                $hasAccess = $true
                                $durationVal = "unlimited"
                                $expiresAt = $null
                            }

                            $u.permissions | Add-Member -NotePropertyName "avito_bot" -NotePropertyValue $hasAccess -Force
                            $u.permissions | Add-Member -NotePropertyName "avito" -NotePropertyValue $hasAccess -Force
                            if ($hasAccess) {
                                $u.permissions | Add-Member -NotePropertyName "tg_bot" -NotePropertyValue $true -Force
                                $u.permissions | Add-Member -NotePropertyName "monitoring" -NotePropertyValue $true -Force
                            } else {
                                $u.permissions | Add-Member -NotePropertyName "tg_bot" -NotePropertyValue $false -Force
                                $u.permissions | Add-Member -NotePropertyName "monitoring" -NotePropertyValue $false -Force
                            }
                            $u.permissions | Add-Member -NotePropertyName "avito_duration" -NotePropertyValue $durationVal -Force
                            $u.permissions | Add-Member -NotePropertyName "avito_expires_at" -NotePropertyValue $expiresAt -Force
                        }

                        if (-not $u.permissions.max_searches) {
                            $defS = if ($u.role -eq "admin" -or $u.username.ToLower() -eq "skynet83") { 999 } else { 1 }
                            $u.permissions | Add-Member -NotePropertyName "max_searches" -NotePropertyValue $defS -Force
                        }
                        if ($u.role -eq "admin" -or $u.username.ToLower() -eq "skynet83") {
                            $u.permissions | Add-Member -NotePropertyName "max_searches" -NotePropertyValue 999 -Force
                        }
                        if (-not $u.avito_searches) {
                            $u | Add-Member -NotePropertyName "avito_searches" -NotePropertyValue @() -Force
                        }
                        break
                    }
                }

                # Fallback: если совпадение не найдено, но запрос локальный или для admin/skynet83
                if (-not $found -and ($remoteIp -in @("127.0.0.1", "::1", "localhost") -or -not $cleanTarget -or $cleanTarget -in @("admin", "skynet", "skynet83"))) {
                    foreach ($usr in $users) {
                        if ($usr.role -eq "admin" -or ($usr.username -and $usr.username.ToString().ToLower().Trim() -eq "skynet83")) {
                            $u = $usr
                            $found = $true
                            if (-not $u.permissions) {
                                $u | Add-Member -NotePropertyName "permissions" -NotePropertyValue ([PSCustomObject]@{}) -Force
                            }
                            if ($permKey -eq "tg_bot" -or ($null -ne $json.tg_bot)) {
                                $tgVal = if ($null -ne $json.tg_bot) { [bool]$json.tg_bot } else { [bool]$json.value }
                                $u.permissions | Add-Member -NotePropertyName "tg_bot" -NotePropertyValue $tgVal -Force
                            }
                            if ($permKey -eq "monitoring" -or ($null -ne $json.monitoring)) {
                                $monVal = if ($null -ne $json.monitoring) { [bool]$json.monitoring } else { [bool]$json.value }
                                $u.permissions | Add-Member -NotePropertyName "monitoring" -NotePropertyValue $monVal -Force
                            }
                            if ($permKey -eq "target_interval" -or $permKey -eq "interval" -or ($null -ne $json.target_interval) -or ($null -ne $json.interval)) {
                                $intervalVal = if ($null -ne $json.target_interval) { [string]$json.target_interval } elseif ($null -ne $json.interval) { [string]$json.interval } else { [string]$json.value }
                                if ($intervalVal.ToLower().StartsWith("rand")) { $intervalVal = "60" }
                                if ($u.PSObject.Properties["target_interval"]) { $u.target_interval = $intervalVal } else { $u | Add-Member -NotePropertyName "target_interval" -NotePropertyValue $intervalVal -Force }
                                if ($u.permissions) {
                                    if ($u.permissions.PSObject.Properties["target_interval"]) { $u.permissions.target_interval = $intervalVal } else { $u.permissions | Add-Member -NotePropertyName "target_interval" -NotePropertyValue $intervalVal -Force }
                                }
                            }
                            break
                        }
                    }
                }

                if ($found) {
                    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
                    for ($w = 0; $w -lt 3; $w++) {
                        try {
                            [System.IO.File]::WriteAllText($usersFile, ($users | ConvertTo-Json -Depth 5), $utf8NoBom)
                            break
                        } catch { Start-Sleep -Milliseconds 60 }
                    }

                    # При необходимости завершаем процесс воркера прокси при отключении и мониторинга, и ТГ
                    if ($permKey -eq "monitoring" -or $permKey -eq "tg_bot" -or ($null -ne $json.monitoring) -or ($null -ne $json.tg_bot)) {
                        $mVal = if ($u.permissions -and $u.permissions.monitoring -ne $null) { [bool]$u.permissions.monitoring } else { $true }
                        $tVal = if ($u.permissions -and $u.permissions.tg_bot -ne $null) { [bool]$u.permissions.tg_bot } else { $true }
                        if (-not ($mVal -or $tVal)) {
                            $wPidFile = Join-Path $path "avito_bot\proxy_worker.pid"
                            if (Test-Path $wPidFile) {
                                try {
                                    $wPid = [int](Get-Content $wPidFile -ErrorAction SilentlyContinue).Trim()
                                    Stop-Process -Id $wPid -Force -ErrorAction SilentlyContinue
                                    Remove-Item -Path $wPidFile -Force -ErrorAction SilentlyContinue
                                } catch {}
                            }
                        }
                    }

                    $daysRemaining = if ($expiresAt) {
                        try {
                            $diff = [DateTime]::Parse($expiresAt) - (Get-Date)
                            [int][Math]::Ceiling($diff.TotalDays)
                        } catch { 0 }
                    } else { 0 }
                    $resObj = @{
                        success = $true
                        message = "Разрешение сохранено"
                        expires_at = $expiresAt
                        days_remaining = $daysRemaining
                        permissions = if ($u) { $u.permissions } else { $null }
                        target_interval = if ($u -and $u.target_interval) { [string]$u.target_interval } else { "60" }
                        active_interval = if ($u -and $u.active_interval) { [string]$u.active_interval } else { "60" }
                    }
                } else {
                    $resObj = @{ success = $false; error = "Пользователь не найден" }
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Привязка Telegram адреса пользователя (POST /api/user/telegram)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/user/telegram") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $qUsername = if ($json.username) { [string]$json.username.ToString().Trim() } else { "" }
                $rawHandle = if ($json.telegram_handle) { [string]$json.telegram_handle.ToString().Trim() } else { "" }

                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $rawText = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8)
                    $users = $rawText | ConvertFrom-Json
                    if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                }

                $targetU = $null
                foreach ($u in $users) {
                    if ($qUsername -and $u.username.ToLower() -eq $qUsername.ToLower()) {
                        $targetU = $u
                        break
                    }
                }
                if (-not $targetU) {
                    throw "Пользователь $qUsername не найден"
                }

                if (-not $rawHandle) {
                    $targetU | Add-Member -NotePropertyName "telegram_chat_id" -NotePropertyValue $null -Force
                    $targetU | Add-Member -NotePropertyName "telegram_username" -NotePropertyValue $null -Force
                    $targetU | Add-Member -NotePropertyName "telegram_pending" -NotePropertyValue $null -Force

                    $jsonStr = $users | ConvertTo-Json -Depth 8
                    $utf8WithBom = New-Object System.Text.UTF8Encoding($true)
                    [System.IO.File]::WriteAllText($usersFile, $jsonStr, $utf8WithBom)
                    $altFile = "e:\TEMP\База-бот\SITE\data\users.json"
                    if ($usersFile -ne $altFile -and [System.IO.File]::Exists("e:\TEMP\База-бот\SITE")) {
                        [System.IO.File]::WriteAllText($altFile, $jsonStr, $utf8WithBom)
                    }

                    $pyScript = Join-Path $path "avito_api_helper.py"
                    & $global:pythonCmd -X utf8 $pyScript "sync-searches" | Out-Null

                    $resObj = @{
                        success = $true
                        status = "unbound"
                        telegram_chat_id = $null
                        telegram_username = $null
                        telegram_pending = $null
                        message = "Telegram адрес отвязан"
                    }
                    $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                    $response.ContentType = "application/json; charset=utf-8"
                    $response.ContentLength64 = $bytes.Length
                    $response.OutputStream.Write($bytes, 0, $bytes.Length)
                    $response.Close()
                    continue
                }

                $cleanH = $rawHandle.Trim().TrimStart('@')
                $isChatId = $cleanH -match '^-?\d+$'
                $cleanChatId = if ($isChatId) { [int64]$cleanH } else { $null }
                $cleanUname = if (-not $isChatId) { $cleanH.ToLower() } else { $null }

                # Проверка: не привязан ли этот Telegram аккаунт к другому пользователю на сайте
                $alreadyTaken = $false
                foreach ($other in $users) {
                    $otherUname = if ($other.username) { $other.username.ToString().Trim().ToLower() } else { "" }
                    if ($otherUname -and $otherUname -ne $qUsername.ToLower()) {
                        if ($cleanChatId -and $other.telegram_chat_id -and [string]$other.telegram_chat_id -eq [string]$cleanChatId) {
                            $alreadyTaken = $true
                            break
                        }
                        if ($cleanUname -and $other.telegram_username -and $other.telegram_username.ToString().Trim().TrimStart('@').ToLower() -eq $cleanUname) {
                            $alreadyTaken = $true
                            break
                        }
                    }
                }

                if ($alreadyTaken) {
                    $resObj = @{ success = $false; error = "Telegram аккаунт уже занят" }
                    $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                    $response.ContentType = "application/json; charset=utf-8"
                    $response.ContentLength64 = $bytes.Length
                    $response.OutputStream.Write($bytes, 0, $bytes.Length)
                    $response.Close()
                    continue
                }

                # Сохраняем Telegram аккаунт в профиле пользователя сразу
                if ($cleanChatId) {
                    $targetU | Add-Member -NotePropertyName "telegram_chat_id" -NotePropertyValue $cleanChatId -Force
                    $targetU | Add-Member -NotePropertyName "telegram_username" -NotePropertyValue $null -Force
                } else {
                    $targetU | Add-Member -NotePropertyName "telegram_chat_id" -NotePropertyValue $null -Force
                    $targetU | Add-Member -NotePropertyName "telegram_username" -NotePropertyValue $cleanUname -Force
                }

                # Переводим в статус ожидания подтверждения
                $pendingObj = [PSCustomObject]@{
                    handle = $rawHandle.Trim()
                    status = "pending"
                    requested_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
                }
                $targetU | Add-Member -NotePropertyName "telegram_pending" -NotePropertyValue $pendingObj -Force

                $jsonStr = $users | ConvertTo-Json -Depth 8
                $utf8WithBom = New-Object System.Text.UTF8Encoding($true)
                [System.IO.File]::WriteAllText($usersFile, $jsonStr, $utf8WithBom)
                $altFile = "e:\TEMP\База-бот\SITE\data\users.json"
                if ($usersFile -ne $altFile -and [System.IO.File]::Exists("e:\TEMP\База-бот\SITE")) {
                    [System.IO.File]::WriteAllText($altFile, $jsonStr, $utf8WithBom)
                }

                # Отправляем подтверждение через Telegram-бота (асинхронно без зависания ответа)
                $pyScript = Join-Path $path "avito_api_helper.py"
                try {
                    Start-Process -FilePath $global:pythonCmd -ArgumentList "-X utf8 `"$pyScript`" send-bind-confirm `"$($targetU.username)`" `"$cleanH`"" -WindowStyle Hidden
                } catch {}

                $resObj = @{
                    success = $true
                    status = "pending"
                    telegram_chat_id = $targetU.telegram_chat_id
                    telegram_username = $targetU.telegram_username
                    telegram_pending = $targetU.telegram_pending
                    message = "Telegram аккаунт привязан"
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Отмена запроса на привязку Telegram (POST /api/user/telegram/cancel)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/user/telegram/cancel") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $qUsername = if ($json.username) { [string]$json.username.ToString().Trim() } else { "" }
                $usersFile = Join-Path $path "data\users.json"
                $users = @()
                if ([System.IO.File]::Exists($usersFile)) {
                    $rawText = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8)
                    $users = $rawText | ConvertFrom-Json
                    if ($users -isnot [System.Collections.IEnumerable]) { $users = @($users) }
                }
                $targetU = $null
                foreach ($u in $users) {
                    if ($qUsername -and $u.username.ToLower() -eq $qUsername.ToLower()) {
                        $targetU = $u
                        break
                    }
                }
                if ($targetU) {
                    if ($targetU.telegram_pending) {
                        $targetU | Add-Member -NotePropertyName "telegram_chat_id" -NotePropertyValue $null -Force
                        $targetU | Add-Member -NotePropertyName "telegram_username" -NotePropertyValue $null -Force
                    }
                    $targetU | Add-Member -NotePropertyName "telegram_pending" -NotePropertyValue $null -Force
                    $jsonStr = $users | ConvertTo-Json -Depth 8
                    $utf8WithBom = New-Object System.Text.UTF8Encoding($true)
                    [System.IO.File]::WriteAllText($usersFile, $jsonStr, $utf8WithBom)
                    $altFile = "e:\TEMP\База-бот\SITE\data\users.json"
                    if ($usersFile -ne $altFile -and [System.IO.File]::Exists("e:\TEMP\База-бот\SITE")) {
                        [System.IO.File]::WriteAllText($altFile, $jsonStr, $utf8WithBom)
                    }
                }
                $resObj = @{ success = $true; message = "Запрос на привязку отменен" }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Сообщения чата с администратором (GET /api/chat/messages?username=...&request_id=...)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/chat/messages") {
            try {
                $qUsername = if ($request.QueryString["username"]) { [string]$request.QueryString["username"] } else { "guest" }
                $qRequestId = if ($request.QueryString["request_id"]) { [string]$request.QueryString["request_id"] } else { "" }
                $messages = Get-ChatMessagesList

                $isAdminUser = ($qUsername.ToLower() -eq "skynet83" -or $qUsername.ToLower() -eq "admin")
                $usersFile = Join-Path $path "data\users.json"
                if ([System.IO.File]::Exists($usersFile)) {
                    $allU = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                    $curU = $allU | Where-Object { $_.username.ToLower() -eq $qUsername.ToLower() } | Select-Object -First 1
                    if ($curU -and $curU.role -eq "admin") { $isAdminUser = $true }
                }

                # Автоопределение request_id сервера для мобильных устройств или клиентов без параметра request_id
                if (-not $qRequestId -or $qRequestId.Trim() -eq "") {
                    if (-not $global:MachineRequestId) {
                        try {
                            $pyScript = Join-Path $path "avito_api_helper.py"
                            $hwRaw = & $global:pythonCmd -X utf8 $pyScript "get-request-id" 2>&1 | Out-String
                            if ($hwRaw) {
                                $hwObj = $hwRaw | ConvertFrom-Json
                                if ($hwObj.success -and $hwObj.request_id) {
                                    $global:MachineRequestId = [string]$hwObj.request_id
                                }
                            }
                        } catch {}
                        if (-not $global:MachineRequestId) {
                        try {
                            $hwRaw = & $global:pythonCmd -X utf8 (Join-Path $path "hwid_security.py") "get_id" 2>&1 | Out-String
                            if ($hwRaw -and $hwRaw.Trim().StartsWith("EBID-")) {
                                $global:MachineRequestId = $hwRaw.Trim()
                            }
                        } catch {}
                    }
                    }
                    # Изоляция переписки: присваиваем MachineRequestId только локальному браузеру сервера,
                    # чтобы мобильные устройства и внешние клиенты не видели чужие сообщения
                    $clientIp = $request.RemoteEndPoint.Address.ToString()
                    if (-not $isAdminUser -and ($clientIp -in @("127.0.0.1", "::1", "localhost"))) {
                        $qRequestId = $global:MachineRequestId
                    }
                }

                $filtered = @()
                $unread = 0
                $qReqNorm = $qRequestId.Trim().ToLower()
                $qUserNorm = $qUsername.Trim().ToLower()

                foreach ($m in $messages) {
                    if ($null -ne $m.id) { $m.id = [string]$m.id }
                    $sNorm = if ($m.sender) { ([string]$m.sender).Trim().ToLower() } else { "" }
                    $rNorm = if ($m.recipient) { ([string]$m.recipient).Trim().ToLower() } else { "" }
                    $sidNorm = if ($m.sender_id) { ([string]$m.sender_id).Trim().ToLower() } else { "" }

                    # Если передан request_id (запрос из модального окна активации конкретного ПК или Телефона)
                    if ($qReqNorm) {
                        $matchReq = ($sNorm -eq $qReqNorm -or $rNorm -eq $qReqNorm -or $sidNorm -eq $qReqNorm)
                        $isBroadcast = ($rNorm -eq "all")

                        if ($matchReq -or $isBroadcast) {
                            $filtered += $m
                            if (-not $m.is_read -and ($rNorm -eq $qReqNorm -or $isBroadcast) -and $sNorm -ne $qReqNorm -and $sidNorm -ne $qReqNorm) {
                                $unread++
                            }
                        }
                    } elseif ($isAdminUser) {
                        # Админ без указания request_id видит всю историю
                        $filtered += $m
                        if (-not $m.is_read -and $sNorm -ne "skynet83" -and $sNorm -ne "admin" -and $sNorm -ne $qUserNorm) {
                            $unread++
                        }
                    } else {
                        # Обычный пользователь без request_id
                        if ($sNorm -eq $qUserNorm -or $rNorm -eq $qUserNorm -or $rNorm -eq "all") {
                            $filtered += $m
                            if (-not $m.is_read -and ($rNorm -eq $qUserNorm -or $rNorm -eq "all") -and $sNorm -ne $qUserNorm) {
                                $unread++
                            }
                        }
                    }
                }

                $resObj = @{
                    success = $true
                    messages = $filtered
                    unread_count = $unread
                    is_admin = $isAdminUser
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Depth 5 -Compress))
                $response.Headers.Add("Cache-Control", "no-cache, no-store, must-revalidate")
                $response.Headers.Add("Pragma", "no-cache")
                $response.Headers.Add("Expires", "0")
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Отправка сообщения в чат (POST /api/chat/send)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/chat/send") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $messages = Get-ChatMessagesList

                $sender = if ($json.sender) { [string]$json.sender } else { "guest" }
                $senderId = if ($json.sender_id) { [string]$json.sender_id } else { $sender }
                $senderName = if ($json.sender_name) { [string]$json.sender_name } else { $sender }
                $recipient = if ($json.recipient) { [string]$json.recipient } else { "admin" }
                $text = if ($json.text) { [string]$json.text } else { "" }

                if ((-not $senderId -or $senderId -eq "guest") -and $recipient -eq "admin") {
                    if (-not $global:MachineRequestId) {
                        try {
                            $hwRaw = & $global:pythonCmd -X utf8 (Join-Path $path "hwid_security.py") "get_id" 2>&1 | Out-String
                            if ($hwRaw -and $hwRaw.Trim().StartsWith("EBID-")) {
                                $global:MachineRequestId = $hwRaw.Trim()
                            }
                        } catch {}
                    }
                    $senderId = $global:MachineRequestId
                    if ($sender -eq "guest") { $sender = $global:MachineRequestId }
                    if ($senderName -eq "guest" -or -not $senderName) { $senderName = "ПК ($global:MachineRequestId)" }
                }

                # Проверка черного списка и блокировки чата
                $usersPath = Join-Path $path "data\users.json"
                if (Test-Path $usersPath) {
                    try {
                        $allU = Get-Content $usersPath -Raw -Encoding UTF8 | ConvertFrom-Json
                        $matchedU = $allU | Where-Object { 
                            ($_.username -and $_.username.ToString().ToLower() -eq $sender.ToLower()) -or 
                            ($_.permissions -and $_.permissions.hwid_request_id -and $_.permissions.hwid_request_id.ToString().ToLower() -eq $senderId.ToLower())
                        }
                        if ($matchedU -and ($matchedU.is_blocked -or $matchedU.chat_blocked)) {
                            $resObj = @{ success = $false; error = "Доступ к чату заблокирован администратором (Чёрный список)." }
                            $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                            $response.ContentType = "application/json; charset=utf-8"
                            $response.ContentLength64 = $bytes.Length
                            $response.OutputStream.Write($bytes, 0, $bytes.Length)
                            $response.Close()
                            continue
                        }
                    } catch {}
                }

                if (-not [string]::IsNullOrWhiteSpace($text)) {
                    $newMsg = [PSCustomObject]@{
                        id = "msg_" + (Get-Date).ToString("yyyyMMddHHmmssfff") + "_" + (Get-Random -Minimum 1000 -Maximum 9999)
                        sender = $sender
                        sender_id = $senderId
                        sender_name = $senderName
                        recipient = $recipient
                        text = $text.Trim()
                        created_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                        is_read = $false
                    }
                    $messages = @($messages) + $newMsg
                    if ($messages.Count -gt 500) {
                        $messages = $messages[($messages.Count - 500)..($messages.Count - 1)]
                    }
                    [System.IO.File]::WriteAllText($chatFile, ($messages | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                    $mirrorChat = if ($path -like "C:*") { "e:\TEMP\База-бот\SITE\data\chat_messages.json" } else { "C:\ins\EXP\Arduino\Проект\База-бот\SITE\data\chat_messages.json" }
                    if (Test-Path (Split-Path $mirrorChat)) {
                        try { [System.IO.File]::WriteAllText($mirrorChat, ($messages | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8) } catch {}
                    }
                    $resObj = @{ success = $true; message = $newMsg }
                } else {
                    $resObj = @{ success = $false; error = "Текст сообщения не может быть пустым" }
                }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Прочтение сообщений (POST /api/chat/read)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/chat/read") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $username = if ($json.username) { [string]$json.username } else { "guest" }
                $requestId = if ($json.request_id) { [string]$json.request_id } else { "" }
                if (-not $requestId -or $requestId.Trim() -eq "") {
                    if (-not $global:MachineRequestId) {
                        try {
                            $hwRaw = & $global:pythonCmd -X utf8 (Join-Path $path "hwid_security.py") "get_id" 2>&1 | Out-String
                            if ($hwRaw -and $hwRaw.Trim().StartsWith("EBID-")) {
                                $global:MachineRequestId = $hwRaw.Trim()
                            }
                        } catch {}
                    }
                    $requestId = $global:MachineRequestId
                }
                $targetUser = if ($json.target_user) { [string]$json.target_user } else { $null }
                $chatFile = Join-Path $path "data\chat_messages.json"
                if ([System.IO.File]::Exists($chatFile)) {
                    $raw = [System.IO.File]::ReadAllText($chatFile, [System.Text.Encoding]::UTF8)
                    if ($raw -and $raw.Trim()) {
                        $messages = $raw | ConvertFrom-Json
                        if ($messages -isnot [System.Collections.IEnumerable]) { $messages = @($messages) }
                        $changed = $false
                        $reqNorm = $requestId.Trim().ToLower()
                        $uNorm = $username.Trim().ToLower()
                        foreach ($m in $messages) {
                            $sNorm = if ($m.sender) { ([string]$m.sender).Trim().ToLower() } else { "" }
                            $rNorm = if ($m.recipient) { ([string]$m.recipient).Trim().ToLower() } else { "" }
                            $sidNorm = if ($m.sender_id) { ([string]$m.sender_id).Trim().ToLower() } else { "" }

                            if ($reqNorm -and ($rNorm -eq $reqNorm -or $rNorm -eq "all") -and $sNorm -ne $reqNorm -and $sidNorm -ne $reqNorm) {
                                if (-not $m.is_read) {
                                    $m.is_read = $true
                                    $changed = $true
                                }
                            } elseif ($uNorm -eq "skynet83" -or $uNorm -eq "admin") {
                                if (-not $m.is_read -and $sNorm -ne "skynet83" -and $sNorm -ne "admin") {
                                    if (-not $targetUser -or $targetUser.ToLower() -eq "all" -or $sNorm -eq $targetUser.ToLower()) {
                                        $m.is_read = $true
                                        $changed = $true
                                    }
                                }
                            } else {
                                if (-not $m.is_read -and ($rNorm -eq $uNorm -or $rNorm -eq "all") -and $sNorm -ne $uNorm) {
                                    $m.is_read = $true
                                    $changed = $true
                                }
                            }
                        }
                        if ($changed) {
                            [System.IO.File]::WriteAllText($chatFile, ($messages | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                            $mirrorChat = if ($path -like "C:*") { "e:\TEMP\База-бот\SITE\data\chat_messages.json" } else { "C:\ins\EXP\Arduino\Проект\База-бот\SITE\data\chat_messages.json" }
                            if (Test-Path (Split-Path $mirrorChat)) {
                                try { [System.IO.File]::WriteAllText($mirrorChat, ($messages | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8) } catch {}
                            }
                        }
                    }
                }
                $resObj = @{ success = $true }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Редактирование приветственного сообщения чата (POST /api/chat/edit-welcome)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/chat/edit-welcome") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $username = if ($json.username) { [string]$json.username } else { "" }
                $newText = if ($json.text) { [string]$json.text } else { "" }

                # Проверка прав администратора
                $isAdminUser = ($username.ToLower() -eq "skynet83")
                $usersFile = Join-Path $path "data\users.json"
                if ([System.IO.File]::Exists($usersFile)) {
                    $allU = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                    $curU = $allU | Where-Object { $_.username.ToLower() -eq $username.ToLower() } | Select-Object -First 1
                    if ($curU -and $curU.role -eq "admin") { $isAdminUser = $true }
                }

                if (-not $isAdminUser) {
                    $resObj = @{ success = $false; error = "Доступ запрещен. Только администратор может редактировать приветствие." }
                    $response.StatusCode = 403
                } elseif ([string]::IsNullOrWhiteSpace($newText)) {
                    $resObj = @{ success = $false; error = "Текст сообщения не может быть пустым." }
                    $response.StatusCode = 400
                } else {
                    $chatFile = Join-Path $path "data\chat_messages.json"
                    $messages = @()
                    if ([System.IO.File]::Exists($chatFile)) {
                        $raw = [System.IO.File]::ReadAllText($chatFile, [System.Text.Encoding]::UTF8)
                        if ($raw -and $raw.Trim()) {
                            $messages = $raw | ConvertFrom-Json
                            if ($messages -isnot [System.Collections.IEnumerable]) { $messages = @($messages) }
                        }
                    }

                    # Находим приветственное сообщение (id = 1)
                    $welcomeMsg = $messages | Where-Object { $_.id -eq 1 } | Select-Object -First 1
                    if ($welcomeMsg) {
                        $welcomeMsg.text = $newText.Trim()
                    } else {
                        $newWelcome = [PSCustomObject]@{
                            id = 1
                            sender = "skynet83"
                            sender_name = "Администратор (skynet83)"
                            recipient = "all"
                            text = $newText.Trim()
                            created_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                            is_read = $true
                        }
                        $messages = @($newWelcome) + @($messages)
                    }

                    [System.IO.File]::WriteAllText($chatFile, ($messages | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                    $resObj = @{ success = $true; text = $newText.Trim() }
                }

                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Редактирование любого отправленного сообщения (POST /api/chat/edit)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/chat/edit") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $msgId = if ($null -ne $json.id) { $json.id } elseif ($null -ne $json.messageId) { $json.messageId } else { $null }
                $username = if ($json.username) { [string]$json.username } else { "guest" }
                $newText = if ($json.text) { [string]$json.text } else { "" }

                if (-not $msgId -or [string]::IsNullOrWhiteSpace($newText)) {
                    $resObj = @{ success = $false; error = "Не передан ID сообщения или текст пуст." }
                    $response.StatusCode = 400
                } else {
                    $isAdminUser = ($username.ToLower() -eq "skynet83")
                    $usersFile = Join-Path $path "data\users.json"
                    if ([System.IO.File]::Exists($usersFile)) {
                        $allU = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                        $curU = $allU | Where-Object { $_.username.ToLower() -eq $username.ToLower() } | Select-Object -First 1
                        if ($curU -and $curU.role -eq "admin") { $isAdminUser = $true }
                    }

                    $chatFile = Join-Path $path "data\chat_messages.json"
                    $messages = @()
                    if ([System.IO.File]::Exists($chatFile)) {
                        $raw = [System.IO.File]::ReadAllText($chatFile, [System.Text.Encoding]::UTF8)
                        if ($raw -and $raw.Trim()) {
                            $messages = $raw | ConvertFrom-Json
                            if ($messages -isnot [System.Collections.IEnumerable]) { $messages = @($messages) }
                        }
                    }

                    $strMsgId = [string]$msgId
                    $targetMsg = $messages | Where-Object { 
                        [string]$_.id -eq $strMsgId -or 
                        ([int64]::TryParse([string]$_.id, [ref]$null) -and [int64]::TryParse($strMsgId, [ref]$null) -and [Math]::Abs([int64]$_.id - [int64]$strMsgId) -le 512)
                    } | Select-Object -First 1
                    $isSenderMatch = ($targetMsg.sender.ToLower() -eq $username.ToLower()) -or 
                        (($targetMsg.sender.ToLower() -in @("guest", "гость")) -and ($username.ToLower() -in @("guest", "гость")))
                    if (-not $targetMsg) {
                        $resObj = @{ success = $false; error = "Сообщение не найдено." }
                        $response.StatusCode = 404
                    } elseif (-not $isAdminUser -and -not $isSenderMatch) {
                        $resObj = @{ success = $false; error = "Вы можете редактировать только свои сообщения." }
                        $response.StatusCode = 403
                    } else {
                        $targetMsg.text = $newText.Trim()
                        $targetMsg | Add-Member -NotePropertyName "edited" -NotePropertyValue $true -Force
                        [System.IO.File]::WriteAllText($chatFile, ($messages | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                        $resObj = @{ success = $true; message = $targetMsg }
                    }
                }

                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.Headers.Add("Cache-Control", "no-cache, no-store, must-revalidate")
                $response.Headers.Add("Pragma", "no-cache")
                $response.Headers.Add("Expires", "0")
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Удаление сообщения из чата (POST /api/chat/delete)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/chat/delete") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $msgId = if ($null -ne $json.id) { $json.id } elseif ($null -ne $json.messageId) { $json.messageId } else { $null }
                $username = if ($json.username) { [string]$json.username } else { "guest" }

                if (-not $msgId) {
                    $resObj = @{ success = $false; error = "Не передан ID сообщения." }
                    $response.StatusCode = 400
                } else {
                    $isAdminUser = ($username.ToLower() -eq "skynet83")
                    $usersFile = Join-Path $path "data\users.json"
                    if ([System.IO.File]::Exists($usersFile)) {
                        $allU = [System.IO.File]::ReadAllText($usersFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                        $curU = $allU | Where-Object { $_.username.ToLower() -eq $username.ToLower() } | Select-Object -First 1
                        if ($curU -and $curU.role -eq "admin") { $isAdminUser = $true }
                    }

                    $chatFile = Join-Path $path "data\chat_messages.json"
                    $messages = @()
                    if ([System.IO.File]::Exists($chatFile)) {
                        $raw = [System.IO.File]::ReadAllText($chatFile, [System.Text.Encoding]::UTF8)
                        if ($raw -and $raw.Trim()) {
                            $messages = $raw | ConvertFrom-Json
                            if ($messages -isnot [System.Collections.IEnumerable]) { $messages = @($messages) }
                        }
                    }

                    $strMsgId = [string]$msgId
                    $targetMsg = $messages | Where-Object { 
                        [string]$_.id -eq $strMsgId -or 
                        ([int64]::TryParse([string]$_.id, [ref]$null) -and [int64]::TryParse($strMsgId, [ref]$null) -and [Math]::Abs([int64]$_.id - [int64]$strMsgId) -le 512)
                    } | Select-Object -First 1

                    $isSenderMatch = $false
                    if ($targetMsg) {
                        $isSenderMatch = ($targetMsg.sender.ToLower() -eq $username.ToLower()) -or 
                            (($targetMsg.sender.ToLower() -in @("guest", "гость")) -and ($username.ToLower() -in @("guest", "гость")))
                    }

                    if (-not $targetMsg) {
                        $resObj = @{ success = $false; error = "Сообщение не найдено." }
                        $response.StatusCode = 404
                    } elseif ([string]$targetMsg.id -eq "1") {
                        $resObj = @{ success = $false; error = "Приветственное сообщение нельзя удалить." }
                        $response.StatusCode = 400
                    } elseif (-not $isAdminUser -and -not $isSenderMatch) {
                        $resObj = @{ success = $false; error = "Вы можете удалять только свои сообщения." }
                        $response.StatusCode = 403
                    } else {
                        $targetIdStr = [string]$targetMsg.id
                        $messages = @($messages | Where-Object { [string]$_.id -ne $targetIdStr })
                        [System.IO.File]::WriteAllText($chatFile, ($messages | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                        $resObj = @{ success = $true; deletedId = $targetIdStr }
                    }
                }

                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.Headers.Add("Cache-Control", "no-cache, no-store, must-revalidate")
                $response.Headers.Add("Pragma", "no-cache")
                $response.Headers.Add("Expires", "0")
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }

        # API: Очистка истории чата (POST /api/chat/clear)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/chat/clear") {
            try {
                $chatFile = Join-Path $path "data\chat_messages.json"
                $cleanMsg = @(
                    [PSCustomObject]@{
                        id = "1"
                        sender = "skynet83"
                        sender_name = "Администратор (@skynet19081983)"
                        recipient = "all"
                        text = "Здравствуйте! Здесь вы можете отправить ваш ID компьютера администратору в Telegram (@skynet19081983) или прямо в этом чате для получения ключа активации SkyBase."
                        created_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
                        is_read = $true
                    }
                )
                [System.IO.File]::WriteAllText($chatFile, ($cleanMsg | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)
                $mirrorChat = if ($path -like "C:*") { "e:\TEMP\База-бот\SITE\data\chat_messages.json" } else { "C:\ins\EXP\Arduino\Проект\База-бот\SITE\data\chat_messages.json" }
                if (Test-Path (Split-Path $mirrorChat)) {
                    try { [System.IO.File]::WriteAllText($mirrorChat, ($cleanMsg | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8) } catch {}
                }
                $resObj = @{ success = $true; message = "История чата успешно очищена." }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
            }
            $response.Close()
            continue
        }
        # API: Статус лицензии и ID оборудования (GET /api/license/status?username=...)
        # API: Статус лицензии и ID оборудования (GET /api/license/status?username=...&request_id=...&device_type=...)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/license/status") {
            try {
                $qUsername = if ($request.QueryString["username"]) { [string]$request.QueryString["username"] } else { "skynet83" }
                $qReqId = if ($request.QueryString["request_id"]) { [string]$request.QueryString["request_id"] } else { "-" }
                $qDevType = if ($request.QueryString["device_type"]) { [string]$request.QueryString["device_type"] } else { "-" }
                $clientIp = $request.RemoteEndPoint.Address.ToString()
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawOut = & $global:pythonCmd -X utf8 $pyScript "get-license-status" $qUsername $clientIp $qReqId $qDevType 2>&1
                $rawJson = Get-CleanJsonOutput $rawOut
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Получение/генерация ID клиента для мобильных или ПК (GET /api/license/client_id)
        if ($request.HttpMethod -eq "GET" -and $localPath -eq "/api/license/client_id") {
            try {
                $qDevType = if ($request.QueryString["device_type"]) { [string]$request.QueryString["device_type"] } else { "auto" }
                $qSeed = if ($request.QueryString["seed"]) { [string]$request.QueryString["seed"] } else { "" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawOut = & $global:pythonCmd -X utf8 $pyScript "get-client-id" $qDevType $qSeed 2>&1
                $rawJson = Get-CleanJsonOutput $rawOut
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Активация ключа тарифа (POST /api/license/activate)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/license/activate") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json
                $rawKey = if ($json.key) { [string]$json.key } else { "-" }
                $uName = if ($json.username) { [string]$json.username } else { "skynet83" }
                $reqId = if ($json.request_id) { [string]$json.request_id } else { "-" }
                $clientIp = if ($request.RemoteEndPoint -and $request.RemoteEndPoint.Address) { $request.RemoteEndPoint.Address.ToString() } else { "-" }
                $pyScript = Join-Path $path "avito_api_helper.py"
                $rawOut = & $global:pythonCmd -X utf8 $pyScript "activate-license" $rawKey $uName $clientIp $reqId 2>&1
                $rawJson = Get-CleanJsonOutput $rawOut
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($rawJson.Trim())
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            } catch {
                $response.StatusCode = 500
                $errObj = @{ success = $false; error = $_.ToString() }
                $bytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $bytes.Length
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
            $response.Close()
            continue
        }

        # API: Загрузка схемы админом (POST /api/upload-circuit)
        if ($request.HttpMethod -eq "POST" -and $localPath -eq "/api/upload-circuit") {
            try {
                $reader = New-Object System.IO.StreamReader($request.InputStream, [System.Text.Encoding]::UTF8)
                $json = $reader.ReadToEnd() | ConvertFrom-Json

                $targetExt = [System.IO.Path]::GetExtension($json.fileName)
                if ([string]::IsNullOrEmpty($targetExt)) { $targetExt = ".png" }
                
                $cleanId = ($json.componentId -replace "[^a-zA-Z0-9_\-]", "").ToLower()
                $savedFileName = "$cleanId" + "_circuit" + $targetExt
                $schemFolder = Join-Path $path "img\schematics"
                if (-not [System.IO.Directory]::Exists($schemFolder)) {
                    [System.IO.Directory]::CreateDirectory($schemFolder) | Out-Null
                }

                $savedFilePath = Join-Path $schemFolder $savedFileName
                $base64Raw = $json.base64Data
                if ($base64Raw -match "base64,(.+)$") {
                    $base64Raw = $matches[1]
                }

                $fileBytes = [System.Convert]::FromBase64String($base64Raw)
                [System.IO.File]::WriteAllBytes($savedFilePath, $fileBytes)

                $notesFile = Join-Path $path "data\engineering_notes.json"
                $notes = @()
                if ([System.IO.File]::Exists($notesFile)) {
                    $notes = [System.IO.File]::ReadAllText($notesFile, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
                    if ($notes -isnot [System.Collections.IEnumerable]) { $notes = @($notes) }
                }

                $relImgPath = "img/schematics/$savedFileName"
                $existing = $notes | Where-Object { 
                    $_.keywords -contains $cleanId -or $_.keywords -contains $json.componentName.ToLower() 
                } | Select-Object -First 1

                if ($existing) {
                    $existing.circuit_image = $relImgPath
                    if ($json.pinout) { $existing.pinout_scheme = $json.pinout }
                    if ($json.wiring) { $existing.wiring_guide = $json.wiring }
                    if ($json.nuances) { 
                        $existing.nuances = @($json.nuances -split "\r?\n" | Where-Object { $_.Trim() -ne "" })
                    }
                } else {
                    $nuanList = @()
                    if ($json.nuances) {
                        $nuanList = @($json.nuances -split "\r?\n" | Where-Object { $_.Trim() -ne "" })
                    }
                    $newNote = [PSCustomObject]@{
                        keywords = @($cleanId, $json.componentName.ToLower())
                        title = "$($json.componentName) — Схема и обвязка"
                        circuit_image = $relImgPath
                        pinout_scheme = if ($json.pinout) { $json.pinout } else { "Распиновка выводов согласно схеме" }
                        wiring_guide = if ($json.wiring) { $json.wiring } else { "Схема обвязки загружена администратором." }
                        nuances = $nuanList
                    }
                    $notes += $newNote
                }

                [System.IO.File]::WriteAllText($notesFile, ($notes | ConvertTo-Json -Depth 5), [System.Text.Encoding]::UTF8)

                $respData = [System.Text.Encoding]::UTF8.GetBytes('{"success":true,"image":"' + $relImgPath + '"}')
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $respData.Length
                $response.OutputStream.Write($respData, 0, $respData.Length)
            } catch {
                $response.StatusCode = 500
                $errData = [System.Text.Encoding]::UTF8.GetBytes('{"success":false,"error":"' + $_.ToString().Replace('"', '\"') + '"}')
                $response.ContentType = "application/json; charset=utf-8"
                $response.ContentLength64 = $errData.Length
                $response.OutputStream.Write($errData, 0, $errData.Length)
            }
            $response.Close()
            continue
        }

        # Запрет прямого открытия веб-страниц в браузере через внутренний порт бэкенда 8081
        if ($port -eq 8081) {
            $response.StatusCode = 403
            $response.StatusDescription = "Forbidden"
            $response.ContentType = "text/html; charset=utf-8"
            $denyB64 = "PCFET0NUWVBFIGh0bWw+PGh0bWwgbGFuZz1ydT48aGVhZD48bWV0YSBjaGFyc2V0PVVURi04Pjx0aXRsZT40MDMg0JTQvtGB0YLRg9C/INC30LDQutGA0YvRgjwvdGl0bGU+PHN0eWxlPmJvZHl7Zm9udC1mYW1pbHk6c2Fucy1zZXJpZjtiYWNrZ3JvdW5kOiMwZjE3MmE7Y29sb3I6I2Y4ZmFmYztkaXNwbGF5OmZsZXg7YWxpZ24taXRlbXM6Y2VudGVyO2p1c3RpZnktY29udGVudDpjZW50ZXI7aGVpZ2h0OjEwMHZoO21hcmdpbjowfS5jYXJke2JhY2tncm91bmQ6IzFlMjkzYjtib3JkZXI6MXB4IHNvbGlkICMzMzQxNTU7Ym9yZGVyLXJhZGl1czoxNnB4O3BhZGRpbmc6Mi41cmVtO21heC13aWR0aDo1MjBweDt0ZXh0LWFsaWduOmNlbnRlcjtib3gtc2hhZG93OjAgMTBweCAyNXB4IHJnYmEoMCwwLDAsMC41KX1oMXtjb2xvcjojZWY0NDQ0O2ZvbnQtc2l6ZToxLjVyZW07bWFyZ2luLXRvcDowfXB7Y29sb3I6Izk0YTNiODtmb250LXNpemU6MC45NXJlbTtsaW5lLWhlaWdodDoxLjY7bWFyZ2luOjFyZW0gMH0uYmFkZ2V7ZGlzcGxheTppbmxpbmUtYmxvY2s7YmFja2dyb3VuZDpyZ2JhKDIzOSw2OCw2OCwwLjE1KTtjb2xvcjojZWY0NDQ0O2JvcmRlcjoxcHggc29saWQgcmdiYSgyMzksNjgsNjgsMC4zKTtib3JkZXItcmFkaXVzOjZweDtwYWRkaW5nOjAuMnJlbSAwLjVyZW07Zm9udC1mYW1pbHk6bW9ub3NwYWNlfS5idG57ZGlzcGxheTppbmxpbmUtYmxvY2s7YmFja2dyb3VuZDojMDI4NGM3O2NvbG9yOiNmZmY7dGV4dC1kZWNvcmF0aW9uOm5vbmU7cGFkZGluZzowLjdyZW0gMS40cmVtO2JvcmRlci1yYWRpdXM6MTBweDtmb250LXdlaWdodDpib2xkO21hcmdpbi10b3A6MXJlbX0uYnRuOmhvdmVye2JhY2tncm91bmQ6IzAzNjlhMX08L3N0eWxlPjwvaGVhZD48Ym9keT48ZGl2IGNsYXNzPWNhcmQ+PGgxPvCflJIg0JTQvtGB0YLRg9C/INC6INC40L3RgtC10YDRhNC10LnRgdGDINC30LDQutGA0YvRgjwvaDE+PHA+0J/QvtGA0YIgPHNwYW4gY2xhc3M9YmFkZ2U+ODA4MTwvc3Bhbj4g0LjRgdC/0L7Qu9GM0LfRg9C10YLRgdGPINC40YHQutC70Y7Rh9C40YLQtdC70YzQvdC+INC60LDQuiDQstC90YPRgtGA0LXQvdC90LjQuSBBUEkt0YHQtdGA0LLQuNGBINCx0Y3QutC10L3QtNCwLjwvcD48cD7Qn9GA0Y/QvNC+0LUg0L7RgtC60YDRi9GC0LjQtSDQstC10LEt0YHRgtGA0LDQvdC40YbRiyDRh9C10YDQtdC3INC/0L7RgNGCIDgwODEg0LfQsNCx0LvQvtC60LjRgNC+0LLQsNC90L4uINCe0YLQutGA0L7QudGC0LUg0YHQsNC50YIg0L/QviDQvtGE0LjRhtC40LDQu9GM0L3QvtC80YMg0LDQtNGA0LXRgdGDOjwvcD48YSBocmVmPWh0dHA6Ly9sb2NhbGhvc3Q6ODA4MC8gY2xhc3M9YnRuPtCf0LXRgNC10LnRgtC4INC90LAg0YHQsNC50YIgKNC/0L7RgNGCIDgwODApPC9hPjwvZGl2PjwvYm9keT48L2h0bWw+"
            $denyBytes = [System.Convert]::FromBase64String($denyB64)
            $response.ContentLength64 = $denyBytes.Length
            $response.OutputStream.Write($denyBytes, 0, $denyBytes.Length)
            $response.Close()
            continue
        }

        # Статическая раздача файлов
        if ($localPath -eq "/" -or [string]::IsNullOrEmpty($localPath)) {
            $localPath = "/index.html"
        }

        $relPath = $localPath.TrimStart('/').Replace('/', '\')
        $filePath = Join-Path $path $relPath

        if ([System.IO.File]::Exists($filePath)) {
            $bytes = [System.IO.File]::ReadAllBytes($filePath)
            $ext = [System.IO.Path]::GetExtension($filePath).ToLower()
            if ($ext -eq ".json" -and $bytes.Length -ge 3) {
                if ($bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191) {
                    $cleanBytes = New-Object byte[] ($bytes.Length - 3)
                    [System.Array]::Copy($bytes, 3, $cleanBytes, 0, $cleanBytes.Length)
                    $bytes = $cleanBytes
                }
            }
            
            $contentType = switch ($ext) {
                ".html" { "text/html; charset=utf-8" }
                ".css"  { "text/css; charset=utf-8" }
                ".js"   { "application/javascript; charset=utf-8" }
                ".json" {
                    if ($filePath -like "*manifest.json") { "application/manifest+json; charset=utf-8" }
                    else { "application/json; charset=utf-8" }
                }
                ".webmanifest" { "application/manifest+json; charset=utf-8" }
                ".svg"  { "image/svg+xml" }
                ".png"  { "image/png" }
                ".jpg"  { "image/jpeg" }
                ".jpeg" { "image/jpeg" }
                ".gif"  { "image/gif" }
                ".ico"  { "image/x-icon" }
                ".woff2"{ "font/woff2" }
                ".woff" { "font/woff" }
                ".pdf"  { "application/pdf" }
                ".torrent" { "application/x-bittorrent" }
                Default { "application/octet-stream" }
            }

            if ($filePath -like "*sw.js") {
                $response.Headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                $response.Headers["Pragma"] = "no-cache"
                $response.Headers["Expires"] = "0"
                $response.Headers["Service-Worker-Allowed"] = "/"
            } elseif ($ext -in ".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".ico", ".woff", ".woff2") {
                $response.Headers["Cache-Control"] = "public, max-age=86400"
            } else {
                $response.Headers["Cache-Control"] = "no-cache, must-revalidate"
            }

            $acceptEncoding = $request.Headers["Accept-Encoding"]
            if ($acceptEncoding -and $acceptEncoding -match "gzip" -and ($ext -in ".html", ".css", ".js", ".json", ".svg", ".webmanifest") -and ($bytes.Length -gt 1024)) {
                try {
                    $ms = New-Object System.IO.MemoryStream
                    $gz = New-Object System.IO.Compression.GZipStream($ms, [System.IO.Compression.CompressionMode]::Compress)
                    $gz.Write($bytes, 0, $bytes.Length)
                    $gz.Close()
                    $compressedBytes = $ms.ToArray()
                    $ms.Close()
                    if ($compressedBytes.Length -lt $bytes.Length) {
                        $response.Headers["Content-Encoding"] = "gzip"
                        $bytes = $compressedBytes
                    }
                } catch {}
            }

            $response.ContentType = $contentType
            $response.ContentLength64 = $bytes.Length
            if ($request.HttpMethod -ne "HEAD") {
                $response.OutputStream.Write($bytes, 0, $bytes.Length)
            }
        } else {
            $response.StatusCode = 404
            $response.ContentEncoding = [System.Text.Encoding]::UTF8
            $response.ContentType = "text/plain; charset=utf-8"
            $err = [System.Text.Encoding]::UTF8.GetBytes("404 Not Found: " + $filePath)
            $response.ContentLength64 = $err.Length
            if ($request.HttpMethod -ne "HEAD") {
                $response.OutputStream.Write($err, 0, $err.Length)
            }
        }
            $response.Close()
        } catch {
            Write-Host "Предупреждение при обработке запроса: $_" -ForegroundColor DarkYellow
            try {
                if ($context -and $context.Response) {
                    $context.Response.StatusCode = 500
                    $context.Response.Close()
                }
            } catch {}
        }
    }
} catch {
    Write-Host "Критическая ошибка цикла listener: $_" -ForegroundColor Red
} finally {
    Write-Host "[*] Завершение работы SkyBase Server — остановка всех служб..." -ForegroundColor Yellow

    # 1. Останавливаем Telegram-бота и воркер прокси
    try {
        $pyScript = Join-Path $path "avito_api_helper.py"
        if (Test-Path $pyScript) {
            & $global:pythonCmd -X utf8 $pyScript "bot-toggle" "stop" 2>&1 | Out-Null
            & $global:pythonCmd -X utf8 $pyScript "fetch-proxies" "stop" 2>&1 | Out-Null
        }
    } catch {}

    # 2. Завершаем PID бота и прокси-воркера из файлов
    foreach ($botPid in @(
        (Join-Path $path "avito_bot\bot.pid"),
        (Join-Path $path "avito_bot\proxy_worker.pid")
    )) {
        if (Test-Path $botPid) {
            try {
                $bPidVal = (Get-Content $botPid -ErrorAction SilentlyContinue | Out-String).Trim()
                if ($bPidVal -match '^\d+$') {
                    Stop-Process -Id [int]$bPidVal -Force -ErrorAction SilentlyContinue
                }
                Remove-Item $botPid -Force -ErrorAction SilentlyContinue
            } catch {}
        }
    }

    # 3. Останавливаем LAN-прокси процесс
    try {
        if ($global:proxyProcess -and -not $global:proxyProcess.HasExited) {
            $global:proxyProcess.Kill()
            $global:proxyProcess.WaitForExit(3000)
        }
        $proxyPidFile = Join-Path $path "lan_proxy.pid"
        if (Test-Path $proxyPidFile) {
            $pPid = (Get-Content $proxyPidFile -ErrorAction SilentlyContinue | Out-String).Trim()
            if ($pPid -match '^\d+$') { Stop-Process -Id [int]$pPid -Force -ErrorAction SilentlyContinue }
            Remove-Item $proxyPidFile -Force -ErrorAction SilentlyContinue
        }
    } catch {}

    # 4. Останавливаем HTTP Listener (сначала Abort активных соединений, потом Stop и Close)
    if ($listener) {
        try {
            if ($listener.IsListening) {
                $listener.Stop()
            }
            $listener.Close()
        } catch {}
    }

    # 5. Удаляем PID-файл сервера
    if (Test-Path $pidFile) {
        Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    }

    Write-Host "[+] SkyBase Server полностью остановлен." -ForegroundColor Green
}

