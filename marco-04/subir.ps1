# Projeto Presença - Marco 4
# SOBE TUDO, SEM DOCKER: banco (PostgreSQL portátil), servidor e âncora do PC.
#
#   .\subir.ps1               banco + servidor + âncora, cada um na sua janela
#   .\subir.ps1 -SemAncora    sem a âncora (ex.: só a ESP32 ou celulares simulados)
#   .\subir.ps1 -Tls          servidor pela porta 8883 em vez de WebSocket (8084)
#   .\subir.ps1 desligar      desliga tudo (o mesmo que .\desligar.ps1)
#
# O banco está em banco\banco.ps1 (na 1ª vez ele baixa ~310 MB para C:\presenca-pg).

param(
    [ValidateSet("subir", "desligar")][string]$acao = "subir",
    [switch]$SemAncora,
    [switch]$Tls
)

$ErrorActionPreference = "Stop"
$AQUI = $PSScriptRoot
$BANCO = Join-Path $AQUI "banco\banco.ps1"

if ($acao -eq "desligar") {
    & (Join-Path $AQUI "desligar.ps1")
    return
}

& $BANCO ligar

function Abrir-Janela($titulo, $pasta, $comando) {
    $script = "`$Host.UI.RawUI.WindowTitle = '$titulo'; `$env:PYTHONUNBUFFERED = '1'; Set-Location -LiteralPath '$pasta'; $comando"
    Start-Process powershell -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $script) | Out-Null
    Write-Host "  janela aberta: $titulo  ($comando)" -ForegroundColor Cyan
}

$transporte = if ($Tls) { "--tls" } else { "--ws" }
Abrir-Janela "Presença · servidor" (Join-Path $AQUI "servidor") "python servidor.py $transporte"
if (-not $SemAncora) {
    Abrir-Janela "Presença · âncora anc-pc-1" (Join-Path $AQUI "ancora") "python ancora.py"
}
Write-Host ""
Write-Host "Relatório e API: http://127.0.0.1:8090/" -ForegroundColor Green
Write-Host "Para desligar tudo no fim: .\desligar.ps1" -ForegroundColor DarkGray
