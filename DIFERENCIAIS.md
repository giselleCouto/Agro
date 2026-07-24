# Peabiru Agro — Diferenciais competitivos

*Documento de posicionamento. Pesquisa de mercado brasileiro (agronegócio / CCT — Colheita, Carregamento e Transporte de cana) realizada em julho de 2026.*

---

## 1. Posicionamento em uma frase

> **O Peabiru Agro não compete com telemetria — ele consome telemetria.**

O mercado brasileiro de agro/frota inteiro está estruturado para responder *"onde está e como está o veículo"* (localização, CAN, jornada, segurança, rastreabilidade documental da cana). A NOKAHI responde uma pergunta que **nenhum outro player responde de forma nativa**:

> *"Por qual dos caminhos possíveis este CVC gasta menos diesel indo deste talhão para esta usina — cheio na ida, vazio na volta, com esta chuva, neste tipo de piso?"*

A diferença é de **natureza, não de grau**:

| | O mercado | A NOKAHI |
|---|---|---|
| Postura | **Observa** o custo depois que ele acontece | **Prescreve** a rota antes, para o custo não acontecer |
| O que relata | Consumo, km rodado, pedágio pago | 4 rotas rankeadas por custo real, antes de despachar |
| Critério | Distância / tempo / janela / segurança | **Custo físico de diesel** |
| Relação | — | **Complementar**, camada de otimização sobre a de observação |

É o **"Waze econômico" do CCT**: roteirização por custo físico real via modelo calibrado

```
L = (R0 + α · rampa%) · superfície · PBT · Δkm · k_clima
```

devolvendo **4 rotas rankeadas por custo** — não por distância, nem por tempo.

---

## 2. Os 12 diferenciais concretos (cada um contra o que o mercado faz)

### 1. Otimização por custo físico de diesel — não por distância/tempo
RoutEasy, SimpliRoute e Maplink Trip API otimizam menor distância, menor tempo ou janela de entrega. A NOKAHI otimiza **menor custo real de combustível**. Duas rotas com a mesma quilometragem têm custos de diesel radicalmente diferentes se uma tem rampa e piso de terra e a outra é asfalto plano — os roteirizadores urbanos são cegos a isso; a NOKAHI faz disso o critério central.

### 2. Modelo físico de consumo calibrado em telemetria — não km/L estático
As calculadoras de rota-pedágio-frete (Rotas Brasil, Qualp, AILOG) estimam combustível com um **km/L fixo digitado pelo usuário**. A NOKAHI substitui a média estática por um modelo que reage a rampa (via elevação SRTM), PBT, superfície e chuva real, e é **recalibrado por machine learning** contra o consumo observado na frota. Não é uma constante — é uma função do terreno e da carga.

### 3. Assimetria cheio-na-ida / vazio-na-volta
Ninguém no comparativo modela que o CVC pesa dezenas de toneladas na ida (talhão→usina, carregado) e volta vazio. Isso muda o consumo por sentido — e até **qual rota é ótima em cada direção**. A NOKAHI trata os dois sentidos como problemas distintos.

### 4. Pedágio real por eixo, com eixo suspenso vazio
Maplink e as calculadoras cobram pedágio por perfil de veículo. Nenhuma modela que o CVC **suspende eixos quando volta vazio**, reduzindo o custo de pedágio no retorno. A NOKAHI incorpora isso no custo total da rota.

### 5. Restrições reais de CVC canavieiro (treminhão / rodotrem / pentatrem)
Os roteirizadores urbanos assumem caminhão genérico ou van. A NOKAHI usa **GraphHopper perfil truck** com peso, dimensões, zonas urbanas evitadas e vias privadas dos Combinados de Veículos de Carga canavieiros — que não passam onde um caminhão comum passa.

### 6. Superfície (asfalto / cascalho / terra) como variável de custo
O "último quilômetro rural" — vias internas de fazenda, estradas de terra/cascalho — é onde o consumo dispara. Concorrentes como Senior+GAtec e AxiWays tratam a **navegabilidade** da via (o veículo passa ou não passa, é seguro ou não). A NOKAHI vai além: pondera o **custo energético** de rodar em cada tipo de piso, não só se é transitável.

### 7. Clima real (chuva) no cálculo — não só no alerta
Chuva muda aderência, atolamento e consumo, especialmente em terra. A NOKAHI insere `k_clima` **dentro do modelo de custo**. As demais tratam clima como alerta de segurança ou dado agronômico separado — não como fator do custo da rota.

