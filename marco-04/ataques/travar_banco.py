#!/usr/bin/env python3
"""
Projeto Presenca - Marco 4
FALHA DE BANCO: congela o PostgreSQL (sem desligar) e depois descongela.

E o pior caso para o servidor: a conexao continua aberta, mas nada responde
(igual a um disco travado ou a uma VM suspensa). O servidor tem que continuar
decidindo a presenca, guardar as gravacoes na fila e gravar tudo quando o
banco voltar, sem recusar mensagem nenhuma por atraso.

Uso (Windows; o banco de banco\\banco.ps1 ligado):
    python travar_banco.py pausar
    python travar_banco.py continuar
    python travar_banco.py 20          # pausa 20 s e continua sozinho

Para o banco sem Docker: congela todos os processos postgres.exe com
NtSuspendProcess (o mesmo que o `docker pause` fazia com o conteiner).
"""

import ctypes
import csv
import io
import subprocess
import sys
import time

ACESSO_SUSPENDER = 0x0800          # PROCESS_SUSPEND_RESUME


def pids_do_postgres():
    saida = subprocess.run(["tasklist", "/FI", "IMAGENAME eq postgres.exe", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True).stdout
    return [int(linha[1]) for linha in csv.reader(io.StringIO(saida)) if len(linha) > 1 and linha[0] == "postgres.exe"]


def aplicar(acao):
    ntdll, kernel32 = ctypes.WinDLL("ntdll"), ctypes.WinDLL("kernel32")
    funcao = ntdll.NtSuspendProcess if acao == "pausar" else ntdll.NtResumeProcess
    pids = pids_do_postgres()
    if not pids:
        raise SystemExit("Nenhum postgres.exe rodando: ligue o banco com banco\\banco.ps1")
    for pid in pids:
        h = kernel32.OpenProcess(ACESSO_SUSPENDER, False, pid)
        if h:
            funcao(h)
            kernel32.CloseHandle(h)
    print(f"banco {'CONGELADO' if acao == 'pausar' else 'de volta'} ({len(pids)} processos postgres)")


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "pausar"
    if arg.isdigit():
        aplicar("pausar")
        time.sleep(int(arg))
        aplicar("continuar")
    elif arg in ("pausar", "continuar"):
        aplicar(arg)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
