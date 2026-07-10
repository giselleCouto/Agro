# NOKAHI AgroRoute — Business Case

_Roteirização econômica multi-tenant para o transporte canavieiro — cobertura Brasil inteiro._
_Valores em BRL. Premissas base 2025/2026; câmbio ~R$ 5,40/USD. Fontes ao final._

> **Conclusão executiva (leia primeiro).** A meta de **80% de lucro líquido é matematicamente
> inviável no Brasil**: só **impostos (~17,5%) + taxas de pagamento (~4,7%) já consomem ~22% da
> receita**, antes de qualquer servidor ou salário. O teto teórico de margem líquida deste negócio
> é **~63,5%**. O que É atingível — e é o que "80%" normalmente significa em SaaS — é **margem
> BRUTA ≥ 80%** (receita menos hospedagem+suporte). Os preços foram calibrados para isso. A margem
> **líquida** saudável (25–35%) depende de **volume de clientes** para diluir o time fixo, não de preço.

---

## 1. O produto e o mercado

A NOKAHI encontra, para cada viagem talhão→usina, a rota de **menor custo real** (combustível por
rampa/peso/superfície/clima, pedágio por eixo e manutenção), respeitando as restrições dos CVCs
(treminhão/rodotrem/pentatrem) e as condições de cada dia. ROI típico por usina: **R$ 200 mil a
R$ 1,2 milhão/ano** em diesel economizado (base −23%).

| Dimensão | Número | Fonte |
|---|---|---|
| Moagem de cana 2024/25 | 676,96 Mt (2ª maior da história) | CONAB |
| Usinas/plantas no Brasil | ~380 (261 operando no Centro-Sul) | UNICA |
| Gasto setorial só com transporte de cana | ~R$ 9 bi/ano (CCT total R$ 20–25 bi) | UNICA/estudos CCT |
| Frota pesada dedicada (CVCs) | ~12–18 mil unidades | estimativa (moagem ~2× vs. 2008) |
| SaaS de roteirização/telemetria no BR | R$ 50–120/veículo/mês | Glassdoor/mercado |

**TAM / SAM / SOM** (base preço-âncora R$ 15 mil/usina/mês = R$ 180 mil/usina/ano):

- **TAM** — 380 usinas × R$ 180 mil = **~R$ 68 mi/ano**.
- **SAM** — 261 usinas operando no Centro-Sul × R$ 180 mil = **~R$ 47 mi/ano**.
- **SOM (Ano 3)** — 35 usinas = **~R$ 6,3 mi/ano** (~9% do TAM).

---

## 2. Estrutura de custos

### 2.1 Custo FIXO anual — **R$ 2.378.000** (independe do nº de clientes)

| Bloco | R$/ano | Nota |
|---|---:|---|
| **Pessoal** (8 posições, custo-empresa) | 1.848.000 | ~R$ 154 mil/mês; encargos CLT ~1,75× já embutidos (13º, férias, FGTS, INSS patronal, benefícios) |
| **Infra cloud base** (AWS sa-east-1) | 230.000 | Cai para ~R$ 160 mil/ano com Savings Plans/Reserved Instances |
| Ferramentas/SaaS internos | 60.000 | GitHub, observabilidade, comunicação, design |
| Jurídico + contábil (BPO) | 60.000 | Recorrente + pontual |
| Marketing/comercial fixo | 180.000 | Eventos setoriais, conteúdo, viagens de venda |
| **TOTAL FIXO** | **2.378.000** | Pessoal = ~78% do fixo — é a variável de decisão real |

**Time mínimo viável (8 posições):** backend sênior, engenheiro de dados/GIS, SRE/DevOps, frontend,
produto/PM, comercial, suporte/CS e fundador/admin parcial. É o mínimo para manter e evoluir um SaaS
B2B com componente pesado de dados/GIS e cobertura nacional.

### 2.2 Infra cloud — detalhe (produção, AWS São Paulo, 2 instâncias de redundância)

Total base **~R$ 19,2 mil/mês (~R$ 230 mil/ano)**; faixa R$ 9,9 mil–43,8 mil/mês. Maior item: a
**RAM alta do GraphHopper** (grafo de todo o Brasil, 64 GB/instância) + **RDS Multi-AZ**.

