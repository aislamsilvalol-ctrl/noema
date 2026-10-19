# NOEMA: auditoria de pricing (2026-10-19)

**Fontes:**
- `docs/pricing/market-2026-10-19.md`: preços oficiais, concorrentes, câmbio e taxas.
- `docs/pricing/usage-audit-2026-10-19.md`: mapa de chamadas, dados de produção e fórmulas.

**Convenções:**
- Câmbio de planejamento: **R$ 5,65 por US$**. A PTAX de 19/10 foi 5,0564. A máxima dos últimos 12 meses foi 5,5739, e o buffer de ~12% cobre a maior alta do ano.
- "Troca" é uma mensagem do aluno mais a resposta do Mino.
- Uma "aula" tem até ~12 trocas.

## Pricing atual

| Plano | Preço | Cota | O que a cota compra na prática |
|---|---|---|---|
| Free | R$ 0 | 100 "unidades de IA" | ~17 trocas por mês |
| Student | R$ 29,90 | 300 | ~53 trocas |
| Pro | R$ 59,90 | 600 | ~105 trocas |
| Max | R$ 99,90 | 1.000 | ~175 trocas |

- Uma unidade equivale a 1.000 tokens, e tokens em cache contam inteiros.
- A página de preços diz "uma unidade ≈ uma troca curta", mas uma troca real gasta ~5,7 unidades. **O texto mostrado ao usuário erra por um fator de ~5.**
- Hoje há 23 usuários, todos no Free, e nenhum pagante.

## Por que o sistema atual é fraco

1. **A unidade não tem significado para o usuário.** Ainda por cima, o texto está errado.
2. **Os planos compram pouco.** O Free dá ~17 trocas por mês, menos de 2 aulas. A margem dos planos pagos é alta (a IA custa 12–22% do preço com uso total), mas o valor entregue é baixo.
3. **Os quatro planos diferem só em volume.** Nenhum vende capacidade de aprendizado.
4. **O custo registrado está errado:**
   - toda chamada da OpenAI foi gravada com custo 0;
   - streams foram gravados com modelo "unknown";
   - chamadas estruturadas foram gravadas com 0 tokens;
   - embeddings, a ingestão de documentos no worker e a demo da landing não geram registro nenhum.
5. **A cota é verificada só antes da chamada.** O `/ai/chat` aceita até 100 mensagens × 32 mil caracteres, ~800 mil tokens numa chamada só, o que custa ~US$ 1,60 no gpt-4.1. Isso é uma porta de abuso.
6. **O cache da OpenAI nunca acertou** (0 hits). O prompt fixo de ~2.200 tokens é cobrado inteiro em toda troca.

## Provedores atuais

- OpenAI e Anthropic, alternando via `NOEMA_AI_ROUTING`. Em produção está `anthropic:0,openai:100`, porque a Anthropic está sem crédito.
- Embeddings: OpenAI `text-embedding-3-small`.
- Não há voz, OCR pago, imagem nem busca web.

## Modelos atuais

| Tier | Anthropic | OpenAI (produção hoje) |
|---|---|---|
| economy | claude-haiku-4-5 | gpt-4.1-mini |
| standard | claude-sonnet-5 | gpt-4.1 |
| premium (correção) | claude-opus-5 | gpt-4.1 |
| sem tier (chat, notas, cards) | claude-sonnet-4-5 (aposenta em 30/11) | gpt-4.1-mini |

**Datas que forçam mudança:**
- `gpt-4.1-nano` sai em 23/10.
- `gpt-4.1` e `gpt-4.1-mini` saem em **14/01/2027**.
- O Haiku 4.5 já passou da data mínima de aposentadoria.

## Tabela oficial de preços das APIs (US$ por 1M tokens, consultada em 19/10/2026)

