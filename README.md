# Process Priority Timer

Este projeto implementa uma atividade focada na manipulação dinâmica de prioridades de processos em sistemas operacionais.

O objetivo principal é garantir que a execução de um script (que possui uma carga de trabalho intensiva) seja finalizada em um tempo **exato** estipulado (por exemplo, 60 segundos), ajustando automaticamente o índice de gentileza (`nice`) do processo no escalonador de CPU. Essa repriorização se baseia no tempo decorrido, comparando o trabalho concluído com a janela de tempo esperada.

---

## 🚀 Como Executar

O projeto acompanha de forma constante o processo e usa utilitários locais de escalonamento como o `renice`; portanto, a execução **requer privilégios de administrador (sudo)**.

### 1. Utilizando o `init.sh` (Uso Rápido e Prático)

O script bash `init.sh` foi criado como wrapper para facilitar a execução da atividade. Ele cuida do processo de carregar variáveis de ambiente de um arquivo `.env` (se existir) e utiliza o comando `taskset` para isolar e fixar os processos de teste nas CPUs corretas.

Ele roda ambos, o script base do professor (`base-lidiano.py`) e a nossa nova versão (`main.py`) de forma paralela.

**Para rodar via script (Basta executar no terminal):**

```bash
sudo ./init.sh
```

### 2. Manualmente (Sem o `init.sh`)

Para configurar o cenário de testes de forma manual (exatamente como o script faz por baixo dos panos), precisamos rodar **ambos** os algoritmos simultaneamente para que compitam pela mesma CPU. É essa competição que força o Kernel a usar o `nice` de fato.

Basta chamar os interpretadores passando as variáveis vitais (`VALOR_TARGET` e `TIME_TARGET`) e utilizando o **imprescindível** `taskset` para fixar a carga massiva no mesmo núcleo (`-c 0`).

```bash
# 1. Primeiro iniciamos o script base original (sem modificações) em segundo plano (&) fixo na CPU 0
sudo VALOR_TARGET=990000000 taskset -c 0 python3 base-lidiano.py &

# 2. Imediatamente depois, iniciamos o nosso script otimizado para competir matematicamente com o mesmo núcleo
sudo VALOR_TARGET=990000000 TIME_TARGET=60 taskset -c 0 python3 main.py
```

### 👀 Acompanhando a Execução em Tempo Real

Durante a execução (seja via `init.sh` ou manualmente), é altamente recomendado abrir um **terminal dedicado** para observar de perto a mágica acontecendo no sistema operacional. Execute o seguinte comando:

```bash
watch -n 0.1 ps -C python3 -o psr,pcpu,pid,time,pri,nice
```

**Como interpretar a saída do comando:**

- A coluna **`PSR`** (Processor) indica em qual CPU o processo está fixado.
- Você verá que **um dos processos** possui um `PSR` diferente: esse é o nosso **Monitor**, rodando isolado em outra CPU para não atrapalhar os cálculos.
- Os processos que dividem o **mesmo `PSR`** são as execuções intensivas competindo pela CPU de alvo (a carga original em `base-lidiano.py` e o nosso _Worker_ em `main.py`).
- A linha onde as colunas **`PRI`** (Prioridade) e **`NI`** (Nice) ficam variando de valor em tempo intermitente reflete perfeitamente a nossa versão otimizada sendo ajustada (_dinamicamente_) pelo monitor ao longo do tempo.

---

## 🔍 Entendendo o Funcionamento Interno (`main.py`)

A ideia mestre do `main.py` foi escrita respeitando o paradigma Produtor/Observador (ou Worker/Monitor). Enquanto um sub-processo tem a finalidade **única e bruta** de executar as iterações pesadas em loop, nosso processo _Worker Pai_ atinge a função exclusiva de vigiar se o _Worker Filho_ está adiantado ou atrasado — corrigindo em tempo real pelo Kernel.

Cada etapa detalhada do nosso principal arquivo acompanha os blocos de trechos de códigos a seguir:

### 1. Memória Compartilhada e Início Paralelo

Ao rodarmos o projeto como script principal na chamada do terminal, ele configura os parâmetros e reserva uma área da memória para que um subprocesso avise ao Processo Principal onde o cálculo atual se encontra. Sem conciliar uma _"Shared Memory"_ (`multiprocessing.Value`), o Monitor jamais veria quantos loops o trabalhador executou, já que as memórias de "subprocessos" nativos não colidem ou vazam de uma instância pra outra no Python.

```python
if __name__ == "__main__":
    # Leitura inicial das variáveis de ambiente ou instanciar defauts
    valor_target = int(os.getenv("VALOR_TARGET", "990000000"))
    time_target = float(os.getenv("TIME_TARGET", "60"))

    # Criamos o ponteiro L (Long integer) para a variável na Shared Memory iniciada como '0'
    progresso = multiprocessing.Value('L', 0)

    # Abstrai a "funcao" fútil pesada no segundo núcleo de software e roda independentemente
    p_trabalho = multiprocessing.Process(target=funcao, args=(valor_target, progresso))
    p_trabalho.start()
```

### 2. A Carga de Trabalho Pesada (`funcao`)

A função que dita os testes (`funcao`) possui uma alteração muito engenhosa para contornar problemas de _Overhead_ no repasse da Informação de Processo do seu Kernel.
Se informássemos a variável _progresso_compartilhado_ de UM EM UM salto individual do iterador, gastaríamos quase 50% de desempenho apenas ativando travas (Locks) de escrita, deixando ela devagar. Por isso reportamos e destravamos essa memória apenas a cada pico de tempo.

