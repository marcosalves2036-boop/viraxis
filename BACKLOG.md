# BACKLOG — Viraxis

> Arquivo gerenciado automaticamente pelo sistema de agentes.
> Marcos pode adicionar tasks em qualquer seção. Agentes leem e atualizam este arquivo a cada ciclo.
> Formato: `- [ ] [AGENTE] Descrição | prioridade: P0/P1/P2 | adicionado: YYYY-MM-DD | fonte: quem adicionou`
>
> **Última curação do Planejador: 2026-07-30.** Fase 2 está tecnicamente entregue — os 2 P0 restantes são
> ações humanas do Marcos, não código. O foco do ciclo passa a ser **hardening de produção + início da Fase 3**.

---

## 🔴 P0 — Bug Crítico (bloqueia usuário)

> ⚠️ Os dois P0 abaixo estão bloqueados desde 2026-07-28 e **nenhum agente consegue avançá-los**.
> Eles não devem impedir o ciclo de rodar — os agentes devem pular direto para P1.

- [ ] [MARCOS/AÇÃO MANUAL] **Meta App Dashboard:** Adicionar `https://viraxis.onrender.com/auth/instagram/callback` em "Valid OAuth Redirect URIs" no app Meta (META_APP_ID=2441320009614747). Sem isso o fluxo `/auth/instagram/authorize` → `/auth/instagram/callback` é recusado pelo Meta com erro de redirect_uri não registrada. Só o Marcos tem acesso ao Meta Developer Console. | prioridade: P0 | adicionado: 2026-07-28 | fonte: dev1 | **BLOQUEADA — requer ação humana (3º ciclo consecutivo)**

- [ ] [MARCOS/AÇÃO MANUAL] **Confirmar/submeter aprovação (audit) do app TikTok** no TikTok for Developers Console (client key aw54mjn8uvws4dkh) — não existe endpoint público de API para consultar status de auditoria programaticamente; só acesso humano ao console resolve. `TIKTOK_DRY_RUN=true` está ativo no Render como proteção temporária. | prioridade: P0 | adicionado: 2026-07-28 | fonte: kevin | **BLOQUEADA — requer ação humana (3º ciclo consecutivo)**

---

## 🟡 P1 — Feature / Avanço do produto

> Promovidos de P2 pelo Planejador em 2026-07-30. O ciclo de 2026-07-30 encerrou sem executar nada
> porque a seção P1 estava vazia e o executor pediu confirmação em vez de cair para P2 (regra 2 do
> AGENT_CONFIG). Estes itens existem para que isso não se repita.

### Hardening de produção (risco real)

- [ ] [DAVI] **Rate limiting na API** — nenhum endpoint tem limite hoje (`grep slowapi|limiter` em `src/` = 0 resultados). Proteger prioritariamente `/brain/*`, `/renderer`, `/content-items/*/process-video` e `/raw-videos/upload-url`, que disparam custo real de LLM/Gemini/FFmpeg. Sugestão: `slowapi` com limite por `user_id` (não por IP — multi-tenant), resposta 429 com `Retry-After`. Incluir teste que prove o 429. | prioridade: P1 | adicionado: 2026-07-27 | fonte: sistema | promovido: 2026-07-30

- [ ] [DAVI] **Expandir `/health` para health check real** — hoje `/health` devolve `{"status":"ok"}` estático e o keep-alive (ping a cada 10min) trata qualquer 200 como "vivo". No Ciclo 2 o Supabase ficou `INACTIVE` e isso passou despercebido. Adicionar checagem real de conectividade com Neon (`SELECT 1`) e Supabase Storage, com `status: degraded` + HTTP 503 quando alguma dependência falhar, e ajustar `keepalive.yml` para falhar o workflow (notificando) em resposta não-200. Reaproveitar o bloco de diagnóstico órfão em `main.py:237-267` (`socket`/`asyncpg`), resolvendo dois itens de uma vez. | prioridade: P1 | adicionado: 2026-07-29 | fonte: planejador | promovido: 2026-07-30

- [ ] [QA] **Suite de testes do pipeline core** — a cobertura atual (`tests/test_auth.py`, `tests/test_uuid_validation.py`, 70 testes) cobre só auth e parsing de UUID. O caminho crítico do produto — BRAIN (`ContentDecision`), RENDERER (`ContentItem`), `scene_extractor`, `video_composer_v2` e `process-video` — **não tem nenhum teste**. Escrever `tests/test_pipeline.py` com LLM/Gemini/FFmpeg mockados nas bordas, mas lógica real de decisão/extração exercitada. Assertions significativas: proibido `assert True` ou mock que só devolve o esperado. Reportar como P0/P1 qualquer bug real encontrado. | prioridade: P1 | adicionado: 2026-07-30 | fonte: planejador

