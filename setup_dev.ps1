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

Write-Host "[1/3] Verificando MySQL..." -ForegroundColor Cyan
$mysqlExe = 'C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe'
if (-not (Test-Path -LiteralPath $mysqlExe)) {
    Show-ErrorAndExit "No se encontró MySQL Server 8.0 en $mysqlExe. Instálalo y asegúrate de que la ruta sea correcta o configura MySQL Server 8.0 antes de ejecutar este script."
}

Write-Host "MySQL encontrado en: $mysqlExe" -ForegroundColor Green

$databaseSql = Join-Path $projectRoot 'database\dorian_automatizacion_dev.sql'
if (-not (Test-Path -LiteralPath $databaseSql)) {
    Show-ErrorAndExit "No se encontró el archivo SQL de restauración: $databaseSql"
}

$mysqlUser = Read-Host "Usuario MySQL (predeterminado: root)"
if ([string]::IsNullOrWhiteSpace($mysqlUser)) {
    $mysqlUser = 'root'
}

Write-Host "Introduzca la contraseña MySQL para el usuario '$mysqlUser'."
$mysqlPasswordSecure = Read-Host "Contraseña MySQL" -AsSecureString
$mysqlPassword = ConvertTo-PlainText -SecurePassword $mysqlPasswordSecure

Write-Host "" 
Write-Host "ADVERTENCIA: Esta operación restaurará el estado DEV de la base de datos 'dorian_automatizacion' y puede reemplazar datos de desarrollo." -ForegroundColor Yellow
Write-Host "Se importará el archivo: $databaseSql" -ForegroundColor Yellow
$confirmation = Read-Host "Para confirmar, escribe RESTAURAR_DEV y presiona Enter"
if ($confirmation -ne 'RESTAURAR_DEV') {
    Show-ErrorAndExit "Importación cancelada por el usuario. No se realizó ninguna restauración de la base de datos."
}

Write-Host "" 
Write-Host "[2/3] Restaurando base de datos DEV..." -ForegroundColor Cyan

$stderrLog = [System.IO.Path]::GetTempFileName()
$originalMysqlPwd = [System.Environment]::GetEnvironmentVariable('MYSQL_PWD')
$importOutput = $null
$stderrText = $null
$importExitCode = $null

try {
    [System.Environment]::SetEnvironmentVariable('MYSQL_PWD', $mysqlPassword, 'Process')
    $importOutput = Get-Content -LiteralPath $databaseSql -Raw | & $mysqlExe --user=$mysqlUser 2>$stderrLog
    $importExitCode = $LASTEXITCODE
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

if ($importExitCode -ne 0) {
    $outputText = @()
    if ($null -ne $importOutput) {
        $outputText += ($importOutput | Out-String)
    }
    if (-not [string]::IsNullOrWhiteSpace($stderrText)) {
        $outputText += $stderrText
    }

    $combinedOutput = ($outputText | Out-String).Trim()
    if (-not [string]::IsNullOrWhiteSpace($combinedOutput)) {
        Write-Host $combinedOutput -ForegroundColor Red
    }

    Show-ErrorAndExit "La restauración de la base de datos falló. Revisa la configuración del usuario y la contraseña de MySQL y vuelve a intentarlo."
}

Write-Host "Base de datos restaurada correctamente." -ForegroundColor Green

$sourceComprobantes = Join-Path $projectRoot 'database\dev_comprobantes'
if (-not (Test-Path -LiteralPath $sourceComprobantes)) {
    Write-Host "No se encontró la carpeta de comprobantes de prueba en $sourceComprobantes. Se omite la restauración de comprobantes." -ForegroundColor Yellow
}
else {
    $destComprobantes = Join-Path $projectRoot 'comprobantes\originales'
    if (-not (Test-Path -LiteralPath $destComprobantes)) {
        New-Item -ItemType Directory -Path $destComprobantes -Force | Out-Null
    }

    Write-Host "" 
    Write-Host "[3/3] Restaurando comprobantes DEV..." -ForegroundColor Cyan

    $items = Get-ChildItem -LiteralPath $sourceComprobantes -Force
    foreach ($item in $items) {
        $destPath = Join-Path $destComprobantes $item.Name
        Copy-Item -LiteralPath $item.FullName -Destination $destPath -Force
    }

    Write-Host "Comprobantes copiados a $destComprobantes" -ForegroundColor Green
}

Write-Host "" 
Write-Host "Entorno DEV restaurado correctamente." -ForegroundColor Green
