# Projeto Presença - Marco 4
# BANCO SEM DOCKER: PostgreSQL 16 + TimescaleDB 2.17 "portátil", numa pasta.
#
# Não instala nada no Windows: sem serviço, sem instalador, sem administrador.
# O banco só existe enquanto estiver ligado (uns 30-50 MB de RAM).
#
#   .\banco\banco.ps1            liga (na 1ª vez baixa ~310 MB e cria o banco)
#   .\banco\banco.ps1 desligar   desliga
#   .\banco\banco.ps1 estado     diz se está ligado e quantas linhas tem
#   .\banco\banco.ps1 psql       abre o console SQL
#
# Mesma porta, usuário e senha do docker-compose (55432, presenca/presenca):
# o servidor e os testes não mudam nada. Pasta: C:\presenca-pg (ou $env:PRESENCA_PG)
# — fora do projeto e sem acento no caminho, que o PostgreSQL não gosta.

param([ValidateSet("ligar", "desligar", "estado", "psql")][string]$acao = "ligar")

$ErrorActionPreference = "Stop"
$PG_VERSAO = "16.6-1"
$TS_VERSAO = "2.17.2"
$PORTA = 55432
$USUARIO = "presenca"
$BASE = if ($env:PRESENCA_PG) { $env:PRESENCA_PG } else { "C:\presenca-pg" }
$PGSQL = Join-Path $BASE "pgsql"
$BIN = Join-Path $PGSQL "bin"
$DADOS = Join-Path $BASE "dados"
$LOG = Join-Path $BASE "banco.log"
$SCHEMA = Join-Path $PSScriptRoot "schema.sql"
$env:PGPASSWORD = "presenca"
$env:PGOPTIONS = "-c client_min_messages=warning"   # sem os NOTICE "already exists" do schema

function Mostrar($cor, $texto) { Write-Host $texto -ForegroundColor $cor }

function Instalar {
    if (Test-Path (Join-Path $BIN "postgres.exe")) { return }
    Mostrar Cyan "Primeira vez: baixando o PostgreSQL $PG_VERSAO e o TimescaleDB $TS_VERSAO para $BASE ..."
    $baixados = Join-Path $BASE "_baixados"
    New-Item -ItemType Directory -Force $baixados | Out-Null
    $ProgressPreference = "SilentlyContinue"   # a barra de progresso deixa o download 10x mais lento
    $pgZip = Join-Path $baixados "pg.zip"
    $tsZip = Join-Path $baixados "ts.zip"
    Invoke-WebRequest "https://get.enterprisedb.com/postgresql/postgresql-$PG_VERSAO-windows-x64-binaries.zip" -OutFile $pgZip
    Invoke-WebRequest "https://github.com/timescale/timescaledb/releases/download/$TS_VERSAO/timescaledb-postgresql-16-windows-amd64.zip" -OutFile $tsZip
    Mostrar Cyan "Descompactando..."
    Expand-Archive $pgZip -DestinationPath $BASE -Force
    foreach ($sobra in "pgAdmin 4", "StackBuilder", "doc", "symbols") {
        $p = Join-Path $PGSQL $sobra
        if (Test-Path $p) { Remove-Item -Recurse -Force $p }
    }
    $ts = Join-Path $baixados "ts"
    Expand-Archive $tsZip -DestinationPath $ts -Force
    Copy-Item (Join-Path $ts "timescaledb\*.dll") (Join-Path $PGSQL "lib") -Force
    Copy-Item (Join-Path $ts "timescaledb\*.sql"), (Join-Path $ts "timescaledb\*.control") (Join-Path $PGSQL "share\extension") -Force
    Remove-Item -Recurse -Force $baixados
}