### 8. Ranking de 4 rotas por custo — não rota única
Entrega alternativas rankeadas por custo real, permitindo trade-off (a mais barata pode ser mais lenta). Roteirizadores devolvem "a rota"; rotogramas dizem "quando despachar". A NOKAHI diz **"por onde ir, e aqui estão as opções ordenadas pelo que você quer minimizar"**.

### 9. Ingestão ABERTA de telemetria — agnóstica de provedor
Cobli, Golfleet, TrackMaker, Ituran e Solinftec funcionam bem **com o próprio hardware** — ecossistemas fechados. A NOKAHI recebe dados brutos ou de qualquer provedor via mapeamento de campos (Flow API da Solinftec pronta, ou qualquer outro). Isso a posiciona **acima** da guerra de hardware, não dentro dela — e é justamente o que permite ser complementar a todos.

### 10. Stack analítico integrado: ML + Pesquisa Operacional + agente + inteligência de frota
Além da rota: ML de calibração de consumo / risco de manutenção / previsão de demanda; PO de alocação ótima multi-origem/multi-destino; agente analítico em chat; painel de MTBF/MTTR, alertas preditivos, manutenção preventiva, heatmap, avaliação de mecânicos/fornecedores. Os players de manutenção (Sofit, Frota Control) fazem "previsão" por intervalo/data — **regra, não ML** — e nenhum liga manutenção ao **custo por rota/operação**. A NOKAHI cobre tanto a alocação (PO) quanto a rota física (menor custo) no mesmo produto.

### 11. Especialização real no par talhão→usina do CCT
Não é roteirizador urbano adaptado nem plataforma agronômica com módulo de logística. O objeto de otimização é a **viagem campo→usina do transporte canavieiro**, com todas as suas particularidades físicas e regulatórias.

### 12. Multi-tenant, cobertura Brasil, precificação por uso
Modelo de entrega SaaS por uso (vs. licença enterprise por usina + hardware embarcado das incumbentes), reduzindo barreira de entrada e alinhando custo a valor gerado.

---

## 3. Panorama competitivo — quem existe e por que não resolve o mesmo problema

A pesquisa varreu **6 categorias** e mais de 30 soluções brasileiras que atendem o público do agronegócio. Nenhuma faz roteirização econômica por custo físico de diesel para CVCs. O quadro abaixo resume por que cada categoria **não é concorrente direto**:

| Categoria | Players representativos | O que fazem | Por que não é a NOKAHI |
|---|---|---|---|
| **Telemetria / rastreamento pesado** | Sascar (Michelin), Onixsat, Omnilink, Autotrac, Veltec/Trimble, Cobli, Ituran, Pósitron, Creare | Localização, segurança/antifurto, gestão de risco, comportamento do motorista | Registram a rota **executada**; não escolhem a rota por custo. São **fonte de dados**, não concorrentes |
| **Rotogramas inteligentes / campo do CCT** | AxiWays/AxiAgro, Aiko, Trust Agro, RastreAgro, Senior+GAtec | Tempo de ciclo, sincronia colhedora↔caminhão↔usina, segurança, conformidade legal/documental | Dizem **quando** despachar e **se** a via serve; a NOKAHI diz **por onde** gastar menos |
| **Roteirização / TMS urbano e APIs** | RoutEasy, SimpliRoute, Maplink, Qualp, Rotas Brasil, AILOG | Distância/tempo/janela para last-mile; pedágio/matriz por API | Consumo é **média estática**; nenhum modela física do terreno nem CVC canavieiro |
| **Pagamento / despesa de frota / marketplace** | Roadcard/Pamcard, Frete.com/CargoX | Pagam e contabilizam pedágio/combustível **depois**; casam carga↔caminhão | Nenhum é roteirizador. Complementares como fonte de custo |
| **Gestão agrícola / agricultura de precisão** | Aegro, Agrare, Strider, Climate FieldView, John Deere Ops Center, Trimble Ag, Jacto/Otmis, Perfarm, Agres | Agronomia, monitoramento de lavoura, gestão fiscal, guiagem de máquina **dentro do talhão** | O "roteiro" que geram é intra-talhão, não transporte rodoviário externo. **Zero sobreposição** com custo de diesel por rota |
| **Gestão de manutenção / frota** | Sofit, Frota Control, TrackMaker, Golfleet, Prime Frotas | Manutenção por quilometragem/data; TCO por veículo | "Previsão" por regra de intervalo, não ML; nenhum liga manutenção ao custo por rota |

### O caso especial: Solinftec

A Solinftec é, ao mesmo tempo, o **concorrente mais próximo em inteligência** e o **parceiro/fonte de dados mais estratégico**:

