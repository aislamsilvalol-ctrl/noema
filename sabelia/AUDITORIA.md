# Auditoria técnica — Sabelia

**Veredito: a claim se sustenta pela metade, e a metade que você acha mais forte é a
que cai. "Melhor em ordenação" é falso — uma regressão logística de 18 features ganha
por 0,10 de AUC e a média de acerto por questão ganha em todas as métricas; contra os
baselines do próprio repositório a liderança é de 0,008 e cabe dentro do ruído entre
seeds. "Pior em probabilidades" é verdadeiro só para o ECE (2,1× pior que o BKT, em
5 de 5 seeds); em log loss e Brier o Sabelia é melhor que o BKT em 4 de 5. E a
comparação publicada que sustentava tudo media modelos em conjuntos de teste
diferentes.**

Auditoria executada em 2026-09-09 sobre o commit `e22636b` (HEAD).
Todos os números abaixo foram medidos rodando o código; nada foi estimado.
Scripts da auditoria em `/private/tmp/.../scratchpad/` (fora do repositório).
Nenhum arquivo do projeto foi modificado.

---

## 1. Mapeamento

### Arquivos relevantes

| Papel | Arquivo |
|---|---|
| Modelo candidato | [`sabelia/models/neural.py`](sabelia/models/neural.py) (`Sabelia`, linhas 155-238) |
| Baseline neural | mesma unidade, `DKT` (linhas 126-149) |
| Baselines clássicos | [`sabelia/models/baselines.py`](sabelia/models/baselines.py) — `GlobalMean`, `ConceptMean`, `MasteryHeuristic`, `PFA`, `BKT`, `DAS3H` |
| Modelo de esquecimento | [`sabelia/memory/forgetting.py`](sabelia/memory/forgetting.py) |
| Blend | [`sabelia/models/stacking.py`](sabelia/models/stacking.py) |
| Treino | [`sabelia/training/trainer.py`](sabelia/training/trainer.py) |
| Avaliação | [`sabelia/evaluation/metrics.py`](sabelia/evaluation/metrics.py) |
| Benchmark | [`sabelia/benchmarks.py`](sabelia/benchmarks.py) |
| Features / split | [`sabelia/features/sequences.py`](sabelia/features/sequences.py) |
| Adaptadores de dados | [`sabelia/data/adapters.py`](sabelia/data/adapters.py) |
| Resultados publicados | [`benchmarks/README.md`](benchmarks/README.md), [`TECHNICAL_REPORT.md`](TECHNICAL_REPORT.md), [`README.md`](README.md), [`MODEL_CARD.md`](MODEL_CARD.md) |

### Arquitetura real

Entrada: sequências por aluno, em ordem temporal ([`sequences.py:150`](sabelia/features/sequences.py:150)).

- **Embedding de interação** ([`neural.py:198-208`](sabelia/models/neural.py:198)) — conceito + resultado
  + item + MLP sobre log(tempo de resposta) + dicas. Soma, `d_model=64`.
- **Encoder causal** ([`neural.py:219-220`](sabelia/models/neural.py:219)) — `TransformerEncoder`,
  1 camada, 4 cabeças, `norm_first=True`, máscara `triu(diagonal=1)`.
- **Query** ([`neural.py:222-225`](sabelia/models/neural.py:222)) — `concept + exposure(prior_seen) + pos`,
  mais o MLP de tempo se `use_time`. **Sem o embedding de item.**
- **Atenção cruzada estritamente causal** ([`neural.py:229-233`](sabelia/models/neural.py:229)) —
  máscara `triu(diagonal=0)` sobre a memória, mais um token de início aprendido.
- **Portão de esquecimento** ([`neural.py:234-237`](sabelia/models/neural.py:234)) —
  `exp(−softplus(r_c)·gap_c)` multiplicando o vetor atendido.
- **Cabeça** ([`neural.py:189-195`](sabelia/models/neural.py:189)) — `LayerNorm → Linear(2d→d) → GELU → Dropout → Linear(d→1)`, saída em logit.
- **Loss**: `binary_cross_entropy_with_logits` mascarada ([`neural.py:409-411`](sabelia/models/neural.py:409)).
- **Otimizador**: AdamW, lr 1e-3, weight decay 1e-4, clip de gradiente 1.0
  ([`trainer.py:77`](sabelia/training/trainer.py:77), [`configs/train/sabelia.yaml`](configs/train/sabelia.yaml)).
- **Saída**: sigmoide do logit dividido por uma temperatura ajustada na validação
  ([`neural.py:292`](sabelia/models/neural.py:292), [`neural.py:357-381`](sabelia/models/neural.py:357)).
- **Incerteza**: MC dropout, desvio padrão entre passes ([`neural.py:283-299`](sabelia/models/neural.py:283)).

### Dados e alvo

**Alvo**: `correct` ∈ {0,1} — o aluno acerta o próximo item, dado só o que veio antes.

