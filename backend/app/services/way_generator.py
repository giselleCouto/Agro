"""
CanaRoute - Gerador de Arquivos WAY/GPX/KML
Formato compatível com Solinftec WAY (waypoints de rota).
"""
from datetime import datetime


class WayGenerator:
    """Gera arquivos de rota em múltiplos formatos."""

    def generate_way(self, route, field, vehicle) -> str:
        """Gerar arquivo .way compatível com Solinftec."""
        coords = route.coordinates or []
        lines = []

        # Header
        lines.append(f"[ROUTE]")
        lines.append(f"NAME=CANAROUTE_{vehicle.slug}_{field.code}")
        lines.append(f"VEHICLE={vehicle.name}")
        lines.append(f"PBT={vehicle.pbt_tons}")
        lines.append(f"DISTANCE_KM={route.distance_km}")
        lines.append(f"FUEL_LITERS={route.fuel_liters}")
        lines.append(f"TOLL_COST={route.toll_cost}")
        lines.append(f"TOTAL_COST={route.total_cost}")
        lines.append(f"GENERATED={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"SOURCE=CanaRoute v1.0")
        lines.append(f"POINTS={len(coords)}")
        lines.append("")

        # Waypoints
        lines.append("[WAYPOINTS]")
        lines.append("# SEQ;LAT;LON;TYPE;DESCRIPTION")

        # Primeiro ponto = origem (talhão)
        if coords:
            lines.append(f"1;{coords[0][0]:.7f};{coords[0][1]:.7f};ORIGIN;{field.name}")

        # Pontos intermediários (amostrar a cada N pontos)
        step = max(1, len(coords) // 50)
        seq = 2
        for i in range(step, len(coords) - 1, step):
            lines.append(f"{seq};{coords[i][0]:.7f};{coords[i][1]:.7f};WP;Waypoint {seq}")
            seq += 1

        # Último ponto = destino (usina)
        if len(coords) > 1:
            lines.append(f"{seq};{coords[-1][0]:.7f};{coords[-1][1]:.7f};DESTINATION;Usina")

        lines.append("")
        lines.append("[END]")

        return "\n".join(lines)

    def generate_gpx(self, route, field, vehicle) -> str:
        """Gerar arquivo GPX."""
        coords = route.coordinates or []
        lines = []

        lines.append('<?xml version="1.0" encoding="UTF-8"?>')
        lines.append('<gpx version="1.1" creator="CanaRoute v1.0"')
        lines.append('  xmlns="http://www.topografix.com/GPX/1/1">')
        lines.append(f'  <metadata>')
        lines.append(f'    <name>CANAROUTE_{vehicle.slug}_{field.code}</name>')
        lines.append(f'    <desc>Rota otimizada: {field.name} → Usina ({route.distance_km} km)</desc>')
        lines.append(f'    <time>{datetime.utcnow().isoformat()}Z</time>')
        lines.append(f'  </metadata>')

        # Track
        lines.append(f'  <trk>')
        lines.append(f'    <name>{vehicle.name}: {field.name} → Usina</name>')
        lines.append(f'    <trkseg>')
        for coord in coords:
            lines.append(f'      <trkpt lat="{coord[0]:.7f}" lon="{coord[1]:.7f}"/>')
        lines.append(f'    </trkseg>')
        lines.append(f'  </trk>')

        # Waypoints (origem e destino)
        if coords:
            lines.append(f'  <wpt lat="{coords[0][0]:.7f}" lon="{coords[0][1]:.7f}">')
            lines.append(f'    <name>{field.name}</name><type>ORIGIN</type>')
            lines.append(f'  </wpt>')
            lines.append(f'  <wpt lat="{coords[-1][0]:.7f}" lon="{coords[-1][1]:.7f}">')
            lines.append(f'    <name>Usina</name><type>DESTINATION</type>')
            lines.append(f'  </wpt>')

        lines.append('</gpx>')
        return "\n".join(lines)

    def generate_kml(self, route, field, vehicle) -> str:
        """Gerar arquivo KML."""
        coords = route.coordinates or []
        coord_str = " ".join([f"{c[1]:.7f},{c[0]:.7f},0" for c in coords])

        kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>CANAROUTE_{vehicle.slug}_{field.code}</name>
    <description>Rota otimizada: {field.name} → Usina ({route.distance_km} km, {route.fuel_liters} L)</description>
    <Style id="routeStyle">
      <LineStyle><color>ff00ff00</color><width>4</width></LineStyle>
    </Style>
    <Placemark>
      <name>{vehicle.name}: {field.name} → Usina</name>
      <styleUrl>#routeStyle</styleUrl>
      <LineString>
        <coordinates>{coord_str}</coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>{field.name} (Origem)</name>
      <Point><coordinates>{coords[0][1]:.7f},{coords[0][0]:.7f},0</coordinates></Point>
    </Placemark>
    <Placemark>
      <name>Usina (Destino)</name>
      <Point><coordinates>{coords[-1][1]:.7f},{coords[-1][0]:.7f},0</coordinates></Point>
    </Placemark>
  </Document>
</kml>"""
        return kml
