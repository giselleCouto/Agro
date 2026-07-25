# Despaxa Agro

**O "Waze do agro": roteirização econômica multi-tenant para CVCs canavieiros (Treminhão, Rodotrem, Pentatrem) em todo o Brasil.**

Evolução dos protótipos SAJB (v3/v5/v6): o modelo físico validado com 51.084 registros de telemetria vira um **serviço de API** que calcula, para cada par talhão→usina, todas as alternativas de rota com custo real de viagem — combustível, pedágio por eixo e manutenção — considerando peso (cheio/vazio), rampa, superfície da via e clima real.

## Modelo físico

Combustível por segmento e por sentido:

```
L = (R₀ + α·max(0, rampa%)) · mult_superfície · PBT · Δkm · k_clima_seg
```

| Parâmetro | Valor | Origem |
|---|---|---|
| R₀ | 0,0030 L/(km·t) | calibrado na telemetria SAJB |
| α | 0,0040 L/(km·t·%) | idem; rampa clipada em 6% |
| PBT ida | tara + carga·ocupação | Treminhão 55 t / Rodotrem 70 t / Pentatrem 90 t |
| PBT volta | tara (vazio) | rampa invertida no sentido de volta |
| k_clima | seco 1,00 · úmido 1,08 · molhado 1,15 · enlameado 1,30 · severo 1,50 | SAJB v3 |

O que este serviço adiciona sobre os protótipos:

- **Clima real por rota (`climate: "auto"`)** — chuva acumulada de 7 dias no ponto médio da rota via Open-Meteo, classificada em seco→severo. O fator é **ponderado pela superfície**: chuva quase não afeta asfalto (15% do efeito) mas vira lama integral na terra (100%). Estrada de terra em período chuvoso encarece; em seca, não.
- **Superfície da via** — asfalto, concreto, cascalho, terra, areia (tags OSM via GraphHopper `details=[surface]`), com multiplicadores de rolamento (terra +28%) e de desgaste de manutenção (terra +60%).
- **Pedágio real por eixo** — tarifa/eixo × eixos; na volta vazia, eixos suspensos pagam menos (regra do Descanso de Eixo, Lei 13.711/2018). Praças cadastradas por tenant (importável da base ANTT).
- **Manutenção** — R$/km por veículo × desgaste da superfície × fator de peso.
- **Restrições urbanas** — zonas de exclusão por cidade (e por tipo de veículo); rota que viola nunca é ranqueada acima de uma rota segura.
- **Lote assíncrono** — N pares OD calculados em paralelo (`asyncio.gather` + semáforo).
- **Multi-tenant** — cada usina/transportadora tem API key, preço de diesel, frota, praças de pedágio, zonas restritas e roteirizador próprios, isolados.

## Arquitetura

```
POST /v1/routes/batch  (X-API-Key: <tenant>)
        │
   tenancy.py ── resolve tenant (frota, diesel, pedágios, zonas, provider)
        │
   service.py ── por job, em paralelo:
        │
        ├─ providers.py   OSRM (overview=full, geojson, alternativas)
        │                 ou GraphHopper (perfil truck, elevação+surface nativos)
        ├─ enrich.py      elevação SRTM 30m (OpenTopoData) → rampa por segmento
        │                 chuva 7d (Open-Meteo) → k_clima automático
        │                 matching de pedágios · zonas urbanas · superfícies
        └─ cost.py        combustível ida cheia/volta vazia · pedágio por eixo
                          · manutenção → ranking por custo total
```

## Quickstart

```powershell
pip install -r requirements.txt
python -m pytest tests -q          # 37 testes, sem rede
python demo/demo_batch.py          # demo ao vivo (OSRM + Open-Meteo + SRTM reais)
uvicorn agroroute.api:app --port 8000
```

Com o servidor no ar:

- **http://localhost:8000/** — [landing page](web/landing.html) comercial (−23% de diesel, atributos em alto nível, planos, **formulário de contato**).
- **http://localhost:8000/app** — [aplicação multi-página](web/index.html) (Fleet Intelligence) com sidebar:
  - **Dashboard** — KPIs da frota, situação (donut), custo das rotas calculadas, alertas de manutenção e rotas recentes.
  - **Rotas** — planejador que retorna **4 rotas possíveis** por par origem→destino (o roteirizador dá até 3 e o restante é completado por desvios reais), com a mais econômica **e segura** no topo.
  - **Manutenção** — manutenção preditiva por componente (pneus/freios/suspensão/motor) com alertas por severidade.