| Dataset | Origem | Verificado nesta auditoria |
|---|---|---|
| EdNet-KT1 | 6.000 alunos sorteados por hash de 784.309 ([`adapters.py:143`](sabelia/data/adapters.py:143)) | 5.792 alunos, 679.012 respostas, 142 conceitos, 12.056 questões, base 0,6503 — **bate com o documentado** |
| Duolingo HLR 300k | primeiras 300.000 linhas de Settles & Meeder ([`adapters.py:230`](sabelia/data/adapters.py:230)) | 6.869 alunos, 299.615 eventos, 8.649 lexemas, base 0,8384 |
| Duolingo HLR 4% | amostra estável de alunos do arquivo inteiro | 4.463 alunos, 512.091 eventos, base 0,8400 |
| Sintético | simulador Rasch com esquecimento ([`simulation/simulator.py`](sabelia/simulation/simulator.py)) | determinístico por seed |

---

## 2. Vazamento de dados

### O que **não** é vazamento (verificado rodando)

| Verificação | Resultado |
|---|---|
| Vazamento de rótulo na arquitetura | **Nenhum.** Sonda estrutural: inverter `y[t]` e medir `\|ΔP(t)\|` → **0,000e+00** em Sabelia e DKT. `\|ΔP(>t)\|` > 0, confirmando que o passado é usado. |
| Aluno em dois splits | **Zero.** treino∩teste = 0, treino∩val = 0, val∩teste = 0 (EdNet e Duolingo). |
| Mesmo aluno sob ids diferentes | **Zero** sequências idênticas duplicadas. |
| Feature derivada do alvo com estatística global | **Nenhuma.** `ConceptMean`, `PFA`, `DAS3H`, `BKT` são ajustados só em `train_ds` ([`benchmarks.py:87`](sabelia/benchmarks.py:87)). `prior_seen`/`prior_correct` são incrementados **depois** de gravar a linha ([`sequences.py:201-202`](sabelia/features/sequences.py:201)). Nenhuma normalização global. |
| Tempo de resposta concorrente | Usado só na **memória** (`response_now`, [`neural.py:205`](sabelia/models/neural.py:205)), nunca na query. Correto. |

### O split é temporal?

**Não. É aleatório por aluno** (hash SHA-256 de `student_id`+seed, 70/10/20 —
[`sequences.py:227-244`](sabelia/features/sequences.py:227)). Medido no EdNet:

```
treino  2017-04-26 .. 2019-12-02
val     2017-07-11 .. 2019-12-02
teste   2017-07-06 .. 2019-12-02
```

As janelas se sobrepõem por completo. Para knowledge tracing esse é o protocolo
padrão da literatura (é mais difícil que dividir dentro do aluno), então **não
invalida** os resultados — mas eles medem "aluno novo, mesmo período", não
"o futuro". Isso deve estar dito em qualquer claim de produto.

### Duplicatas entre treino e teste (números exatos)

| Dataset | eventos de teste com vetor de features idêntico no treino | idem com o mesmo rótulo | duplicatas exatas dentro do teste | eventos por vetor distinto |
|---|---|---|---|---|
| EdNet-KT1 (seed 0) | **11.130 / 125.116 (8,9 %)** | 9.215 (7,4 %) | 3.633 (2,9 %) | 1,0 |
| Duolingo 300k (seed 0) | **42.266 / 60.670 (69,7 %)** | 40.947 (67,5 %) | **32.353 (53,3 %)** | 2,3 |
| Duolingo 4% (seed 0) | 44.478 / 92.938 (47,9 %) | — | — | 1,6 |

No EdNet isso é colisão natural e desprezível. **No Duolingo é estrutural**: 65 % dos
eventos de teste são a primeira tentativa naquele lexema, sem tempo de resposta e sem
dicas, então o vetor de features é essencialmente só o id do lexema. O conjunto de
teste de 60.670 eventos tem **26.379 vetores distintos**. Qualquer barra de erro
calculada como se fossem 60.670 observações independentes é otimista.

### Agrupamento

O split é por aluno, então não há o vazamento clássico de grupo. **Mas o vocabulário
é construído sobre o dataset inteiro antes do split** ([`sequences.py:161`](sabelia/features/sequences.py:161),
chamado de `adapters.py` antes de `split_by_student`). É transdutivo: não vaza rótulo,
mas os embeddings de item existem para questões que só aparecem no teste. Impacto medido:
46 itens (0,05 % dos eventos) no EdNet, 577 (1,25 %) no Duolingo. Desprezível.

---

## 3. Metodologia de avaliação

### Qual métrica sustenta a claim

`auc()` em [`metrics.py:24-42`](sabelia/evaluation/metrics.py:24) — Mann-Whitney U com
tratamento de empates por rank médio. **A implementação está correta**: testada contra
força bruta O(n²) em 200 casos aleatórios com empates forçados, **200/200 idênticos**
até 1e-12. Não há NDCG, MAP nem Spearman no repositório; a claim de ordenação é AUC.

### Baselines

Sete, todos no repositório: `global_mean`, `concept_mean`, `mastery_heuristic`, `PFA`,
`DAS3H`, `BKT`, `half_life`, mais `DKT`. **Nenhuma comparação com modelo publicado
externo foi feita** — nem SAKT, nem AKT, nem SAINT+, nem pyKT. A claim de ser melhor
que "qualquer coisa do mercado" não tem evidência nenhuma no repositório, nem a favor
nem contra: nunca foi testada.

