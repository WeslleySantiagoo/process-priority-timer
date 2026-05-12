import os
import time
import multiprocessing
import dis
def funcao(valor_target, progresso_compartilhado):
    """Executa a carga de trabalho e atualiza o progresso em memória compartilhada."""
    for i in range(valor_target + 1):
        progresso_compartilhado.value = i
        z = i * i

valor = int(
    os.getenv("VALOR_TARGET", "990000000")
)  # Escolher o valor de forma que demore 60s para ser executado
progresso = multiprocessing.Value('i', 0, lock=False)
start = time.time()
funcao(valor, progresso)
duration = time.time() - start
print(f"\n[FIM] Script do Professor (base-weslley.py) terminou em: {duration:.2f}s")

# dis.dis(funcao)