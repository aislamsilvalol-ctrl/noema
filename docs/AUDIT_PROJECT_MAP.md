# Auditoria NOEMA — mapa do projeto

Data da leitura: 2026-10-07. Escopo: somente leitura do código, schema, migrações, exemplos de ambiente, histórico git, testes e configuração. Nenhum código de aplicação foi alterado. Achados citam arquivos reais. Valores de segredo não aparecem aqui; só o lugar onde o nome da variável vive.

O README ainda descreve o produto como pré-alfa, com a fase 2 em andamento e a tabela de features como intenção (`README.md:20-25`, `README.md:62-75`, `README.md:140-148`). O código já passou disso: Professor, FSRS, quizzes, exames, maestria, Modo TDAH, billing Stripe, MFA e readiness estão implementados. Este relatório descreve o que o código faz hoje.

---

## 1. PROJECT MAP

### O que é

NOEMA é uma plataforma de aprendizagem adaptativa: o aluno traz material ou um objetivo, o sistema extrai conceitos, estima o que ele sabe e escolhe o próximo passo. A IA é a camada que explica, pergunta, corrige e gera exercícios; o estado de aprendizagem fica no banco, não só no chat (`README.md:27-39`, `apps/api/noema/professor/engine.py:1-19`).

O mascote-professor se chama Mino. A identidade de produto no prompt é “Mino, the tutor inside Noema”, sem nomear o modelo por baixo (`apps/api/noema/prompts/__init__.py:25-31`).

Não há bot Telegram, Mini App, loja de itens, rede social nem painel de perfil separado. O que existe no lugar de cada um está na seção 2.

### Stack

| Camada | O que roda | Onde |
|---|---|---|
| Frontend | Next.js 15.5.27, React 19, TypeScript, Tailwind 3.4, TipTap 3.30, Vitest | `apps/web/package.json:15-52` |
| Backend | FastAPI 0.141.1, Starlette 1.7, Uvicorn, Pydantic 2, Python ≥ 3.12 | `apps/api/pyproject.toml:6-14` |
| ORM / migrações | SQLAlchemy 2 asyncio + Alembic. Cabeça atual: `0034_learning_events` | `apps/api/pyproject.toml:19-21`, `apps/api/alembic/versions/` |
| Banco | PostgreSQL 16 + pgvector | `docker-compose.yml:16-28`, `apps/api/noema/db/models.py:450-464` |
| Cache / broker | Redis 7 | `docker-compose.yml:32-41` |
| Fila | Dramatiq + Redis. Atores: `ingest`, `purge_accounts`, `sweep_abandoned_sessions` | `apps/api/noema/workers/__init__.py:45-77` |
| Objetos | Driver `local` ou S3 (`boto3`) | `apps/api/noema/ingestion/storage.py:1-4`, `.env.example:12-18` |
| Pagamento | Stripe Checkout e Customer Portal. Cartão não passa pelo backend | `apps/api/noema/services/billing.py:1-15` |
| E-mail | Resend via HTTP | `apps/api/noema/services/email.py` |
| ML de aprendiz (sombra) | Pacote `sabelia/`, chamado por HTTP se configurado | `sabelia/README.md:1-19`, `apps/api/noema/professor/shadow.py:1-23` |
| Licença | AGPL-3.0 | `README.md:170-174` |

### Frontend

App em `apps/web`. O browser fala só com a mesma origem: `next.config.mjs` faz proxy de `/api/v1/*` para a API, para o cookie de sessão ser first-party (`apps/web/next.config.mjs:1-10`). Rotas de página estão na seção 7. O middleware redireciona quem não tem o cookie `noema_session` antes de pintar a shell (`apps/web/src/middleware.ts:16-26`, `apps/web/src/lib/route-guard.ts:13-36`).

### Backend e APIs

`create_app()` monta `/api/v1` com auth, conta, segurança, progressão, meta, demo, biblioteca, fontes, conceitos, estudo, notas, imports, exports, AI, jornadas, tokens, feedback, foco, admin e billing, mais `/health` e `/health/ready` (`apps/api/noema/main.py:164-189`, `196-226`). Docs OpenAPI só fora de produção (`apps/api/noema/main.py:84-95`).

### Auth

Sessão em cookie, refresh com rotação de família, CSRF double-submit no header `x-csrf-token` (`apps/api/noema/api/v1/deps.py:42-48`, `166-191`). Bearer token com escopos `read`/`write` (`apps/api/noema/api/v1/deps.py:80-98`). Senha com Argon2. Checagem de senha vazada (k-anonimato, fail-open) (`apps/api/noema/core/config.py:62-63`). MFA TOTP (`apps/api/noema/db/models.py:178-200`). Verificação de e-mail (`apps/api/noema/db/models.py:159-176`). Admin é allowlist de e-mail em `NOEMA_ADMIN_EMAILS` mais MFA obrigatório; token de API não entra (`apps/api/noema/api/v1/deps.py:135-160`).

### Workers, filas, cron

Dramatiq não tem scheduler. `ingest` roda na subida do upload. `purge_accounts` e `sweep_abandoned_sessions` precisam de cron externo (`apps/api/noema/workers/__init__.py:57-77`, `docs/self-hosting.md:129-134`, `docs/operations.md:52-55`). Backup noturno é um container `pg_dump` para bucket (`infra/db-backup/Dockerfile:1-6`, `docs/backups.md`).

### Webhooks