O próprio [`RESEARCH.md:40-45`](RESEARCH.md:40) registra que modelos publicados ficam
em 0,70–0,79 de AUC no ASSISTments 2009 sob a avaliação do pyKT. O Sabelia mede
0,63–0,66 no EdNet. Não são o mesmo dataset, então não é uma refutação direta — mas
é o único ponto de referência externo no repositório e ele aponta para baixo.

**Fraqueza dos baselines** (achado material): nenhum dos sete modela **habilidade do
aluno entre conceitos**. `PFA` usa só contagens no mesmo conceito
([`baselines.py:142-146`](sabelia/models/baselines.py:142)), `DAS3H` idem por janela
temporal ([`baselines.py:335-354`](sabelia/models/baselines.py:335)), `BKT` é um HMM
por conceito, `ConceptMean` é a média da tag. **E nenhum estima dificuldade por
questão** — só por tag (142 tags contra 12.056 questões no EdNet). São dois dos
preditores mais fortes da tarefa, e a família inteira de baselines é cega para os dois.


### As métricas foram escolhidas depois de ver os resultados?

**Não.** O critério de saída da V1 (AUC **e** log loss contra o melhor baseline logístico)
está escrito em [`ROADMAP.md:26`](ROADMAP.md:26) e o repositório o aplica contra si mesmo
— declara `not met`. Isso é a favor da honestidade do processo. O que aconteceu foi
o oposto de *p-hacking*: o critério ficou, e a medição contra ele estava errada.

### Tamanho do teste e intervalo de confiança (bootstrap, 1000 reamostragens)

EdNet-KT1, seed 0, n = 125.116 eventos de **1.138 alunos**:

| modelo | AUC | IC 95% agrupado por aluno | IC 95% iid por evento |
|---|---|---|---|
| **gradient boosting** (auditoria) | **0,7441** | [0,7363; 0,7520] | [0,7415; 0,7469] |
| **regressão logística** (auditoria) | **0,7308** | [0,7232; 0,7385] | [0,7280; 0,7334] |
| dkt | 0,6372 | [0,6263; 0,6488] | [0,6340; 0,6403] |
| bkt | 0,6333 | [0,6229; 0,6437] | [0,6302; 0,6367] |
| das3h | 0,6323 | [0,6220; 0,6428] | [0,6292; 0,6355] |
| **sabelia** | **0,6295** | **[0,6169; 0,6415]** | [0,6262; 0,6329] |

Duas leituras:

1. **O IC correto é o agrupado por aluno** (±0,012), não o iid por evento (±0,003).
   Eventos do mesmo aluno não são independentes; reamostrar eventos finge um n
   quatro vezes maior do que o efetivo. O repositório não calcula IC nenhum.
2. **O IC do Sabelia cruza o do BKT, do DAS3H e do DKT.** Num único seed, a
   diferença entre esses quatro modelos é ruído. Qualquer afirmação de ordenação
   entre eles precisa de mais seeds — e é exatamente o que a seção 6 mostra.

---

## 4. Calibração

### Discriminação e calibração são coisas separadas

A claim mistura as duas. Elas se separam assim: **AUC só depende da ordem**;
Brier, log loss e ECE dependem do valor. Uma transformação monótona
(temperatura, Platt) muda os valores e **não muda a ordem**. Verificado
numericamente abaixo. Ter AUC alta e calibração ruim é o comportamento
esperado de uma rede neural — não é um mistério, e o repositório já sabia disso
([`neural.py:357`](sabelia/models/neural.py:357) aplica temperature scaling).

### Métricas de calibração no teste (EdNet, seed 0, n = 125.116)

| modelo | Brier | log loss | ECE (10 bins iguais) | MCE (idem) | ECE (10 bins massa igual) | MCE (idem) | AUC |
|---|---|---|---|---|---|---|---|
| gradient boosting | **0,1883** | **0,5584** | 0,0233 | 0,0358 | 0,0230 | 0,0400 | **0,7441** |
| regressão logística | 0,1931 | 0,5693 | 0,0211 | 0,0940 | 0,0208 | 0,0693 | 0,7308 |
| dkt | 0,2135 | 0,6169 | 0,0218 | 0,1804 | 0,0205 | 0,0351 | 0,6372 |
| dkt sem temperatura | 0,2135 | 0,6172 | 0,0174 | 0,1874 | 0,0182 | 0,0537 | 0,6372 |
| bkt | 0,2145 | 0,6190 | **0,0096** | 0,8207 | **0,0094** | 0,0175 | 0,6333 |
| das3h | 0,2155 | 0,6208 | **0,0064** | 0,8257 | **0,0082** | 0,0158 | 0,6323 |
| **sabelia** | 0,2148 | 0,6198 | **0,0249** | 0,0605 | **0,0247** | 0,0435 | 0,6295 |
| sabelia sem temperatura | 0,2148 | 0,6199 | 0,0264 | 0,0575 | 0,0263 | 0,0436 | 0,6295 |
| pfa | 0,2177 | 0,6270 | 0,0195 | 0,1959 | 0,0218 | 0,0594 | 0,6201 |
| mastery_heuristic | 0,2222 | 0,6368 | 0,0536 | 0,2645 | 0,0528 | 0,1317 | 0,6153 |
| concept_mean | 0,2203 | 0,6314 | 0,0035 | 0,1477 | 0,0045 | 0,0119 | 0,5984 |
| global_mean | 0,2266 | 0,6456 | 0,0009 | 0,0009 | 0,0009 | 0,0009 | 0,5000 |

