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

## 🔍 Linha de Raciocínio e Funcionamento Interno

Dado o objetivo da atividade (terminar a carga de trabalho em aproximadamente 60 segundos controlando a prioridade do processo), nos deparamos com uma série de desafios técnicos de desempenho e concorrência. A arquitetura de solução foi desenvolvida seguindo 7 passos de raciocínio fundamental:

### 1. Calibragem do Valor Target

A premissa básica é colocar um `VALOR_TARGET` tal que a função que faz o trabalho pesado consiga terminar o mais próximo possível de 60s em seu ritmo normal. Esse valor será nosso marco matemático para toda a lógica subsequente.

### 2. Monitoramento e Diferenças Relativas

O coração da atividade é alterar o `nice` do processo de carga, mas como saber se devemos alterar positivamente (ser mais solidário e dar espaço) ou negativamente (ser egoísta e puxar a carga para si)?
Resolvemos isso com uma função de **Monitor**. Ela verifica o progresso do tempo (decorrido vs limite) e o progresso do trabalho (iteração vs target) em formato percentual. Calculando a diferença entre as duas porcentagens, o monitor decide exatamente para onde direcionar e regular on $\pm$ `nice`.

### 3. Isolamento do Monitor

A função de carga precisa ser altamente eficiente para ficar o mais parecida possível com a base teórica; adicionar qualquer "if" de tempo dentro dela iria aumentar drasticamente as verificações por segundo e prejudicar o desempenho. Pensando nisso, extraímos toda a computação lógica da função principal, e definimos que o Monitor deve ser executado obrigatoriamente **em uma CPU totalmente diferente** do programa da carga (através do comando `taskset`), não prejudicando a performance crua da métrica.

### 4. Memória Compartilhada

Com processos distintos rodando paralelos, surge outro problema: como o monitor irá saber qual o valor da iteração atual para fazer os cálculos isolados?
Para isso, foi necessário criar uma **variável compartilhada** (`multiprocessing.Value`) entre os processos. A função de carga subscreve e reporta seu progresso nesta memória, o que permite o Monitor ler seu valor ao vivo e tomar as decisões corretamente, calculando o `diferenca`.

### 5. O Impacto Atômico do Compartilhamento

O passo anterior muda levemente a função de sobrecarga original (adicionando a linha `progresso_compartilhado.value = i`). Fica impossível comunicar sem informar iterativamente. Mas isso afeta o desempenho da função? Sim. Acompanhe a dissecação usando a biblioteca `dis` do Python em Nível Atômico (_Bytecode_):

**A antiga função sem a linha:**

```text
  5           RESUME                   0
  7           LOAD_GLOBAL              1 (range + NULL)
              LOAD_FAST                0 (valor_target)
...
      L1:     FOR_ITER                 7 (to L2)
              STORE_FAST               2 (i)
  9           LOAD_FAST_LOAD_FAST     34 (i, i)
              BINARY_OP                5 (*)
...
```

**A função com atualização de IPC:**

```text
  5           RESUME                   0
  7           LOAD_GLOBAL              1 (range + NULL)
              LOAD_FAST                0 (valor_target)
...
      L1:     FOR_ITER                13 (to L2)
              STORE_FAST               2 (i)
  8           LOAD_FAST_LOAD_FAST     33 (i, progresso_compartilhado)
              STORE_ATTR               1 (value)
  9           LOAD_FAST_LOAD_FAST     34 (i, i)
...
```

Essa chamada microcópica do `STORE_ATTR` emite instruções adicionais aos iteradores, o que infere um acréscimo temporal natural estimado em cerca de 12.5%(baseasdo em números de linhas a mais). Como o valor target é gigantesco, qualquer pequena instrução dentro do laço altera o final de forma brutal.

### 6. Destravando Gargalos (Locks)

Ao pensar que somente as duas linhas lógicas acrescentariam 12.5% de ônus, a constatação prática surpreendeu com aproximadamente **50% de lentidão a mais**(baseado em teste práticos) comparado com os laços originais que não compartilhavam itens de memória.
O culpado? O Python embute um bloqueador de acesso (_Lock_) silencioso padrão para garantir que memórias IPC não apresentem leitura ou corrupção cruzada durante a concorrência de núcleo. Esses Locks automáticos sugavam a rapidez do nosso processo pela raiz.
Por sorte, como neste caso não corremos risco de _Race Conditions_ problemáticos, usamos a funcionalidade mágica nativa de desativar esse lock, mudando a assinatura do recurso compartilhado:

```python
progresso = multiprocessing.Value('L', 0, lock=False)
```

Isso desidratou a perda gerada pelos semáforos e recuperou o desempenho, baixando novamente a defasagem para uma média aceitável de 20%.

### 7. Realizando Competição Plena (A Disputa)

Por fim, fica ainda um último impedimento: De que adianta estourar negativamente (dar maior solidariedade, p. ex. um _nice_ entre 0 e 19) se não há tráfego nenhum naquele pino da CPU? Concorrendo com espaço _em branco_, a CPU não vai escalonar ninguém na frente do nosso processamento alvo.
Para materializar as concorrências que darão sentido à troca de repriorização, chamamos o `init.sh` de modo a iniciar, juntamente e propositalmente na **MESMA CPU**, a função do professor (base). Quando o nice abaixar, o código do professor engolirá o processamento e nosso alvo diminuirá sua velocidade temporariamente.

---

## 📊 Arquitetura de Priorização On-the-Fly

A representação a seguir (em texto simples) ilustra como ocorre a distribuição física e a comunicação dos processos, provando como garantimos não haver conflitos de processamento do monitor contra os trabalhadores.

```text
+-----------------------------------------------------------------------+
|                       SISTEMA OPERACIONAL (OS)                        |
+-----------------------------------------------------------------------+

         [ CPU #1 ]                                [ CPU #0 ]
   Monitoramento Contínuo                     Competição de Carga

 +------------------------+               +------------------------+
 | Processo Monitor (Pai) |               | Script Base (Oponente) |
 | (Calcula Dif de Tempo) |               | (Nice Estático: 0)     |
 +-----------+------------+               +-----------+------------+
             |                                        ^  (Competem
             | (Lê estado a                           v   pelo núcleo)
             v  cada X segs)              +------------------------+
 [ Memória IPC Lock-Free  ] <---(Avisa)---| Nosso Worker (Filho)   |
 [ progresso_compartilhado]               | (Nice Dinâmico: ±20)   |
             |                            +-----------+------------+
             |                                        ^
             +----------(Aplica comando 'renice')-----+
```

**Resumo Visual do Ciclo:**

1. **Ambiente Hostil (CPU 0):** Abriga os dois processos de carga extrema. Eles estão disputando 100% daquele núcleo ativamente.
2. **Monitoramento Isolado (CPU 1):** O nosso "Pai" (Monitor) fica reservado do lado de fora da arena apenas coletando dados, dessa forma não perde velocidade pelos processamentos matemáticos.
3. **Leitura Ágil (Shared Memory):** O nosso worker relata seu crescimento (ex.: "loop #3500") pra variável de memória.
4. **Manipulação "On-the-Fly" (Renice):** O Monitor descobre a defasagem (ex.: "estAMOS ADIANTADOS em 5%"). Dali mesmo atira um comando via Shell limitando/aumentando o nível social do nosso worker na disputa pela **CPU 0**. Isso faz o oponente roubar mais ou menos espaço de máquina no tempo seguinte, regulando em tempo real o momento de linha de chegada.