| Provedor | Modelo | Input | Cache (leitura) | Output | Observação |
|---|---|---|---|---|---|
| Anthropic | Haiku 5.5 | 0,10 | 0,01 | 0,50 | Até 100K de prompt. 10× mais barato que o Haiku 4.5 |
| Anthropic | Haiku 4.5 (em uso) | 1,00 | 0,10 | 5,00 | |
| Anthropic | Sonnet 5.5 | 2,00 | 0,10 | 10,00 | Escrita de cache 1,25× (5 min) |
| Anthropic | Sonnet 5 (em uso) | 2,00 | 0,20 | 10,00 | |
| Anthropic | Opus 5.5 | 4,00 | 0,20 | 20,00 | Mais barato que o Opus 5 |
| Anthropic | Opus 5 (em uso) | 5,00 | 0,50 | 25,00 | |
| Anthropic | Fable 5.1 | 10,00 | 0,25 | 50,00 | |
| OpenAI | GPT-5.6 Luna | 0,20 | 0,02 | 1,20 | Escrita de cache 1,25× |
| OpenAI | GPT-5.6 Terra | 2,00 | 0,20 | 12,00 | |
| OpenAI | GPT-5.6 Sol | 4,00 | 0,40 | 20,00 | Acima de 272K de input: 2× input, 1,5× output |
| OpenAI | gpt-4.1 (em uso) | 2,00 | 0,50 | 8,00 | Sai em 14/01/2027 |
| OpenAI | gpt-4.1-mini (em uso) | 0,40 | 0,10 | 1,60 | Sai em 14/01/2027 |
| OpenAI | text-embedding-3-small | 0,02 | — | — | |

- Batch tem 50% de desconto nos dois provedores.
- Residência de dados custa +10%.
- Busca web da OpenAI: US$ 10 por mil chamadas.

## Benchmark dos planos grátis (19/10/2026)

| Produto | Free | Planos pagos no Brasil |
|---|---|---|
| ChatGPT | Texto "ilimitado" num modelo pequeno, com limites dinâmicos (não verificado oficialmente: páginas com erro 403) | Go R$ 39,90 · Plus R$ 99,90 |
| Claude | Sonnet/Haiku, janela de 5 h | Pro R$ 129,90 |
| Gemini | Flash-Lite, janela de 5 h + teto semanal | AI Plus R$ 24,99 · Pro R$ 96,99 |
| Perplexity | 3 buscas Pro por dia | Pro R$ 99,90–129,90 |
| Duolingo | Cursos grátis com anúncios + "Energia" | Super ~R$ 31,90 por mês |
| Speak | — | R$ 39,90 por mês / R$ 299,90 por ano |
| Khanmigo | Grátis para professores | Aluno US$ 4 (sem preço em reais) |

**O que o mercado espera:**
- Free generoso, com janelas de reset.
- Entrada paga entre R$ 25 e 40.
- Plano "completo" entre R$ 97 e 130.

## Arquitetura atual de uso de IA

Cada mensagem do aluno gera:
- uma chamada de ensino;
- o classificador de rota, em ~35% das trocas;
- a compactação da memória quando o histórico passa de ~3.500 tokens.

Uma matéria nova adiciona parse do objetivo + currículo (~4 chamadas na primeira mensagem). Revisão, recap, recall e correção de quiz não usam IA. O mapa completo das chamadas está em `usage-audit-2026-10-19.md`.

## Custo por recurso (US$, preços oficiais)

| Operação | Hoje (gpt-4.1, sem cache) | Proposto, conservador | Proposto, otimizado |
|---|---|---|---|
| Troca com o Professor | 1,4 ¢ | 0,74 ¢ | 0,34 ¢ |
| Matéria nova (parse + currículo) | 0,25 ¢ | 0,1 ¢ | 0,02 ¢ |
| Quiz de checkpoint | 0,4–0,7 ¢ | 0,3 ¢ | 0,1 ¢ |
| Compactação de memória | 0,29 ¢ | 0,03 ¢ | 0,03 ¢ |
| Lote de flashcards | 0,12 ¢ | 0,02 ¢ | 0,02 ¢ |
| PDF de 100 páginas | ~4,3 ¢ | ~0,6 ¢ | ~0,6 ¢ |
| Revisão, recap, recall, correção de quiz | 0 | 0 | 0 |

