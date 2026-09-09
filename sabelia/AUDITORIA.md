# Auditoria técnica — Sabelia

**Veredito: a claim está errada nas duas metades — o modelo não é o melhor em
ordenação (baselines de 20 linhas ganham dele em 8 de 8 seeds, nos dois datasets
reais) e não é pior em probabilidades (no Duolingo ele tem o melhor ECE dos dez
modelos e ganha do BKT nas quatro métricas).**

O detalhe. **Ordenação**: uma regressão logística de 18 features causais ganha
+0,0886 ± 0,0078 de AUC no EdNet (5/5 seeds, t = 25,4) e +0,0101 ± 0,0016 no Duolingo
(3/3); o gradient boosting ganha mais ainda. No EdNet até a média de acerto por
questão — três linhas de numpy — ganha nas quatro métricas. Contra os baselines *do
próprio repositório* a liderança é real no Duolingo (+0,027 a +0,058, fora do ruído)
mas some no EdNet (+0,008 contra um desvio entre seeds de 0,011). **Probabilidades**:
no Duolingo o Sabelia é o mais bem calibrado de todos (ECE 0,0101 contra 0,0381 do
BKT); no EdNet perde do BKT em ECE (0,0161 vs 0,0077, 5/5 seeds) mas ganha em log loss
e Brier em 4/5. Não existe o trade-off que a claim descreve: no EdNet um gradient
boosting com isotônica bate o BKT nas quatro métricas ao mesmo tempo. **E a comparação
publicada que sustentava tudo media modelos em conjuntos de teste diferentes.**

Auditoria executada em 2026-09-09 sobre o commit `e22636b` (HEAD).
Todos os números abaixo foram medidos rodando o código; nada foi estimado.
Dois datasets reais: **EdNet-KT1 (5 seeds)** e **Duolingo-HLR 300k (3 seeds)**, ambos
com o scoring corrigido. O harness foi validado contra a CLI do repositório — números
idênticos até a 4ª casa (§5).
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

### No Duolingo a resposta se inverte

Tudo acima é EdNet. Repeti a medição no Duolingo-300k (seed 0, n = 60.670, base 0,8438),
e a segunda metade da claim deixa de valer:

| modelo | AUC | log loss | Brier | ECE (largura igual) | ECE (massa igual) |
|---|---|---|---|---|---|
| gbm | 0,6683 | 0,4149 | 0,1262 | 0,0215 | 0,0216 |
| logreg | 0,6625 | **0,4109** | **0,1254** | 0,0166 | 0,0161 |
| **sabelia** | 0,6530 | 0,4116 | 0,1253 | **0,0089** | **0,0091** |
| dkt | 0,6328 | 0,4341 | 0,1328 | 0,0494 | 0,0485 |
| das3h | 0,5995 | 0,4283 | 0,1309 | 0,0107 | 0,0129 |
| bkt | 0,5969 | 0,4542 | 0,1364 | 0,0383 | 0,0406 |

**O Sabelia é o mais bem calibrado da tabela e o BKT é um dos piores** — o oposto exato
do EdNet. Nos três seeds: ECE 0,0101 ± 0,0016 contra 0,0381 ± 0,0010 do BKT, **3,8×
melhor**, e o Sabelia ganha do BKT nas quatro métricas simultaneamente. A afirmação
"pior que um modelo bayesiano simples em probabilidades" **não é uma propriedade do
modelo; é uma propriedade do EdNet.**

A preservação da AUC se confirma no segundo dataset: temperatura e Platt dão
0,65297109 nas três linhas, idêntico até a 8ª casa; a isotônica muda −0,0003, de novo
por empates do PAV. Aqui o temperature scaling também é inócuo (T = 1,003).

Diagramas de confiabilidade: [`auditoria_confiabilidade_ednet.png`](auditoria_confiabilidade_ednet.png)
e [`auditoria_confiabilidade_duolingo.png`](auditoria_confiabilidade_duolingo.png).

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

**Sem rodeios: os dois baselines ganham do Sabelia, e por muito.** E **`item_mean` —
um número por questão, sem aluno, sem sequência, sem tempo, três linhas de numpy —
ganha nas quatro métricas** (+0,079 AUC, melhor log loss, melhor Brier, melhor ECE).