| Item | R$/mês (base) |
|---|---:|
| GraphHopper self-hosted (Brasil inteiro, 2× 64 GB RAM) | 6.340 |
| PostgreSQL gerenciado (RDS Multi-AZ) + storage | 4.100 |
| Servidores de aplicação (FastAPI, 2×) | 2.070 |
| Cache + fila (ElastiCache + SQS) | 1.350 |
| OpenTopoData self-hosted (SRTM/Copernicus) | 1.200 |
| Egress / banda (sa-east-1 = egress mais caro da AWS) | 810 |
| Armazenamento (EBS grafo/OSM/DEM + S3) | 810 |
| Observabilidade (logs/métricas/alertas) | 810 |
| NAT Gateway / rede VPC | 520 |
| Backups (snapshots RDS/EBS) | 430 |
| CDN (CloudFront) | 380 |
| Balanceador (ALB + LCUs) | 190 |
| DNS/segredos/registro (Route 53, Secrets, ECR) | 160 |
| **Total** | **~19.180** |

### 2.3 Custo VARIÁVEL por usina-cliente — **R$ 26.000/ano** (~R$ 2.170/mês)

| Item | R$/usina/ano |
|---|---:|
| Cloud incremental (rotas/dia, storage, egress, cache) | 18.000 |
| Suporte/onboarding incremental (integração, viagens) | 8.000 |
| **Subtotal opex variável** | **26.000** |

### 2.4 Impostos + taxas — **~22% da receita** (escala com preço, não com nº de clientes)

- **Até R$ 4,8 mi/ano (Anos 1–2):** Simples Nacional **Anexo III** com Fator R ≥ 28% → DAS efetivo
  **~19,6%** (embute ISS, PIS, COFINS, IRPJ, CSLL e CPP da folha num único imposto). O time enxuto
  naturalmente mantém folha ≥ 28% da receita.
- **Acima de R$ 4,8 mi/ano (Ano 3):** Simples é vedado → **Lucro Presumido**, tributos efetivos
  **~17–19%** (ISS 2–5% + PIS/COFINS 3,65% + IRPJ + CSLL sobre base presumida de 32%). Atenção: no
  Presumido a folha (CPP ~20% + FGTS) é paga à parte — já contabilizada em Pessoal.
- **Taxas de pagamento (Stripe):** ~4,7% (cartão nacional 3,99% + billing 0,7%). **Migrar para Pix
  (1,19%)** derruba para ~2% — é a alavanca de margem mais fácil.
- **Carga efetiva total recomendada: ~22% da receita** (17,5% tributos + 4,7% taxas).

---

## 3. Por que 80% de lucro líquido é impossível — e o que é possível

Margem líquida de 80% exige **custos totais ≤ 20% da receita**. Mas **impostos + taxas já são ~22%
da receita** — o teto de 20% é estourado pela Receita Federal + adquirente **antes** de pagar uma
pessoa ou um servidor. A equação `(0,20 − 0,22) × Receita ≥ Custo Fixo` tem coeficiente **negativo**:
**nenhum preço ou volume** a resolve.

- **Teto teórico de margem líquida** (fixo diluído em N→∞, Pix, preço no topo): **~63,5%**.
- **"80%" atingível = margem BRUTA** (receita − hospedagem − suporte): **80–86%** nos preços abaixo.

| Métrica | Definição | NOKAHI |
|---|---|---|
| Margem **bruta** | (Receita − infra − suporte) / Receita | **80–86%** ✅ (meta reinterpretada) |
| Margem de contribuição pós-impostos | (Receita − variável − impostos − taxas) / Receita | ~60–63% |
| Margem **líquida** (após time fixo) | Lucro / Receita | −201% (Y1) → +26–30% (Y3) |

---

## 4. Preços — calibrados para margem bruta ≥ 80%

Custo variável direto por usina ≈ **R$ 2.170/mês**. Para **margem bruta ≥ 80%**, o preço-piso é
`2.170 / 0,20 ≈ R$ 10.850/mês`. Preços definidos no produto (`agroroute/billing.py`):