**Premissas das colunas:**
- **Conservador:** Sonnet 5.5 com cache incremental do histórico (800 tokens novos, 4.500 em cache, saída média de 300) em 95% das trocas, e Opus 5.5 em 5%.
- **Otimizado:** 60% das trocas no Haiku 5.5, 35% no Sonnet 5.5 e 5% no Opus 5.5. **Depende de o Haiku 5.5 passar no piso de qualidade da suíte de avaliação.**

## Custo estimado por sessão de aprendizado

- Uma aula de 10 trocas mais as chamadas laterais custa **7,8 ¢ (R$ 0,44)** no cenário conservador e **3,8 ¢ (R$ 0,22)** no otimizado.
- Hoje, no gpt-4.1, custa ~14 ¢. Nos tiers atuais da Anthropic, 23–28 ¢.
- O dado real de produção ainda é pequeno (mediana de 2 trocas por sessão). As premissas serão recalibradas com telemetria.

## Custo mensal de IA por perfil (R$, câmbio a 5,65)

| Perfil | Trocas por mês | Conservador | Otimizado |
|---|---|---|---|
| Free ativado | ~40 | R$ 1,67 | R$ 0,77 |
| Light | ~80 | R$ 3,35 | R$ 1,54 |
| Normal | ~250 | R$ 10,46 | R$ 4,80 |
| Power | ~700 | R$ 29,28 | R$ 13,44 |
| Extreme, sem teto | ~2.500 | R$ 104,56 | R$ 47,99 |
| Extreme, com o uso justo proposto | teto | Plus R$ 28,71 / Pro R$ 79,82 | — |

## Margem bruta atual

- **Real:** receita R$ 0. O custo de IA dos últimos 30 dias foi ~US$ 0,13 recalculado; o registrado diz US$ 0.
- **Teórica, nos planos de hoje:** a IA custa 12–22% do preço com uso total, porque os planos dão quase nada.

## Roteamento de modelos proposto

| Tarefa | Primário | Fallback | Emergência |
|---|---|---|---|
| Classificação de rota, parse de objetivo | Haiku 5.5 | GPT-5.6 Luna | regra local |
| Extração de memória, compactação, flashcards | Haiku 5.5 (batch quando der) | Luna | adiar |
| Explicação simples, follow-up curto | Haiku 5.5 / Luna **se passar no eval** | Sonnet 5.5 | Luna |
| Aula normal | Sonnet 5.5 | GPT-5.6 Terra | Luna, com aviso |
| Correção de erro conceitual, raciocínio difícil | Opus 5.5 | GPT-5.6 Sol | Sonnet 5.5 |
| Currículo | Sonnet 5.5 | Terra | Haiku 5.5 |
| Embeddings | text-embedding-3-small | — | fila |

**Regras de uso:**
- Cache incremental do histórico nos dois provedores.
- Saída limitada por movimento: teto médio de ~300 tokens.
- `/ai/chat` com histórico cortado no servidor.
- Nenhuma troca de modelo entra sem passar na suíte de avaliação (qualidade ÷ custo).

## Plano Free proposto: "Comece a aprender"

- **3 aulas com o Mino por semana.** Reseta na segunda-feira.
- A primeira aula de cada trilha usa o modo completo. As demais usam o modo padrão (modelo eficiente aprovado no eval).
- Revisão e flashcards sem limite (custo zero).
- Modo TDAH incluído.
- 1 trilha ativa e 3 materiais (PDF) por mês.
- **Orçamento-alvo:** até R$ 1,00 por usuário Free ativado por mês. Teto duro de R$ 1,50.

## Planos pagos propostos

| | Plus (recomendado) | Pro |
|---|---|---|
| Para quem | Quem estuda todo dia | Quem estuda pesado: concurso, faculdade, carreira |
| O que importa | ~40 aulas completas por mês (≈1–2 por dia); depois disso continua no modo padrão | ~125 aulas completas por mês; raciocínio avançado com o dobro da frequência |
| Materiais | 30 PDFs por mês | 100 PDFs por mês, maiores |
| Trilhas | Ilimitadas | Ilimitadas + simulados/provas |
| Memória | Completa | Completa |