function Criar {
    if (Test-Path (Join-Path $DADOS "PG_VERSION")) { return $false }
    Mostrar Cyan "Criando o banco em $DADOS ..."
    $senha = Join-Path $BASE "senha.tmp"
    Set-Content -Path $senha -Value "presenca" -Encoding ascii -NoNewline
    & (Join-Path $BIN "initdb.exe") -D $DADOS -U $USUARIO --pwfile=$senha -A scram-sha-256 -E UTF8 --locale=C | Out-Null
    Remove-Item $senha
    if ($LASTEXITCODE -ne 0) { throw "initdb falhou" }
    # Configuração enxuta para um PC de 8 GB, e a TimescaleDB carregada na partida.
    Add-Content -Path (Join-Path $DADOS "postgresql.conf") -Encoding ascii -Value @"

# --- Presenca ---
port = $PORTA
listen_addresses = 'localhost'
max_connections = 20
shared_buffers = 64MB
work_mem = 4MB
maintenance_work_mem = 32MB
shared_preload_libraries = 'timescaledb'
timescaledb.telemetry_level = off
timescaledb.max_background_workers = 4
max_worker_processes = 12
timezone = 'America/Sao_Paulo'
log_timezone = 'America/Sao_Paulo'
"@
    return $true
}

function Ligado {
    & (Join-Path $BIN "pg_ctl.exe") status -D $DADOS *> $null
    return $LASTEXITCODE -eq 0
}

function Psql([string[]]$resto) {
    & (Join-Path $BIN "psql.exe") -h localhost -p $PORTA -U $USUARIO @resto
}

switch ($acao) {
    "ligar" {
        Instalar
        $novo = Criar
        if (Ligado) {
            Mostrar Green "O banco já estava ligado (porta $PORTA)."
        } else {
            # Start-Process e esperar SÓ o pg_ctl: com pipe (| Out-Null) o postgres herda
            # a saída e o PowerShell fica esperando para sempre.
            $p = Start-Process (Join-Path $BIN "pg_ctl.exe") -ArgumentList @("start", "-D", "`"$DADOS`"", "-l", "`"$LOG`"", "-w", "-t", "30") -WindowStyle Hidden -PassThru
            $p.WaitForExit()
            if (-not (Ligado)) { Get-Content $LOG -Tail 15; throw "o banco não ligou (log: $LOG)" }
        }
        $existe = Psql @("-d", "postgres", "-tAc", "SELECT 1 FROM pg_database WHERE datname = 'presenca'")
        if ("$existe".Trim() -ne "1") {
            Psql @("-d", "postgres", "-q", "-c", "CREATE DATABASE presenca") | Out-Null
        }
        # O schema é idempotente: rodar toda vez aplica o que for novo sem apagar nada.
        Psql @("-d", "presenca", "-q", "-v", "ON_ERROR_STOP=1", "-f", $SCHEMA) | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "o schema falhou" }
        Mostrar Green "Banco LIGADO: postgresql://presenca:presenca@localhost:$PORTA/presenca (TimescaleDB $TS_VERSAO)"
        Mostrar DarkGray "Para desligar: .\banco\banco.ps1 desligar"
    }
    "desligar" {
        if (-not (Ligado)) { Mostrar Yellow "O banco já estava desligado."; break }
        & (Join-Path $BIN "pg_ctl.exe") stop -D $DADOS -m fast -w | Out-Null
        Mostrar Green "Banco desligado."
    }
    "estado" {
        if (-not (Test-Path (Join-Path $BIN "postgres.exe"))) { Mostrar Yellow "Não instalado ainda: rode .\banco\banco.ps1"; break }
        if (-not (Ligado)) { Mostrar Yellow "Desligado. Para ligar: .\banco\banco.ps1"; break }
        Mostrar Green "Ligado na porta $PORTA."
        Psql @("-d", "presenca", "-c", "SELECT (SELECT count(*) FROM eventos) AS eventos, (SELECT count(*) FROM sensores) AS sensores, (SELECT count(*) FROM sessoes) AS sessoes, (SELECT count(*) FROM identificacao) AS identificados, (SELECT extversion FROM pg_extension WHERE extname = 'timescaledb') AS timescaledb")
    }
    "psql" { Psql @("-d", "presenca") }
}