- **http://localhost:8000/app?demo=1** — **demonstração pública** (Triângulo Mineiro/MG), sem cadastro: conecta, semeia frota de exemplo e carrega uma rota de exemplo.
- **http://localhost:8000/admin** — [painel de leads](web/admin.html) (token de admin).

## Frota, manutenção e dashboard

Veículos ficam na tabela `vehicles` ([db.py](agroroute/db.py)); a manutenção preditiva ([fleet.py](agroroute/fleet.py)) calcula desgaste% por componente e severidade (faixas 50/75/90). Endpoints: `GET /v1/fleet` (frota + resumo), `POST /v1/fleet` (adicionar), `GET /v1/dashboard` (KPIs agregados + rotas recentes). Cada cálculo de rota é registrado em `route_logs` para alimentar o dashboard.

## 4 rotas possíveis

`RouteJob.max_alternatives=4` por padrão. O roteirizador devolve as alternativas que consegue (OSRM público até 3, GraphHopper conforme o grafo) e o serviço completa até 4 com **desvios reais** por ponto intermediário (waypoints deslocados perpendicularmente à linha origem→destino), deduplicando por distância. Rotas que violam zona urbana nunca vencem uma segura no ranking.

## Machine Learning ([ml.py](agroroute/ml.py))

- **FuelCalibrator** — mínimos quadrados que calibra o modelo de consumo por veículo a partir da telemetria (litros previstos × reais); fecha o loop de aprendizado. `POST /v1/ml/fuel-calibrate`.
- **MaintenanceRiskModel** — regressão logística (scikit-learn) que estima a probabilidade de intervenção por componente; pesos padrão calibrados por domínio, re-treinável. `GET /v1/ml/maintenance-risk`.
- **DemandForecaster** — previsão de demanda diária de rotas (tendência + sazonalidade semanal). `GET /v1/ml/demand-forecast`.

## Pesquisa Operacional ([or_opt.py](agroroute/or_opt.py))

Otimização **multi-origem/multi-destino** sobre o custo real de rota. `POST /v1/optimize` resolve o **problema de transporte** (quanto enviar de cada talhão para cada usina ao menor custo, via `scipy.linprog`) e dimensiona o nº de viagens; há também **atribuição** de rotas a veículos (algoritmo húngaro). É o "calcular várias rotas ao mesmo tempo" com decisão ótima de alocação.

## Integração de dados / telemetria ([ingest.py](agroroute/ingest.py))

Recebe telemetria de **qualquer sistema** — bruta ou de provedores — normalizando para um modelo canônico que alimenta a inteligência automaticamente. Baseado nos esquemas reais das extrações Solinftec.

- **Solinftec pronto** — mapeamentos embutidos para `SOL_TELEMETRIA`, `HORAS_GERENCIAIS`/`SOL_GERENCIAIS` e `SGPA_ALARMES` (Flow API `flow-api.saas-solinftec.com`).
- **Qualquer sistema** — um `mapping` de campos (origem → canônico) conecta qualquer ERP/telemetria/banco.
- **Formas de conexão**: push/webhook (`POST /v1/ingest/telemetry` · `/v1/ingest/alarms`), pull HTTP (`POST /v1/connectors` + `/v1/connectors/{id}/sync`, com auth bearer/header/query/basic), ou **arquivo** CSV/XLSX (`POST /v1/ingest/file`).
- `GET /v1/ingest/stats` · `GET /v1/ingest/providers` · página **Integrações** no app (upload, conectores, telemetria recente).
- Quando há telemetria ingerida, `GET /v1/intel/overview` passa a usar os **dados reais** (verificado com extrações Solinftec: 100 registros, 7 equipamentos).

## Inteligência de frota ([intelligence.py](agroroute/intelligence.py))

Painel completo de inteligência operacional (página **Inteligência** no app), calculado de verdade e ancorado nos modelos de ML — telemetria determinística por tenant. `GET /v1/intel/overview` entrega:

- **KPIs de manutenção** — disponibilidade, MTBF, MTTR, % corretiva, custo de paradas.
- **KPIs de telemetria** — score de condução, eficiência, operadores agressivos, variação de consumo.
- **Alertas inteligentes** — detecção de anomalias (consumo, frenagem, temperatura, ociosidade, score) com os limiares do dashboard v8.
- **Alertas preditivos** — probabilidade de falha por veículo (via `MaintenanceRiskModel`), com recomendação e prazo.
- **Manutenção preventiva** — cronograma de intervenções (componente crítico, dias até intervenção, prioridade, custo estimado).
- **Períodos críticos**, **mapa de risco por frente** (heatmap), **impacto financeiro** (ociosidade/consumo/manutenção) e **avaliação de mecânicos e fornecedores** (scoring).