### Os 5 seeds — não é um seed sortudo

Rodei os baselines honestos nos cinco seeds (o relatório anterior tinha só o seed 0).

| modelo | AUC | log loss | Brier | ECE |
|---|---|---|---|---|
| gradient boosting | **0,7499 ± 0,0059** | **0,5569 ± 0,0055** | **0,1881 ± 0,0024** | 0,0194 ± 0,0026 |
| regressão logística | 0,7355 ± 0,0050 | 0,5699 ± 0,0053 | 0,1935 ± 0,0022 | 0,0205 ± 0,0032 |
| **sabelia** | 0,6469 ± 0,0109 | 0,6169 ± 0,0039 | 0,2136 ± 0,0018 | 0,0161 ± 0,0057 |
| dkt | 0,6419 ± 0,0065 | 0,6191 ± 0,0040 | 0,2145 ± 0,0019 | 0,0213 ± 0,0012 |
| bkt | 0,6390 ± 0,0075 | 0,6209 ± 0,0044 | 0,2154 ± 0,0020 | **0,0077 ± 0,0019** |
| das3h | 0,6348 ± 0,0075 | 0,6245 ± 0,0051 | 0,2172 ± 0,0024 | 0,0124 ± 0,0049 |
| pfa | 0,6145 ± 0,0098 | 0,6356 ± 0,0070 | 0,2217 ± 0,0031 | 0,0267 ± 0,0106 |
| mastery_heuristic | 0,6177 ± 0,0064 | 0,6403 ± 0,0054 | 0,2238 ± 0,0024 | 0,0534 ± 0,0039 |
| concept_mean | 0,5912 ± 0,0048 | 0,6377 ± 0,0055 | 0,2232 ± 0,0026 | 0,0109 ± 0,0072 |
| global_mean | 0,5000 | 0,6503 ± 0,0053 | 0,2289 ± 0,0026 | 0,0099 ± 0,0079 |

Diferença pareada de AUC contra o Sabelia, seed a seed:

| vs sabelia | s0 | s1 | s2 | s3 | s4 | média | vence em | t (gl=4) |
|---|---|---|---|---|---|---|---|---|
| gradient boosting | +0,1146 | +0,0951 | +0,0998 | +0,1053 | +0,1003 | **+0,1030 ± 0,0074** | **5/5** | 31,1 |
| regressão logística | +0,1013 | +0,0807 | +0,0863 | +0,0899 | +0,0850 | **+0,0886 ± 0,0078** | **5/5** | 25,4 |
| dkt | +0,0076 | −0,0085 | −0,0101 | −0,0085 | −0,0053 | −0,0050 ± 0,0073 | 1/5 | −1,53 |
| bkt | +0,0037 | −0,0130 | −0,0147 | −0,0089 | −0,0065 | −0,0079 ± 0,0072 | 1/5 | −2,43 |

O seed 0, que estava no relatório anterior, é o **pior** seed do Sabelia (0,6295 contra
uma média de 0,6469). Mesmo assim a conclusão não muda de sinal em nenhum seed: os
baselines honestos ganham em **5 de 5**, por 0,089 a 0,103 de AUC, com t de 25 a 31.
Isso é doze vezes o desvio entre seeds do próprio Sabelia (0,0109). **Não há leitura
dos dados em que "melhor em ordenação" sobreviva.**

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

### O experimento natural: o mesmo modelo no Duolingo

Não corrigi `neural.py:222` — a auditoria é sem correções. Mas o repositório já contém
o teste controlado, e ninguém o leu assim. **No Duolingo, item e conceito são o mesmo
lexema.** Medido sobre o dataset inteiro:

| dataset | conceitos | itens | pares distintos | itens por conceito |
|---|---|---|---|---|
| EdNet-KT1 | 142 | 12.056 | 12.056 | **84,9** |
| Duolingo-300k | 8.644 | 8.644 | 8.644 | **1,00 — bijeção** |

Quando há bijeção, `self.concept(b.concept)` na query **é** o embedding de item: a
cegueira desaparece sem trocar uma linha. Se o diagnóstico está certo, a lacuna para a
regressão logística tem que encolher no Duolingo. Encolhe:

| | EdNet-KT1 (5 seeds) | Duolingo-300k (3 seeds) | razão |
|---|---|---|---|
| regressão logística − sabelia | **+0,0886 ± 0,0078** | **+0,0101 ± 0,0016** | **8,8×** |
| gradient boosting − sabelia | **+0,1030 ± 0,0074** | **+0,0143 ± 0,0009** | **7,2×** |

Mesmo código, mesmas 18 features, mesmo protocolo. A única variável que muda é se a
query consegue distinguir a questão. **Isso é evidência causal do diagnóstico, não
inferência.** E prevê o resultado do conserto: adicionar o item à query deve recuperar
a maior parte dos 0,089 no EdNet — mas isso **não foi testado**, porque testar exigiria
modificar o modelo.

### Duolingo-HLR 300k, 3 seeds, scoring corrigido

O run que faltava no relatório anterior. Baselines honestos nos três seeds.

| modelo | AUC | log loss | Brier | ECE |
|---|---|---|---|---|
| gradient boosting | **0,6717 ± 0,0040** | 0,4145 ± 0,0010 | 0,1263 ± 0,0004 | 0,0193 ± 0,0021 |
| regressão logística | 0,6674 ± 0,0058 | **0,4115 ± 0,0016** | **0,1258 ± 0,0006** | 0,0132 ± 0,0035 |
| **sabelia** | 0,6573 ± 0,0046 | 0,4132 ± 0,0015 | 0,1261 ± 0,0008 | **0,0101 ± 0,0016** |
| dkt | 0,6302 ± 0,0023 | 0,4371 ± 0,0026 | 0,1341 ± 0,0011 | 0,0483 ± 0,0011 |
| mastery_heuristic | 0,6042 ± 0,0022 | 0,4343 ± 0,0013 | 0,1335 ± 0,0007 | 0,0305 ± 0,0008 |
| das3h | 0,6027 ± 0,0031 | 0,4299 ± 0,0015 | 0,1317 ± 0,0007 | 0,0100 ± 0,0006 |
| bkt | 0,5998 ± 0,0032 | 0,4566 ± 0,0021 | 0,1375 ± 0,0010 | 0,0381 ± 0,0010 |
| pfa | 0,5960 ± 0,0046 | 0,4329 ± 0,0012 | 0,1328 ± 0,0006 | 0,0184 ± 0,0012 |
| concept_mean | 0,5858 ± 0,0025 | 0,4316 ± 0,0015 | 0,1318 ± 0,0007 | 0,0136 ± 0,0009 |
| global_mean | 0,5000 | 0,4358 ± 0,0021 | 0,1328 ± 0,0009 | 0,0058 ± 0,0022 |

Diferença pareada de AUC contra o Sabelia: gradient boosting **+0,0143 ± 0,0009 (3/3)**,
regressão logística **+0,0101 ± 0,0016 (3/3)**, DKT −0,0271 (0/3), DAS3H −0,0546 (0/3),
BKT −0,0575 (0/3).

**Aqui a claim se inverte.** O Sabelia **perde** em ordenação para os dois baselines
honestos, em 3 de 3 seeds — mas é **o modelo mais bem calibrado da tabela** (ECE 0,0101,
empatado com o DAS3H e melhor que a logística, o GBM e 3,8× melhor que o BKT), com
Brier praticamente empatado com o melhor (0,1261 vs 0,1258). Ou seja: no dataset onde a
query enxerga a questão, o modelo é *pior em ordenação e melhor em probabilidades* —
exatamente o contrário do que a claim afirma. Diagrama de confiabilidade em
[`auditoria_confiabilidade_duolingo.png`](auditoria_confiabilidade_duolingo.png).

### Verificação cruzada: a CLI do repositório dá os mesmos números

Enquanto eu rodava, uma sessão paralela sua executava
`sabelia benchmark --dataset configs/datasets/duolingo-hlr-300k.yaml --out benchmarks/runs-duolingo-fixed --seeds 3 --epochs 20`
— o mesmo experimento, pela CLI do próprio repositório em vez do meu harness. Comparei
linha a linha os seeds já concluídos:

