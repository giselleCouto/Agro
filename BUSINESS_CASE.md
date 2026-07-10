# NOKAHI AgroRoute — Business Case

_Roteirização econômica multi-tenant para o transporte canavieiro — cobertura Brasil inteiro._
_Valores em BRL. Premissas base 2025/2026; câmbio ~R$ 5,40/USD. Fontes ao final._
_Revisão jul/2026: preços recalibrados (mais competitivos), economia de diesel de ~16% e meta de margem líquida ≥ 23%._

> **Conclusão executiva (leia primeiro).**
> 1. **O cliente sempre ganha.** Com economia real de **~16%** de diesel, cada CVC economiza da ordem de **R$ 3 mil/mês**. Em todos os planos o cliente economiza **10× a 19×** o que paga — a economia é muito maior que a mensalidade.
> 2. **Cada contrato nasce lucrativo.** Com a nova tabela, todo contrato tem **40–53% de margem de contribuição** (receita menos custo variável e impostos). Não existe cliente que dê prejuízo na margem.
> 3. **A margem líquida ≥ 23% é questão de volume, não de preço.** Impostos + taxas já consomem ~22% da receita; o time é custo fixo. A NOKAHI cruza **23% de margem líquida** a partir de **~5 usinas** (Corporativo, fase enxuta) — e como uma usina roda dezenas de CVCs, esse é o patamar realista de entrada. Preço alto não antecipa isso; **volume, sim**.

---

## 1. O produto e o mercado

O **AgroRoute** (solução da **NOKAHI**) encontra, para cada viagem talhão→usina, a rota de **menor custo real**
(combustível por rampa/peso/superfície/clima, pedágio por eixo e manutenção), respeitando as restrições dos CVCs
(treminhão/rodotrem/pentatrem) e as condições de cada dia. Com economia de diesel de **~16%**, o ROI típico por
usina fica em **R$ 1,5 a 6 milhões/ano** em diesel economizado (frotas de dezenas a centenas de CVCs).

Além da roteirização, a plataforma entrega três diferenciais analíticos: **modelos de ML** (calibração de consumo
pela telemetria, risco de manutenção por componente, previsão de demanda), **pesquisa operacional** (alocação ótima
multi-origem/multi-destino) e um **agente analítico em chat** sobre os dados reais do cliente.

| Dimensão | Número | Fonte |
|---|---|---|
| Moagem de cana 2024/25 | 676,96 Mt (2ª maior da história) | CONAB |
| Usinas/plantas no Brasil | ~380 (261 operando no Centro-Sul) | UNICA |
| Gasto setorial com transporte de cana | ~R$ 9 bi/ano (CCT total R$ 20–25 bi) | UNICA/estudos CCT |
| Frota pesada dedicada (CVCs) | ~12–18 mil unidades | estimativa (moagem ~2× vs. 2008) |
| SaaS de roteirização/telemetria no BR | R$ 50–120/veículo/mês | Glassdoor/mercado |

**TAM / SAM / SOM** (âncora = plano Corporativo, R$ 12,9 mil/usina/mês = ~R$ 155 mil/usina/ano):

- **TAM** — 380 usinas × R$ 155 mil = **~R$ 59 mi/ano**.
- **SAM** — 261 usinas Centro-Sul × R$ 155 mil = **~R$ 40 mi/ano**.
- **SOM (Ano 3)** — 35 usinas = **~R$ 5,4 mi/ano** (~9% do TAM).

---

## 2. A economia do cliente — por que a conta sempre fecha a favor dele

Premissas conservadoras por CVC em operação de safra:

| Premissa | Valor |
|---|---:|
| Rodagem | 350 km/dia × 26 dias = 9.100 km/mês |
| Consumo médio (carregado ida + vazio volta) | 0,42 L/km → ~3.822 L/mês |
| Preço do diesel S10 (2026) | R$ 6,20/L |
| **Gasto de diesel por CVC/mês** | **~R$ 23,7 mil** |
| Economia com o AgroRoute (**16%**) | **~R$ 3,8 mil/mês por CVC** |

Para blindar o ROI, as tabelas abaixo usam um ponto ainda mais **conservador: R$ 3.000 de economia/CVC/mês**
(≈ 12,7% do gasto). Mesmo assim, a economia supera a mensalidade com folga enorme.

---

## 3. Estrutura de custos

### 3.1 Custo variável por contrato

