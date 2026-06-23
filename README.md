# CanaRoute — Sistema de Otimização de Rotas para Transporte de Cana-de-Açúcar

## Visão Geral

CanaRoute é uma plataforma escalável para otimização de rotas de transporte de cana-de-açúcar, projetada para funcionar em **qualquer região do Brasil**. O sistema calcula rotas alternativas considerando:

- **Modelo de consumo calibrado**: F = (R₀ + α·slope) × distância × PBT × f_clima
- **Perfil altimétrico SRTM 30m**: inclinação real dos segmentos
- **Classificação de vias por largura**: primary (7m) → track (3.5m)
- **Restrição por tipo de veículo**: Treminhão (55t), Rodotrem (70t), Pentaminhão (90t)
- **Pedágios por eixo**: custo real por praça
- **Zonas urbanas**: evitar passagem de canavieiros em cidades
- **Trafegabilidade**: score por cenário climático (seco/úmido/molhado/enlameado)
- **Tempo estimado**: velocidade por tipo de via e veículo

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                        CanaRoute                             │
├──────────┬──────────┬──────────┬──────────┬────────────────┤
│ Frontend │ Backend  │ OSRM     │ PostGIS  │ Redis          │
│ (React)  │ (FastAPI)│ (Truck)  │ (DB)     │ (Cache)        │
│ :80      │ :8000    │ :5000    │ :5432    │ :6379          │
└──────────┴──────────┴──────────┴──────────┴────────────────┘
```

## Quick Start

### 1. Pré-requisitos
- Docker + Docker Compose v2
- 8 GB RAM mínimo (OSRM usa ~4 GB para SP)
- 20 GB disco (dados OSM + SRTM)

### 2. Configuração

```bash
# Clonar e configurar
cd canaroute
cp .env.example .env
# Editar .env com suas credenciais
```

### 3. Subir serviços

```bash
# Modo completo (com OSRM local)
docker-compose up -d

# Modo leve (sem OSRM local, usa API pública)
docker-compose up -d postgres redis backend frontend
```

### 4. Acessar

- **Frontend**: http://localhost
- **API Docs (Swagger)**: http://localhost/docs
- **API Base**: http://localhost/api/v1

## Onboarding de Nova Região

### Via API (1 clique)

```bash
curl -X POST http://localhost/api/v1/onboarding/ \
  -H "Content-Type: multipart/form-data" \
  -F "client_name=Usina Nova" \
  -F "client_slug=usina-nova" \
  -F "state=SP" \
  -F "plant_name=Usina Nova" \
  -F "plant_latitude=-21.34" \
  -F "plant_longitude=-48.30" \
  -F "shapefile=@talhoes.zip"
```

O sistema automaticamente:
1. Cria o cliente/região
2. Importa talhões do shapefile (calcula centroides)
3. Detecta zonas urbanas na região (Overpass API)
4. Calcula rotas para todos os talhões × veículos
5. Aplica modelo de consumo com elevação SRTM

### Via Frontend

1. Acesse http://localhost
2. Clique em "Nova Região"
3. Preencha: nome da usina, coordenadas
4. Faça upload do shapefile (ZIP com .shp/.shx/.dbf/.prj)
5. Clique "Processar" → sistema calcula tudo automaticamente

## API REST

### Endpoints Principais

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| GET | `/api/v1/clients/` | Listar clientes/regiões |
| POST | `/api/v1/clients/` | Criar cliente |
| GET | `/api/v1/plants/` | Listar usinas |
| POST | `/api/v1/plants/` | Criar usina |
| GET | `/api/v1/fields/` | Listar talhões |
| POST | `/api/v1/fields/upload-shapefile` | Upload shapefile |
| GET | `/api/v1/vehicles/` | Listar veículos |
| GET | `/api/v1/tolls/` | Listar pedágios |
| GET | `/api/v1/urban-zones/` | Listar zonas urbanas |
| POST | `/api/v1/routes/calculate` | Calcular rota |
| GET | `/api/v1/routes/field/{id}` | Rotas de um talhão |
| GET | `/api/v1/economy/summary` | Resumo de economia |
| GET | `/api/v1/economy/season-projection` | Projeção safra |
| GET | `/api/v1/way/{route_id}` | Gerar arquivo WAY |
| GET | `/api/v1/way/{route_id}/gpx` | Gerar GPX |
| GET | `/api/v1/way/{route_id}/kml` | Gerar KML |
| POST | `/api/v1/onboarding/` | Onboarding completo |
| GET | `/api/v1/onboarding/status/{id}` | Status do onboarding |

### Autenticação

```bash
# Obter token
curl -X POST http://localhost/api/v1/auth/token \
  -d "username=admin&password=admin"

