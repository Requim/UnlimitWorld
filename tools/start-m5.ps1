<#
.SYNOPSIS
Starts isolated M5 API and browser development servers in hidden windows.
.PARAMETER ApiPort
Preferred API port; an occupied port advances to the next free port.
.PARAMETER WebPort
Preferred browser port; an occupied port advances to the next free port.
.OUTPUTS
Service URLs and a local JSON record with process IDs. Unrelated processes are never stopped.
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
    if (-not $process -or -not $process.CommandLine) { return $false }
    return $process.CommandLine.Contains($Marker) -and $process.CommandLine.Contains($root)
}

function Get-ExistingServices {
    if (-not (Test-Path -LiteralPath $recordPath)) { return $null }
    try {
        $saved = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
        $apiMatch = Test-RecordedProcess $saved.apiPid 'server.interface.roguelike_app:app'
        $webMatch = Test-RecordedProcess $saved.webPid (Join-Path $root 'web-client')
        if ($saved.workspace -ne $root) { return $null }
        $apiHealthy = $apiMatch -and (Test-Endpoint "$($saved.apiUrl)/health")
        $webHealthy = $webMatch -and (Test-Endpoint $saved.webUrl)
        $saved | Add-Member -NotePropertyName apiHealthy -NotePropertyValue $apiHealthy
        $saved | Add-Member -NotePropertyName webHealthy -NotePropertyValue $webHealthy
        return $saved
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
    $helper = Join-Path $root 'tools\run-m5-web.ps1'
    return Start-Process -FilePath 'powershell.exe' -WorkingDirectory $root `
        -WindowStyle Hidden -PassThru `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$helper`"", `
            '-Node', "`"$Node`"", '-Vite', "`"$Vite`"", '-Port', "$Port", '-ApiUrl', $ApiUrl)
}

function Stop-ManagedService([System.Diagnostics.Process]$HostProcess, [string]$Marker) {
    if (-not (Test-RecordedProcess $HostProcess.Id $Marker)) {
        throw 'Refusing to stop a service process outside this workspace.'
    }
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($HostProcess.Id)"
    foreach ($child in $children) {
        if (Test-RecordedProcess $child.ProcessId $Marker) {
            Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue
        }
    }
    $HostProcess.Refresh()
    if (-not $HostProcess.HasExited) { $HostProcess.Kill() }
    $HostProcess.WaitForExit()
}

$existing = Get-ExistingServices
if ($existing -and $existing.apiHealthy -and $existing.webHealthy) {
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
$reuseApi = $existing -and $existing.apiHealthy
if ($reuseApi) {
    $ApiPort = ([uri]$existing.apiUrl).Port
} else {
    $ApiPort = Find-FreePort $ApiPort
}
if ($existing -and $existing.webHealthy) {
    $oldWeb = Get-Process -Id $existing.webPid
    Stop-ManagedService $oldWeb $vite
    $WebPort = ([uri]$existing.webUrl).Port
}
$WebPort = Find-FreePort $WebPort $ApiPort
$apiUrl = "http://127.0.0.1:$ApiPort"
$webUrl = "http://127.0.0.1:$WebPort"
$api = $null
$web = $null
try {
    if ($reuseApi) { $api = Get-Process -Id $existing.apiPid }
    else { $api = Start-Api $python $ApiPort }
    Wait-Endpoint "$apiUrl/health" $api
    $web = Start-Web $node $vite $WebPort $apiUrl
    Wait-Endpoint $webUrl $web
} catch {
    if ($web -and -not $web.HasExited) { Stop-ManagedService $web $vite }
    if (-not $reuseApi -and $api -and -not $api.HasExited) {
        Stop-ManagedService $api 'server.interface.roguelike_app:app'
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