Três observações:

- **A segunda metade da claim se sustenta neste seed.** O Sabelia é pior calibrado
  que o BKT: ECE 0,0249 contra 0,0096 (2,6×), e log loss 0,6198 contra 0,6190.
- **O MCE de largura igual é enganoso.** BKT tem MCE 0,82 e DAS3H 0,83 porque um
  bin quase vazio no extremo puxa o máximo. Com bins de massa igual eles caem para
  0,0175 e 0,0158 — ainda **melhores** que os 0,0435 do Sabelia, então a conclusão
  não muda, mas o número de largura igual não deve ser citado.
- **O temperature scaling do Sabelia é praticamente inócuo.** T ajustado = 1,020;
  ECE vai de 0,0264 para 0,0249 e o log loss de 0,6199 para 0,6198. O "caminho de
  calibração" a que os documentos creditam parte da vantagem não faz nada aqui.

### Recalibração (ajustada na validação, aplicada no teste)

**Sabelia (a partir do logit sem temperatura):**

| calibração | Brier | log loss | ECE | AUC |
|---|---|---|---|---|
| nenhuma | 0,2148 | 0,6199 | 0,0264 | 0,62954588 |
| temperatura (T = 1,006) | 0,2149 | 0,6200 | 0,0271 | 0,62954588 |
| Platt (a = 0,896, b = +0,091) | 0,2144 | 0,6191 | 0,0193 | 0,62954588 |
| isotônica | 0,2144 | 0,6193 | **0,0172** | 0,62913924 |

**A AUC não muda** com temperatura nem com Platt: 0,62954588 nos três, idêntico
até a 8ª casa. Confirma que transformação monótona preserva a ordem, como pedido.
A isotônica muda na 4ª casa (0,62913924, −0,0004) porque o *pool-adjacent-violators*
cria empates entre pontos antes distintos — é a única exceção e ela é conhecida.

**Isso resolve?** Não. A melhor recalibração leva o ECE do Sabelia a 0,0172, ainda
**79 % pior** que os 0,0096 do BKT sem calibração nenhuma. E o log loss recalibrado
(0,6191) continua acima do BKT (0,6190).

**E o BKT?** Recalibrar o BKT o **piora** (ECE 0,0096 → 0,0213): ele já está
calibrado, e o ajuste na validação só adiciona ruído.

**O ponto decisivo.** O gradient boosting com isotônica:

| modelo | AUC | log loss | Brier | ECE |
|---|---|---|---|---|
| **gbm + isotônica** | **0,7438** | **0,5567** | **0,1878** | **0,0076** |
| bkt (sem calibração) | 0,6333 | 0,6190 | 0,2145 | 0,0096 |
| sabelia (melhor calibração) | 0,6291 | 0,6193 | 0,2144 | 0,0172 |

Ele ganha do BKT **nas quatro métricas ao mesmo tempo**. Não existe o trade-off que
a claim descreve: não é que o modelo "troca calibração por ordenação". Ele
simplesmente perde nas duas.

Diagrama de confiabilidade: [`auditoria_confiabilidade_ednet.png`](auditoria_confiabilidade_ednet.png).

---

## 5. Baseline honesto

Implementados para esta auditoria, no **mesmo split**, com **features estritamente
causais** (nenhuma usa informação do evento t nem estatística global — a codificação
alvo de conceito e item é ajustada só no treino):

`concept`, `item` (codificação alvo, k=20, ajustada no treino), `log_gap`,
`log_gap_concept`, contadores no conceito (vistos, certos, errados, taxa suavizada),
contadores do aluno (posição, acertos acumulados, taxa suavizada), resultado anterior,
último resultado no conceito, sequência de acertos no conceito, tempo de resposta e
dicas **do evento anterior**, e os logs desses contadores. 18 colunas.

- **Regressão logística**: `LogisticRegression(C=1.0)` sobre features padronizadas.
- **Gradient boosting**: `HistGradientBoostingClassifier` (max_iter 500, lr 0,05,
  63 folhas, early stopping interno em 10 % do treino). *LightGBM foi tentado e
  falhou: `OSError: Library not loaded: '@rpath/libomp.dylib'` — o Mac não tem
  `libomp`. O `HistGradientBoosting` do sklearn traz o próprio OpenMP e é o
  substituto direto.*

### Tabela comparativa — EdNet-KT1, seed 0, mesmos 125.116 eventos

