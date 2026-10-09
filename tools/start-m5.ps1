<#
.SYNOPSIS
Starts isolated M5 API and browser development servers in hidden windows.
.PARAMETER ApiPort
Preferred API port; an occupied port advances to the next free port.
.PARAMETER WebPort
Preferred browser port; an occupied port advances to the next free port.
.OUTPUTS
Service URLs and a local JSON record with process IDs. No existing process is stopped.
#>
[CmdletBinding()]
param(
    [ValidateRange(1024, 65000)][int]$ApiPort = 8787,
    [ValidateRange(1024, 65000)][int]$WebPort = 5173
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$data = Join-Path $root '.data'
$recordPath = Join-Path $data 'm5-services.json'

function Find-FreePort([int]$Preferred, [int]$Excluded = 0) {
    for ($port = $Preferred; $port -lt ($Preferred + 30); $port++) {
        $listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        if (-not $listeners -and $port -ne $Excluded) { return $port }
    }
    throw "No free local port near $Preferred."
}

function Test-Endpoint([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Wait-Endpoint([string]$Url, [System.Diagnostics.Process]$Process) {
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        if ($Process.HasExited) { throw "Service exited before becoming ready: $Url" }
        if (Test-Endpoint $Url) { return }
        Start-Sleep -Milliseconds 200
        $Process.Refresh()
    }
    throw "Service did not become ready: $Url. See .data/*.log."
}

function Test-RecordedProcess([int]$ProcessId, [string]$Marker) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId"
    return $process -and $process.CommandLine.Contains($Marker)
}

function Get-ExistingServices {
    if (-not (Test-Path -LiteralPath $recordPath)) { return $null }
    try {
        $saved = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
        $apiMatch = Test-RecordedProcess $saved.apiPid 'server.interface.roguelike_app:app'
        $webMatch = Test-RecordedProcess $saved.webPid (Join-Path $root 'web-client')
        if ($saved.workspace -ne $root -or -not $apiMatch -or -not $webMatch) { return $null }
        if ((Test-Endpoint "$($saved.apiUrl)/health") -and (Test-Endpoint $saved.webUrl)) {
            return $saved
        }
    } catch { return $null }
    return $null
}

function Start-Api([string]$Python, [int]$Port) {
    return Start-Process -FilePath $Python -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -ArgumentList @('-m', 'uvicorn', 'server.interface.roguelike_app:app', '--host', '127.0.0.1', '--port', "$Port") `
        -RedirectStandardOutput (Join-Path $data 'm5-api.log') `
        -RedirectStandardError (Join-Path $data 'm5-api-error.log')
}

function Start-Web([string]$Node, [string]$Vite, [int]$Port, [string]$ApiUrl) {
    $previous = $env:M5_API_URL
    try {
        $env:M5_API_URL = $ApiUrl
        return Start-Process -FilePath $Node -WorkingDirectory (Join-Path $root 'web-client') `
            -WindowStyle Hidden -PassThru `
            -ArgumentList @("`"$Vite`"", '--host', '127.0.0.1', '--port', "$Port", '--strictPort') `
            -RedirectStandardOutput (Join-Path $data 'm5-web.log') `
            -RedirectStandardError (Join-Path $data 'm5-web-error.log')
    } finally { $env:M5_API_URL = $previous }
}

$existing = Get-ExistingServices
if ($existing) {
    Write-Output "Browser: $($existing.webUrl)"
    Write-Output "API: $($existing.apiUrl)"
    exit 0
}
$python = Join-Path $root '.venv\Scripts\python.exe'
$vite = Join-Path $root 'web-client\node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create .venv and install server/requirements-m5.txt first.' }
if (-not (Test-Path -LiteralPath $vite)) { throw 'Run npm ci in web-client first.' }
$node = (Get-Command node -ErrorAction Stop).Source
New-Item -ItemType Directory -Path $data -Force | Out-Null
$ApiPort = Find-FreePort $ApiPort
$WebPort = Find-FreePort $WebPort $ApiPort
$apiUrl = "http://127.0.0.1:$ApiPort"
$webUrl = "http://127.0.0.1:$WebPort"
$api = $null
$web = $null
try {
    $api = Start-Api $python $ApiPort
    Wait-Endpoint "$apiUrl/health" $api
    $web = Start-Web $node $vite $WebPort $apiUrl
    Wait-Endpoint $webUrl $web
} catch {
    foreach ($started in @($api, $web)) {
        if ($started -and -not $started.HasExited) { $started.Kill() }
    }
    throw
}
$record = [ordered]@{
    workspace = $root
    apiPid = $api.Id
    webPid = $web.Id
    apiUrl = $apiUrl
    webUrl = $webUrl
    startedAt = (Get-Date).ToString('o')
}
$record | ConvertTo-Json | Set-Content -LiteralPath $recordPath -Encoding UTF8
Write-Output "Browser: $webUrl"
Write-Output "API: $apiUrl"
Write-Output "Service record: $recordPath"
