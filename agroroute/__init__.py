"""NOKAHI AgroRoute — roteirização econômica multi-tenant para frotas agrícolas pesadas.

Generaliza o modelo SAJB (v3/v5/v6) para todo o Brasil:
  L = (R0 + alpha * max(0, slope%)) * mult_superficie * PBT * dKm * k_clima(segmento)

Componentes:
  models     — tipos de domínio (veículos, rotas, custos, tenants)
  cost       — motor físico de custo (combustível, manutenção, pedágio por eixo)
  providers  — roteirizadores (OSRM, GraphHopper) com geometria real
  enrich     — elevação (SRTM), clima (Open-Meteo), superfície, pedágios, restrições
  tenancy    — isolamento multi-tenant por API key
  service    — orquestração (rota -> enriquecimento -> custo)
  api        — FastAPI (cálculo unitário e em lote)
"""

__version__ = "0.1.0"
