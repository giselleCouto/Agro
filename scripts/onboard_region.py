#!/usr/bin/env python3
"""
CanaRoute - Script CLI de Onboarding de Nova Região
Uso: python onboard_region.py --name "Usina X" --lat -21.34 --lon -48.30 --shapefile talhoes.zip
"""
import argparse
import requests
import sys
import time

API_BASE = "http://localhost:8000/api/v1"


def main():
    parser = argparse.ArgumentParser(description="CanaRoute - Onboarding de Nova Região")
    parser.add_argument("--name", required=True, help="Nome do cliente/usina")
    parser.add_argument("--slug", help="Slug (gerado automaticamente se não informado)")
    parser.add_argument("--state", default="SP", help="Estado (UF)")
    parser.add_argument("--plant-name", help="Nome da usina (default: mesmo que --name)")
    parser.add_argument("--lat", type=float, required=True, help="Latitude da usina")
    parser.add_argument("--lon", type=float, required=True, help="Longitude da usina")
    parser.add_argument("--capacity", type=int, default=15000, help="Capacidade (ton/dia)")
    parser.add_argument("--shapefile", required=True, help="Caminho do shapefile (ZIP)")
    parser.add_argument("--api-base", default=API_BASE, help="URL base da API")

    args = parser.parse_args()
    api = args.api_base

    slug = args.slug or args.name.lower().replace(" ", "-").replace(".", "")
    plant_name = args.plant_name or args.name

    print(f"🚀 CanaRoute - Onboarding: {args.name}")
    print(f"   Usina: {plant_name} ({args.lat}, {args.lon})")
    print(f"   Shapefile: {args.shapefile}")
    print()

    # 1. Criar cliente
    print("1️⃣  Criando cliente...")
    resp = requests.post(f"{api}/clients/", json={
        "name": args.name, "slug": slug, "state": args.state
    })
    if resp.status_code not in [200, 201]:
        print(f"   ⚠️  Cliente pode já existir: {resp.text}")
    else:
        print(f"   ✅ Cliente criado: {resp.json()['id']}")
    client_id = resp.json().get("id", 1)

    # 2. Criar usina
    print("2️⃣  Criando usina...")
    resp = requests.post(f"{api}/plants/", json={
        "client_id": client_id,
        "name": plant_name,
        "latitude": args.lat,
        "longitude": args.lon,
        "capacity_tons_day": args.capacity
    })
    if resp.status_code not in [200, 201]:
        print(f"   ⚠️  Usina pode já existir: {resp.text}")
    else:
        print(f"   ✅ Usina criada: {resp.json()['id']}")
    plant_id = resp.json().get("id", 1)

    # 3. Upload shapefile
    print("3️⃣  Importando talhões do shapefile...")
    with open(args.shapefile, "rb") as f:
        resp = requests.post(
            f"{api}/fields/upload-shapefile",
            files={"file": (args.shapefile, f, "application/zip")},
            data={"client_id": client_id}
        )
    if resp.status_code == 200:
        result = resp.json()
        print(f"   ✅ {result['fields_created']} talhões importados de {result['farms_created']} fazendas")
        print(f"   📐 Área total: {result['total_area_ha']} ha")
    else:
        print(f"   ❌ Erro: {resp.text}")
        sys.exit(1)

    # 4. Detectar zonas urbanas
    print("4️⃣  Detectando zonas urbanas na região...")
    resp = requests.post(f"{api}/urban-zones/detect", json={"client_id": client_id})
    if resp.status_code == 200:
        zones = resp.json()
        print(f"   ✅ {len(zones)} zonas urbanas detectadas")
    else:
        print(f"   ⚠️  Detecção automática falhou (pode ser feita manualmente)")

    # 5. Calcular rotas
    print("5️⃣  Calculando rotas para todos os talhões...")
    resp = requests.post(f"{api}/routes/calculate-all", json={
        "client_id": client_id,
        "plant_id": plant_id
    })
    if resp.status_code == 200:
        result = resp.json()
        print(f"   ✅ {result.get('routes_calculated', '?')} rotas calculadas")
    else:
        print(f"   ⚠️  Cálculo em background: {resp.text}")

    # 6. Resumo
    print()
    print("=" * 50)
    print(f"✅ ONBOARDING COMPLETO: {args.name}")
    print(f"   Frontend: http://localhost/?client={slug}")
    print(f"   API: {api}/fields/?client_id={client_id}")
    print("=" * 50)


if __name__ == "__main__":
    main()
