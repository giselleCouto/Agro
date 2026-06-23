# Guia de Onboarding de Nova Região

## Visão Geral

O CanaRoute foi projetado para que o onboarding de uma nova região/cliente exija o **mínimo esforço possível**. O processo completo leva menos de 5 minutos para regiões com até 500 talhões.

## Pré-requisitos

Para onboarding de nova região, você precisa de:

1. **Shapefile dos talhões** (ZIP contendo .shp, .shx, .dbf, .prj)
   - Cada polígono = 1 talhão
   - Colunas recomendadas: FAZENDA, TALHAO, AREA (ha)
   - Projeção: qualquer (será reprojetado para WGS84)

2. **Coordenadas da usina** (latitude, longitude em WGS84)

3. **Nome do cliente/região**

## Método 1: Via Script CLI (recomendado)

```bash
python scripts/onboard_region.py \
  --name "Usina São José" \
  --state SP \
  --lat -21.3437 \
  --lon -48.3051 \
  --capacity 15000 \
  --shapefile /path/to/talhoes.zip
```

O script executa automaticamente:
1. Cria cliente no banco
2. Cria usina com coordenadas
3. Importa talhões do shapefile (calcula centroides)
4. Detecta zonas urbanas na região (Overpass API/OSM)
5. Calcula rotas para todos os talhões × 3 veículos
6. Aplica modelo de consumo com elevação SRTM

## Método 2: Via API REST

### Passo 1: Criar cliente

```bash
curl -X POST http://localhost:8000/api/v1/clients/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Usina São José", "slug": "usina-sao-jose", "state": "SP"}'
```

### Passo 2: Criar usina

```bash
curl -X POST http://localhost:8000/api/v1/plants/ \
  -H "Content-Type: application/json" \
  -d '{"client_id": 1, "name": "COA", "latitude": -21.3437, "longitude": -48.3051, "capacity_tons_day": 15000}'
```

### Passo 3: Upload shapefile

```bash
curl -X POST http://localhost:8000/api/v1/fields/upload-shapefile \
  -F "client_id=1" \
  -F "file=@talhoes.zip"
```

### Passo 4: Detectar zonas urbanas

```bash
curl -X POST http://localhost:8000/api/v1/urban-zones/detect \
  -H "Content-Type: application/json" \
  -d '{"client_id": 1}'
```

### Passo 5: Calcular todas as rotas

```bash
curl -X POST http://localhost:8000/api/v1/routes/calculate-all \
  -H "Content-Type: application/json" \
  -d '{"client_id": 1, "plant_id": 1}'
```

## Método 3: Via Frontend

1. Acesse http://localhost
2. Menu → "Nova Região"
3. Preencha formulário (nome, coordenadas da usina)
4. Arraste o shapefile para a área de upload
5. Clique "Processar"
6. Aguarde (barra de progresso mostra status)

## O que é feito automaticamente

### Importação de Talhões
- Lê shapefile com GeoPandas
- Detecta colunas automaticamente (FAZENDA, TALHAO, AREA)
- Calcula centroide de cada polígono
- Agrupa por fazenda
- Calcula distância até a usina

### Detecção de Zonas Urbanas
- Consulta Overpass API (OSM) na bounding box dos talhões
- Busca: place=city, place=town, place=village
- Define raio de restrição: city=5km, town=3km, village=1.5km
- Marca como "blocked" ou "caution"

### Cálculo de Rotas
- Para cada talhão × veículo (3 tipos):
  1. Calcula rota OSRM (overview=full, geometries=geojson)
  2. Obtém perfil altimétrico (opentopodata SRTM 30m)
  3. Aplica modelo de consumo (R₀ + α·slope) × dist × PBT × f_clima
  4. Verifica pedágios (proximidade 500m)
  5. Verifica zonas urbanas
  6. Calcula trafegabilidade (score por cenário climático)
  7. Calcula tempo estimado (velocidade por tipo de via)
  8. Armazena resultado no banco (cache)

### Pedágios
- Base inicial: 8 praças da região SP
- Para novas regiões: cadastro manual ou integração futura com base ANTT
- Custo por eixo × número de eixos do veículo × 2 (ida+volta)

## Tempos Estimados

| Etapa | 50 talhões | 500 talhões | 5000 talhões |
|-------|-----------|-------------|--------------|
| Import shapefile | <1s | 2s | 15s |
| Detectar zonas urbanas | 3s | 3s | 3s |
| Calcular rotas (3 veículos) | 2 min | 20 min | 3h |
| **Total** | **~2 min** | **~20 min** | **~3h** |

## Adicionando Pedágios Manualmente

```bash
curl -X POST http://localhost:8000/api/v1/tolls/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Pedágio Guariba SP-322",
    "latitude": -21.355,
    "longitude": -48.228,
    "highway": "SP-322",
    "km_marker": 345,
    "cost_per_axle": 7.80,
    "bidirectional": true
  }'
```

## Adicionando Zonas Urbanas Manualmente

```bash
curl -X POST http://localhost:8000/api/v1/urban-zones/ \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": 1,
    "name": "Guariba",
    "latitude": -21.355,
    "longitude": -48.228,
    "radius_m": 2500,
    "restriction_level": "blocked"
  }'
```

## Recalcular Rotas

Após adicionar novos pedágios ou zonas urbanas:

```bash
curl -X POST http://localhost:8000/api/v1/routes/recalculate \
  -H "Content-Type: application/json" \
  -d '{"client_id": 1, "force": true}'
```

## Exportar Resultados

### Arquivo WAY (Solinftec)
```bash
curl http://localhost:8000/api/v1/way/{route_id} -o rota.way
```

### GPX (GPS)
```bash
curl http://localhost:8000/api/v1/way/{route_id}/gpx -o rota.gpx
```

### KML (Google Earth)
```bash
curl http://localhost:8000/api/v1/way/{route_id}/kml -o rota.kml
```

### Relatório Excel
```bash
curl http://localhost:8000/api/v1/economy/export?client_id=1&format=xlsx -o relatorio.xlsx
```