| modelo | AUC | log loss | Brier | ECE |
|---|---|---|---|---|
| **gradient boosting + isotônica** | **0,7438** | **0,5567** | **0,1878** | **0,0076** |
| gradient boosting | 0,7441 | 0,5584 | 0,1883 | 0,0233 |
| regressão logística | 0,7308 | 0,5693 | 0,1931 | 0,0211 |
| **item_mean** (taxa de acerto da questão no treino) | **0,7081** | **0,5815** | **0,1983** | **0,0088** |
| dkt | 0,6372 | 0,6169 | 0,2135 | 0,0218 |
| bkt | 0,6333 | 0,6190 | 0,2145 | 0,0096 |
| das3h | 0,6323 | 0,6208 | 0,2155 | 0,0064 |
| **sabelia** | **0,6295** | **0,6198** | **0,2148** | **0,0249** |
| pfa | 0,6201 | 0,6270 | 0,2177 | 0,0195 |
| mastery_heuristic | 0,6153 | 0,6368 | 0,2222 | 0,0536 |
| concept_mean | 0,5984 | 0,6314 | 0,2203 | 0,0035 |
| global_mean | 0,5000 | 0,6456 | 0,2266 | 0,0009 |

**Sem rodeios: os dois baselines ganham do Sabelia, e por muito.** +0,101 de AUC
para a regressão logística, +0,115 para o gradient boosting. E **`item_mean` —
um número por questão, sem aluno, sem sequência, sem tempo, três linhas de numpy —
ganha nas quatro métricas** (+0,079 AUC, melhor log loss, melhor Brier, melhor ECE).

### De onde vem a diferença

Ablação de grupos de features na regressão logística (mesmo split, seed 0):

| features | AUC |
|---|---|
| todas | 0,7308 |
| **só identidade** (dificuldade de conceito + questão, estimada no treino) | **0,7067** |
| sem identidade | 0,6381 |
| só contadores no conceito | 0,6112 |
| só habilidade do aluno | 0,6202 |
| só resultado anterior | 0,5571 |
| só tempo | 0,5175 |

**Praticamente toda a vantagem é dificuldade da questão.** Sem ela, a regressão cai
para 0,6381 — a mesma faixa dos modelos de KT do repositório.

### A causa no código

[`neural.py:222`](sabelia/models/neural.py:222):

```python
q = self.concept(b.concept) + self.exposure(b.prior_seen.unsqueeze(-1)) + self.pos(pos)
```

A *query* — o vetor que representa "a questão que o aluno vai responder agora" — tem
conceito, contagem de exposições, posição e tempo. **Não tem o embedding de item.**
O embedding de item entra apenas em `_interaction()` ([`neural.py:204`](sabelia/models/neural.py:204)),
ou seja, só na memória, descrevendo questões já respondidas. A cabeça recebe
`[q, attended]` e nunca sabe *qual* é a questão a prever — só a tag (142 tags para
12.056 questões).

Isso explica de uma vez duas coisas que o repositório registra como mistério:

1. Por que remover o embedding de item não custa nada — ele ocupa 771k dos 862k
   parâmetros e está no lugar onde quase não serve.
2. Por que uma média por questão bate o modelo inteiro.


---

## 6. Reprodutibilidade

### Seeds e determinismo

`set_seed()` ([`neural.py:414`](sabelia/models/neural.py:414)) fixa `random`, `numpy`
e `torch`; a ordem dos lotes vem de `np.random.default_rng(cfg.seed)`
([`trainer.py:80`](sabelia/training/trainer.py:80)). Não há
`torch.use_deterministic_algorithms(True)`, mas na CPU não faz falta.

**Teste rodado**: mesmo dataset, mesmo seed, dois treinos completos.

```
repeticao 0: AUC=0.5913940000  LL=0.6902180000  T=0.76461875
repeticao 1: AUC=0.5913940000  LL=0.6902180000  T=0.76461875
max |dif| entre as duas execucoes: 0.000e+00  -> DETERMINISTICO
```

Bit a bit idêntico. **A reprodutibilidade dentro de um seed está correta.**

### Entre seeds — o problema

EdNet-KT1, **5 seeds**, código atual (scoring corrigido), AUC no teste:

| seed | n teste | sabelia | dkt | bkt | das3h | posição do sabelia |
|---|---|---|---|---|---|---|
| 0 | 125.116 | 0,6295 | 0,6372 | 0,6333 | 0,6323 | **4º de 4** |
| 1 | 129.985 | 0,6572 | 0,6486 | 0,6442 | 0,6337 | 1º |
| 2 | 129.411 | 0,6435 | 0,6334 | 0,6288 | 0,6243 | 1º |
| 3 | 127.028 | 0,6516 | 0,6431 | 0,6427 | 0,6402 | 1º |
| 4 | 115.067 | 0,6525 | 0,6472 | 0,6460 | 0,6434 | 1º |
| **média ± dp** | | **0,6469 ± 0,0109** | 0,6419 ± 0,0065 | 0,6390 ± 0,0075 | 0,6348 ± 0,0074 | |

**AUC, comparação pareada por seed contra o BKT** (o teste certo — os modelos
compartilham o split dentro de um seed):

```
diferença por seed: -0,0038  +0,0130  +0,0147  +0,0089  +0,0065
média +0,0079, dp 0,0073, positiva em 4 de 5 seeds
t pareado = 2,42, gl = 4  →  p ≈ 0,07
```