```python
def funcao(valor_target, progresso_compartilhado):
    start_work = time.time()
    for i in range(valor_target + 1):
        # Para evitar enchentes e gargalos de Locks com o núcleo principal: O update ocorre apenas a cada cota de Meio Milhão
        if i % 500000 == 0:
            progresso_compartilhado.value = i

        # Linha de cálculo Fútil que força a carga à Unidade Central (ALU)
        _ = i * i

    # Fim da execução limpa
    progresso_compartilhado.value = valor_target
```

**Por que atualizar apenas a cada 500.000 iterações?**

Cada acesso à memória compartilhada exige um **Lock** (sincronização do sistema operacional). Se atualizássemos a cada iteração, dos 990 milhões de ciclos, ~99,9% do tempo seria gasto apenas sincronizando locks, perdendo metade do desempenho. Atualizando a cada 500k reduzimos para apenas ~1.980 locks, mantendo precisão suficiente (a cada 100ms, o monitor verifica ~1,65 milhões de iterações e recebe 3-4 atualizações), sem desperdiçar CPU.

### 3. O Monitor e Motor de Equilíbrio (`monitor`)

Nosso monitor roda no Processo Pai num _Polling While Loop_. Ele captura o tempo decorrido até aquele milésimo comparado ao andamento anotado até os últimos passos registrados ali, aplicando assim o fator de cálculo percentual que gerará nossa diferença (`diferenca`).

A equação reflete de modo óbvio:

- Se estamos na marca de 15 Segundos Decorridos (Temos que totalizar e finalizar em 60s) = Nossa **Porcentagem de Tempo (perc_tempo) é 25%**
- Se o Ponto flutuante avisado pelas repetições mostra que o loop está em 300 Milhões (Dentro de 1 Bilhão de chamadas originais) = Nosso **Trabalho está em 30%**
- A `diferenca` então nos diz: `100 * (30% - 25%)` -> **+5% (Nesse contexto, nós estamos trabalhando Rápido Demais - precisamos acalmar a fila para fechar exatamente cravados aos 60s)**.

```python
        # Extrair e alinhar as taxas relativas
        perc_tempo = (elapsed / time_target) * 100
        perc_trabalho = (atual_iter / valor_target) * 100
        diferenca = perc_trabalho - perc_tempo
```

Quando caímos neste caso, o `renice` é ajustado nos blocos abaixo e ativado no sub-processo via terminal pelo Python:

```python
                if diferenca >= threshold: # Limiar tolerável (1% etc)
                    if current_nice < 19:
                        new_nice = current_nice + 1
                        msg = f"ADIANTADO {diferenca:.2f}%. Aumentando Nice: {current_nice} -> {new_nice}"

                elif diferenca <= -threshold:
                    if current_nice > -20:
                        new_nice = current_nice - 1
                        msg = f"ATRASADO {diferenca:.2f}%. Diminuindo Nice: {current_nice} -> {new_nice}"
```

**Regras do Escalonador de Prioridade:**
Para o sistema operacional (sob a semântica da prioridade de gentileza "_Nice_"), ele mapeia limites que englobam a base **-20 (Agressividade e Máxima Prioridade)** aos fundos de **+19 (Muito gentil, aguarde os recursos, atrasando a lógica em favor do SO)**.
Conforme as lógicas balançam negativamente (Atrasos reais), empurramos um _nice_ violento (-1 até o limite de piso em -20). Se caminharmos acima da pressa esperada sem motivo, incrementamos e cedemos tempo na fila aguardando mais até alcançar +19 (para retardar os acúmulos).

---

## 🎯 Conclusão

Esta atividade demonstra, na prática, como é possível construir uma ponte robusta entre um aplicativo de nível de usuário (nosso script Python) e o nível de núcleo de um sistema operacional. Em resumo, os principais aprendizados foram:

1. **Isolamento de CPU (`taskset`):** Vimos como é vital fixar cargas de trabalho para garantir que decisões métricas não sejam falseadas pelos ruídos do escalonador padrão alternando núcleos.
2. **Memória Compartilhada e Redução de Overhead Locks:** Entendemos que travar recursos é muito "caro" em sistemas computacionais. Compartilhar de forma seletiva (a cada 500mil loops ao invés de a cada 1) protege 99% da performance e fornece amostragem suficiente para a fiscalização.(É o assunto da nossa proxima atividade)
3. **Padrão Worker / Monitor Dinâmico:** Implementar a lógica de ter quem Trabalha (Gerador do Cálculo) e um Agente Auditor (Monitor) garante que ajustes na prioridade do hardware sejam aplicados a quente (live).
4. **Política de _Nice/Renice_ Exata:** Com o refinamento feito na taxa percentual (Progresso Trabalhado X Tempo Esvaído), manipulamos matematicamente os graus entre -20 (Máxima Atenção do Processador) e +19 (Sem Pressa e Complacente), fazendo o processo atrasar ou adiantar com uma margem de precisão milimétrica até a cravada de tempo limite esperada.

Essa prova de conceito atesta plenamente que com arquitetura assíncrona, inteligência de bloqueio de variáveis e manipulação adequada de sistemas OS, conseguimos forçar o ecossistema a obedecer a métricas estritas com extrema flexibilidade.