### Produto

- [ ] [ARTHUR] **Retry na UI para RawVideo com `status=failed`** — hoje um vídeo que falha na análise fica morto na Biblioteca e o usuário precisa re-uploadar. Adicionar botão "Tentar novamente" que re-dispara a análise sem novo upload, com estados de loading/erro. Requer endpoint de re-trigger — se não existir, anotar dependência `[DAVI] POST /raw-videos/{id}/reanalyze` e implementar em conjunto. Persistir também o tipo de erro (`download_failed`, `timeout`, `analysis_failed`) para permitir retry automático futuro. | prioridade: P1 | adicionado: 2026-07-28 | fonte: kevin+arthur | promovido: 2026-07-30

- [ ] [KEVIN] **Notificação por email quando `ContentItem.status` → `ready`** — usar Resend (credencial já presente nos env vars do Render). Enviar ao dono do escritório com link direto para `/dashboard/conteudo/{id}`. Incluir opt-out por usuário e não enviar em modo dry-run/dev. É o primeiro loop de retenção do produto: hoje o usuário só descobre que o vídeo ficou pronto se voltar ao dashboard. | prioridade: P1 | adicionado: 2026-07-28 | fonte: sistema | promovido: 2026-07-30

- [ ] [ARTHUR/DEV1] **Tutorial de onboarding travado (gate de primeiro uso)** — a `marketing/landing-page-copy.md` já publica 3 planos pagos (Solo R$97 / Pro R$197 / Completo R$297) e `vault/06-marca/viraxis-marca.md` exige um tutorial obrigatório de primeiro uso para mitigar chargeback. Esse tutorial **não existe**. A LARA registrou aviso explícito: não rodar tráfego pago até ele estar no ar. Implementar fluxo travado no primeiro login (não pulável até completar o primeiro upload → primeira decisão → primeiro vídeo). | prioridade: P1 | adicionado: 2026-07-30 | fonte: planejador (deriva do aviso da LARA no Ciclo 4)

### Estratégia / Fase 3

- [ ] [DEV1] **Escrever `vault/03-fases/fase-3-spec.md`** — a Fase 2 está declarada tecnicamente entregue e não existe spec da Fase 3; sem ela o sistema autônomo fica sem norte estratégico e o backlog vira só manutenção. Basear em: (a) itens fora de escopo da Fase 2 (Billing/Stripe — necessário porque a landing já anuncia preços), (b) a DÚVIDA aberta em `fase-2-spec.md` sobre evoluir o BRAIN de agente único para crew de 3 (Trend Researcher → Clip Curator → Hook Writer), (c) YouTube Shorts como 3ª plataforma de publicação, (d) o Niche Memory DB como moat (ADR-002). Definir critério de pronto mensurável. | prioridade: P1 | adicionado: 2026-07-30 | fonte: planejador

- [ ] [INTEL] **Pesquisar 3 competidores diretos** (automação de vídeo para criadores BR — OpusClip, Submagic, Klap, Pictory). Para cada um: preço em BRL, proposta de valor, pontos fracos visíveis, o que fazem melhor que a Viraxis hoje. Usar WebSearch/WebFetch com dados reais e fontes citadas — não inventar números. Salvar em `vault/04-inteligencia/competidores-2026-07.md`. Pedido direto do Marcos, aberto desde 2026-07-29 sem execução. | prioridade: P1 | adicionado: 2026-07-29 | fonte: marcos | promovido: 2026-07-30

### Infra do sistema de agentes