- **Por que é a mais avançada:** ML real, agente multiagente (Alice), predição de falha por código de erro, otimização de transbordo, >90% da cana brasileira.
- **Por que não é a mesma coisa:** otimiza a **operação agronômica e a logística interna de abastecimento da moagem** (quando ir, alocação campo→indústria, filas de transbordo), em ecossistema proprietário de computador de bordo. **Não é engine aberta de rota rodoviária de menor custo por par origem-destino.**
- **A relação NOKAHI:** ingere a telemetria da Solinftec via Flow API e **adiciona a camada econômica que a Solinftec não entrega**. A NOKAHI ganha se a Solinftec existir e for boa — melhores dados de entrada calibram melhor o modelo físico.

---

## 4. Onde está o fosso (e onde é só janela)

**O que defende a NOKAHI hoje:** a profundidade do modelo físico (rampa + PBT + superfície + clima), o pedágio por eixo com eixo suspenso, as restrições reais de CVC e o agnosticismo de dados. Combinados, formam uma especialização que nenhum player adjacente tem hoje e que exige domínio simultâneo de logística rodoviária + física de consumo + realidade canavieira.

**O que é honestamente uma janela, não um fosso permanente:** nada impede tecnicamente que um rotograma (AxiWays) ou a própria Solinftec adicione um modelo de custo de rota. A vantagem é de **profundidade e tempo de mercado**, não de barreira intransponível. A resposta estratégica é aprofundar a calibração (que melhora com histórico e é difícil de copiar rápido) e firmar o posicionamento complementar antes que um incumbente decida internalizar a camada.

---

## 5. Limitações e riscos — a leitura honesta

Um documento de diferenciais que só lista forças não é confiável. Os riscos reais:

- **Dependência de dados de terceiros.** A NOKAHI não fabrica hardware nem coleta telemetria própria. Quem controla o hardware (Solinftec, Cobli, Sascar) controla a torneira de dados. *Mitigação parcial:* a ingestão agnóstica reduz a dependência de um único provedor — mas não elimina a dependência de *algum* provedor.
- **A calibração é o produto, e precisa de tempo e histórico.** Os ~16% de diesel só se materializam com o modelo bem calibrado por frota/terreno. Em cliente novo, sem histórico, há **risco de cold-start** e a economia varia muito por operação (relevo plano vs. acidentado, malha asfaltada vs. terra).
- **A economia de ~16% precisa de validação de campo publicável.** É a média atual observada, não um resultado provado no material. Concorrentes usam números análogos (SimpliRoute: −30% de custo logístico; Jacto: +10-30% de rendimento) — a NOKAHI precisa de **estudos de caso auditáveis** para não soar como marketing.
- **Assimetria de marca.** Solinftec (mira R$500 mi em 2026), Sascar (Michelin), Trimble e John Deere têm marca, base instalada e canal de venda consultiva dentro das usinas. A NOKAHI entra como camada nova sobre incumbentes poderosas.
- **Risco de "feature, não produto".** Ver seção 4 — a defensabilidade está na profundidade, não numa barreira.
- **Integração real é mais difícil que "mapeamento de campos".** Cada provedor tem formato, latência, lacunas e ruído próprios. O custo de integração e a qualidade heterogênea dos dados são risco operacional recorrente.
- **Escopo rodoviário externo, não intra-talhão.** A NOKAHI é forte no par talhão→usina em vias mapeáveis. A micro-logística da frente de colheita (sincronia colhedora↔transbordo) é território de Solinftec/AxiWays — a NOKAHI **complementa, não substitui**.

---

## 6. Resumo executivo

1. **Categoria própria.** A NOKAHI cria uma categoria — *roteirização econômica por custo físico para CVCs* — em vez de disputar as categorias saturadas (telemetria, rastreamento, TMS urbano, gestão agrícola).
2. **Complementar por design.** É a camada de otimização que se assenta sobre a camada de observação que o mercado já vende — ingerindo, inclusive, os dados dos "concorrentes".
3. **Profundidade técnica como diferencial.** Modelo físico calibrado, assimetria de carga, pedágio por eixo, superfície e clima no custo, restrições de CVC — nenhum player brasileiro combina isso hoje.
4. **Honestidade sobre a defensabilidade.** A vantagem é de profundidade e tempo, não um fosso permanente; a estratégia é aprofundar a calibração e firmar o posicionamento complementar.

---

*Fonte: pesquisa de mercado NOKAHI, julho/2026. Soluções citadas são de seus respectivos detentores; a análise reflete posicionamento público conhecido na data.*