**Leitura honesta.** O Sabelia de fato ordena um pouco melhor que o BKT na média dos
5 seeds. Mas: (a) a vantagem é **+0,008**, não os +0,025 publicados; (b) o desvio entre
seeds (0,0109) é **1,38× a vantagem**; (c) num dos cinco seeds ele fica em **último**
entre os quatro; (d) o IC bootstrap agrupado por aluno do seed 0 (±0,012) cobre os três
concorrentes; (e) com 5 seeds o teste pareado dá p ≈ 0,07 — não passa em 0,05.

Pelo critério do próprio pedido — "se o desvio for maior que a vantagem alegada, a claim
não se sustenta" — **não se sustenta**. E a vantagem alegada era 0,025; a real é 0,008.

A tabela publicada relata `sabelia 0,6600 ± 0,0023`
([`benchmarks/README.md:203`](benchmarks/README.md:203)). O desvio real é **4,7× maior**;
o ±0,0023 vinha do subconjunto de 40 % dos eventos, que por acaso variava menos.

### Calibração nos 5 seeds — aqui a claim precisa ser corrigida

| métrica | sabelia | bkt | quem ganha | consistência |
|---|---|---|---|---|
| **ECE** | **0,0161 ± 0,0057** | **0,0077 ± 0,0019** | **BKT, 2,1×** | **5 de 5 seeds** |
| log loss | **0,6169 ± 0,0039** | 0,6209 ± 0,0044 | **Sabelia** | 4 de 5 seeds |
| Brier | **0,2136 ± 0,0018** | 0,2154 ± 0,0020 | **Sabelia** | 4 de 5 seeds |

**A segunda metade da claim está mal enunciada.** O Sabelia é pior **calibrado** — o ECE
é 2,1× o do BKT e isso é consistente em todos os cinco seeds. Mas "pior em
probabilidades" no sentido de regra de pontuação própria é **falso**: em log loss e
Brier, que combinam discriminação e calibração, o Sabelia é melhor em 4 de 5 seeds.

O que existe é um desalinhamento local: as probabilidades estão sistematicamente
deslocadas dentro de faixas (o que o ECE mede), mas a ordenação boa o suficiente
compensa no agregado. É por isso que o Platt corrige boa parte do ECE (0,0264 → 0,0193)
sem mexer na AUC.

**Correção ao seed 0.** Na tabela do seed 0 o Sabelia tem log loss 0,6198 contra 0,6190
do BKT — pior. Esse é o único seed em que isso acontece. Reportar só ele, como faz o
[`benchmarks/README.md:218`](benchmarks/README.md:218) e o
[`MODEL_CARD.md:59`](MODEL_CARD.md:59), inverte a conclusão de log loss.

---

## 7. Problemas encontrados, por gravidade

### P1 — CRÍTICO. As tabelas publicadas comparam modelos em conjuntos de teste diferentes

**Onde**: [`sabelia/models/neural.py:301-329`](sabelia/models/neural.py:301) na versão
que gerou as tabelas (pré-`e22636b`); tabelas em
[`benchmarks/README.md:200-214`](benchmarks/README.md:200),
[`README.md:141-149`](README.md:141), [`TECHNICAL_REPORT.md:97-102`](TECHNICAL_REPORT.md:97),
[`MODEL_CARD.md:59-60`](MODEL_CARD.md:59), [`ROADMAP.md:28-31`](ROADMAP.md:28).

**O que era**: `predict_dataset` truncava toda sequência com mais de `max_len=200`
eventos, pontuando os modelos neurais apenas nos **últimos 200 eventos de cada aluno**.
Os baselines eram pontuados em todos.

**Medido**: no EdNet seed 0, 118 dos 1.138 alunos de teste têm mais de 200 eventos.
O código antigo pontuava **50.185 eventos (40,1 %)**, base 0,6007; descartava **74.931**,
base 0,6880. Os `n` e `base_rate` gravados em `runs-ednet/runs.jsonl` batem exatamente
com essa reconstrução: 50.185 / 0,5997 para `sabelia` e `dkt`, contra 125.116 / 0,653
para os baselines.

**Impacto**: **toda a evidência de que "o motor ordena melhor que qualquer baseline"
foi medida numa comparação inválida.** Corrigido, o resultado se inverte no seed 0.
Afeta as três tabelas de dados reais: EdNet (40 % dos eventos), Duolingo-300k (~4 %),
Duolingo 4 % dos alunos (39 %). O bug foi corrigido em `e22636b` (HEAD) mas
**nenhum documento foi atualizado** — todos ainda publicam os números antigos.

### P2 — CRÍTICO. A regressão logística de 18 features ganha do modelo por 0,10 de AUC

**Medido** (EdNet seed 0, mesmo split, mesmos 125.116 eventos):
regressão logística 0,7308; gradient boosting 0,7441; sabelia 0,6295.
Até `item_mean` — a taxa de acerto da questão no treino, sem aluno, sem sequência —
faz 0,7081 e ganha nas quatro métricas.

**Causa, em uma linha**: [`neural.py:222`](sabelia/models/neural.py:222) — a *query*
não inclui o embedding de item. O modelo prevê o acerto sem saber qual é a questão.
Ablação: só a identidade (conceito + questão) vale 0,7067 de AUC; sem ela, tudo cai
para 0,6381.