Um webhook: `POST /api/v1/billing/webhook`, fora do CSRF, com assinatura Stripe (`apps/api/noema/api/v1/billing.py:1-10`, `91-97`). Eventos tratados: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed` (`apps/api/noema/services/billing.py:312-317`).

### Admin

`/admin` no web e `/api/v1/admin/*`: inteligência de uso, economia do professor, simulador, lista de usuários, troca de plano, relatório de margem, CSV, feedback, ops (readiness e circuitos) (`apps/api/noema/api/v1/admin.py:71-385`, `apps/web/src/app/admin/page.tsx`).

### Integrações

| Provedor | No repositório |
|---|---|
| Anthropic, OpenAI, Ollama, mock | Registrados em `apps/api/noema/providers/{anthropic,openai,ollama,mock}.py` |
| Gemini, OpenRouter | Chaves e ordem de fallback existem (`apps/api/noema/core/config.py:78-79`, `apps/api/noema/api/v1/deps.py:260`). O provider em si é plugin (`apps/api/noema/plugins.py:8-15`). Nenhum pacote `noema_provider_gemini` está neste repo |
| Stripe, Resend, S3, Have I Been Pwned | Serviços acima |
| OCW / legendas acadêmicas | Biblioteca offline com licença (`apps/api/noema/academic/`). Sem rota HTTP |
| Plausible | Script só em produção (`apps/web/src/app/layout.tsx:99-112`) |
| Notion, Obsidian, Anki, Zotero | Importers em `apps/api/noema/importers/` |

### Dinheiro

Planos `free` / `student` / `pro` / `max`. Preço de vitrine em centavos inteiros de BRL (`apps/api/noema/db/models.py:1030-1054`). Custo de IA em `ai_usage.cost_cents` como `float` (`apps/api/noema/db/models.py:968`). Entitlement usa tokens inteiros, não esse float (`apps/api/noema/services/entitlements.py:25-29`). Não há saldo de carteira do aluno.

### Storage, cache, observabilidade

Uploads com chave gerada, nunca o nome do arquivo (`apps/api/noema/ingestion/storage.py:1-4`). Cache de embedding com TTL (`apps/api/noema/providers/cache.py`, `apps/api/noema/core/config.py:90-92`). Logs structlog com redação (`apps/api/noema/core/logging.py:1-6`). Request id no header, no log e em `ai_usage.request_id` (`apps/api/noema/main.py:107-125`, `apps/api/alembic/versions/0033_request_ids.py:28-29`). Circuit breaker por provider, em processo (`apps/api/noema/providers/circuit.py:1-18`). Readiness com timeout e classe do erro, sem mensagem do driver (`apps/api/noema/core/health.py:1-10`). Boot de produção recusa chave placeholder, cookie inseguro, CORS `*` e defaults de laptop (`apps/api/noema/core/config.py:315-348`).

### Deploy e CI

`docker compose up` sobe postgres, redis, api (migrate + uvicorn), worker e web (`docker-compose.yml:15-75`). Modo local fecha egress (`docs/self-hosting.md:53-71`, `docker-compose.local.yml`). CI (`.github/workflows/ci.yml`): API lint/types/migração passo a passo/pytest com cobertura ≥ 80; web lint/types/test/build; Sabelia; pip-audit + gitleaks; compose a partir de clone limpo.

### Variáveis de ambiente (só nomes)

De `.env.example` e `apps/api/noema/core/config.py`:

`NOEMA_MODE`, `NOEMA_ENV`, `NOEMA_LOG_LEVEL`, `DATABASE_URL`, `REDIS_URL`, `STORAGE_DRIVER`, `STORAGE_LOCAL_PATH`, `S3_ENDPOINT` / `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `NOEMA_BACKUP_BUCKET`, `NOEMA_BACKUP_ENDPOINT_URL`, `NOEMA_BACKUP_REGION`, `NOEMA_BACKUP_ACCESS_KEY_ID`, `NOEMA_BACKUP_SECRET_ACCESS_KEY`, `NOEMA_MASTER_KEY`, `NOEMA_SESSION_SECRET`, `NOEMA_SECURE_COOKIES`, `NOEMA_ALLOW_SIGNUPS`, `NOEMA_BREACHED_PASSWORD_CHECK`, `NOEMA_CORS_ORIGINS`, `NOEMA_ADMIN_EMAILS`, `ACCESS_TOKEN_TTL_SECONDS`, `REFRESH_TOKEN_TTL_SECONDS`, `NOEMA_DEFAULT_PROVIDER`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_BASE_URL`, `NOEMA_MODEL_TUTOR`, `NOEMA_MODEL_EXTRACT`, `NOEMA_MODEL_GRADE`, `NOEMA_MODEL_SUMMARIZE`, `NOEMA_EMBEDDING_PROVIDER`, `NOEMA_EMBEDDING_MODEL`, `NOEMA_EMBEDDING_DIM`, `NOEMA_EMBEDDING_CACHE_TTL_DAYS`, `NOEMA_GIT_SHA` (fallback `RAILWAY_GIT_COMMIT_SHA`), `NOEMA_MAX_UPLOAD_MB`, `NOEMA_USER_STORAGE_QUOTA_MB`, `NOEMA_RATE_LIMIT_PER_MINUTE`, `NOEMA_AUTH_RATE_LIMIT_PER_MINUTE`, `NOEMA_AI_CALLS_PER_MINUTE`, `NOEMA_DEMO_ENABLED`, `NOEMA_DEMO_PER_CALLER_PER_DAY`, `NOEMA_DEMO_MAX_TOKENS`, `NOEMA_DEMO_MODEL`, `NOEMA_TRUSTED_PROXY_HOPS`, `NOEMA_AI_DAILY_TOKEN_BUDGET`, `NOEMA_AI_INTERACTIVE_RESERVE`, `NOEMA_STRIPE_SECRET_KEY`, `NOEMA_STRIPE_WEBHOOK_SECRET`, `NOEMA_STRIPE_PRICE_STUDENT`, `NOEMA_STRIPE_PRICE_PRO`, `NOEMA_STRIPE_PRICE_MAX`, `NOEMA_WEB_ORIGIN`, `NOEMA_RESEND_API_KEY`, `NOEMA_EMAIL_FROM`, `NOEMA_PASSWORD_RESET_TTL_SECONDS`, `NOEMA_EMAIL_VERIFICATION_TTL_SECONDS`, `NOEMA_REQUIRE_VERIFIED_EMAIL_FOR_AI`, `NOEMA_PROFESSOR_*` (orçamento de transcript, compactação, checkpoint, flashcards, assessments, abandono), `NOEMA_FSRS_TARGET_RETENTION`, `NOEMA_FSRS_OPTIMIZE_MIN_REVIEWS`, `NOEMA_MASTERY_MODEL_VERSION`, `NOEMA_SABELIA_CONCEPT_LINK`, `NOEMA_SABELIA_URL`, `NOEMA_SABELIA_TIMEOUT_MS`, `NOEMA_EXPORT_SECRET`, `NOEMA_GUARD_ENABLED`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_DEMO`, `NEXT_PUBLIC_DESIGN_V2`, `NOEMA_API_ORIGIN`.

Segredos: `NOEMA_MASTER_KEY` embrulha chaves BYOK (`SecretBox`, `apps/api/noema/core/crypto.py`). Produção recusa `CHANGE_ME` (`apps/api/noema/core/config.py:320-323`). Redação de log e de transcript em `apps/api/noema/core/secrets.py:20-41` (inclui `sk_live_` / `sk_test_` / `whsec_` / `pk_`). Placeholders de teste vivem só em `apps/api/tests/`.

### Testes que já existem

API: 126 arquivos `apps/api/tests/test_*.py` (motores puros, tenancy, professor, billing, foco, health, circuito, request id). Web: 54 arquivos `*.test.ts(x)`. Sabelia: `sabelia/tests/`. Como rodar e o que esta auditoria executou: seção 6.

### Histórico recente (~30 commits)

| Commit | Data | Assunto |
|---|---|---|
| `b0b644c` | 2026-10-07 | Reliability: readiness, boot checks, AI circuit breaker, request ids, lifecycle events, isolation sweep, ops view (#260) |
| `ddd91da` | 2026-10-07 | Modo TDAH: lugar próprio, sessões curtas (#259) |
| `36b723d`–`aab0832` | 2026-10-07 | Bumps de dependência (prosemirror, brace-expansion, source-map, sharp/next, markdown-it, Python; SQLAlchemy permanece 2.0) |
| `de44c55` | 2026-10-07 | Backup noturno prova restore (#251) |
| `3367ee8` | 2026-10-01 | Micro-motion da lição, Mino reage (#248) |
| `8ab7868`–`f6c6911` | 2026-09-30 / 10-01 | Landing V6 e filmes de cena |
| `3e131b8`, `a22b79d` | 2026-09-30 | Backup noturno para bucket Railway (#242, #243) |
| `ef10304` | 2026-09-28 | Mapa mostra o que foi aprendido só conversando (#241) |
| `32e0c09` | 2026-09-28 | Verificação de e-mail (#237) |
| `bb9d3fe` | 2026-09-28 | Memória visível e apagável (#236) |
| `eb82ec4` | 2026-09-28 | Nível sobe quando o aluno demonstra que está à frente (#235) |
| `5cc508e` | 2026-09-28 | Resposta escrita a um check conta como check (#234) |
| `de4e6df` | 2026-09-28 | Gabarito do quiz fica no servidor até a escolha (#232) |
| `108e987` | 2026-09-28 | Toda rota de IA passa pelo mesmo gate (#227) |

O trabalho de confiabilidade de 7 de outubro é a base para evoluir: não reabrir liveness vs readiness, não tirar o circuito do gateway, não parar de gravar `request_id`.

### Dependências entre módulos

```
web (Next) --proxy /api/v1--> api (FastAPI)
api --> Postgres/pgvector, Redis, storage, providers
api/professor --> prompts, gateway, retrieval, student, focus, memory, shadow
api/study + engines --> FSRS, mastery, scheduler, placement (funções puras)
api/workers --> ingestion.pipeline --> knowledge.extraction
sabelia <-- HTTP opcional -- professor/shadow.py (não decide o turno)
academic/ --> sem rota; cache de legendas com licença
```

`engines/` e boa parte de `professor/moves.py`, `professor/student.py:project` e `engines/learner.py` são funções puras. I/O fica em services e rotas.

### Foco pedido: estado pedagógico

**Professor.** Um turno é `ProfessorEngine.prepare` + `stream` (`apps/api/noema/professor/engine.py:1-15`). O roteador `decide()` escolhe o movimento antes do modelo falar (`apps/api/noema/professor/moves.py:1-20`, `400-404`). Movimentos: teach, question, correct, review, example, practice, flashcard, quiz, exam, motivate, summarize, advance, reorient, return, park, answer, guide (`moves.py:57-80`). Escada de estratégia: definition → analogy → scenario → worked_example → contrast → prerequisite → socratic (`moves.py:108-116`).

- Nível: parser de objetivo com enum introductory…expert, fallback “foundational” se o modelo falha (`apps/api/noema/professor/intent.py:1-8`, `30-31`, `73-75`). Onboarding manda nível e propósito como a primeira frase da lição (`apps/web/src/app/learn/new/page.tsx:74-82`). O motor Rasch de placement existe e é puro (`apps/api/noema/engines/placement.py:1-28`); ele não é o primeiro passo obrigatório de `/learn/new`.
- Explicação adaptativa: a escada troca de estratégia quando erra ou diz que não entendeu (`moves.py:474-506`).
- Memória de contexto educacional: seis camadas em `apps/api/noema/professor/memory.py:1-21`.
- Lacunas: `wrong_streak`, remediação pós-assessment, estágio `uncertain`, misconceptions no estado (`student.py:127-132`, `models.py:1383`).
- Exercícios, revisão, teste: quiz/flashcard/exam/checkpoint (`moves.py`, `professor/assessment.py`, `professor/flashcards.py`).
- Dificuldade: tier de custo por movimento (`moves.py:120-138`) e carga cognitiva do foco (`professor/focus.py:51-57`). Dificuldade de item calibrada em `engines/difficulty.py`.
- Próximo passo: currículo da jornada mais `GET /me/next-activity` (`services/next_activity.py`, `api/v1/focus.py`).

**Separação de memória.**

| Camada | Onde vive |
|---|---|
| Chat / contexto ativo (L0) | turnos não arquivados, orçamento de tokens (`professor/memory.py:6-7`, `budget.py`) |
| Memória da lição (L1–L2) | `memory_summaries` (`models.py:1444-1481`) |
| Perfil do aprendiz na jornada (L3) | `learning_journeys.profile` JSON (`models.py:1326-1329`) |
| Preferências da conta | `users.settings` (modo, minutos) — não é o perfil pedagógico (`models.py:90`, `api/v1/account.py:67-93`) |
| Estado por conceito na jornada (L4) | `student_concept_states` (`models.py:1353-1392`) |
| Estado por conceito no grafo | `concept_mastery` (`models.py:633-659`) |
| Arquivo (L5) | turnos com `archived_at` |

As duas projeções de maestria são lidas juntas em `engines/learner.py:1-18` e entram no prompt como um número (`professor/student.py:509-521`). O roteador ainda decide com o estágio da jornada e `REVIEW_AFTER = 7 dias` (`student.py:71-72`, `143-176`), não com o `due_at` do FSRS.

**Grafo / conceito.** `concepts` no workspace, arestas `prerequisite_of | part_of | related_to | contrasts_with` (`models.py:406-489`). Candidato fica oculto até corroboração (`models.py:393-397`). O estado da jornada tem score, streaks, misconceptions, `last_evidence_at`. Não há colunas `confidence`, `attempts` (há `evidence_count`), `last_review` nem `next_review` em `student_concept_states`. Confiança do aluno vai em `mastery_events.confidence` quando a interface manda (`models.py:1437-1438`). Revisão de cartão tem `card_schedules.due_at` e `last_review_at` (`models.py:573-584`).

**Motor adaptativo.** Não existe uma classe `LearningEngine`. O equivalente é `decide()` + `ProfessorEngine`. Sabelia recomenda em sombra e o produto ignora a recomendação (`professor/shadow.py:1-8`).

**Modo TDAH.** Preferência `learning_mode=focus` e rotas `/foco` e `/foco/sessao`. Não é um segundo motor: a lição continua em `POST /ai/professor` e a revisão em `POST /reviews` (`models.py:1655-1662`, `apps/web/src/app/foco/page.tsx:1-12`). Carga: blocos de 90/160/260 palavras, um conceito nos níveis 1–2, pergunta frequente (`professor/focus.py:51-114`). O texto do módulo diz que a profundidade não muda, só o ritmo (`focus.py:1-17`).

**Mascote.** SVG (`MinoRig`), estados em `apps/web/src/components/mino/machine.ts:11-35` (idle, curious, listening, thinking, teaching, happy, celebrating, sleepy, confused, questioning, correcting, exam, …). O servidor manda o estado; o texto do modelo não escolhe a pose (`moves.py:140-160`). WebGL foi aposentado; `mino.glb` (~356 KB, citado em `docs/noema-design-v3.md:47`) não é importado por nenhum `.ts`/`.tsx`. `detectQuality()` ainda reduz mola e blink em aparelho fraco ou `prefers-reduced-motion` (`MinoController.tsx:59-72`, `177-242`).

**Recompensas.** XP só a partir de evidência, idempotente em `(owner, kind, source_id)` (`models.py:1515-1542`, `services/progression.py:1-28`). Níveis por curva, missões, marcas. Sem itens virtuais, sem loja, sem streak de engajamento como moeda (o streak de conceito é pedagógico: `wrong_streak` / `correct_streak`).

**Social e privacidade.** Sem amigos, feed ou perfil público. Dados de estudo são `owner_id`. Admin vê uso e pode exportar CSV. Export e exclusão de conta existem (`api/v1/account.py`). Memória da jornada é visível e apagável (commit `bb9d3fe`).

**Ingestão e copyright.** Upload multipart: PDF, DOCX, MD, TXT, CSV, transcript, paste (`api/v1/sources.py:71-78`). Parser de HTML/URL existe (`ingestion/parsers/__init__.py:45-46`) e o pipeline lê `source_metadata.url`, mas nenhuma rota cria uma fonte buscando uma URL. Aquisição acadêmica só baixa legenda com licença que permite derivado (`academic/acquire.py:11-16`, `academic/registry.py:45-48`). Não há fluxo de DMCA na API.

**Camada de IA — nomes reais.**

| Nome pedido | O que existe |
|---|---|
| AIGateway | `apps/api/noema/providers/gateway.py:115` — retry, fallback antes do primeiro token, orçamento, usage, cache de embedding, circuito |
| ModelRouter | `providers/registry.py:63` (`Router`: notebook → usuário → default) mais tier de custo em `services/professor.py` e `ModelTierConfig` |
| PromptRegistry | `prompts/__init__.py:load` — arquivos `nome.vN.md`, ~55 prompts |
| UsageTracker | `services/usage.py:UsageWriter` + `DailyBudget` + `services/entitlements.py` |
| FallbackManager | a cadeia dentro de `AIGateway.stream` (`gateway.py:165-178`) e `_fallback_chain` (`api/v1/deps.py:267-278`) |
| MemoryService | `professor/memory.py:ContextCompactor` |
| LearningEngine | repartido: `professor/engine.py`, `professor/moves.py`, `engines/*`, `services/next_activity.py` |
| RAGService | `retrieval/search.py` + `retrieval/grounding.py` + `ingestion/pipeline.py` |

Roteamento é por classe de tarefa (`NOEMA_MODEL_*`) e por tier economy/standard/premium (`moves.py:117-138`), não por um classificador de complexidade/latência em tempo real. RAG: parse → chunk → embed → index → extract (`ingestion/pipeline.py:1-10`, `53-70`). Recuperação híbrida densa+esparsa com piso absoluto (`retrieval/search.py:1-5`, `41-55`). Citação inventada é descartada (`retrieval/grounding.py:1-10`). Notebook vazio responde de conhecimento geral; notebook com material e sem hit recusa (`retrieval/search.py:133-143`).

**Performance (do código e do build).** First Load JS medido nesta auditoria: compartilhado 103 kB; landing 201 kB; `/chat` 214 kB; `/foco/sessao` 207 kB (`npm run build`). Mino ao vivo usa `requestAnimationFrame` no provider. Polling: fontes a cada 2 s (`components/SourceList.tsx:55`), relógio do foco a cada 15 s (`app/foco/sessao/page.tsx:123`). GLB não entra no bundle JS.

---

## 2. Classificação

| Área | Classe | Por quê |
|---|---|---|
| Sessão, CSRF, MFA, tenancy `OwnedRepository` | FUNCIONA | `deps.py`, `db/repository.py:24-48`, testes `test_db_tenancy.py`, `test_db_auth.py` |
| Professor (roteador, streaming, blocos, checkpoint) | FUNCIONA | `professor/engine.py`, `moves.py`; testes `test_db_professor_engine.py`, `test_professor_engine_units.py` |
| Memória em camadas da jornada | FUNCIONA | `professor/memory.py`, `memory_summaries` |
| FSRS de cartões, reviews idempotentes | FUNCIONA | `engines/fsrs.py`, `models.py:621-629` |
| RAG com citação e recusa | FUNCIONA | `retrieval/search.py`, `grounding.py` |
| Modo TDAH como modo próprio | FUNCIONA | `/foco`, `professor/focus.py`, `focus_sessions` |
| Mino SVG e estados | FUNCIONA | `components/mino/`; GLB não é o runtime |
| XP / níveis a partir de evidência | FUNCIONA | `services/progression.py` |
| Readiness, boot, circuito, request id | FUNCIONA | commit `b0b644c`, `core/health.py`, `providers/circuit.py` |
| Admin com allowlist + MFA | FUNCIONA | `deps.py:135-160` |
| Detecção de nível | PARCIAL | parser + frase de onboarding; placement Rasch não conduz a primeira lição |
| Revisão por conceito | PARCIAL | cartão tem `due_at`; conceito da jornada usa 7 dias fixos |
| Duas maestrias (grafo × jornada) | PARCIAL | `engines/learner.py:1-18` lê as duas; o roteador age sobre uma |
| Ingestão de URL / link | PARCIAL | parser sim, rota de fetch não |
| Gemini / OpenRouter | PARCIAL | nome e chave sim, implementação é plugin ausente |
| Billing Stripe | PARCIAL | webhook assinado e idempotente; retorno do browser é 404; ver seção 3 |
| Guard de segurança | PARCIAL | código existe, default desligado; `RESTRICTED` só registra (`services/guard.py:20-35`) |
| E-mail em produção | PARCIAL | `onboarding@resend.dev` só entrega ao dono da conta Resend (`config.py:301-308`) |
| Verificação de e-mail obrigatória para IA | PARCIAL | banner existe; `NOEMA_REQUIRE_VERIFIED_EMAIL_FOR_AI` default false (`config.py:185-189`) |
| Sabelia no produto | PARCIAL | sombra; não escolhe o movimento |
| README / roadmap | LEGADO | ainda diz fase 2 e features por construir (`README.md:20-25`, `140-148`) |
| Landing v5, `NEXT_PUBLIC_DESIGN_V2`, `mino.glb` | LEGADO | v6 é a página (`app/page.tsx:1-12`); v5 permanece; GLB é arquivo em `public/` |
| `POST /ai/chat` com modo manual | LEGADO | comentário em `services/professor.py:1-6`: a rota antiga ficou |
| Comentário de `learn/new` e docstring do pipeline | LEGADO | o corpo de `learn/new` já abre `/chat?new=1` (`page.tsx:74-82`); o pipeline já chama extração (`pipeline.py:70`) embora o docstring diga que extração é “a próxima fatia” (`pipeline.py:9-10`) |
| Retorno `/billing/success` e `/billing` | QUEBRADO | rotas não existem no build do Next; ver seção 3 |
| Dois checkouts antes do webhook | QUEBRADO | `user.plan` só muda no webhook; dois POSTs criam duas sessões Stripe |
| Custo de IA em float | RISCO | não é saldo do aluno; distorce relatório |
| Rate limit fail-open sem Redis | RISCO | documentado; readiness marca Redis |
| `past_due` mantém plano pago; `invoice.payment_failed` só loga | RISCO | `billing.py:43-46`, `290-299` |
| Demo público de IA | RISCO | teto diário e de tokens (`api/v1/demo.py:1-9`); some com Redis fora |
| CORS / proxy hops errados em produção | RISCO | boot recusa `*`; hops 0 trata o IP do edge como cliente (`config.py:132-135`) |
| Unificar `next_review` do conceito com FSRS | MELHORIAS | seção 8, P1 |
| Alvos de toque `h-8`, `min-h-screen` no teclado | MELHORIAS | seção 7, P2 |
| URL com allowlist anti-SSRF | MELHORIAS | P1, só quando a rota existir |

Não há Telegram, Mini App, loja, perfil social nem página `/signup` separada. Cadastro é `/login?mode=register` (`apps/web/src/app/login/page.tsx:15-23`).

---

## 3. Dinheiro

Há cobrança de assinatura e contabilidade de custo de IA. Não há saldo interno que o aluno gaste.

**Preço do plano: inteiro.** `plan_configs.monthly_price_cents` é inteiro (`models.py:1041-1054`). Checkout manda um Price ID do Stripe, não um float calculado no browser (`billing.py:88-100`).

**Custo de IA: float.** `AIUsage.cost_cents` e as três colunas `*_cost_per_million_usd` são `float` (`models.py:968`, `1021-1027`). `PricingService.cost_cents` faz aritmética binária e devolve `float` (`services/pricing.py:32-67`). O simulador de margem também é float (`services/economics.py:41-128`). O limite que trava o aluno é soma de tokens inteiros (`entitlements.py:79+`, `usage.py:114-120`), então um erro de centavo não libera plano. O risco é o relatório de lucro do admin mentir por acumulação.

**Atualização de plano.** Só `handle_webhook` escreve `User.plan` (`billing.py:8-10`). O frontend redireciona e não grava plano (`apps/web/src/app/settings/page.tsx:164-173`).

**Idempotência do webhook.** Assinatura obrigatória; sem `NOEMA_STRIPE_WEBHOOK_SECRET` a rota recusa (`billing.py:176-184`). `stripe_events.event_id` é único (`models.py:1057-1069`). O handler consulta antes e insere depois (`billing.py:186-206`). Duas entregas concorrentes do mesmo id: a segunda esbarra no unique e a transação desfaz a escrita duplicada. Não há `INSERT … ON CONFLICT` explícito; a corrida vira 500 e a retentativa da Stripe encontra a linha. Aceitável, não elegante.

**O que está quebrado.**

1. `success_url` é `{origin}/billing/success` e `cancel_url` é `{origin}/billing` (`billing.py:100-101`). O build do Next não tem essas rotas (saída de `npm run build`: páginas estáticas listadas, sem `/billing`). Quem paga cai no 404 (`app/not-found.tsx`). O portal volta certo para `/settings` (`billing.py:171`).
2. O bloqueio de segundo checkout olha `user.plan is not Plan.FREE` (`billing.py:75-87`). O plano continua `free` até o webhook. Dois cliques, ou um retry enquanto o webhook não chegou, criam duas Subscriptions no mesmo customer. O próprio comentário do código descreve esse efeito.

**`invoice.payment_failed`** só registra log (`billing.py:290-299`). Status `past_due` continua na lista que mantém o plano pago (`billing.py:43-46`). É política explícita, sem dunning.

**Reconciliação.** Não há job que compare assinaturas Stripe com `users.plan`. A verdade é o último webhook aplicado.

**XP.** Não é dinheiro. Insert idempotente (`services/progression.py:5-7`). Reviews de cartão têm `client_event_id` único (`models.py:621-629`).

---

## 4. Segurança

**Autenticação.** Cookie de sessão, rotação de refresh, CSRF ligado à sessão e não só ao cookie (`deps.py:166-191`). Bearer com escopo por método HTTP (`deps.py:80-98`). Admin: cookie + e-mail na allowlist + MFA (`deps.py:135-160`). Rotas de admin usam `AdminUser` (`api/v1/admin.py:1-5`).

**IDOR.** `OwnedRepository` filtra `owner_id` e devolve 404 para o que não é do dono (`db/repository.py:1-8`, `42-48`). Testes de tenancy e isolamento de rota existem (`test_db_tenancy.py`, `test_db_route_isolation.py`).

**Mass assignment.** Updates passam por modelos Pydantic com campos nomeados (`api/v1/schemas.py:234-276`). `User.plan` não está no payload de preferências (`api/v1/account.py:82-93`). `NotebookUpdate.retrieval_settings` é `dict` livre — configuração de retrieval do próprio notebook, não privilégio.

**SQLi.** Consultas via SQLAlchemy. Não há `text(f"...")` com interpolação de input em `apps/api/noema`.

**XSS.** Markdown da lição vira elementos React, não HTML (`apps/web/src/lib/markdown.tsx:1-14`). O único `dangerouslySetInnerHTML` é o script de tema, constante montada com `JSON.stringify` da chave de storage (`apps/web/src/lib/theme.tsx:78-80`, `app/layout.tsx:96`). CSP da API é `default-src 'none'` em JSON (`main.py:140-143`). CSP do web permite `'unsafe-inline'` em script e style por causa do bootstrap do Next (`next.config.mjs:16-24`).

**SSRF.** Não há rota que faça o servidor buscar uma URL escolhida pelo aluno. `http_fetch` do OCW segue redirect sem allowlist (`academic/ocw.py:165-178`) e não é exposto em `api/`. Quando alguém ligar ingestão de URL, esse padrão não pode ser copiado para input do usuário.

**Upload / path traversal.** Chave de storage gerada (`ingestion/storage.py:1-4`). Tipo por magic bytes (`ingestion/validation.py:4`, `72-73`). Importers usam `PurePosixPath` (`importers/notion.py:105`, `obsidian.py:103`).

**Rate limit e abuso de IA.** GCRA atômico no Redis, fail-open se o Redis cai (`core/ratelimit.py:1-14`). Limite geral, limite de auth, limite de chamadas de IA por minuto, orçamento diário de tokens com reserva interativa, teto do demo (`config.py:116-141`). Entitlements mensais por plano. Gate único nas rotas de IA (commit `108e987`). Verificação de e-mail para IA está desligada por default.

**Segredos no repo.** Padrões de Stripe já estão em `core/secrets.py:30-33`. Chaves em testes são fictícias. `.env.example` tem `CHANGE_ME`, não uma chave real. Gitleaks está no CI (`.github/workflows/ci.yml:187-188`). Frontend não embute chave de provider; BYOK vai para a API.

**Outros.** Headers `nosniff`, `DENY`, referrer, permissions, HSTS se cookie seguro (`main.py:128-150`). Quiz: gabarito fica no servidor até a resposta (commit `de4e6df`, `professor/engine.py:192-198`). Guard desligado por default (`config.py:235-240`).

---

## 5. TODO, FIXME, mock, placeholder, legado

Busca por `TODO` / `FIXME` no código de produto quase não acha marcadores clássicos. O que importa:

| Onde | O que é |
|---|---|
| `apps/web/src/app/learn/new/page.tsx:16-18` | Comentário de cabeçalho ainda diz que a jornada “vai substituir” subject+notebook. O `start()` já só preenche a primeira fala e abre `/chat?new=1` (`74-82`) |
| `apps/api/noema/ingestion/pipeline.py:9-10` | Docstring diz que extração de conceito é a próxima fatia. `_extract_concepts` já roda na linha 70 |
| `README.md:20-25`, `140-148` | Status e roadmap atrás do código |
| `apps/api/noema/services/professor.py:1-6` | `POST /ai/chat` e modos manuais continuam |
| `apps/api/noema/services/guard.py:20-31` | `RESTRICTED` é permitido e logado; `BLOCKED` está reservado e não é preenchido |
| `apps/api/noema/plugins.py:30-34` | Importers/exporters ainda não são plugins instaláveis |
| `apps/api/noema/services/billing.py:290-294` | Dunning de fatura falha é “fora desta fase” |
| `apps/api/noema/professor/shadow.py:21-23` | Sabelia fica em sombra até uma comparação favorecer o motor |
| `apps/web/src/components/mino/Mino.tsx:18-22` | WebGL aposentado; `public/brand/mino/mino.glb` permanece |
| `apps/web/src/app/page.tsx:3-5` | Landing v5 fica na árvore para rollback |
| `apps/web/src/app/layout.tsx:10-14` | Flag `NEXT_PUBLIC_DESIGN_V2=0` ainda renderiza tokens v1 |
| `apps/web/src/components/legal/LegalDocument.tsx:19` | Placeholders legais só aparecem se a config da empresa estiver vazia; o teste exige isso (`LegalDocument.test.tsx:43-89`) |
| `apps/api/noema/providers/mock.py` | Provider de teste/CI, não de produção |
| `apps/api/noema/api/v1/demo.py` | Lição demo real, com teto; o cliente cai para um texto escrito se o modelo falta |

Não há `dummy` de pagamento que finja plano pago sem webhook.

---

## 6. Testes

### Como rodar

API, no diretório `apps/api` (CI em `.github/workflows/ci.yml:43-107`):

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run alembic upgrade head   # exige Postgres+pgvector
uv run pytest --cov=noema --cov-fail-under=80
```

`NOEMA_REQUIRE_DB=1` faz o pytest falhar se o banco não estiver lá (`apps/api/tests/conftest.py:41-80`). Sem isso, testes de banco dão skip.

Web, em `apps/web`:

```bash
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Sabelia (CI instala torch CPU): `sabelia/` → `pytest` e `sabelia benchmark --quick`. Não foi executado aqui (torch não instalado).

### O que esta auditoria rodou (2026-10-07)

Ambiente sem Postgres, sem Redis e sem Docker. `uv` foi instalado na hora. Segredos de produção não foram usados.

| Comando | Resultado |
|---|---|
| `apps/web` `npm run lint` | passou (aviso: `next lint` será removido no Next 16) |
| `apps/web` `npm run typecheck` | passou |
| `apps/web` `npm test` | 54 arquivos, 288 testes, passou. stderr de jsdom: `HTMLMediaElement.play` não implementado na landing; os testes mesmo assim passaram |
| `apps/web` `npm run build` | passou. 33 páginas. First Load JS: compartilhado 103 kB, `/` 201 kB, `/chat` 214 kB |
| `apps/api` `ruff check` e `ruff format --check` | passou |
| `apps/api` `mypy` | passou, 295 arquivos |
| `apps/api` `pytest` sem `NOEMA_REQUIRE_DB` | **970 passou, 643 skipped**, 23 warnings. Os skips são os testes que pedem Postgres/Redis (`conftest.py`). A cobertura de 80% do CI não foi medida porque essa fatia não rodou |
| `alembic upgrade` | não rodou: sem Postgres |
| Sabelia | não rodou |
| `npm audit` (efeito colateral do `npm ci`) | 58 avisos (2 low, 41 moderate, 13 high, 2 critical). Não foi triado pacote a pacote nesta passagem |

Warnings de pytest: vários testes síncronos em arquivos `test_db_*.py` estão marcados `asyncio` à toa. Não falham.

---

## 7. UX / mobile

Leitura do código e dos testes de componente. Não houve passagem em browser com a API de pé (sem Postgres neste ambiente). Números de bundle vêm do build acima.

Shell: rail a partir de `md`; abaixo disso, barra com Hoje, Aprender (`/chat`), Revisão, Progresso e “Mais” (`components/Shell.tsx:109-133`, `249-278`). A barra soma `pb-[env(safe-area-inset-bottom)]`. No Modo TDAH e na lição imersiva a barra some (`257`). Altura real vai para `--noema-tabbar-height` (`58-73`).

| Rota pedida | Rota real | Leitura de layout |
|---|---|---|
| Landing | `/` → `LandingV6` (`app/page.tsx:11`) | `min-h-screen`, cenas com vídeo (`landing/v5/SceneFilm.tsx` ainda usado pelo filme). Input do herói. CTA para `/login?mode=register` ou `/today` |
| Login | `/login` | `AuthFrame`: `min-h-screen` no `<main>` e de novo na coluna do form (`auth/AuthFrame.tsx:22-32`). No telefone o painel lateral some. Teclado virtual pode somar com `min-h-screen` e criar scroll duplo |
| Signup | mesma página, `?mode=register` (`login/page.tsx:15-23`) | Não há `/signup`. Meta esconde “criar conta” se `allow_signups` for falso (`34-49`) |
| Onboarding | `/learn/new` | Passos subject → level → purpose → mode (normal/foco) → path (`learn/new/page.tsx:31-37`, `169-205`). `autoFocus` no assunto. Mino `lg` só a partir de `sm` (`98`). Termina em `/chat?new=1` |
| Dashboard | `/today` | Cartão do Modo TDAH com uma tarefa (`today/page.tsx:338-355`). Teste cobre o cartão (`today/page.test.tsx`) |
| Professor | `/chat` e `/notebooks/[id]/professor` | Lição com composer grudado e safe-area (`professor/Lesson.tsx:562-576`). Sessão na query `?session=` (`chat/page.tsx:5-8`) |
| Aprender | `/chat`, `/learn/new`, `/explain`, `/socratic` | Explain e Socratic são telas antigas ainda no guard (`route-guard.ts:29-30`) |
| Perfil | não há `/perfil` | Nome em configurações; XP e mapa em `/progress` |
| Configurações | `/settings` | Página longa, âncora `#billing` (`settings/page.tsx:231-273`). Sem retorno de checkout para essa âncora |
| Loja | não há | Preços em `/pricing`; assinar em `/settings` |
| Social | não há | |
| Modo TDAH | `/foco`, `/foco/sessao` | Home quase vazia, `max-w-md`, safe-area, link de saída `min-h-11` (`foco/page.tsx:102-110`). Sessão: uma etapa, pausa, saída, relógio 15 s. Testes em `foco/page.test.tsx` e `foco/sessao/page.test.tsx`. Tom adulto no módulo Python (`professor/focus.py:1-17`) |
| Erro | `app/error.tsx` | `min-h-[100svh]`, retry, digest, diálogo de feedback (`error.tsx:40`) |
| Erro de layout | `app/global-error.tsx` | Cópia em pt e en, sem provider de i18n (`13-23`) |
| 404 | `app/not-found.tsx` | Cena da landing, CTA conforme sessão (`1-9`) |

**Alvos de toque.** `Button` `sm` é `h-8` (32 px), `md` é `h-10` (40 px), `lg` é `h-12` (`components/ui/Button.tsx:32-36`). A barra móvel é `py-3 text-xs` (`Shell.tsx:267`). O foco usa `min-h-11` em pelo menos o link de saída.

**Modais e menus.** Command palette (`components/CommandPalette.tsx`, `max-h-80 overflow-y-auto`). Feedback dialog. `BottomSheet` com `max-h-[85dvh]` (`components/ui/BottomSheet.tsx:84`). Rail colapsável só no desktop.

**Overflow.** Grafos e admin com `overflow-x-auto` (`app/graph/page.tsx:154`, `app/admin/page.tsx:431`). Markdown e blocos de código com `overflow-x-auto` (`lib/markdown.tsx:249`). Mapa de conceitos também (`components/progress/ConceptTerrain.tsx:237`).

**Teclado.** Input de onboarding com focus. Composer da lição acompanha a tab bar. Auth e várias homes usam `min-h-screen` (100 vh), que no iOS não desconta a barra do browser nem o teclado; erro e foco usam `svh` / safe-area.

**Mino no mobile.** Sem contexto WebGL. `detectQuality` marca `low` com ≤2 cores ou ≤2 GB e corta animação (`MinoController.tsx:59-72`). O GLB em `public/` só custa se alguém pedir a URL; o app não pede.

---

## 8. BACKLOG

Tamanho: P = um módulo e testes; M = dois ou três módulos; G = atravessa professor, schema e UI.

### P0

**1. Checkout Stripe devolve 404 e aceita duas assinaturas**

- Evidência: `apps/api/noema/services/billing.py:75-101`; build do web sem `/billing`; `apps/web/src/app/settings/page.tsx:164-173`.
- Risco: quem paga não volta para o produto; um segundo clique antes do webhook abre outra Subscription e outra cobrança.
- Abordagem: `success_url` e `cancel_url` para `/settings?billing=success|cancel` (rota que existe). Antes de criar sessão, recusar se já existe checkout aberto ou se `stripe_customer_id` já tem subscription não cancelada. Travar a linha do usuário no banco durante o POST.
- Tamanho: P.

### P1

**2. Revisão do conceito não é agendada; são 7 dias fixos**

- Evidência: `professor/student.py:71-72`, `143-176`; `card_schedules.due_at` em `models.py:583-584`; ausência de `next_review` em `StudentConceptState` (`models.py:1353-1392`).
- Risco: o mapa diz “precisa revisar” no calendário, enquanto o cartão usa FSRS. O aluno vê dois relógios.
- Abordagem: gravar `next_review_at` na projeção da jornada a partir da retrievability já calculada no grafo quando houver `concept_id`, e do FSRS do cartão ligado ao conceito. `decide()` lê essa data. Sem fórmula nova.
- Tamanho: M.

**3. O roteador ignora a leitura unificada das duas maestrias**

- Evidência: `engines/learner.py:1-18`; o prompt mostra um número (`student.py:509-521`); `decide()` olha estágio, streak e `REVIEW_AFTER` (`moves.py:400-547`).
- Risco: grafo e jornada discordam e a lição segue só a jornada.
- Abordagem: `Situation` ganha a `LearnerState` já existente quando `concept_id` está ligado. Regras atuais permanecem; o caso “grafo diz que esqueceu e a jornada diz mastered” vira `REVIEW`.
- Tamanho: M. Fazer depois ou junto do item 2, sem fundir as tabelas.

**4. Ingestão de link não tem rota, e o fetch acadêmico não serve de modelo**

- Evidência: `SourceKind.URL` e `parse_html` (`parsers/__init__.py:45-46`); upload só arquivo (`api/v1/sources.py:71-78`); `academic/ocw.py:165-178` segue redirect.
- Risco: a promessa de “URL” do README não funciona; um fetch ingênuo vira SSRF.
- Abordagem: rota autenticada que baixa com allowlist de esquema `https`, bloqueio de IP privado, limite de redirect e tamanho, grava os bytes como as outras fontes, e reusa o pipeline. Licença de material de terceiros continua no caminho acadêmico, separado.
- Tamanho: M.

**5. IA sem e-mail verificado, com chaves da plataforma**

- Evidência: `config.py:185-189`; banner em `components/VerifyEmailBanner.tsx`; remetente default não entrega (`config.py:301-308`).
- Risco: conta descartável gasta o orçamento da plataforma. O teto existe, a porta está aberta.
- Abordagem: em produção com chave da casa, ligar `NOEMA_REQUIRE_VERIFIED_EMAIL_FOR_AI` só depois de `NOEMA_EMAIL_FROM` sair de `resend.dev`. Não ligar os dois flags no escuro: o código já avisa que o domínio de teste não entrega.
- Tamanho: P (config + teste do gate, que já existe em `test_email_verification.py`).

### P2

**6. Alvos de 32 px e `min-h-screen` no teclado**

- Evidência: `Button.tsx:32-36`; `AuthFrame.tsx:22-32`; foco já usa `svh`/safe-area.
- Risco: toque errado e campo escondido pelo teclado no login e no onboarding.
- Abordagem: `sm` sobe para pelo menos 44 px nas barras móveis; auth e `/learn/new` usam `min-h-[100svh]` e padding de teclado. Não redesenhar a shell.
- Tamanho: P.

**7. Landing e chat acima de 200 kB de JS inicial**

- Evidência: build desta auditoria, rotas `/` e `/chat`.
- Risco: primeiro paint lento no celular, em cima da animação do Mino.
- Abordagem: medir o que o landing puxa (filme/vídeo) e carregar a cena abaixo da primeira vista depois. Não trocar o Mino SVG.
- Tamanho: M.

### P3

**8. `cost_cents` em float**

- Evidência: `models.py:968`, `pricing.py:32-67`.
- Risco: relatório de margem, não a cobrança do aluno.
- Abordagem: gravar micros de centavo inteiros na escrita nova; ler o float antigo. Sem reescrever o Stripe.
- Tamanho: P.

**9. Pytest com marca asyncio em função síncrona; testes de banco não rodaram aqui**

- Evidência: warnings no pytest desta passagem; 643 skips sem Postgres.
- Abordagem: tirar o mark indevido; CI já sobe pgvector. Nada de produto.
- Tamanho: P.

**10. README e docstrings desatualizados**

- Evidência: seção 5.
- Abordagem: alinhar o status do README ao que a seção 1 descreve, num commit só de docs.
- Tamanho: P.

**11. Sabelia continua sombra até o shadow-eval**

- Evidência: `professor/shadow.py:1-23`.
- Abordagem: não promover o motor. Rodar `scripts/shadow-eval.py` quando houver eventos exportados.
- Tamanho: M, e só leitura.

**12. Guard desligado e `past_due` sem dunning**

- Evidência: `config.py:235-240`, `billing.py:43-46`, `290-299`.
- Abordagem: decisão de operação, não um patch silencioso. Se ligar o guard, manter o caminho educativo que o módulo descreve.
- Tamanho: P para documentar a decisão; M se houver dunning.

---

## 9. Primeira tarefa

A P0 é a única que perde dinheiro ou quebra o retorno de quem pagou. As P1 pedagógicas (itens 2 e 3) vêm em seguida, em cima do readiness e do circuito que já existem, sem fundir tabelas.

### TASK

Fazer o Stripe Checkout voltar para `/settings` e impedir uma segunda assinatura enquanto a primeira não foi liquidada pelo webhook.

### CONTEXT

Checkout e portal estão em `BillingService` (`apps/api/noema/services/billing.py`). O plano do usuário só muda em `handle_webhook`. A tela de configurações redireciona o browser para a URL da Stripe e não grava `account.plan` (`apps/web/src/app/settings/page.tsx:164-173`). `success_url` e `cancel_url` apontam para rotas que o Next não tem. A trava “já tem plano” lê `user.plan`, que ainda é `free` até o webhook. Dois POSTs em `/api/v1/billing/checkout` criam duas sessões.

### FILES

- `apps/api/noema/services/billing.py` — URLs e a criação da sessão.
- `apps/api/noema/api/v1/billing.py` — o POST de checkout.
- `apps/api/tests/test_db_billing.py` — já exige metadata e que `success_url` comece na origem (`test_checkout_calls_stripe_with_the_right_price_and_metadata`, por volta da linha 153). Acrescentar o path e o caso concorrente.
- `apps/web/src/app/settings/page.tsx` — ler `billing=success|cancel` e mostrar o estado sem escrever o plano no cliente.
- `apps/web/src/app/settings/page.test.tsx` — o teste que hoje só confere o redirect para a URL da Stripe.

Não criar página `/billing`. Não mudar o webhook além do necessário para consultar a subscription existente.

### CURRENT BEHAVIOR

`create_checkout_session` envia `success_url = {origin}/billing/success` e `cancel_url = {origin}/billing` (`billing.py:100-101`). Essas rotas caem em `app/not-found.tsx`. Se `user.plan` ainda é `FREE`, cada chamada cria uma Checkout Session nova (`billing.py:75-100`), mesmo que a anterior já tenha sido paga e o webhook não tenha chegado.

### REQUIRED BEHAVIOR

- Sucesso e cancelamento abrem `/settings`, com um query param que a página entende, na origem já calculada por `web_origin`.
- A página mostra que o retorno aconteceu e que o plano vem do servidor. Ela não atribui plano a partir do query param.
- Um segundo `create_checkout_session` para a mesma conta, enquanto existe sessão de checkout aberta ou subscription não cancelada na Stripe para aquele `stripe_customer_id`, responde conflito e aponta o portal — o mesmo conflito que o código já usa quando `user.plan` não é free (`billing.py:83-87`).
- O primeiro checkout de quem nunca teve customer continua criando a sessão, com os mesmos metadata `noema_user_id` e `noema_plan`.

### DO NOT BREAK

- Assinatura do webhook e a tabela `stripe_events`.
- A regra de que o browser não escreve `User.plan`.
- Portal, cuja `return_url` já é `/settings` (`billing.py:171`).
- Plano free sem checkout.
- Cancelamento de subscription na exclusão de conta (`billing.py:128-159`), que engole erro da Stripe de propósito.
- O teste existente de metadata e de price id.

### IMPLEMENTATION

1. Trocar só as duas URLs para a origem + `/settings?billing=success` e `/settings?billing=cancel`.
2. No início de `create_checkout_session`, se `user.stripe_customer_id` estiver preenchido, listar subscriptions não terminadas (o código já lista as `active` em `cancel_active_subscriptions`). Se houver alguma, levantar o `Conflict` que já existe.
3. Serializar o POST: `SELECT … FOR UPDATE` na linha do usuário antes de chamar a Stripe, para dois cliques no mesmo processo não passarem os dois pelo `if plan is FREE`.
4. Na settings page, se a query for `success` ou `cancel`, mostrar um aviso e refazer `GET` da conta. O plano exibido continua sendo o da API.
5. Não adicionar tabela nova se a consulta à Stripe cobrir o caso. Se a listagem falhar, falhar fechado (não criar a segunda sessão).

### TESTS

- Estender `test_checkout_calls_stripe_with_the_right_price_and_metadata` para exigir path `/settings?billing=success` e cancel `/settings?billing=cancel`.
- Novo teste: usuário com `stripe_customer_id` e uma subscription `active` ou `incomplete` na Stripe falsa recebe conflito e o client de checkout não é chamado de novo.
- Novo teste de página: `?billing=success` renderiza o aviso e não chama `checkout` sozinho.
- Rodar `uv run pytest apps/api/tests/test_db_billing.py` com Postgres (no CI isso já sobe) e `npm test -- src/app/settings/page.test.tsx`.

### ACCEPTANCE CRITERIA

- Nenhuma URL de retorno da Stripe aponta para um path ausente do `next build`.
- Dois checkouts seguidos, com webhook ainda não aplicado, produzem uma sessão e um conflito, não duas subscriptions.
- `User.plan` permanece escrito somente em `handle_webhook`.
- Os testes de billing que já passavam continuam passando, com a asserção de URL atualizada para o path novo.
