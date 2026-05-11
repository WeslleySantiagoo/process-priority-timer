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
    
    # Fixa o processo do Monitor em uma CPU isolada (ex: CPU 1) para não competir com a carga
    os.system(f"taskset -cp {cpu_monitor} {os.getpid()} > /dev/null")
    
    # Marca o tempo inicial de execução para nossa referência base de 0 segundos
    start_time = time.time()
    BLUE = '\033[94m'
    RESET = '\033[0m'
    
    print(f"{BLUE}[MONITOR] Iniciado. Intervalo: {interval}s | Threshold: {threshold}%{RESET}")
    
    # Loop de Polling (Fica vigiando o processo de trabalho de tempos em tempos)
    while True:
        # Calcula o tempo total decorrido desde o start
        elapsed = time.time() - start_time
        
        # Lê a iteração atual do processo filho através da memória compartilhada
        atual_iter = progresso_compartilhado.value
        
        # Condição de parada: Se o trabalho chegou ao fim ou passou do prazo máximo de segurança
        if atual_iter >= valor_target or elapsed >= time_target * 5:
            print(f"{BLUE}[MONITOR] Finalizando monitoramento...{RESET}")
            break
            
        # Converte o andamento do tempo e o andamento do trabalho em escalas de 0% a 100%
        perc_tempo = (elapsed / time_target) * 100
        perc_trabalho = (atual_iter / valor_target) * 100
        
        # O quão adiantado ou atrasado estamos em relação ao tempo que se passou (Trabalho - Tempo)
        diferenca = perc_trabalho - perc_tempo
        
        print(f"{BLUE}[MONITOR] Tempo: {perc_tempo:.1f}% | Trabalho: {perc_trabalho:.1f}% | Dif: {diferenca:.2f}%{RESET}")

        try:
            # Captura o valor de "nice" atual do processo de trabalho chamando o utilitário 'ps'
            res = os.popen(f"ps -o nice= -p {pid_trabalho}").read().strip()
            if res:
                current_nice = int(res)
                new_nice = current_nice
                
                # Se estamos trabalhando MAIS RÁPIDO do que devíamos (Adiantados acima do threshold tolerado)
                if diferenca >= threshold:
                    # Limite máximo de gentileza do Linux é 19. Aumentar o nice = Perder prioridade na CPU
                    if current_nice < 19:
                        new_nice = current_nice + 1
                        msg = f"ADIANTADO {diferenca:.2f}%. Aumentando Nice: {current_nice} -> {new_nice}"
                
                # Se estamos trabalhando MAIS DEVAGAR do que devíamos (Atrasados abaixo do threshold tolerado)
                elif diferenca <= -threshold:
                    # Limite máximo de agressividade do Linux é -20. Diminuir o nice = Ganhar prioridade brutal na CPU
                    if current_nice > -20:
                        new_nice = current_nice - 1
                        msg = f"ATRASADO {diferenca:.2f}%. Diminuindo Nice: {current_nice} -> {new_nice}"
                
                # Se após os cálculos o nice houver sofrido alteração, aplicamos no SO com uso do utilitário 'renice'
                if new_nice != current_nice:
                    os.system(f"sudo renice -n {new_nice} -p {pid_trabalho} > /dev/null")
                    print(f"{BLUE}[MONITOR] !!! {msg}{RESET}")
        except Exception as e:
            print(f"Erro ao ajustar nice: {e}")
        
        # Pausa o monitor pelo intervalo definido para aliviar a carga da CPU isolada
        time.sleep(interval)

if __name__ == "__main__":
    # Carrega variáveis ou insere as métricas padronizadas para nosso objetivo
    carregar_env()
    valor_target = int(os.getenv("VALOR_TARGET", "990000000"))
    time_target = float(os.getenv("TIME_TARGET", "60"))
    cpu_monitor = os.getenv("CPU_MONITOR", "1")
    monitor_interval = float(os.getenv("MONITOR_INTERVAL", "0.1"))
    monitor_threshold = float(os.getenv("MONITOR_THRESHOLD", "0.1"))
    
    # Inicia ponteiro de memória compartilhada para trocar informações com o Processo Filho de forma Assíncrona.
    # OBS: O lock=False desativa o bloqueador natural do Python (Semáforo de IO IPC) para não prejudicar absurdamente (25%+) do nosso processador bruto.
    progresso = multiprocessing.Value('L', 0, lock=False)
    
    # Criamos o sub-processo que rodará a função pesada sem sujar nosso loop pai
    p_trabalho = multiprocessing.Process(target=funcao, args=(valor_target, progresso))
    start_work = time.time()
    
    # Dispara paralelamente o Processo Filho (que rodará amarrado na CPU 0 graças ao taskset superior)
    p_trabalho.start()
    
    # BLOCO DE CONFIABILIDADE (Try / Except / Finally)
    # Motivo: Quando mexemos com múltiplos processos nativos via multiprocessing, o Kernel os destacha.
    # Se o Usuário cancelar abruptamente com 'Ctrl + C' (KeyboardInterrupt), o processo Pai morreria mas o
    # Filho continuaria sendo um "Zumbi" gastando 100% da sua CPU em segundo plano eternamente.
    try:
        # A main (pai) inicia sua vida de monitor enquanto o filho está rodando de forma assíncrona
        monitor(p_trabalho.pid, valor_target, time_target, progresso, cpu_monitor, monitor_interval, monitor_threshold)
        
    except KeyboardInterrupt:
        # Permite interrupção limpa do usuário (Ctrl+C) e apenas segue em frente para fechar a porta com chave.
        pass
        
    finally:
        # O bloco 'finally' roda ABSOLUTAMENTE SEMPRE (seja no término natural ou numa quebra do usuário).
        # o '.join()' tranca o Pai para obrigá-lo a esperar e destruir completamente a thread do Filho (limpeza sem Processos Zumbis)
        p_trabalho.join()
        
        # Assim que o ciclo todo acabou, imprimimos o tempo cravado que de fato levamos do início ao fim
        duration = time.time() - start_work
        print(f"\n[FIM] Seu script (main.py) terminou em: {duration:.2f}s")