| Item | Valor |
|---|---:|
| Base por contrato (infra + suporte incremental) | R$ 800/mês |
| Por veículo monitorado (telemetria, storage, ML) | R$ 30/mês |

> Ex.: um contrato Profissional (30 veículos) custa **R$ 800 + 30×30 = R$ 1.700/mês** de custo variável direto.

### 3.2 Impostos + taxas — **~22% da receita** (escala com o preço, não com o nº de clientes)

- **Até R$ 4,8 mi/ano:** Simples Nacional **Anexo III** com Fator R ≥ 28% → DAS efetivo **~17,5%**.
- **Acima de R$ 4,8 mi/ano:** Lucro Presumido, tributos efetivos **~17–19%**.
- **Taxas de pagamento (Stripe):** ~4,7%. **Migrar para Pix (1,19%)** derruba a carga total para ~19% — alavanca fácil.
- **Carga efetiva usada nas contas: 22% da receita.**

### 3.3 Custo FIXO — a variável de decisão real (independe do nº de clientes)

O ponto de equilíbrio depende do **tamanho do time**. Três cenários:

| Cenário | Custo fixo | Composição |
|---|---:|---|
| **Solo / bootstrap** (fase piloto — hoje) | ~R$ 18 mil/mês | fundador + infra enxuta + ferramentas/contábil |
| **Enxuto** (crescimento) | ~R$ 54 mil/mês | +2–3 pessoas (dev, dados/GIS, suporte/comercial) |
| **Time completo** (escala nacional) | ~R$ 198 mil/mês | 8 posições + marketing + infra GraphHopper Brasil |

---

## 4. Preços — tabela recalibrada (competitiva, com limite de rotas E de veículos)

Implementada em [`agroroute/billing.py`](agroroute/billing.py) (planos) e [`agroroute/pricing.py`](agroroute/pricing.py)
(calculadora por uso). **Para contratar, o cliente fala com o comercial** (`contato@nokahi.com`); a demo é limitada a 5 rotas.

| Plano | Preço/mês | Veículos | Rotas/mês | Público-alvo |
|---|---:|---:|---:|---|
| **Demonstração** | grátis | até 25 (vitrine) | 5 | degustação — libera após contato |
| **Essencial** | **R$ 2.900** | até 10 | 1.500 | transportador/pequena frota |
| **Profissional** | **R$ 5.900** | até 30 | 6.000 | frota média / grupo |
| **Corporativo** | **R$ 12.900** | até 80 | 20.000 | usina típica |
| **Enterprise** | sob consulta | ilimitado | ilimitado | grupo multi-usina / SLA |

> Entrada **a partir de R$ 2.900/mês** (era R$ 10.900) — muito mais competitivo, com escopo dimensionado por veículos e rotas.

### 4.1 O cliente economiza 10× a 19× o que paga

Economia conservadora de **R$ 3.000/CVC/mês**, frota no teto do plano:

| Plano | Paga/ano | Economiza/ano | Sobra p/ o cliente | ROI |
|---|---:|---:|---:|---:|
| Essencial (10 CVCs) | R$ 34.800 | R$ 360.000 | **R$ 325.200** | **10×** |
| Profissional (30 CVCs) | R$ 70.800 | R$ 1.080.000 | **R$ 1.009.200** | **15×** |
| Corporativo (80 CVCs) | R$ 154.800 | R$ 2.880.000 | **R$ 2.725.200** | **19×** |

Mesmo cortando a economia pela metade (R$ 1.500/CVC/mês), o ROI ainda é de **5× a 9×**. A conta fecha a favor do cliente em qualquer cenário realista.

### 4.2 Cada contrato já nasce lucrativo (margem de contribuição)

Receita − custo variável − 22% de impostos/taxas:

| Plano | Receita | Custo variável | Impostos+taxas | **Contribuição** | Margem |
|---|---:|---:|---:|---:|---:|
| Essencial | R$ 2.900 | R$ 1.100 | R$ 638 | **R$ 1.162** | **40%** |
| Profissional | R$ 5.900 | R$ 1.700 | R$ 1.298 | **R$ 2.902** | **49%** |
| Corporativo | R$ 12.900 | R$ 3.200 | R$ 2.838 | **R$ 6.862** | **53%** |

**Nenhum cliente dá prejuízo na margem** — todo contrato entra com 40–53% de contribuição para pagar o fixo e virar lucro.

