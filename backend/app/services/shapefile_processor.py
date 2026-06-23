"""
CanaRoute - Processador de Shapefiles
Extrai talhões de shapefiles, calcula centroides e cria registros no banco.
"""
import zipfile
import tempfile
import os
import geopandas as gpd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.field import Field
from ..models.farm import Farm
from ..schemas.field import FieldBulkResponse


async def process_shapefile(zip_path: str, client_id: int, db: AsyncSession) -> FieldBulkResponse:
    """
    Processar shapefile zipado:
    1. Extrair ZIP
    2. Ler shapefile com GeoPandas
    3. Calcular centroide de cada polígono
    4. Criar/atualizar fazendas e talhões
    """
    # Extrair ZIP
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(tmpdir)

        # Encontrar .shp
        shp_files = []
        for root, dirs, files in os.walk(tmpdir):
            for f in files:
                if f.endswith('.shp'):
                    shp_files.append(os.path.join(root, f))

        if not shp_files:
            return FieldBulkResponse(
                fields_created=0, farms_created=0,
                total_area_ha=0, message="Nenhum arquivo .shp encontrado no ZIP"
            )

        # Ler shapefile
        gdf = gpd.read_file(shp_files[0])

        # Reprojetar para WGS84 se necessário
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        # Detectar colunas de fazenda e talhão
        farm_col = _detect_column(gdf, ["FAZENDA", "FARM", "FAZ", "PROPRIEDADE", "DESCFAZENDA"])
        code_col = _detect_column(gdf, ["TALHAO", "CDTALHAO", "CD_TALHAO", "FIELD", "ID", "COD"])
        area_col = _detect_column(gdf, ["AREA", "AREA_HA", "AREAHA", "HECTARES"])

        farms_created = 0
        fields_created = 0
        total_area = 0
        farm_cache = {}

        for idx, row in gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue

            # Centroide
            centroid = geom.centroid
            lat = centroid.y
            lon = centroid.x

            # Fazenda
            farm_name = str(row[farm_col]).strip() if farm_col and row[farm_col] else f"Fazenda {idx}"
            if farm_name not in farm_cache:
                # Buscar ou criar
                result = await db.execute(
                    select(Farm).where(Farm.name == farm_name, Farm.client_id == client_id)
                )
                farm = result.scalar_one_or_none()
                if not farm:
                    farm = Farm(name=farm_name, client_id=client_id)
                    db.add(farm)
                    await db.flush()
                    farms_created += 1
                farm_cache[farm_name] = farm.id

            # Código do talhão
            code = str(row[code_col]) if code_col and row[code_col] else str(idx)

            # Área
            area_ha = None
            if area_col and row[area_col]:
                try:
                    area_ha = float(row[area_col])
                except (ValueError, TypeError):
                    pass
            if not area_ha and geom:
                # Calcular área aproximada
                area_ha = round(geom.area * 111320 * 111320 * abs(cos(radians(lat))) / 10000, 2)

            if area_ha:
                total_area += area_ha

            # Criar talhão
            field = Field(
                client_id=client_id,
                farm_id=farm_cache[farm_name],
                code=code,
                name=f"Talhão {code}",
                area_ha=area_ha,
                latitude=round(lat, 7),
                longitude=round(lon, 7),
                active=True
            )
            db.add(field)
            fields_created += 1

        await db.flush()

        return FieldBulkResponse(
            fields_created=fields_created,
            farms_created=farms_created,
            total_area_ha=round(total_area, 1),
            message=f"Importados {fields_created} talhões de {farms_created} fazendas ({total_area:.0f} ha)"
        )


def _detect_column(gdf, candidates):
    """Detectar coluna por nome candidato."""
    cols_upper = {c.upper(): c for c in gdf.columns}
    for candidate in candidates:
        if candidate.upper() in cols_upper:
            return cols_upper[candidate.upper()]
    return None


from math import radians, cos