## Agente analítico ([assistant.py](agroroute/assistant.py))

Chatbot flutuante (ícone no canto inferior do app) que responde sobre a operação — frota, manutenção (com risco por ML), rotas/economia, previsão de demanda, plano/uso e otimização — computando as respostas sobre os **dados reais do tenant**. Determinístico e offline (`POST /v1/assistant`), com gancho opcional para LLM.

## Precificação por uso ([pricing.py](agroroute/pricing.py))

O custo ao cliente é dimensionado por **veículos, rotas, origens e destinos** — cada unidade com markup ≥ 5× (margem bruta ≥ 80%). `POST /v1/billing/quote` (público) alimenta a calculadora da landing. Ver **[BUSINESS_CASE.md](BUSINESS_CASE.md)** para o modelo de custos, a análise da meta de 80% e o P&L.

## Banco de dados

Fonte de verdade em SQLAlchemy ([db.py](agroroute/db.py)) — tabelas `tenants`, `subscriptions`, `leads`.
Padrão: **SQLite** em `data/nokahi.db` (zero infraestrutura). Na 1ª execução, `data/tenants.json` é
carregado para o banco (idempotente). Produção: aponte `DATABASE_URL` para PostgreSQL
(`postgresql://user:pass@host/nokahi`) — mesmo schema, criado no boot. Aceita
também `postgres://` (Railway/Heroku) — normalizado automaticamente.

## Assinatura mensal (billing) — ativar cobrança real

Planos com recorrência mensal e cota de rotas ([billing.py](agroroute/billing.py)): Essencial R$ 1.990 (1.000 rotas/mês), Profissional R$ 4.990 (10.000), Enterprise sob consulta. Todo tenant novo ganha **14 dias de trial**; sem assinatura vigente ou com a cota estourada, os endpoints de cálculo respondem **402** e o app mostra o CTA de planos.

Passo a passo para ligar o Stripe de verdade:

```powershell
copy .env.example .env
# 1) cole a Secret Key em .env  (STRIPE_SECRET_KEY=sk_live_... ou sk_test_...)
python -m agroroute.stripe_setup            # cria produtos + prices mensais em BRL e grava os price IDs no .env
#    opcional, cria o endpoint de webhook e grava o signing secret:
python -m agroroute.stripe_setup --webhook-url https://api.suaempresa.com/v1/billing/webhook
# 2) no painel do Stripe, aponte o webhook para POST /v1/billing/webhook (eventos: checkout.session.completed,
#    invoice.paid, invoice.payment_failed, customer.subscription.deleted) e cole o whsec_... em STRIPE_WEBHOOK_SECRET
uvicorn agroroute.api:app --port 8000       # reinicie para carregar o .env
```

- O checkout vira uma Stripe Checkout Session `mode=subscription`; o webhook (com **assinatura HMAC verificada**) trata ativação, renovação mensal (`invoice.paid`), inadimplência e cancelamento.
- Com `STRIPE_SECRET_KEY` presente e **sem** `STRIPE_WEBHOOK_SECRET`, o webhook é recusado (segurança) e o atalho sandbox `dev/activate` fica indisponível.
- **Sem Stripe** (dev): modo sandbox — o checkout devolve uma URL local que ativa a assinatura na hora.

## Demonstração pública (Triângulo Mineiro / MG)

O tenant `demo-mg` ([data/tenants.json](data/tenants.json), `is_demo`) dá uma degustação sem cadastro na região canavieira de MG (Uberaba, Frutal, Delta, Conceição das Alagoas…). Usa OSRM (cobre o Brasil todo), assinatura demo perene com cota de 300 rotas/mês. `GET /v1/demo/config` entrega a chave pública e uma rota de exemplo; a landing e o `/app?demo=1` fazem a conexão automática. Em produção, aponte o `graphhopper_url` do tenant demo para um GraphHopper com o extrato de MG.

## Leads (formulário de contato) e painel admin

