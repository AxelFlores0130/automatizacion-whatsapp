Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

function Show-ErrorAndExit {
    param(
        [string]$Message,
        [int]$ExitCode = 1
    )

    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit $ExitCode
}

function ConvertTo-PlainText {
    param(
        [System.Security.SecureString]$SecurePassword
    )

    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
    try {
        return [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        if ($bstr) {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
}

$projectRoot = $PSScriptRoot
if (-not $projectRoot) {
    $projectRoot = (Get-Location).Path
}

$databaseDir = Join-Path $projectRoot 'database'
$targetSql = Join-Path $databaseDir 'dorian_automatizacion_dev.sql'
$tempSql = Join-Path $databaseDir 'dorian_automatizacion_dev.sql.tmp'
$sourceComprobantes = Join-Path $projectRoot 'comprobantes\originales'
$devComprobantes = Join-Path $databaseDir 'dev_comprobantes'

Write-Host "[1/3] Verificando mysqldump..." -ForegroundColor Cyan
$mysqldumpExe = 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe'
if (-not (Test-Path -LiteralPath $mysqldumpExe)) {
    Show-ErrorAndExit "No se encontro mysqldump.exe en $mysqldumpExe. Instala MySQL Server 8.0 o configura la ruta antes de ejecutar este script."
}

if (-not (Test-Path -LiteralPath $databaseDir)) {
    New-Item -ItemType Directory -Path $databaseDir -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $sourceComprobantes)) {
    Show-ErrorAndExit "No se encontro la carpeta de comprobantes de origen: $sourceComprobantes"
}

$mysqlUser = Read-Host "Usuario MySQL (predeterminado: root)"
if ([string]::IsNullOrWhiteSpace($mysqlUser)) {
    $mysqlUser = 'root'
}

Write-Host "Ingrese la contrasena MySQL para el usuario '$mysqlUser'."
$mysqlPasswordSecure = Read-Host "Contrasena MySQL" -AsSecureString
$mysqlPassword = ConvertTo-PlainText -SecurePassword $mysqlPasswordSecure

Write-Host ""
Write-Host "Se exportara la base 'dorian_automatizacion' hacia: $targetSql" -ForegroundColor Yellow

Write-Host ""
Write-Host "[2/3] Guardando base de datos DEV..." -ForegroundColor Cyan

$stderrLog = [System.IO.Path]::GetTempFileName()
$originalMysqlPwd = [System.Environment]::GetEnvironmentVariable('MYSQL_PWD', 'Process')
$dumpExitCode = $null
$dumpOutput = $null
$stderrText = $null

try {
    if (Test-Path -LiteralPath $tempSql) {
        Remove-Item -LiteralPath $tempSql -Force -ErrorAction SilentlyContinue
    }

    [System.Environment]::SetEnvironmentVariable('MYSQL_PWD', $mysqlPassword, 'Process')

    $dumpOutput = & $mysqldumpExe --user=$mysqlUser --databases dorian_automatizacion --routines --triggers --events --single-transaction --result-file="$tempSql" 2>$stderrLog
    $dumpExitCode = $LASTEXITCODE
}
finally {
    if ($null -eq $originalMysqlPwd) {
        [System.Environment]::SetEnvironmentVariable('MYSQL_PWD', $null, 'Process')
    }
    else {
        [System.Environment]::SetEnvironmentVariable('MYSQL_PWD', $originalMysqlPwd, 'Process')
    }

    if (Test-Path -LiteralPath $stderrLog) {
        $stderrText = Get-Content -LiteralPath $stderrLog -Raw -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stderrLog -Force -ErrorAction SilentlyContinue
    }

    $mysqlPassword = $null
}

if ($dumpExitCode -ne 0) {
    if (Test-Path -LiteralPath $tempSql) {
        Remove-Item -LiteralPath $tempSql -Force -ErrorAction SilentlyContinue
    }

    $combinedOutput = @()
    if ($null -ne $dumpOutput) {
        $combinedOutput += ($dumpOutput | Out-String)
    }
    if (-not [string]::IsNullOrWhiteSpace($stderrText)) {
        $combinedOutput += $stderrText
    }

    $text = ($combinedOutput | Out-String).Trim()
    if (-not [string]::IsNullOrWhiteSpace($text)) {
        Write-Host $text -ForegroundColor Red
    }

    Show-ErrorAndExit "La exportacion de la base de datos falló. No se reemplazo el SQL anterior."
}

if (Test-Path -LiteralPath $targetSql) {
    Remove-Item -LiteralPath $targetSql -Force
}

Move-Item -LiteralPath $tempSql -Destination $targetSql -Force
Write-Host "SQL generado: $targetSql" -ForegroundColor Green

Write-Host ""
Write-Host "[3/3] Guardando comprobantes DEV..." -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $devComprobantes)) {
    New-Item -ItemType Directory -Path $devComprobantes -Force | Out-Null
}
else {
    $existingItems = Get-ChildItem -LiteralPath $devComprobantes -Force
    foreach ($item in $existingItems) {
        if ($item.PSIsContainer) {
            Remove-Item -LiteralPath $item.FullName -Recurse -Force
        }
        else {
            Remove-Item -LiteralPath $item.FullName -Force
        }
    }
}

$copiedCount = 0
$sourceFiles = Get-ChildItem -LiteralPath $sourceComprobantes -Force
foreach ($item in $sourceFiles) {
    $destPath = Join-Path $devComprobantes $item.Name
    Copy-Item -LiteralPath $item.FullName -Destination $destPath -Force
    $copiedCount++
}

Write-Host "Cantidad de comprobantes copiados: $copiedCount" -ForegroundColor Green
Write-Host ""
Write-Host "Estado DEV guardado correctamente." -ForegroundColor Green
Write-Host "SQL generado: $targetSql" -ForegroundColor Green
