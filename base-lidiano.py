import os
import time

def funcao(valor_temp):
    for i in range(valor_temp):
        z = i * i


valor = int(
    os.getenv("VALOR_TARGET", "1000000000")
)  # Escolher o valor de forma que demore 60s para ser executado
start = time.time()
funcao(valor)
duration = time.time() - start
print(f"\n[FIM] Script do Professor (base-lidiano.py) terminou em: {duration:.2f}s")
