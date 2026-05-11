import os
import time
import multiprocessing
import sys


def carregar_env():
    """Carrega as variáveis de ambiente do arquivo .env."""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value


def funcao(valor_target, progresso_compartilhado):
    """Executa a carga de trabalho e atualiza o progresso em memória compartilhada."""
    for i in range(valor_target + 1):
        progresso_compartilhado.value = i
        z = i * i
    

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
    # Fallback para os mesmos valores padrão do init.sh
    carregar_env()
    valor_target = int(os.getenv("VALOR_TARGET", "990000000"))
    time_target = float(os.getenv("TIME_TARGET", "60"))
    cpu_monitor = os.getenv("CPU_MONITOR", "1")
    monitor_interval = float(os.getenv("MONITOR_INTERVAL", "0.1"))
    monitor_threshold = float(os.getenv("MONITOR_THRESHOLD", "0.1"))
    
    progresso = multiprocessing.Value('L', 0, lock=False)
    
    p_trabalho = multiprocessing.Process(target=funcao, args=(valor_target, progresso))
    start_work = time.time()
    p_trabalho.start()
    
    try:
        monitor(p_trabalho.pid, valor_target, time_target, progresso, cpu_monitor, monitor_interval, monitor_threshold)
    except KeyboardInterrupt:
        pass
    finally:
        p_trabalho.join()
        duration = time.time() - start_work
        print(f"\n[FIM] Seu script (main.py) terminou em: {duration:.2f}s")
