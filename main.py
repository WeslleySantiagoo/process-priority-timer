import os
import time
import multiprocessing
import sys

def funcao(valor_target, progresso_compartilhado):
    """Executa a carga de trabalho e atualiza o progresso em memória compartilhada."""
    start_work = time.time()
    for i in range(valor_target + 1):
        if i % 500000 == 0:
            progresso_compartilhado.value = i
        _ = i * i
    progresso_compartilhado.value = valor_target
    duration = time.time() - start_work
    print(f"\n[FIM] Seu script (main.py) terminou em: {duration:.2f}s")

def monitor(pid_trabalho, valor_target, time_target, progresso_compartilhado, cpu_monitor, interval, threshold):
    """Monitora o progresso e ajusta o nice do processo de trabalho se necessário."""
    os.system(f"taskset -cp {cpu_monitor} {os.getpid()} > /dev/null")
    
    start_time = time.time()
    BLUE = '\033[94m'
    RESET = '\033[0m'
    
    print(f"{BLUE}[MONITOR] Iniciado. Intervalo: {interval}s | Threshold: {threshold}%{RESET}")
    
    while True:
        elapsed = time.time() - start_time
        atual_iter = progresso_compartilhado.value
        
        if atual_iter >= valor_target or elapsed >= time_target * 5:
            print(f"{BLUE}[MONITOR] Finalizando monitoramento...{RESET}")
            break
            
        perc_tempo = (elapsed / time_target) * 100
        perc_trabalho = (atual_iter / valor_target) * 100
        diferenca = perc_trabalho - perc_tempo
        
        print(f"{BLUE}[MONITOR] Tempo: {perc_tempo:.1f}% | Trabalho: {perc_trabalho:.1f}% | Dif: {diferenca:.2f}%{RESET}")

        try:
            res = os.popen(f"ps -o nice= -p {pid_trabalho}").read().strip()
            if res:
                current_nice = int(res)
                new_nice = current_nice
                
                if diferenca >= threshold:
                    if current_nice < 19:
                        new_nice = current_nice + 1
                        msg = f"ADIANTADO {diferenca:.2f}%. Aumentando Nice: {current_nice} -> {new_nice}"
                elif diferenca <= -threshold:
                    if current_nice > -20:
                        new_nice = current_nice - 1
                        msg = f"ATRASADO {diferenca:.2f}%. Diminuindo Nice: {current_nice} -> {new_nice}"
                
                if new_nice != current_nice:
                    os.system(f"sudo renice -n {new_nice} -p {pid_trabalho} > /dev/null")
                    print(f"{BLUE}[MONITOR] !!! {msg}{RESET}")
        except Exception as e:
            print(f"Erro ao ajustar nice: {e}")
        
        time.sleep(interval)

if __name__ == "__main__":
    valor_target = int(os.getenv("VALOR_TARGET", "1000000000"))
    time_target = float(os.getenv("TIME_TARGET", "60"))
    cpu_monitor = os.getenv("CPU_MONITOR", "1")
    monitor_interval = float(os.getenv("MONITOR_INTERVAL", "1.0"))
    monitor_threshold = float(os.getenv("MONITOR_THRESHOLD", "1.0"))
    
    progresso = multiprocessing.Value('L', 0)
    
    p_trabalho = multiprocessing.Process(target=funcao, args=(valor_target, progresso))
    p_trabalho.start()
    
    try:
        monitor(p_trabalho.pid, valor_target, time_target, progresso, cpu_monitor, monitor_interval, monitor_threshold)
    except KeyboardInterrupt:
        pass
    finally:
        p_trabalho.join()