O formulário da landing (`POST /v1/leads`, público, com honeypot + rate-limit por IP) grava na tabela `leads`.
O time comercial vê tudo em **/admin** (`GET /v1/admin/leads`, header `X-Admin-Token` = `AGROROUTE_ADMIN_TOKEN`),
podendo marcar status (novo → contatado → qualificado → descartado). Contato: **contato@nokahi.com**.

Exemplo de chamada:

```bash
curl -X POST http://localhost:8000/v1/routes/batch \
  -H "X-API-Key: sajb-dev-key-troque-em-producao" -H "Content-Type: application/json" \
  -d '{"jobs":[{"job_id":"talhao-42","origin_lat":-21.05,"origin_lon":-48.15,
       "dest_lat":-21.3437,"dest_lon":-48.3051,"vehicle_id":"rodotrem",
       "occupancy":1.0,"round_trip":true,"climate":"auto","max_alternatives":3}]}'
```

A resposta traz, por alternativa: geometria real completa, km, subida/descida, km por superfície, praças de pedágio cruzadas, violações urbanas e o custo aberto (litros, R$ combustível, R$ pedágio, R$ manutenção, k de clima aplicado).

Tenants são configurados em [data/tenants.json](data/tenants.json) (`AGROROUTE_TENANTS` para outro caminho).

## GraphHopper self-hosted (roteirização truck de verdade)

O OSRM público usa perfil de **carro**; o GraphHopper self-hosted em [graphhopper/](graphhopper/) resolve isso. Já vem configurado com:

- **Perfil `truck`** ([nokahi_truck.json](graphhopper/data/custom_models/nokahi_truck.json)): bloqueia vias com limite legal de peso/altura/largura abaixo do CVC, evita ruas residenciais, reduz velocidade em cascalho/terra.
- **Elevação SRTM embutida no grafo** — a resposta já vem 3D (sem chamadas externas por rota).
- **Superfície por trecho** (`details=[surface]`, tags OSM) — o custo diferencia asfalto/cascalho/terra de verdade.
- **Custom model por requisição** (modo flexível, sem CH): o Despaxa Agro injeta o PBT do veículo (`max_weight < PBT → bloqueado`) e as zonas urbanas do tenant como `areas` com prioridade ~0 — as alternativas retornadas **já desviam** das cidades.

### Rodar localmente (sem Docker, JRE portátil incluído)

```powershell
cd graphhopper
# 1ª vez: baixa OSM de SP (~360 MB) se ainda não existir em data/
#   https://download.openstreetmap.fr/extracts/south-america/brazil/southeast/sao-paulo-latest.osm.pbf
.\jre\bin\java.exe -Xmx6g -Xms2g -jar graphhopper-web-11.0.jar server config-local.yml
# 1ª execução importa o grafo (5–15 min) e baixa tiles SRTM; depois sobe em segundos
```

O tenant SAJB já aponta para `http://localhost:8989` (`graphhopper_url` em tenants.json). Se o GraphHopper estiver fora do ar, o serviço **degrada automaticamente para OSRM** (a resposta indica `osrm (fallback)`).

### Produção (Docker)

[graphhopper/docker-compose.yml](graphhopper/docker-compose.yml) — mesmo config; para o Brasil inteiro troque o pbf por `brazil-latest.osm.pbf` (Geofabrik, ~1,6 GB) e suba `JAVA_OPTS=-Xmx12g`. **Estradas particulares das usinas**: mesclar o shape das vias internas ao OSM antes do import (ou manter `access=private` e liberar por tenant via custom model).

**OpenTopoData self-hosted** com SRTM/Copernicus segue recomendado para o caminho OSRM/fallback (elimina o rate-limit de 1 req/s).

## Roadmap sugerido

- Tenants em PostgreSQL + PostGIS com row-level security; zonas restritas como polígonos reais (limites municipais IBGE) em vez de círculos.
- Pedágio: importador da base aberta ANTT/ARTESP + free-flow (pórticos sem praça); validar sentido de cobrança.
- Clima por **segmento** (grade de chuva) em vez de ponto médio — relevante em rotas > 80 km.
- Calibração contínua: comparar litros previstos × telemetria/CAN bus e reajustar R₀/α por frota (fechando o loop de aprendizado).
- Cache de rotas (mesmo OD + veículo) e fila (Celery/ARQ) para lotes de milhares de talhões no início da safra.
- Velocidade média por classe de via → custo de tempo/oportunidade (R$/h do conjunto) no ranking.
- AET (Autorização Especial de Trânsito): validar rota contra trechos liberados por DER/DNIT para cada CVC.