**Impacto**: a claim "melhor que qualquer coisa em ordenação" é falsa contra um
baseline de 20 linhas. E explica dois "mistérios" registrados no repositório: por que
remover o embedding de item (89 % dos parâmetros) não custa nada, e por que as
ablações são todas nulas.

### P3 — ALTO. O desvio entre seeds é 1,38× a vantagem sobre o BKT

Sabelia 0,6469 ± 0,0109 (5 seeds) contra BKT 0,6390 ± 0,0075. Vantagem +0,0079,
desvio 0,0109. Pareado por seed: +0,0079 ± 0,0073, positivo em 4 de 5, t = 2,42,
p ≈ 0,07. Em 1 dos 5 seeds o Sabelia fica em último entre os quatro modelos de KT.
O repositório publica ±0,0023 e uma vantagem de +0,025 — ambos medidos no subconjunto
errado de eventos.

### P4 — ALTO. O corte Duolingo-300k cobre 6 h 12 min, não "tempo real"

[`configs/datasets/duolingo-hlr-300k.yaml:7`](configs/datasets/duolingo-hlr-300k.yaml:7).
Janela medida: 2013-02-28 18:28 → 2013-03-01 00:40 (**0,26 dias**). Gap máximo entre
eventos consecutivos de um aluno: 0,179 dias. **0,00 %** dos gaps passam de 1 dia.

**Impacto**: é o dataset apresentado como "the first public dataset with real time"
([`benchmarks/README.md:49`](benchmarks/README.md:49)) e o único que a ROADMAP conta como
tendo passado nas duas metades do critério V1 ([`ROADMAP.md:28`](ROADMAP.md:28)). As
ablações nulas de tempo e esquecimento nele são **garantidas por construção**, não
evidência. A variante de histórias completas cobre 11,8 dias — a extensão total do
dataset de Settles & Meeder; **nenhuma variante do Duolingo pode medir esquecimento de
longo prazo.**

### P5 — ALTO. 69,7 % dos eventos de teste do Duolingo têm vetor idêntico no treino

53,3 % são duplicatas exatas dentro do próprio teste; 26.379 vetores distintos em
60.670 eventos. Não é vazamento de rótulo, mas o n efetivo é uma fração do nominal e
a tarefa se reduz em grande parte a decorar o lexema. O EdNet não tem esse problema
(8,9 % / 1,0 evento por vetor).

### P6 — MÉDIO. Só os modelos neurais recebem calibração

[`trainer.py:130-132`](sabelia/training/trainer.py:130) ajusta temperatura na validação
para `sabelia` e `dkt`; nenhum baseline em [`benchmarks.py:66-91`](sabelia/benchmarks.py:66)
recebe tratamento equivalente. Assimetria a favor do modelo neural nas métricas de
probabilidade — e mesmo assim o BKT ganha. (Medido: a temperatura do Sabelia é
praticamente inócua, T = 1,020, ECE 0,0264 → 0,0249.)

### P7 — MÉDIO. `sabelia-no_time` desliga tempo **e** esquecimento

[`benchmarks.py:30`](sabelia/benchmarks.py:30): `{"use_time": False, "use_forgetting": False}`.
As tabelas e o texto tratam como ablação isolada de tempo, e listam `no_time` e
`no_forgetting` lado a lado como se fossem independentes
([`benchmarks/README.md:230-233`](benchmarks/README.md:230)). Além disso `use_hints`
nunca é ablacionado, embora [`TECHNICAL_REPORT.md:49`](TECHNICAL_REPORT.md:49) o liste
como um dos interruptores.

### P8 — MÉDIO. Nenhum intervalo de confiança é calculado

[`benchmarks.py:128-139`](sabelia/benchmarks.py:128) reporta média e desvio padrão sobre
3 seeds. Não há IC, e três seeds não sustentam teste algum — o próprio repositório
reconhece isso ([`benchmarks/README.md:159`](benchmarks/README.md:159)). Medido nesta
auditoria: o IC bootstrap **agrupado por aluno** é ±0,012; o iid por evento seria
±0,003, quatro vezes menor e errado, porque eventos do mesmo aluno não são independentes.

### P9 — MÉDIO. ECE com bins de largura igual, sem alternativa

[`metrics.py:60-90`](sabelia/evaluation/metrics.py:60). Com base 0,84 (Duolingo) quase
tudo cai em um ou dois bins. E o MCE dessa forma é dominado por bins quase vazios: o
BKT aparece com MCE 0,82 que vira 0,0175 com bins de massa igual.

### P10 — BAIXO. Vocabulário construído sobre o dataset inteiro antes do split

[`sequences.py:161`](sabelia/features/sequences.py:161). Transdutivo. Não vaza rótulo.
Impacto medido: 0,05 % dos eventos de teste no EdNet, 1,25 % no Duolingo.

### P11 — BAIXO. Código morto

[`neural.py:63-64`](sabelia/models/neural.py:63): `Batch.response` e `Batch.hints`
(versões deslocadas, do evento anterior) são construídas em `make_batch` e nunca lidas
por nenhum modelo.