| seed | concept_mean | mastery | pfa | das3h | bkt | dkt | sabelia | n |
|---|---|---|---|---|---|---|---|---|
| 0, CLI | 0,5834 | 0,6023 | 0,5908 | 0,5995 | 0,5969 | 0,6328 | 0,6530 | 60.670 |
| 0, esta auditoria | 0,5834 | 0,6023 | 0,5908 | 0,5995 | 0,5969 | 0,6328 | 0,6530 | 60.670 |
| 1, CLI | 0,5855 | 0,6036 | 0,5976 | 0,6030 | 0,5994 | — | — | 60.270 |
| 1, esta auditoria | 0,5855 | 0,6036 | 0,5976 | 0,6030 | 0,5994 | 0,6284 | 0,6570 | 60.270 |

**Idêntico até a 4ª casa, com o mesmo `n`.** Os números desta auditoria não são artefato
do meu harness — ele reproduz a CLI do repositório exatamente. *(Esse arquivo,
`benchmarks/runs-duolingo-fixed/runs.jsonl`, foi escrito por aquela sessão, não por esta
auditoria; nenhum arquivo do projeto foi tocado aqui além deste relatório e dos dois PNGs.)*

**E as ablações dessa mesma execução confirmam o diagnóstico de `neural.py:222`**
(seed 0, scoring corrigido):

| variante | AUC | vs sabelia |
|---|---|---|
| **sabelia-no_item** | **0,6562** | **+0,0032** |
| sabelia-no_forgetting | 0,6559 | +0,0029 |
| sabelia-no_response | 0,6541 | +0,0011 |
| sabelia (completo) | 0,6530 | — |
| sabelia-no_time | 0,6499 | −0,0031 |

**Remover o embedding de item — 771k dos 862k parâmetros — não custa nada: melhora.**
É exatamente o que a §5 prevê. Onde item e conceito são o mesmo lexema, o embedding de
item é redundância pura; onde não são (EdNet), ele existe mas está no lugar errado, e o
modelo perde 0,089 de AUC para uma regressão logística por causa disso.

**Duas ressalvas que impedem de comemorar esse ECE.** Primeira: 69,7 % dos eventos de
teste do Duolingo têm vetor de features idêntico no treino (P5), então o n efetivo é
muito menor que 60.670. Segunda: o corte cobre 6 h 12 min (P4). O Duolingo é o dataset
em que o Sabelia vai melhor e é também o mais contaminado dos dois.


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

### E no Duolingo? Aqui o critério é atendido

| Duolingo-300k, 3 seeds | s0 | s1 | s2 | média ± dp |
|---|---|---|---|---|
| **sabelia** | 0,6530 | 0,6570 | 0,6621 | **0,6573 ± 0,0046** |
| dkt | 0,6328 | 0,6284 | 0,6294 | 0,6302 ± 0,0023 |
| das3h | 0,5995 | 0,6030 | 0,6057 | 0,6027 ± 0,0031 |
| bkt | 0,5969 | 0,5994 | 0,6031 | 0,5998 ± 0,0032 |

Pareado: **+0,0271 ± 0,0063** sobre o DKT e **+0,0575 ± 0,0014** sobre o BKT, positivo
em **3/3**. Aqui a vantagem é 4 a 41× o desvio — o critério "desvio menor que a vantagem"
é atendido com folga, ao contrário do EdNet. **Contra os baselines do repositório, no
Duolingo, o modelo ganha de verdade.** O que ele não faz, em nenhum dos dois datasets, é
ganhar dos baselines honestos (§5) — e o mesmo Duolingo é o dataset com 69,7 % de vetores
de teste repetidos no treino (P5) e 6 h de janela (P4).

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

**E no Duolingo nem a metade que sobrava se sustenta.** Lá o Sabelia tem ECE
0,0101 ± 0,0016 contra 0,0381 ± 0,0010 do BKT — **3,8× melhor**, não pior — além de
ganhar em AUC, log loss e Brier. Ou seja: das duas metades da claim de calibração, a que
vale no EdNet (ECE pior) **não vale no outro dataset real**. Isso não é uma propriedade
do modelo; é uma propriedade do EdNet, onde a query não distingue a questão e as
probabilidades saem deslocadas por faixa.

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
foi medida numa comparação inválida.** Afeta as três tabelas de dados reais: EdNet
(40 % dos eventos truncados), Duolingo-300k (~4 %), Duolingo com histórias completas
(39 %).

**Quanto isso muda, agora medido nos dois datasets com o scoring corrigido:**

