#!/bin/bash
# CanaRoute - Download de dados OSM para OSRM
# Uso: ./download_osm.sh [regiao]
# Regiões: sp, mg, go, ms, mt, pr, al, pe, pb, brasil

set -e

REGION=${1:-sp}
DATA_DIR="/data/osrm"
mkdir -p "$DATA_DIR"

echo "🗺️  CanaRoute - Download OSM para OSRM"
echo "   Região: $REGION"

# URLs de download (Geofabrik)
declare -A URLS=(
    ["sp"]="https://download.geofabrik.de/south-america/brazil/sudeste-latest.osm.pbf"
    ["mg"]="https://download.geofabrik.de/south-america/brazil/sudeste-latest.osm.pbf"
    ["go"]="https://download.geofabrik.de/south-america/brazil/centro-oeste-latest.osm.pbf"
    ["ms"]="https://download.geofabrik.de/south-america/brazil/centro-oeste-latest.osm.pbf"
    ["mt"]="https://download.geofabrik.de/south-america/brazil/centro-oeste-latest.osm.pbf"
    ["pr"]="https://download.geofabrik.de/south-america/brazil/sul-latest.osm.pbf"
    ["al"]="https://download.geofabrik.de/south-america/brazil/nordeste-latest.osm.pbf"
    ["pe"]="https://download.geofabrik.de/south-america/brazil/nordeste-latest.osm.pbf"
    ["brasil"]="https://download.geofabrik.de/south-america/brazil-latest.osm.pbf"
)

URL=${URLS[$REGION]}
if [ -z "$URL" ]; then
    echo "❌ Região não reconhecida: $REGION"
    echo "   Regiões válidas: sp, mg, go, ms, mt, pr, al, pe, pb, brasil"
    exit 1
fi

FILENAME=$(basename "$URL")

echo "📥 Baixando $FILENAME..."
wget -c "$URL" -O "$DATA_DIR/$FILENAME"

echo "🔧 Processando com OSRM (perfil truck)..."
cd "$DATA_DIR"

# Extract
osrm-extract -p /opt/car.lua "$FILENAME" || \
docker run --rm -v "$DATA_DIR:/data" osrm/osrm-backend:latest \
    osrm-extract -p /opt/car.lua "/data/$FILENAME"

# Partition
osrm-partition "${FILENAME%.osm.pbf}.osrm" || \
docker run --rm -v "$DATA_DIR:/data" osrm/osrm-backend:latest \
    osrm-partition "/data/${FILENAME%.osm.pbf}.osrm"

# Customize
osrm-customize "${FILENAME%.osm.pbf}.osrm" || \
docker run --rm -v "$DATA_DIR:/data" osrm/osrm-backend:latest \
    osrm-customize "/data/${FILENAME%.osm.pbf}.osrm"

echo "✅ OSRM pronto para região: $REGION"
echo "   Dados em: $DATA_DIR"
echo "   Para iniciar: osrm-routed --algorithm=MLD $DATA_DIR/${FILENAME%.osm.pbf}.osrm"