### P12 — BAIXO (cosmético). `log(log(...))` aninhado

[`trainer.py:113-118`](sabelia/training/trainer.py:113): `log(log(f"epoch ..."))`.
Imprime a linha e depois `None`.

---

## 8. O que NÃO consegui verificar

| Item | Por quê |
|---|---|
| **Baselines honestos nos seeds 1–4** | Rodei a regressão logística e o gradient boosting só no seed 0. A diferença é de 0,10 de AUC, nove vezes o desvio entre seeds (0,011), mas os 5 seeds não foram medidos. |
| **Re-execução do Duolingo com o scoring corrigido** | O run estava enfileirado atrás do EdNet e não chegou a começar. Sei que o bug afetou 4 % dos eventos no corte de 300k e 39 % na variante de histórias completas, mas **não medi o efeito nas métricas.** A afirmação "Sabelia ganha no Duolingo" continua **não verificada** — nem confirmada, nem refutada. |
| **Comparação com modelos publicados** (SAKT, AKT, SAINT+, pyKT) | Nenhum foi executado. O repositório também nunca os executou. A claim "melhor que qualquer coisa do mercado" **não foi testada por ninguém**, aqui ou lá. |
| **EdNet completo** (784.309 alunos) | Só a amostra de 6.000. Modelos de atenção costumam melhorar com escala; é possível que o Sabelia se saia melhor com mais dados. Não testado. |
| **Se um Sabelia com item na query fecharia a lacuna** | Diagnostiquei a causa em [`neural.py:222`](sabelia/models/neural.py:222) mas **não corrigi nem testei** — a auditoria foi explicitamente sem correções. É a primeira coisa a testar. |
| **ASSISTments 2009** | O adaptador existe; o dataset não está baixado. |
| **Qualidade da política / recomendações** | Fora do escopo da claim. Não avaliada. |
| **LightGBM** | Falhou: `OSError: Library not loaded: '@rpath/libomp.dylib'`. Substituído pelo `HistGradientBoostingClassifier` do sklearn. |

---

## 9. Resumo para copiar e colar

```
AUDITORIA SABELIA (commit e22636b) — a claim se sustenta pela metade; a metade forte cai.

1. As tabelas publicadas comparam modelos em conjuntos de teste DIFERENTES. No EdNet os
   modelos neurais eram pontuados em 50.185 eventos (os últimos 200 de cada aluno) e os
   baselines em 125.116. Confirmado pelos n gravados em runs-ednet/runs.jsonl.
2. "MELHOR EM ORDENAÇÃO" É FALSO. Uma regressão logística de 18 features causais faz
   0,7308 de AUC contra 0,6295 do Sabelia no seed 0 (+0,101); gradient boosting 0,7441;
   e a simples média de acerto por questão faz 0,7081 e ganha em AUC, log loss, Brier
   E ECE. Nada disso é "do mercado" — são baselines de 20 linhas.
3. Causa: neural.py:222 — a query não inclui o embedding de item. O modelo prevê o
   acerto sem saber qual é a questão (só a tag: 142 tags para 12.056 questões). Explica
   por que remover o item, 89% dos parâmetros, não custa nada.
4. Contra os baselines DO PRÓPRIO REPO o Sabelia lidera, mas por 0,008, não 0,025:
   0,6469 ± 0,0109 (5 seeds) vs BKT 0,6390 ± 0,0075. Pareado: +0,0079 ± 0,0073, positivo
   em 4/5 seeds, p ≈ 0,07. O desvio é 1,38x a vantagem. Em 1 de 5 seeds fica em ÚLTIMO.
5. "PIOR EM PROBABILIDADES" ESTÁ MAL ENUNCIADO. Pior CALIBRADO sim: ECE 0,0161 vs 0,0077
   do BKT, 2,1x, consistente em 5/5 seeds. Mas em log loss (0,6169 vs 0,6209) e Brier
   (0,2136 vs 0,2154) o Sabelia GANHA do BKT em 4/5 seeds. Não existe o trade-off:
   um gradient boosting com isotônica bate o BKT nas QUATRO métricas simultaneamente
   (0,7438 / 0,5567 / 0,1878 / 0,0076).
6. O corte Duolingo-300k, apresentado como "o primeiro dataset público com tempo real" e
   o único que a ROADMAP conta como aprovado no V1, cobre 6 HORAS (0,26 dias). 0% dos
   intervalos passam de 1 dia. As ablações nulas de tempo/esquecimento nele são
   garantidas por construção. Nenhuma variante do Duolingo tem mais de 12 dias.
7. Sem vazamento: causalidade verificada (|dP(t)|=0 ao inverter o rótulo em t), zero
   alunos em dois splits, AUC implementada corretamente, treino determinístico bit a
   bit, 34 testes passam. O processo de honestidade do repo é bom; falhou a medição.
8. NÃO verificado: Duolingo com o scoring corrigido, comparação com modelos publicados
   (nunca feita por ninguém, nem aqui nem no repo — "melhor que o mercado" é NÃO
   TESTADA), EdNet completo, baselines honestos fora do seed 0.
```
