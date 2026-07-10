"""Pesquisa Operacional — otimização de transporte multi-origem/multi-destino.

Sobre o motor de custo de rotas (que dá o custo R$ de cada par talhão→usina),
esta camada resolve DUAS decisões clássicas de OR:

1. Problema de transporte (transportation problem): dado o volume disponível em
   cada origem (talhão, t de cana), a capacidade de recebimento de cada destino
   (usina/pátio) e o custo por tonelada de cada par, decide QUANTO enviar de
   cada origem para cada destino minimizando o custo total. Resolve via
   programação linear (scipy.optimize.linprog).

2. Problema de atribuição (assignment): distribui as viagens/rotas entre os
   veículos disponíveis minimizando o custo total. Resolve via algoritmo
   húngaro (scipy.optimize.linear_sum_assignment).

Ambos operam sobre uma matriz de custo — tipicamente construída pelo motor de
rotas (service.build_cost_matrix). São o coração do "calcular várias rotas ao
mesmo tempo" com decisão ótima de alocação.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment, linprog


def solve_transportation(
    supply: list[float], demand: list[float], cost: list[list[float]]
) -> dict:
    """Fluxo ótimo origem→destino minimizando custo total.

    supply[i]  — disponibilidade da origem i (ex.: t de cana no talhão)
    demand[j]  — necessidade do destino j (ex.: capacidade da usina)
    cost[i][j] — custo por unidade (t) da origem i ao destino j

    Restrições: cada origem envia no máximo sua oferta; cada destino recebe ao
    menos sua demanda (se a oferta total permitir; senão, atende o possível).
    """
    S, D = len(supply), len(demand)
    c = np.asarray(cost, dtype=float).reshape(S * D)
    total_supply, total_demand = float(sum(supply)), float(sum(demand))

    # x[i*D + j] >= 0 ; minimizar c·x
    # oferta: sum_j x[i,j] <= supply[i]   (A_ub)
    A_ub, b_ub = [], []
    for i in range(S):
        row = np.zeros(S * D)
        row[i * D:(i + 1) * D] = 1.0
        A_ub.append(row); b_ub.append(supply[i])

    # demanda: sum_i x[i,j] >= demand[j]  ->  -sum <= -demand
    feasible_demand = min(total_demand, total_supply)
    scale = (feasible_demand / total_demand) if total_demand > 0 else 0.0
    for j in range(D):
        row = np.zeros(S * D)
        for i in range(S):
            row[i * D + j] = -1.0
        A_ub.append(row); b_ub.append(-demand[j] * scale)

    res = linprog(c, A_ub=np.array(A_ub), b_ub=np.array(b_ub),
                  bounds=[(0, None)] * (S * D), method="highs")
    if not res.success:
        return {"success": False, "message": res.message}
    flow = res.x.reshape(S, D)
    return {
        "success": True,
        "flows": np.round(flow, 3).tolist(),
        "total_cost": round(float(res.fun), 2),
        "delivered": round(float(flow.sum()), 3),
        "unmet_demand": round(max(0.0, total_demand - total_supply), 3),
    }


def solve_assignment(cost_matrix: list[list[float]]) -> dict:
    """Atribuição ótima 1:1 (veículo→rota) via algoritmo húngaro.

    Aceita matriz retangular (nº de veículos ≠ nº de rotas); só as atribuições
    viáveis são retornadas.
    """
    C = np.asarray(cost_matrix, dtype=float)
    row_ind, col_ind = linear_sum_assignment(C)
    pairs = [{"row": int(r), "col": int(c), "cost": round(float(C[r, c]), 2)}
             for r, c in zip(row_ind, col_ind)]
    return {
        "assignments": pairs,
        "total_cost": round(float(C[row_ind, col_ind].sum()), 2),
        "n_assigned": len(pairs),
    }


def allocate_trips_to_vehicles(
    trip_costs: list[list[float]], vehicle_capacity: list[int]
) -> dict:
    """Distribui rotas entre veículos respeitando quantas viagens cada um faz.

    trip_costs[v][r]      — custo do veículo v operar a rota r
    vehicle_capacity[v]   — nº máximo de viagens do veículo v no período

    Expande cada veículo em `capacity` slots e resolve como atribuição.
    Rotas excedentes (sem veículo) ficam de fora e são reportadas.
    """
    n_routes = len(trip_costs[0]) if trip_costs else 0
    slots, slot_owner = [], []
    for v, cap in enumerate(vehicle_capacity):
        for _ in range(cap):
            slots.append(trip_costs[v]); slot_owner.append(v)
    if not slots or n_routes == 0:
        return {"assignments": [], "total_cost": 0.0, "unassigned_routes": list(range(n_routes))}

    C = np.asarray(slots, dtype=float)  # (n_slots, n_routes)
    # completa para quadrado com custo alto (slots ociosos)
    n_slots = C.shape[0]
    size = max(n_slots, n_routes)
    BIG = float(C.max() * 10 + 1e6)
    M = np.full((size, size), BIG)
    M[:n_slots, :n_routes] = C
    row_ind, col_ind = linear_sum_assignment(M)

    assignments, assigned_routes, total = [], set(), 0.0
    for r, cslot in zip(row_ind, col_ind):
        if r < n_slots and cslot < n_routes:
            cost = float(C[r, cslot])
            assignments.append({"vehicle": slot_owner[r], "route": int(cslot),
                                "cost": round(cost, 2)})
            assigned_routes.add(int(cslot)); total += cost
    unassigned = [r for r in range(n_routes) if r not in assigned_routes]
    return {
        "assignments": assignments,
        "total_cost": round(total, 2),
        "unassigned_routes": unassigned,
    }