| Plano | Preço/usina/mês | Rotas/mês | Margem bruta | Alvo |
|---|---:|---:|---:|---|
| **Essencial** | **R$ 10.900** | 3.000 | **80,1%** | 1 usina, piloto |
| **Profissional** | **R$ 18.900** | 25.000 | **88,5%** | grupo/multi-usina |
| **Enterprise** | sob consulta | ilimitado | — | grandes grupos, SLA |
| _Demonstração_ | R$ 0 | 300 | — | degustação MG |

**Preço-âncora de venda recomendado: R$ 15–18 mil/usina/mês**, ancorado em % do ROI comprovado
(economia de R$ 200 mil–1,2 mi/ano por usina sustenta com folga; WTP de mercado R$ 6–40 mil/mês).

---

## 5. Projeção de resultado (P&L) — preço-âncora R$ 15 mil/usina/mês

| Ano | Usinas | Receita | Custo fixo | Custo variável | Impostos+taxas (22%) | **Resultado líquido** | Margem |
|---:|---:|---:|---:|---:|---:|---:|---:|
| **1** | 5 | 900.000 | 2.378.000 | 130.000 | 198.000 | **−1.806.000** | −201% |
| **2** | 15 | 2.700.000 | 2.378.000 | 390.000 | 594.000 | **−662.000** | −24,5% |
| **3** | 35 | 6.300.000 | 2.378.000 | 910.000 | 1.386.000 | **+1.626.000** | **+25,8%** |

**Preço de break-even (lucro zero) por ano** — evidencia que o gargalo é volume, não preço:

| Ano | Usinas | Preço/usina/mês p/ empatar |
|---:|---:|---:|
| 1 | 5 | R$ 53.600 _(acima do WTP → Y1 é fase de investimento)_ |
| 2 | 15 | R$ 19.700 _(viável, perto do zero)_ |
| 3 | 35 | R$ 10.000 _(folga confortável)_ |

O Ano 1 é **estruturalmente deficitário** (queima de caixa para provar ROI em pilotos) — normal e
esperado. O negócio **respira a partir de ~15–20 usinas**, quando a receita dilui o time fixo.

---

## 6. Recomendações

1. **Reformule a meta interna:** persiga **margem bruta ≥ 80%** (já entregue) e **margem líquida de
   25–35% no regime (Ano 3+)** — padrão best-in-class de SaaS B2B no Brasil. 80% líquido não existe aqui.
2. **O caminho para lucro é volume + preço-prêmio**, não corte de custo — o time já é o mínimo viável.
   Cada usina nova é altamente lucrativa na margem (contribuição ~60% pós-impostos); o desafio é
   **fechar 15→35 contratos** para amortizar o fixo.
3. **Alavancas de margem controláveis:**
   - **Pix** em vez de cartão: −3,5 p.p. de custo sobre a receita (a mais fácil).
   - **Savings Plans/RI na AWS**: −~R$ 70 mil/ano no fixo.
   - **Fator R ≥ 28%** para permanecer no Simples Anexo III enquanto a receita permitir.
4. **Precificar por valor (% do ROI)**, não por custo: com economia comprovada de R$ 200 mil–1,2 mi/ano,
   R$ 15–18 mil/mês é uma fração pequena do ganho do cliente.

---

## Fontes

Custos AWS sa-east-1: aws-pricing.com, DoiT Compute, AWS pricing (RDS/EC2/ELB/S3/EBS/CloudFront/
ElastiCache/VPC/CloudWatch). Salários: Glassdoor BR, Robert Half Guia Salarial 2026, salario.com.br,
PM3/Tera. Tributação: Simples Nacional (LC 123/2006, Anexos III/V, Fator R), Lucro Presumido (RFB);
Stripe Brasil (pricing). Mercado: CONAB (moagem 2024/25), UNICA (usinas Centro-Sul), estudos de CCT.

> Estimativas de planejamento com faixas low/base/high; validar com contador e cotações AWS antes de
> decisões financeiras. Câmbio e preços de cloud variam.