## Preços mensais propostos

- **Plus: R$ 34,90.** Fica abaixo do ChatGPT Go (R$ 39,90) e acima do Gemini AI Plus (R$ 24,99).
- **Pro: R$ 69,90.** Fica abaixo do ChatGPT Plus (R$ 99,90) e do Claude Pro (R$ 129,90).
- **Saem** Student e Max: quatro planos que só diferem em volume confundem.

## Preços anuais propostos

- 10× o mensal ("2 meses grátis", ~17%).
- **Plus: R$ 349 por ano** (R$ 29,08 por mês).
- **Pro: R$ 699 por ano** (R$ 58,25 por mês).
- Descontos maiores destroem o LTV sem prova de que reduzem o churn.

## Limites dos planos (o que o usuário vê)

| | Free | Plus | Pro |
|---|---|---|---|
| Aulas no modo completo | 1ª de cada trilha | ~40 por mês | ~125 por mês |
| Depois do limite | Espera o reset | Continua no modo padrão | Continua no modo padrão |
| Revisão e flashcards | Sem limite | Sem limite | Sem limite |
| Modo TDAH | Sim | Sim | Sim |
| PDFs por mês | 3 | 30 | 100 |

**Ao chegar no limite**, a mensagem diz: "Você usou suas aulas completas deste mês. Pode continuar no modo padrão, esperar até dia X ou fazer upgrade." Nunca mostra "unidades".

## Limites internos de uso justo

- **Crédito interno:** 1 crédito = US$ 0,001 de custo de lista, calculado pela versão vigente da tabela de preços. O usuário não vê créditos.

| | Free | Plus | Pro |
|---|---|---|---|
| Soft (aviso + modo padrão) | 180 créditos | 4.000 | 12.500 |
| Hard (bloqueio do modo completo) | 270 créditos | 2.000 trocas por mês no total | 4.000 trocas por mês no total |
| Por dia | 40 trocas | 150 | 300 |

**Proteções globais:**
- Taxa de 30 trocas por minuto (já existe).
- Teto de tokens por chamada.
- Orçamento diário global com alerta em 50%, 80% e 100%, e circuit breaker.
- Alerta para conta com custo mais de 10× a mediana do plano.

## Tetos de CAC

LTV medido em lucro bruto. A receita líquida média por pagante é R$ 36,19 por mês (mix de 80% Plus e 20% Pro, já descontados imposto, gateway e reembolsos).

| Margem bruta \ churn mensal | 7% | 10% | 15% |
|---|---|---|---|
| 62% | R$ 321 | R$ 224 | R$ 150 |
| 70% | R$ 362 | R$ 253 | R$ 169 |
| 76% | R$ 393 | R$ 275 | R$ 183 |

**Para o agente de tráfego** (caso base: margem de 70%, churn de 10%):
- CAC de break-even por pagante: R$ 253.
- **CAC-alvo (LTV:CAC 3:1): R$ 84.**
- Payback de 3 meses: CAC ≤ R$ 76.
- Com 3% de conversão do cadastro em pagante, isso dá **≤ R$ 2,50 por cadastro**. Esse número é instável até termos dados reais de conversão.

## Riscos

1. **O custo do Free é o maior risco.** Com o roteamento conservador, um Free ativado custa ~R$ 1,67. Em 10 mil cadastros com 3% de conversão, o Free consumiria quase toda a contribuição dos pagantes. **O Free só fecha a conta se o modelo eficiente passar no eval de ensino.**
2. **Margem:** no roteamento conservador a margem bruta fica em 61–62%. No otimizado, 77–78%. Um alvo realista pós-otimização é 70–75%. 80% ou mais só com o modelo eficiente aprovado na maioria das trocas.
3. **FinOps quebrado:** custo registrado como zero, ingestão e demo sem medição, e o `/ai/chat` sem limite de histórico. Sem consertar isso, nenhum limite de plano é confiável.
4. **Modelos aposentando:** gpt-4.1 e gpt-4.1-mini em 14/01/2027, Sonnet 4.5 em 30/11.
5. **Câmbio e IOF:** custos em dólar e um IOF de 3,5% em discussão judicial. Confirmar com contador.
6. **Imposto:** usei 6% sobre a receita, mas ainda não há CNPJ nem regime tributário definido.
7. **Pagamento:** a chave do Stripe expirou e a migração para a Braintree está pendente (sem preço público para o Brasil).
8. **Amostra pequena:** 240 chamadas e 23 usuários. Toda estimativa de distribuição é hipótese até o lançamento.

