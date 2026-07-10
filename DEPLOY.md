# Deploy — agroroute.despaxai.com

Publicar o NOKAHI AgroRoute no subdomínio **`agroroute.despaxai.com`** (domínio
GoDaddy `despaxai.com`). A aplicação já está preparada: URL pública configurável,
proxy reverso com HTTPS e host permitido.

Há **duas rotas** — escolha uma:
- **A. VPS próprio** (Docker + Caddy, HTTPS automático) — controle total.
- **B. PaaS** (Render / Railway / Fly.io) — sem servidor para gerenciar.

---

## Passo 1 — DNS na GoDaddy (comum às duas rotas)

1. Acesse **godaddy.com** → *Meus Produtos* → em **despaxai.com** clique em **DNS**
   (ou *Gerenciar DNS*).
2. Em **Registros**, clique **Adicionar** e crie:

   | Rota | Tipo | Nome (host) | Valor | TTL |
   |---|---|---|---|---|
   | **A. VPS** | `A` | `agroroute` | `IP_PÚBLICO_DO_SERVIDOR` | 600 |
   | **B. PaaS** | `CNAME` | `agroroute` | `host-do-provedor` (ex.: `nokahi.onrender.com`) | 600 |

   > O campo **Nome** é só `agroroute` (a GoDaddy completa com `.despaxai.com`).
3. Salve. A propagação leva de minutos a ~1 h. Verifique com:
   `nslookup agroroute.despaxai.com` (deve resolver para o IP/host escolhido).

---

## Rota A — VPS com Docker + Caddy (HTTPS automático)

Pré-requisitos no servidor (Ubuntu): Docker + Docker Compose, portas **80 e 443**
liberadas no firewall e no provedor.

```bash
# 1. clonar o projeto (branch com a solução)
git clone -b nokahi-agroroute https://github.com/giselleCouto/Agro.git
cd Agro/deploy

# 2. segredos (opcional, mas recomendado): crie deploy/.env
cat > .env <<'EOF'
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ESSENCIAL=price_...
STRIPE_PRICE_PROFISSIONAL=price_...
AGROROUTE_ADMIN_TOKEN=<gere: openssl rand -hex 24>
SMTP_HOST=smtp.seuprovedor.com
SMTP_USER=...
SMTP_PASSWORD=...
EOF

# 3. subir (Caddy obtém o certificado HTTPS sozinho)
docker compose up -d --build
docker compose logs -f caddy   # acompanhe a emissão do certificado
```

Pronto: **https://agroroute.despaxai.com** no ar. O `PUBLIC_BASE_URL`,
`ALLOWED_HOSTS` e `AGROROUTE_TRUST_PROXY` já vêm setados no compose.

> Alternativa sem Caddy: use `deploy/nginx.conf` + `certbot` (comentários no arquivo).

---

## Rota B — PaaS (Render / Railway / Fly.io)

1. Crie um **Web Service** apontando para o repositório (branch `nokahi-agroroute`).
   O provedor detecta o `Dockerfile` na raiz.
2. Defina as **variáveis de ambiente**:

   ```
   PUBLIC_BASE_URL=https://agroroute.despaxai.com
   ALLOWED_HOSTS=agroroute.despaxai.com
   AGROROUTE_TRUST_PROXY=1
   AGROROUTE_ADMIN_TOKEN=<token forte>
   STRIPE_SECRET_KEY=...            # opcional
   STRIPE_WEBHOOK_SECRET=...        # opcional
   # persistência: use o Postgres gerenciado do provedor
   DATABASE_URL=postgresql://user:pass@host:5432/nokahi
   ```

   > No SQLite o disco do PaaS costuma ser efêmero — em produção use **PostgreSQL**
   > (`DATABASE_URL`). Com Postgres, pode subir os workers do gunicorn.
3. Em **Custom Domain**, adicione `agroroute.despaxai.com`; o provedor mostra o
   host CNAME a usar no Passo 1 e emite o TLS automaticamente.

> **Porta:** o container escuta automaticamente na porta que a plataforma injeta
> (`$PORT`) — não fixe uma porta. A URL do provedor (ex.: `*.up.railway.app`)
> continua funcionando mesmo com `ALLOWED_HOSTS` setado.

---

## Passo 2 — Stripe (cobrança real)

1. `python -m agroroute.stripe_setup` (uma vez, com `STRIPE_SECRET_KEY`) cria os
   produtos/prices e grava os `STRIPE_PRICE_*`.
2. No painel Stripe → **Webhooks** → adicione o endpoint
   **`https://agroroute.despaxai.com/v1/billing/webhook`** com os eventos
   `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`,
   `customer.subscription.deleted`; cole o *Signing secret* em `STRIPE_WEBHOOK_SECRET`.

Como `PUBLIC_BASE_URL` está setado, os `success_url`/`cancel_url` do checkout já
usam o domínio correto.

---

## Verificação

```bash
curl https://agroroute.despaxai.com/v1/health          # {"status":"ok",...}
```
Depois abra:
- `https://agroroute.despaxai.com/`            → landing
- `https://agroroute.despaxai.com/app?demo=1`  → demonstração (MG)
- `https://agroroute.despaxai.com/admin`        → painel de leads (token)

## Notas

- **GraphHopper** (perfil truck) é um serviço à parte e opcional; sem ele o tenant
  cai para OSRM automaticamente. Para produção nacional, suba-o num serviço próprio
  e ajuste `graphhopper_url` do tenant em `data/tenants.json`.
- **Upload de extrações**: Caddy/nginx já aceitam corpos grandes (60 MB) para os
  arquivos CSV/XLSX da tela de Integrações.