| Duolingo-300k, 3 seeds | publicado (scoring antigo) | corrigido | Δ |
|---|---|---|---|
| sabelia | 0,6615 | 0,6573 | **−0,0042** |
| dkt | 0,6347 | 0,6302 | **−0,0045** |
| das3h / bkt / pfa / mastery / concept_mean | — | idênticos a 4 casas | 0,0000 |

Só os modelos neurais mudam, porque só eles eram truncados. **A ordenação publicada da
tabela do Duolingo sobrevive à correção** — lá o Sabelia continua à frente dos baselines
do repositório, e por margem larga. O que não sobrevive é a tabela do EdNet, onde o
truncamento descartava 60 % dos eventos e a diferença entre o conjunto pontuado
(base 0,6007) e o descartado (base 0,6880) era enorme. **É preciso dizer as duas coisas:
o bug invalidou a comparação, e no Duolingo o resultado teria sido o mesmo sem ele.**

O bug foi corrigido em `e22636b` (HEAD) mas **nenhum documento foi atualizado** — todos
ainda publicam os números antigos.

### P2 — CRÍTICO. Baselines de 20 linhas ganham do modelo nos dois datasets, em 8 de 8 seeds

**Medido** (EdNet, 5 seeds, mesmo split): gradient boosting 0,7499 ± 0,0059;
regressão logística 0,7355 ± 0,0050; sabelia 0,6469 ± 0,0109. Pareado seed a seed:
**+0,1030 ± 0,0074** (GBM) e **+0,0886 ± 0,0078** (logreg), positivo em **5/5**,
t = 31,1 e 25,4. Até `item_mean` — a taxa de acerto da questão no treino, sem aluno,
sem sequência — faz 0,7081 no seed 0 e ganha nas quatro métricas.

**No Duolingo** (3 seeds) a lacuna é muito menor mas o sinal é o mesmo: GBM
**+0,0143 ± 0,0009** e logreg **+0,0101 ± 0,0016**, ambos **3/3**. Somando os dois
datasets: **8 de 8 seeds**, sem uma única exceção.

**Causa, em uma linha**: [`neural.py:222`](sabelia/models/neural.py:222) — a *query*
não inclui o embedding de item. O modelo prevê o acerto sem saber qual é a questão.
Ablação: só a identidade (conceito + questão) vale 0,7067 de AUC; sem ela, tudo cai
para 0,6381.

**Impacto**: a claim "melhor que qualquer coisa em ordenação" é falsa contra um
baseline de 20 linhas. E explica dois "mistérios" registrados no repositório: por que
remover o embedding de item (89 % dos parâmetros) não custa nada, e por que as
ablações são todas nulas.

### P3 — ALTO. No EdNet o desvio entre seeds é 1,38× a vantagem sobre o BKT

Sabelia 0,6469 ± 0,0109 (5 seeds) contra BKT 0,6390 ± 0,0075. Vantagem +0,0079,
desvio 0,0109. Pareado por seed: +0,0079 ± 0,0073, positivo em 4 de 5, t = 2,42,
p ≈ 0,07. Em 1 dos 5 seeds o Sabelia fica em último entre os quatro modelos de KT.
O repositório publica ±0,0023 e uma vantagem de +0,025 — ambos medidos no subconjunto
errado de eventos.

**Isso é um problema do EdNet, não do modelo.** No Duolingo a vantagem sobre os
baselines do repositório é de +0,027 (DKT) a +0,058 (BKT) com desvios de 0,001–0,006:
folgadamente fora do ruído, 3/3 seeds. A leitura correta não é "o modelo não ganha de
ninguém" — é **"o modelo ganha dos baselines do repositório onde a query enxerga a
questão, e não ganha onde ela não enxerga"** (§5). Em nenhum dos dois casos ele ganha
dos baselines honestos.

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

