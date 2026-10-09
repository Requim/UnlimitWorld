<#
.SYNOPSIS
Keeps the hidden browser-server console and its log streams alive.
.PARAMETER Node
Absolute Node executable path.
.PARAMETER Vite
Absolute Vite CLI path in the current workspace.
.PARAMETER Port
Local browser port.
.PARAMETER ApiUrl
Local authority API URL used by the Vite proxy.
.OUTPUTS
Writes runtime logs under .data; exits with the browser process exit code.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Node,
    [Parameter(Mandatory)][string]$Vite,
    [Parameter(Mandatory)][ValidateRange(1024, 65000)][int]$Port,
    [Parameter(Mandatory)][string]$ApiUrl
)

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$data = Join-Path $root '.data'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$env:M5_API_URL = $ApiUrl
$env:CI = 'true'
Set-Location -LiteralPath (Join-Path $root 'web-client')
$lifecycle = Join-Path $data 'm5-web-lifecycle.log'
"Started hidden host at $((Get-Date).ToString('o')); CI=$env:CI" |
    Set-Content -LiteralPath $lifecycle -Encoding UTF8
try {
    if (-not (Test-Path -LiteralPath $Node) -or -not (Test-Path -LiteralPath $Vite)) {
        throw 'Node or Vite executable path does not exist.'
    }
    & $Node $Vite --host 127.0.0.1 --port $Port --strictPort `
        1> (Join-Path $data 'm5-web.log') 2> (Join-Path $data 'm5-web-error.log')
    $code = $LASTEXITCODE
} catch {
    $_ | Out-String | Add-Content -LiteralPath (Join-Path $data 'm5-web-error.log')
    $code = 1
}
"Browser process exited at $((Get-Date).ToString('o')); code=$code" |
    Add-Content -LiteralPath $lifecycle -Encoding UTF8
exit $code