## Planilha de economia unitária

- **Arquivo:** `docs/pricing/noema-unit-economics.xlsx`.
- **Regenerar:** `uv run --with openpyxl python scripts/pricing/build_unit_economics.py` (o openpyxl não é dependência da aplicação).
- Abas: `Premissas` (câmbio, imposto, gateway, reembolsos, churn, conversão, LTV:CAC, payback, mix), `Preços API`, `Custo por operação`, `Perfis`, `Planos`, `CAC`, `Free burn`. Toda célula derivada é fórmula; as entradas estão em azul sobre fundo amarelo, e os valores desta auditoria aparecem em cinza ao lado, para comparar.
- **O que ela reproduz:** 0,74¢ / 0,34¢ por troca, os perfis mensais, a receita líquida de R$ 36,19 por pagante, o LTV de R$ 253, o CAC-alvo de R$ 84, o payback de R$ 76, os R$ 2,50 por cadastro e a tabela de sensibilidade inteira.
- **Onde ela diverge desta auditoria:**
  - A troca a 0,74¢ só fecha com **500 tokens de saída** (ou 1.800 de input novo), não os 300 escritos acima. A planilha usa 500; com 300, a troca conservadora cai para ~0,53¢.
  - A aula de 10 trocas dá 7,6¢ (R$ 0,43) e 3,6¢ (R$ 0,20), contra 7,8¢ e 3,8¢ aqui: as chamadas laterais no Haiku 5.5 custam menos do que as colunas "proposto" acima (quiz 0,08¢ em vez de 0,3¢; matéria nova 0,075¢ em vez de 0,1¢ / 0,02¢). O PDF de 100 páginas dá 0,7¢ com batch, contra ~0,6¢.
  - A margem bruta depende do uso esperado por plano, que esta auditoria não fixa. Com Plus no perfil Normal (250 trocas) e Pro no Power (700), a planilha dá 65% / 52% (conservador) e 84% / 78% (otimizado); no mix 80/20, 61% e 82%, contra 61–62% e 77–78% aqui.
  - Os R$ 28,71 / R$ 79,82 do "Extreme com uso justo" não foram reproduzidos a partir dos limites internos; a planilha calcula o teto como trocas do limite hard × custo da troca + PDFs do limite.
  - A ativação do Free (40%) é premissa da planilha, não desta auditoria.

## Recomendação

1. **Antes de mudar qualquer preço, P0 de FinOps:**
   - corrigir o registro de custo (modelo real, tokens das chamadas estruturadas, embeddings, ingestão e demo);
   - cortar o histórico do `/ai/chat` no servidor;
   - tabela de preços versionada no banco (`ai_price_registry`) em vez de `_LIST_PRICES` no código;
   - cache incremental do histórico.
2. **Migrar os tiers** para Haiku 5.5 / Sonnet 5.5 / Opus 5.5 e GPT-5.6 Luna / Terra / Sol, e rodar a suíte de avaliação comparando qualidade ÷ custo. É isso que decide se o Free e a margem de 75% são viáveis.
3. **Três planos, Free / Plus R$ 34,90 / Pro R$ 69,90, com Plus como recomendado.** Anual com 2 meses grátis. Vender aulas e capacidade, não tokens nem nomes de modelos.
4. **Segunda entrega:** planilha de economia unitária com fórmulas editáveis (custos dos modelos, câmbio, usuários, trocas por dia, conversão, preços, infra).
5. **Terceira entrega:** sistema de planos (Plan, Entitlement, UsageMeter, PriceVersion), paywall, tela de preços, upgrade e eventos do funil.