# Usar token
curl -H "Authorization: Bearer <token>" http://localhost/api/v1/fields/
```

## Modelo Matemático

### Consumo de Combustível

```
F = (R₀ + α · slope_clipped) × distância × PBT × f_clima × f_via
```

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| R₀ | 0,0030 L/(km·t) | Consumo base em terreno plano |
| α | 0,0040 L/(km·t·%) | Fator de inclinação |
| slope_clip | 6% | Limite de inclinação |
| f_clima | 1.0–1.5 | Fator climático |
| f_via | 1.0–1.3 | Fator por tipo de via |

### Cenários Climáticos

| Cenário | f_clima | Descrição |
|---------|---------|-----------|
| Seco | 1.00 | Condição ideal |
| Úmido | 1.08 | Chuva leve |
| Molhado | 1.15 | Chuva moderada |
| Enlameado | 1.30 | Solo comprometido |
| Severo | 1.50 | Intransitável em tracks |
| Safra-Mix | 1.069 | 50% seco + 30% úmido + 15% molhado + 5% enlameado |

### Veículos

| Veículo | PBT | Eixos | Comprimento | Largura | Vias Permitidas |
|---------|-----|-------|-------------|---------|-----------------|
| Treminhão | 55t | 7 | ~20m | 2.6m | Todas (track com cautela) |
| Rodotrem | 70t | 9 | ~25m | 2.6m | Secondary+ (tertiary com cautela) |
| Pentaminhão | 90t | 11 | ~30m | 3.2m | Primary/Secondary apenas |

### Trafegabilidade (Score q10)

```
Score = Σ(score_via × pct_via × f_veiculo × f_clima) / Σ(pct_via)
```

Ponderado por distância, com percentil q10 para cenário pessimista.

## Estrutura do Projeto

```
canaroute/
├── docker-compose.yml          # Orquestração de serviços
├── .env.example                # Template de configuração
├── README.md                   # Esta documentação
│
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── migrations/
│   │   └── init.sql            # Schema PostgreSQL + PostGIS
│   └── app/
│       ├── main.py             # FastAPI app
│       ├── core/
│       │   ├── config.py       # Settings (Pydantic)
│       │   └── database.py     # SQLAlchemy async
│       ├── models/             # SQLAlchemy models
│       │   ├── client.py
│       │   ├── plant.py
│       │   ├── farm.py
│       │   ├── field.py
│       │   ├── vehicle.py
│       │   ├── toll_plaza.py
│       │   ├── urban_zone.py
│       │   └── route.py
│       ├── schemas/            # Pydantic schemas
│       │   ├── client.py
│       │   ├── plant.py
│       │   ├── field.py
│       │   ├── vehicle.py
│       │   ├── toll.py
│       │   ├── urban_zone.py
│       │   ├── route.py
│       │   ├── economy.py
│       │   └── onboarding.py
│       ├── routers/            # API endpoints
│       │   ├── health.py
│       │   ├── clients.py
│       │   ├── plants.py
│       │   ├── fields.py
│       │   ├── vehicles.py
│       │   ├── tolls.py
│       │   ├── urban_zones.py
│       │   ├── routes.py
│       │   ├── economy.py
│       │   ├── onboarding.py
│       │   └── way_files.py
│       └── services/           # Business logic
│           ├── route_calculator.py
│           ├── shapefile_processor.py
│           ├── way_generator.py
│           ├── urban_detector.py
│           └── onboarding_service.py
│
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   └── index.html              # SPA (React-like vanilla JS)
│
└── scripts/
    ├── seed_data.py            # Popular dados iniciais
    ├── download_osm.sh         # Baixar dados OSM da região
    └── onboard_region.py       # Script CLI de onboarding
```

## Deploy em Produção

### AWS (recomendado)

```bash
# EC2 t3.xlarge (4 vCPU, 16 GB RAM)
# EBS 50 GB gp3
# Região: sa-east-1

# Instalar Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu

# Deploy
git clone <repo> && cd canaroute
cp .env.example .env
# Editar .env
docker-compose up -d
```

### Custos estimados (AWS sa-east-1)

| Recurso | Custo/mês |
|---------|-----------|
| EC2 t3.xlarge | R$ 850 |
| EBS 50 GB | R$ 50 |
| Backup S3 | R$ 20 |
| **Total** | **R$ 920/mês** |

## Licença

Proprietário — Uso exclusivo do cliente.