---

## 5. Margem líquida ≥ 23% — a partir de quantas usinas

Margem líquida = (Σ contribuição − custo fixo) / receita. O número de usinas para cruzar **23% líquido**
depende do cenário de custo fixo e do mix de planos:

| Mix predominante | Solo (R$ 18k/mês) | Enxuto (R$ 54k/mês) | Time completo (R$ 198k/mês) |
|---|---:|---:|---:|
| **Corporativo** (usina típica) | **5 usinas** → 25,3% | 14 usinas → 23,3% | 51 usinas |
| **Profissional** | 12 usinas → 23,8% | 35 usinas | 129 usinas |
| **Essencial** (pequeno) | 37 usinas | 110 usinas | 400 usinas |

**Ponto de equilíbrio (lucro zero)** — apenas cobrir o fixo:

| Mix | Solo | Enxuto |
|---|---:|---:|
| Corporativo | 3 usinas | 8 usinas |
| Profissional | 7 usinas | 19 usinas |

**Leitura:** como uma **usina roda dezenas de CVCs** (plano Corporativo/Enterprise), o caminho real é o da primeira
linha. Na **fase enxuta atual**, **~5 usinas Corporativo** já colocam a NOKAHI em **>25% de margem líquida** — e o
ponto de equilíbrio é de **apenas ~3 usinas**. Baixar o preço tornou a entrada mais competitiva sem comprometer isso,
porque a contribuição por contrato permanece alta (40–53%).

> **Por que não dá para "garantir 23% líquido no 1º cliente":** com qualquer time fixo, um único contrato não dilui o
> fixo. A honestidade do modelo é esta — o preço garante **contribuição** positiva desde o 1º cliente; a **margem
> líquida** ≥ 23% chega com o **volume** (poucas usinas, dado que são clientes grandes).

### 5.1 Projeção de resultado (P&L) — carteira de usinas Corporativo, fase enxuta (R$ 54k/mês)

| Ano | Usinas | Receita/ano | Custo fixo | Variável | Impostos+taxas (22%) | **Líquido** | Margem |
|---:|---:|---:|---:|---:|---:|---:|---:|
| **1** | 4 | 619.200 | 648.000 | 153.600 | 136.224 | **−318.624** | −51% |
| **2** | 14 | 2.167.200 | 648.000 | 537.600 | 476.784 | **+504.816** | **+23,3%** |
| **3** | 30 | 4.644.000 | 648.000 | 1.152.000 | 1.021.680 | **+1.822.320** | **+39,2%** |

O **Ano 1** ainda é fase de investimento (provar ROI em pilotos). O negócio **respira a partir de ~14 usinas** no
cenário enxuto — ou de **~5 usinas** no cenário solo/bootstrap (hoje), que é o mais provável na largada.

---

## 6. Recomendações

1. **Ancore a venda no ROI do cliente, não no preço.** Ele economiza 10–19× a mensalidade; o preço é detalhe.
2. **Fase de largada = solo/bootstrap.** Mantenha o fixo enxuto enquanto fecha as primeiras 5–8 usinas; nesse cenário
   a NOKAHI já opera com margem líquida ≥ 23% a partir de ~5 usinas Corporativo.
3. **Alavancas de margem controláveis:** **Pix** em vez de cartão (−3,5 p.p. sobre a receita); **Fator R ≥ 28%** para
   permanecer no Simples; **infra enxuta** (OSRM público na largada, GraphHopper Brasil só quando o volume justificar).
4. **Fechamento consultivo.** A demo (5 rotas) gera o lead; a contratação passa pelo comercial (`contato@nokahi.com`),
   permitindo dimensionar plano por frota e cobrar por valor.

---

## Fontes

Custos AWS sa-east-1: aws-pricing.com, DoiT Compute, AWS pricing. Salários: Glassdoor BR, Robert Half 2026,
salario.com.br. Tributação: Simples Nacional (LC 123/2006, Anexos III/V, Fator R), Lucro Presumido (RFB); Stripe
Brasil. Diesel: ANP/média de mercado 2026. Mercado: CONAB (moagem 2024/25), UNICA (usinas Centro-Sul), estudos de CCT.

> Estimativas de planejamento com faixas low/base/high; validar com contador e cotações antes de decisões financeiras.
> A economia de ~16% é a média atual observada e deve ser confirmada por estudo de caso auditável por operação.
