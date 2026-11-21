# Projeto Presença - Marco 4
# DESLIGA TUDO o que o subir.ps1 ligou: servidor, âncora do notebook, celulares simulados e o banco.
#
#   .\desligar.ps1              para os programas Python do projeto e desliga o banco
#   .\desligar.ps1 -FicaBanco   para só os programas e deixa o banco ligado
#
# Só encerra Python que esteja rodando um destes arquivos: servidor.py, ancora.py,
# celulares.py, travar_banco.py. Outros programas Python do computador não são tocados.

param([switch]$FicaBanco)

$AQUI = $PSScriptRoot
$PROGRAMAS = "servidor\.py|ancora\.py|celulares\.py|travar_banco\.py"

# Se o banco foi congelado por travar_banco.py, solta antes de desligar.
$travar = Join-Path $AQUI "ataques\travar_banco.py"
if (Test-Path $travar) { python $travar continuar *> $null }

$achados = Get-CimInstance Win32_Process -Filter "name='python.exe' or name='pythonw.exe'" |
    Where-Object { $_.CommandLine -match $PROGRAMAS }
if (-not $achados) {
    Write-Host "Nenhum programa do Presença rodando." -ForegroundColor DarkGray
}
foreach ($p in $achados) {
    $qual = [regex]::Match($p.CommandLine, $PROGRAMAS).Value
    try {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
        Write-Host "  parado: $qual (processo $($p.ProcessId))" -ForegroundColor Cyan
    } catch {
        Write-Host "  não consegui parar $qual (processo $($p.ProcessId)): $_" -ForegroundColor Yellow
    }
}

# As janelas abertas pelo subir.ps1 ficam vazias (-NoExit); fecha as que têm o título do projeto.
Get-Process powershell -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -like "Presença ·*" } |
    ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }

if (-not $FicaBanco) {
    & (Join-Path $AQUI "banco\banco.ps1") desligar
}
Write-Host "Tudo desligado." -ForegroundColor Green