- [ ] [DEV1] **Versionar o vault e o sistema de agentes no repo** — `vault/`, `BACKLOG.md`, `SISTEMA/` e `RELATORIOS/` existem só em `C:\Users\Marcos\Claude\Projects\SAAS - Escritorio virtual\` e **não estão no git**. Toda a memória institucional (ADRs, specs de fase, marca, relatórios de ciclo) está sem backup e sem histórico. `CLAUDE.md` no repo aponta para `@vault/00-index.md`, que não existe lá — o link está quebrado para qualquer agente que só clone o repo. Commitar essas pastas (excluindo credenciais) e alinhar `CLAUDE.md`. | prioridade: P1 | adicionado: 2026-07-30 | fonte: planejador

---

## 🟢 P2 — Melhoria (nice to have)

### Código / dívida técnica

- [ ] [DAVI] Revisar uso amplo de `except Exception` em 21 arquivos — garantir que erros não sejam engolidos silenciosamente (o exception handler global do commit `cf05bf2` ajuda no topo, mas não nos `except` internos) | prioridade: P2 | adicionado: 2026-07-27 | fonte: scout
- [ ] [DAVI] Extrair helper comum `_upsert_social_account(...)` em `oauth.py` — os 4 fluxos (google/tiktok/instagram/meta) duplicam ~150 linhas cada de troca de token + persistência de `SocialAccount`, com retry de cold-start assimétrico entre plataformas (só instagram/meta/tiktok têm, google não) | prioridade: P2 | adicionado: 2026-07-29 | fonte: davi
- [ ] [KEVIN] Inconsistência de forma de erro nos 4 fluxos OAuth callback (`oauth.py`): `google_callback` não tem `try/except` ao redor do `_parse_uuid`, então UUID malformado no `state` propaga como 422 real; `tiktok_callback`, `instagram_callback` e `meta_callback` envolvem o mesmo trecho num `except Exception` amplo, que converte silenciosamente o 422 em redirect (`status=error`). Não é regressão nem crash, mas os 4 fluxos deveriam se comportar igual. Documentado em `tests/test_uuid_validation.py` (`TestOauthCallbacksUuidValidation`). | prioridade: P2 | adicionado: 2026-07-29 | fonte: qa
- [ ] [DAVI] Padronizar respostas 403→404 remanescentes em rotas antigas de "escritório não encontrado" para consistência com o restante da API | prioridade: P2 | adicionado: 2026-07-28 | fonte: davi
- [ ] [DAVI] Limpar `render_error` residual em `production_meta` quando um reprocessamento subsequente tem sucesso (hoje o erro antigo permanece visível mesmo com `status=ready`, confunde debugging) | prioridade: P2 | adicionado: 2026-07-28 | fonte: dev1
- [ ] [ARTHUR] Refatorar `biblioteca/page.tsx` (741 linhas) — extrair componentes `VideoCard` e `EmptyState` | prioridade: P2 | adicionado: 2026-07-28 | fonte: arthur
- [ ] [DAVI/ARTHUR] Confirmar verbo HTTP de troca de senha: BACKLOG/spec diziam `PUT /me/password`, o código implementa `POST /users/me/password` (`src/viraxis/api/routers/users.py:66`). Testes já exercitam o real (POST). Verificar o proxy `viraxis_db/frontend/src/app/api/users/me/password/route.ts` antes de mexer — só ajustar documentação, não é bug funcional. | prioridade: P2 | adicionado: 2026-07-29 | fonte: qa

### Escala / performance (só quando o volume justificar)

- [ ] [KEVIN] Mover polling de `publish_to_instagram` (até 3min bloqueando thread) para job assíncrono/fila se volume de publicações crescer | prioridade: P2 | adicionado: 2026-07-28 | fonte: dev1
- [ ] [DAVI] Trocar `_download_video` do TikTok publisher (carrega vídeo inteiro em memória) por streaming em disco se vídeos maiores entrarem no pipeline | prioridade: P2 | adicionado: 2026-07-28 | fonte: kevin+davi
- [ ] [DAVI] Aplicar padrão de refresh automático de token (hoje só TikTok) a Google/Meta quando publishers dessas plataformas amadurecerem | prioridade: P2 | adicionado: 2026-07-28 | fonte: kevin+davi
- [ ] [DAVI] Considerar tabela `social_posts` dedicada em vez de `ContentItem.publication_log` (JSONB) se for necessário histórico granular por post | prioridade: P2 | adicionado: 2026-07-28 | fonte: kevin+davi

### Validação pendente

- [ ] [KEVIN] Testar fluxo `publish_to_instagram` contra Graph API real assim que houver conta de teste | prioridade: P2 | adicionado: 2026-07-28 | fonte: dev1 | **depende do P0 de redirect URI**
- [ ] [DAVI] Testar fluxo OAuth completo (Google/TikTok/Meta) fim-a-fim contra provedores reais — análise de código mostra que é seguro por construção (`office_id` vem de state JWT assinado), mas não foi validado com chamada real | prioridade: P2 | adicionado: 2026-07-28 | fonte: davi | **depende dos 2 P0**
- [ ] [DAVI] Confirmar que `/api/analytics/summary`, `/timeline`, `/publications` e `/api/offices/{id}/decisions` continuam coerentes carregados na mesma sessão da página consolidada `/dashboard/analytics` (abas) — sem overlap de rate-limit ou contenção de token. **Revisitar depois do P1 de rate limiting**, que muda a premissa. | prioridade: P2 | adicionado: 2026-07-28 | fonte: arthur

### Limpeza

- [ ] [DAVI] Executar `scripts/cleanup_test_users.py` (criado no commit `3afd8df`, ainda não rodado) contra produção para remover `davi.test.qa+bugcheck@viraxis.dev` e as contas `davi-audit-a-*@test.com` / `davi-audit-b-*@test.com`. Confere consolidação de 2 itens antigos do backlog. | prioridade: P2 | adicionado: 2026-07-30 | fonte: planejador
- [ ] [KEVIN] Avaliar remoção de `run_renderer()` em `agents/renderer/runner.py` — mantido no commit `c761744` por precaução (referenciado por uma task Celery nunca enfileirada). Se o Celery segue desativado (substituído por BackgroundTask), é código morto e pode sair junto com a task. | prioridade: P2 | adicionado: 2026-07-30 | fonte: planejador

### Decisões que precisam do Marcos (não são de código)

- [ ] [MARCOS] **Upgrade de plano Render free → starter.** Os fixes de memória (`-threads 1`, `-preset ultrafast`) são mitigação, não eliminam o risco estrutural de OOM em picos de FFmpeg concorrente. Somado a isso, o keep-alive a cada 10min mantém o serviço sempre acordado — monitorar as 750h/mês do free considerando outros serviços na mesma conta. Decisão de custo, não de engenharia. | prioridade: P2 | adicionado: 2026-07-28 | fonte: davi+kevin
- [ ] [MARCOS] **Troca de fornecedores para hospedagem pública:** Render free → Render paid ou Railway; Supabase free → Supabase pro. Mesma natureza do item acima — decidir antes de qualquer tráfego pago para a landing. | prioridade: P2 | adicionado: 2026-07-27 | fonte: marcos
- [ ] [KEVIN] Registrar ADR respondendo a DÚVIDA aberta em `fase-2-spec.md`: o BRAIN deve virar crew de 3 especialistas (Trend Researcher → Clip Curator → Hook Writer) ou o agente único basta? Avaliar com base na qualidade real das `ContentDecision` em produção, não em preferência arquitetural. Alimenta o P1 de `fase-3-spec.md`. | prioridade: P2 | adicionado: 2026-07-30 | fonte: planejador

---

## 🔵 Em andamento

<!-- Agentes movem tasks aqui quando começam a trabalhar -->

---

## ✅ Concluído

- [x] [KEVIN] Remover endpoint legado `POST /offices/{id}/decisions/{id}/render` — 52 linhas removidas de `offices.py`; `run_renderer()` mantido por precaução (ver P2 de follow-up). Commit `c761744`, deploy Render `live` em 2026-07-30T02:14. | concluído: 2026-07-29
- [x] [DAVI] Mover a anon key do `.github/workflows/keepalive.yml` para GitHub Secret (`SUPABASE_ANON_KEY`) + criar `scripts/cleanup_test_users.py` (194 linhas). Commit `3afd8df`. | concluído: 2026-07-29
- [x] [ARTHUR] Publisher UI — seletor de conta quando há múltiplas contas conectadas à mesma plataforma. Commit `e3dfaed` (`PublishModal.tsx` +136). | concluído: 2026-07-29
- [x] [ARTHUR] Publisher UI — campo de caption/hashtags customizado no modal de Publicar. Commit `e3dfaed` (mesmo PR do seletor de conta). | concluído: 2026-07-29
- [x] [DEV1] Atualizar `vault/03-fases/fase-2-spec.md` — tabela de status corrigida (Publisher, OAuth Instagram, Analytics, pipeline e2e e análise automática movidos para ✅), Next.js corrigido de 14 para `^15.5.19`, critério de pronto reescrito e seção "Ainda pendente" reduzida às 2 ações humanas. | concluído: 2026-07-29
- [x] [DAVI] Padrão `_parse_uuid` (extraído para `src/viraxis/api/utils.py`) aplicado em `content_items.py`, `oauth.py` (16 ocorrências) e `social_accounts.py` — UUID inválido retorna 422 legível em vez de 500. Commit `d1d4349`. | concluído: 2026-07-29
- [x] [DAVI] Exception handler global no FastAPI (`main.py`) — `@app.exception_handler(Exception)` com `logger.exception` + JSON consistente, sem vazar stack trace. Commit `cf05bf2`, deploy `dep-d9l6lu1t0dsc73fsr92g` `live`. | concluído: 2026-07-29
- [x] [QA] Suite pytest de autenticação — 29 testes em `tests/test_auth.py` + `conftest.py` (SQLite in-memory). Register (11), login (7), GET /users/me (4), POST /users/me/password (7). Nenhum bug real encontrado. Commit `c36f058`. | concluído: 2026-07-29
- [x] [QA] Testes de validação de UUID — 41 testes em `tests/test_uuid_validation.py`. Regressão confirmada experimentalmente: revertendo o fix do `utils.py`, 13 testes falham. Commit `00c2cb4`. | concluído: 2026-07-29
- [x] [LARA] Copy completo da landing page (`marketing/landing-page-copy.md`, 156 linhas) + sequência de 3 emails de onboarding (`marketing/emails-onboarding.md`, 139 linhas). Commit `0ea4bce`. **Aviso:** não rodar tráfego pago até o tutorial de onboarding travado existir (virou P1). | concluído: 2026-07-29
- [x] [DEV1] Pipeline end-to-end validado em produção (upload → Gemini/Whisper → BRAIN editing_plan → process-video FFmpeg → ready) | concluído: 2026-07-28
- [x] [DEV1] OAuth Instagram/Meta completo — authorize/callback/status + `publish_to_instagram()` real (Graph API v19) + botão "Conectar Instagram" | concluído: 2026-07-28
- [x] [DEV1] Dashboard de analytics completo — `/dashboard/analytics` + endpoints `/analytics/summary`, `/timeline`, `/publications` | concluído: 2026-07-28
- [x] [KEVIN+DAVI] TikTok publisher real — `publish_to_tiktok()` (init/upload/status polling) + refresh automático de token + dry-run; corrigido bug de chave Fernet divergente | concluído: 2026-07-28
- [x] [KEVIN+ARTHUR] Análise automática de vídeo com `status=failed` + UX da Biblioteca (badges, polling 5s, preview inline, chips, empty state) | concluído: 2026-07-28
- [x] [DAVI] Auditoria de segurança multi-tenant — 26 testes reais em produção, nenhum vazamento entre escritórios; 1 correção de defesa-em-profundidade em `social_accounts.py` | concluído: 2026-07-28
- [x] [DAVI] Bug 500 em `POST /raw-videos/upload-url` — causa real: UUID malformado sem tratamento. Corrigido com `_parse_uuid()` + hardening do Supabase Storage | concluído: 2026-07-28
- [x] [DAVI] Keep-alive Render + Supabase — `.github/workflows/keepalive.yml` a cada 10min | concluído: 2026-07-28
- [x] [KEVIN] `TIKTOK_DRY_RUN=true` ativado no Render como proteção até confirmação humana | concluído: 2026-07-28
- [x] [KEVIN] `video_composer_v2` (new_script) validado e2e em produção — 2 bugs de OOM kill corrigidos (`-threads 1`, `-preset ultrafast`); vídeo validado via ffprobe (1080x1920, h264/aac, 25.47s) | concluído: 2026-07-28
- [x] [ARTHUR] Consolidação `/dashboard/analiticos` + `/dashboard/analytics` em página única com abas, com redirect preservando bookmarks | concluído: 2026-07-28
- [x] [DAVI] Cold start de ~42s no Render free — mitigado pelo keep-alive | concluído: 2026-07-28
- [x] [DAVI] Endpoint `GET /content-items/ffmpeg-check` — FFmpeg confirmado em produção (7.1.5, `/usr/bin/ffmpeg`) | concluído: 2026-07-27
- [x] [KEVIN] Integração OAuth TikTok (authorize/callback/status) com tokens Fernet-criptografados | concluído: 2026-07-27
- [x] [ARTHUR] Tela do Publisher — botão "Publicar" em `ContentItem status=ready` + modal de seleção de plataforma | concluído: 2026-07-27
- [x] [DAVI] Upload streaming do vídeo bruto (sem `read_bytes`) | concluído: 2026-07-11
- [x] [DAVI] `editing_plan` assíncrono via BackgroundTask | concluído: 2026-07-11
- [x] [DAVI] Sessão DB isolada do FFmpeg (3 blocos) | concluído: 2026-07-16
- [x] [DAVI] Upload do resultado em streaming | concluído: 2026-07-16
- [x] [KEVIN] `batch-run` — N decisões por raw_video com `focus_hint` | concluído: 2026-07-11
- [x] [KEVIN] Smart video count + `batch-suggest` + highlights sintéticos | concluído: 2026-07-16
- [x] [ARTHUR] React error #31 fix (`toText` helper) | concluído: 2026-07-16
- [x] [ARTHUR] Barra de progresso durante rendering | concluído: 2026-07-16
- [x] [ARTHUR] Modal "Gerar X vídeos" na Biblioteca | concluído: 2026-07-16
