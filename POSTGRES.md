# PostgreSQL — passo a passo

Por que: no Railway (e em qualquer PaaS) o disco é **efêmero** — a cada deploy o
banco SQLite reinicia, perdendo os leads e a contagem de rotas da demo. Com
**PostgreSQL**, os dados **persistem**. O app já está pronto: cria as tabelas e
semeia os tenants sozinho no primeiro boot; basta apontar `DATABASE_URL`.

---

## No Railway (recomendado — 5 cliques)

1. **Crie o banco.** No seu projeto do Railway, clique **+ New** → **Database** →
   **Add PostgreSQL**. O Railway sobe um serviço `Postgres` com a variável
   `DATABASE_URL` já pronta.

2. **Ligue a API ao banco.** Abra o serviço da **API** (o do NOKAHI AgroRoute) →
   aba **Variables** → **+ New Variable** → **Add Reference** → escolha o serviço
   **Postgres** e a variável **`DATABASE_URL`**.
   - Se preferir digitar, crie a variável `DATABASE_URL` com o valor:
     `${{ Postgres.DATABASE_URL }}`  (o Railway substitui pela URL real).

3. **Confirme as demais variáveis** no serviço da API (se ainda não tiver):
   ```
   PUBLIC_BASE_URL=https://agroroute.despaxai.com
   ALLOWED_HOSTS=agroroute.despaxai.com
   AGROROUTE_TRUST_PROXY=1
   AGROROUTE_ADMIN_TOKEN=<um token forte>
   ```

4. **Redeploy da API.** O Railway redeploya sozinho ao salvar a variável; senão,
   clique **Deploy**. No **Deploy Log** deve aparecer o gunicorn subindo e, ao
   abrir o app, tudo funciona igual — agora sobre Postgres.

5. **Pronto.** As tabelas (`tenants`, `subscriptions`, `leads`, `telemetry`,
   `connectors`, …) são criadas automaticamente e os tenants semeados a partir de
   `data/tenants.json`. Os leads e o limite de 5 rotas da demo agora **persistem**
   entre deploys.

### Ver os dados no Railway
No serviço **Postgres** → aba **Data** dá para navegar pelas tabelas (ex.: ver os
`leads` recebidos). Para uma ferramenta externa (DBeaver/psql), use os campos em
**Postgres → Variables** (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`)
ou a `DATABASE_URL` completa (aba **Connect**).

---

## Alternativa — Postgres externo (Neon, Supabase, Render)

1. Crie um Postgres grátis no provedor e copie a **connection string** (algo como
   `postgres://user:senha@host:5432/dbname`).
2. No Railway (ou onde a API roda), defina a variável:
   `DATABASE_URL=postgres://user:senha@host:5432/dbname`
3. Redeploy. O app aceita tanto `postgres://` quanto `postgresql://` (normaliza
   sozinho) e usa o driver **psycopg2** (já no `requirements.txt`).

---

## Notas

- **Migração de dados**: o SQLite anterior era efêmero, então não há o que migrar —
  o Postgres começa limpo e é semeado no boot.
- **Escala (múltiplos workers)**: o padrão do `Dockerfile` é `--workers 1`, que é
  seguro. Com Postgres você pode aumentar os workers do gunicorn; a semeadura de
  boot tolera corridas entre workers (trata conflito de chave) e a cota de rotas
  usa trava de linha (`SELECT … FOR UPDATE`), correta em concorrência real.
- **Local**: sem `DATABASE_URL`, continua usando SQLite (`data/nokahi.db`) — nada
  muda no desenvolvimento.