**Impacto agora que o Duolingo rodou**: é justamente o dataset onde o Sabelia vai bem
(+0,027 a +0,058 sobre os baselines do repositório, 3/3 seeds, desvios de 0,001–0,006)
e onde ele é o mais bem calibrado. Os desvios entre seeds são pequenos *porque* o
conjunto efetivo é pequeno e repetido — reproduzir o mesmo número três vezes num
conjunto quase-decorado não é a mesma coisa que reproduzi-lo em dados novos. **O
resultado mais favorável ao modelo vem do dataset mais contaminado dos dois.**

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
| ~~Baselines honestos fora do seed 0~~ | **Fechado.** Rodados nos 5 seeds do EdNet e nos 3 do Duolingo. |
| ~~Re-execução do Duolingo com o scoring corrigido~~ | **Fechado.** Três seeds. A correção custa −0,0042 ao Sabelia e −0,0045 ao DKT e não move os baselines; a ordenação publicada sobrevive. "Sabelia ganha no Duolingo" está **confirmado contra os baselines do repositório** (3/3, +0,027 a +0,058) e **refutado contra os baselines honestos** (perde 3/3, −0,010 a −0,014). |
| **Duolingo com histórias completas** | O corte de 300k foi re-executado; a variante de alunos inteiros (onde o truncamento afetava 39 % dos eventos, quase tanto quanto no EdNet) **não foi.** É a tabela em que a correção pode ter o maior efeito e ela continua não medida. |
| **Seeds 3 e 4 do Duolingo** | O benchmark do repositório usa 3 seeds nesse dataset e mantive isso. As conclusões do Duolingo se apoiam em 3 seeds, não em 5. |
| **Comparação com modelos publicados** (SAKT, AKT, SAINT+, pyKT) | Nenhum foi executado. O repositório também nunca os executou. A claim "melhor que qualquer coisa do mercado" **não foi testada por ninguém**, aqui ou lá. |
| **EdNet completo** (784.309 alunos) | Só a amostra de 6.000. Modelos de atenção costumam melhorar com escala; é possível que o Sabelia se saia melhor com mais dados. Não testado. |
| **Se um Sabelia com item na query fecharia a lacuna** | Diagnostiquei a causa em [`neural.py:222`](sabelia/models/neural.py:222) mas **não corrigi nem testei** — a auditoria foi explicitamente sem correções. O contraste EdNet↔Duolingo (lacuna 8,8× menor onde item = conceito) é evidência forte, mas é observacional: **não é a mesma coisa que rodar o modelo corrigido.** É a primeira coisa a testar. |
| **ASSISTments 2009** | O adaptador existe; o dataset não está baixado. |
| **Qualidade da política / recomendações** | Fora do escopo da claim. Não avaliada. |
| **LightGBM** | Falhou: `OSError: Library not loaded: '@rpath/libomp.dylib'`. Substituído pelo `HistGradientBoostingClassifier` do sklearn. |

---

## 9. Resumo para copiar e colar

```
AUDITORIA SABELIA (e22636b) — as DUAS metades da claim estão erradas.
1. ORDENAÇÃO, falso: logreg de 18 features ganha em 5/5 seeds no EdNet (+0,0886±0,0078,
   t=25,4) e 3/3 no Duolingo (+0,0101); GBM +0,1030/+0,0143; no EdNet a média de acerto
   por questão faz 0,7081 vs 0,6469 e vence nas 4 métricas. São baselines de 20 linhas.
2. PROBABILIDADES, falso: no Duolingo o Sabelia é o MAIS BEM calibrado dos 10 (ECE 0,0101
   vs 0,0381 do BKT) e vence o BKT nas 4; no EdNet perde só em ECE (0,0161 vs 0,0077,
   5/5) e vence em log loss/Brier 4/5. GBM+isotônica bate o BKT nas 4 ao mesmo tempo.
3. CAUSA: neural.py:222 — a query não tem embedding de item, o modelo não sabe qual é a
   questão (142 tags/12.056 itens). No Duolingo item=conceito e a lacuna cai 8,8x: prova
   causal com o mesmo código. Conserto diagnosticado mas NÃO testado (auditoria só).
4. As tabelas publicadas comparam conjuntos de teste DIFERENTES: neurais nos últimos 200
   eventos (50.185 de 125.116), baselines em todos. Corrigido no código, não nos docs.
5. Vs baselines do repo: Duolingo +0,027 a +0,058 (3/3, real); EdNet +0,0079±0,0073 com
   desvio entre seeds 0,0109 — e o Duolingo tem 69,7% dos eventos de teste duplicados no
   treino e cobre 6 HORAS. Sem vazamento de rótulo. "Melhor que o mercado" NÃO foi testada.
```
