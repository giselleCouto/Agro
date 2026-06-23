# Modelo Matemático — CanaRoute

## 1. Modelo de Consumo de Combustível

### Fórmula Principal

```
F_ida = (R₀ + α · min(slope, 6%)) × D × PBT × f_clima × f_via
F_volta = (R₀ + α · min(slope, 6%)) × D × PBT_vazio × f_clima × f_via
F_total = F_ida + F_volta
```

### Parâmetros Calibrados

| Parâmetro | Valor | Unidade | Descrição |
|-----------|-------|---------|-----------|
| R₀ | 0,0030 | L/(km·t) | Consumo base em terreno plano |
| α | 0,0040 | L/(km·t·%) | Coeficiente de inclinação |
| slope_clip | 6 | % | Limite máximo de inclinação considerado |
| PBT_vazio | 0,40 × PBT | t | Tara do veículo (40% do PBT) |
| Preço diesel | 6,00 | R$/L | Preço médio diesel S10 |

### Fatores Climáticos (f_clima)

| Cenário | f_clima | Composição |
|---------|---------|------------|
| Seco | 1,000 | Condição ideal |
| Úmido | 1,080 | Chuva leve, solo úmido |
| Molhado | 1,150 | Chuva moderada |
| Enlameado | 1,300 | Solo comprometido |
| Severamente enlameado | 1,500 | Intransitável em tracks |
| **Safra-Mix** | **1,069** | 50%×1,0 + 30%×1,08 + 15%×1,15 + 5%×1,30 |

### Fatores por Tipo de Via (f_via)

| Tipo de Via | f_via | Justificativa |
|-------------|-------|---------------|
| primary | 1,00 | Asfalto bom, sem restrição |
| secondary | 1,02 | Asfalto, curvas mais frequentes |
| tertiary | 1,05 | Asfalto/cascalho, irregularidades |
| unclassified | 1,10 | Cascalho/terra, resistência ao rolamento |
| track | 1,20 | Terra/areia, alta resistência |

## 2. Perfil Altimétrico

### Fonte de Dados
- SRTM 30m (Shuttle Radar Topography Mission)
- API: opentopodata.org/v1/srtm30m
- Resolução: ~30m horizontal, ~1m vertical

### Cálculo de Inclinação

```
slope_i = |elev[i+1] - elev[i]| / dist_horizontal[i] × 100%
slope_avg = mean(slope_i para todos os segmentos)
slope_max = max(slope_i)
slope_clipped = min(slope_avg, 6%)
```

### Ganho/Perda Altimétrica

```
elevation_gain = Σ max(0, elev[i+1] - elev[i])
elevation_loss = Σ max(0, elev[i] - elev[i+1])
```

## 3. Classificação de Vias e Restrição por Veículo

### Largura por Tipo de Via (OSM)

| highway tag | Largura típica | Treminhão (2.6m) | Rodotrem (2.6m) | Pentaminhão (3.2m) |
|-------------|---------------|------------------|-----------------|-------------------|
| primary | ~7m | ✓ LIVRE | ✓ LIVRE | ✓ LIVRE |
| secondary | ~6m | ✓ LIVRE | ✓ LIVRE | ✓ LIVRE |
| tertiary | ~5.5m | ✓ LIVRE | ⚠️ CAUTELA | ⛔ BLOQUEADO |
| unclassified | ~4.5m | ⚠️ CAUTELA | ⛔ BLOQUEADO | ⛔ BLOQUEADO |
| track | ~3.5m | ⚠️ CAUTELA | ⛔ BLOQUEADO | ⛔ BLOQUEADO |

### Velocidade por Tipo de Via e Veículo

| Via | Treminhão | Rodotrem | Pentaminhão |
|-----|-----------|----------|-------------|
| primary | 60 km/h | 55 km/h | 50 km/h |
| secondary | 50 km/h | 45 km/h | 40 km/h |
| tertiary | 40 km/h | 35 km/h | 25 km/h |
| unclassified | 30 km/h | 25 km/h | 20 km/h |
| track | 20 km/h | 15 km/h | 10 km/h |

## 4. Pedágios

### Modelo de Custo

```
custo_pedagio = custo_por_eixo × n_eixos × (2 se bidirecional)
```

| Veículo | Eixos | Custo/praça (bidirecional) |
|---------|-------|---------------------------|
| Treminhão | 7 | R$ 109,20 |
| Rodotrem | 9 | R$ 140,40 |
| Pentaminhão | 11 | R$ 171,60 |

### Detecção de Passagem

Rota cruza pedágio se qualquer ponto da geometria está a menos de 500m da praça:

```
cruza = any(haversine(ponto_rota, praça) < 0.5 km)
```

## 5. Trafegabilidade

### Score por Cenário Climático

```
Score = Σ(score_via_clima × pct_via × f_veiculo) / Σ(pct_via)
```

### Tabela de Scores Base (0-100)

| Via | Seco | Úmido | Molhado | Enlameado | Severo |
|-----|------|-------|---------|-----------|--------|
| primary | 100 | 98 | 95 | 90 | 85 |
| secondary | 100 | 95 | 90 | 80 | 70 |
| tertiary | 95 | 85 | 75 | 60 | 45 |
| unclassified | 85 | 70 | 55 | 35 | 20 |
| track | 70 | 50 | 30 | 10 | 0 |

### Penalidade por Veículo

| Veículo | Fator | Justificativa |
|---------|-------|---------------|
| Treminhão | 1,00 | Referência |
| Rodotrem | 0,85 | Mais pesado, menos manobrável |
| Pentaminhão | 0,70 | Muito pesado, afunda em solo mole |

### Score Safra-Mix

```
Score_safra = Score_seco × 0,50 + Score_umido × 0,30 + Score_molhado × 0,15 + Score_enlameado × 0,05
```

## 6. Tempo de Viagem

### Fórmula

```
T_ida = Σ(dist_segmento / vel_via_veiculo) + T_pedagios
T_volta = T_ida × 0,91  (vazio = 10% mais rápido)
T_total = T_ida + T_volta
T_pedagio = 5 min/praça
```

## 7. Economia

### Por Viagem

```
Economia_viagem = Custo_GPS - Custo_Alternativa
Custo = F_total × Preço_diesel + Custo_pedagios
```

### Projeção Safra

```
Dias_efetivos = 220 × 0,85 = 187 dias
Viagens_dia = 5
Viagens_safra = 187 × 5 = 935 viagens
Economia_safra = Economia_viagem × 935
```

## 8. Validação (Hausdorff)

Distância de Hausdorff entre rota GPS e alternativa:

```
H(A, B) = max(sup_a∈A inf_b∈B d(a,b), sup_b∈B inf_a∈A d(a,b))
```

Se H < 500m → rotas são essencialmente iguais (sem economia real).
Se H > 2km → rotas são significativamente diferentes (potencial economia).
