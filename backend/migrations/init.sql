-- ============================================================
-- CanaRoute - Schema Inicial
-- ============================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- Clientes / Regiões
-- ============================================================
CREATE TABLE IF NOT EXISTS clients (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    state CHAR(2) NOT NULL DEFAULT 'SP',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Usinas
-- ============================================================
CREATE TABLE IF NOT EXISTS plants (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50),
    location GEOMETRY(Point, 4326) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    capacity_tons_day DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_plants_location ON plants USING GIST(location);

-- ============================================================
-- Fazendas
-- ============================================================
CREATE TABLE IF NOT EXISTS farms (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Talhões
-- ============================================================
CREATE TABLE IF NOT EXISTS fields (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
    farm_id INTEGER REFERENCES farms(id) ON DELETE SET NULL,
    code VARCHAR(50),
    name VARCHAR(255),
    area_ha DOUBLE PRECISION,
    centroid GEOMETRY(Point, 4326),
    boundary GEOMETRY(MultiPolygon, 4326),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_fields_centroid ON fields USING GIST(centroid);
CREATE INDEX idx_fields_boundary ON fields USING GIST(boundary);
CREATE INDEX idx_fields_client ON fields(client_id);

-- ============================================================
-- Veículos (tipos)
-- ============================================================
CREATE TABLE IF NOT EXISTS vehicles (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(50) NOT NULL,
    pbt_tons DOUBLE PRECISION NOT NULL,
    axles INTEGER NOT NULL,
    length_m DOUBLE PRECISION NOT NULL,
    width_m DOUBLE PRECISION NOT NULL,
    -- Restrições de via
    min_road_class VARCHAR(20) DEFAULT 'tertiary',  -- primary, secondary, tertiary, unclassified, track
    caution_road_classes TEXT[] DEFAULT '{}',
    blocked_road_classes TEXT[] DEFAULT '{}',
    -- Velocidades por tipo de via (JSON)
    speed_by_road_class JSONB DEFAULT '{}',
    -- Consumo
    fuel_r0 DOUBLE PRECISION DEFAULT 0.0030,
    fuel_alpha DOUBLE PRECISION DEFAULT 0.0040,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Praças de Pedágio
-- ============================================================
CREATE TABLE IF NOT EXISTS toll_plazas (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    name VARCHAR(255) NOT NULL,
    highway VARCHAR(50),
    km DOUBLE PRECISION,
    location GEOMETRY(Point, 4326) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    cost_per_axle DOUBLE PRECISION NOT NULL DEFAULT 7.80,
    bidirectional BOOLEAN DEFAULT TRUE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tolls_location ON toll_plazas USING GIST(location);

-- ============================================================
-- Zonas Urbanas (restrição de passagem)
-- ============================================================
CREATE TABLE IF NOT EXISTS urban_zones (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id),
    name VARCHAR(255) NOT NULL,
    center GEOMETRY(Point, 4326) NOT NULL,
    boundary GEOMETRY(Polygon, 4326),
    radius_m DOUBLE PRECISION DEFAULT 2000,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    restriction_level VARCHAR(20) DEFAULT 'blocked',  -- blocked, caution, allowed
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_urban_zones_center ON urban_zones USING GIST(center);
CREATE INDEX idx_urban_zones_boundary ON urban_zones USING GIST(boundary);

-- ============================================================
-- Rotas Calculadas (cache)
-- ============================================================
CREATE TABLE IF NOT EXISTS routes (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
    field_id INTEGER REFERENCES fields(id) ON DELETE CASCADE,
    plant_id INTEGER REFERENCES plants(id) ON DELETE CASCADE,
    vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE CASCADE,
    route_type VARCHAR(20) NOT NULL DEFAULT 'alternative',  -- gps_real, alternative
    -- Geometria
    geometry GEOMETRY(LineString, 4326),
    geometry_geojson JSONB,
    coordinates JSONB,  -- [[lon, lat], ...]
    -- Métricas
    distance_km DOUBLE PRECISION,
    duration_min DOUBLE PRECISION,
    elevation_gain_m DOUBLE PRECISION,
    elevation_loss_m DOUBLE PRECISION,
    avg_slope_pct DOUBLE PRECISION,
    max_slope_pct DOUBLE PRECISION,
    -- Consumo
    fuel_liters DOUBLE PRECISION,
    fuel_cost DOUBLE PRECISION,
    -- Pedágios
    toll_count INTEGER DEFAULT 0,
    toll_cost DOUBLE PRECISION DEFAULT 0,
    toll_plazas_ids INTEGER[] DEFAULT '{}',
    -- Custo total
    total_cost DOUBLE PRECISION,
    -- Classificação de vias
    highway_mix JSONB DEFAULT '{}',
    -- Trafegabilidade
    suitability_score INTEGER DEFAULT 100,
    trafficability_scores JSONB DEFAULT '{}',  -- {seco: 100, umido: 85, ...}
    -- Alertas
    passes_urban_zone BOOLEAN DEFAULT FALSE,
    urban_zones_crossed INTEGER[] DEFAULT '{}',
    -- Elevação
    elevation_profile JSONB,  -- [{dist: 0, elev: 500}, ...]
    -- Metadados
    calculated_at TIMESTAMP DEFAULT NOW(),
    valid_until TIMESTAMP,
    source VARCHAR(50) DEFAULT 'osrm'  -- osrm, graphhopper, manual
);

CREATE INDEX idx_routes_field_plant ON routes(field_id, plant_id);
CREATE INDEX idx_routes_client ON routes(client_id);
CREATE INDEX idx_routes_vehicle ON routes(vehicle_id);
CREATE INDEX idx_routes_geometry ON routes USING GIST(geometry);

-- ============================================================
-- Economia (resultados comparativos)
-- ============================================================
CREATE TABLE IF NOT EXISTS economy_results (
    id SERIAL PRIMARY KEY,
    client_id INTEGER REFERENCES clients(id) ON DELETE CASCADE,
    field_id INTEGER REFERENCES fields(id) ON DELETE CASCADE,
    plant_id INTEGER REFERENCES plants(id) ON DELETE CASCADE,
    vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE CASCADE,
    gps_route_id INTEGER REFERENCES routes(id),
    alt_route_id INTEGER REFERENCES routes(id),
    -- Economia
    fuel_saving_liters DOUBLE PRECISION,
    fuel_saving_cost DOUBLE PRECISION,
    toll_difference DOUBLE PRECISION,
    total_saving_per_trip DOUBLE PRECISION,
    total_saving_per_season DOUBLE PRECISION,
    saving_pct DOUBLE PRECISION,
    -- Configuração usada
    climate_scenario VARCHAR(20) DEFAULT 'safra_mix',
    occupancy_pct DOUBLE PRECISION DEFAULT 100,
    fuel_price DOUBLE PRECISION DEFAULT 6.0,
    season_trips INTEGER DEFAULT 935,
    calculated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Dados de Seed (veículos padrão)
-- ============================================================
INSERT INTO vehicles (client_id, name, slug, pbt_tons, axles, length_m, width_m, min_road_class, caution_road_classes, blocked_road_classes, speed_by_road_class, fuel_r0, fuel_alpha)
VALUES
(NULL, 'Treminhão', 'treminhao', 55, 7, 20, 2.6, 'track',
 '{track}', '{}',
 '{"primary": 60, "secondary": 50, "tertiary": 40, "unclassified": 30, "track": 20, "residential": 30}',
 0.0030, 0.0040),
(NULL, 'Rodotrem', 'rodotrem', 70, 9, 25, 2.6, 'tertiary',
 '{tertiary}', '{track,unclassified}',
 '{"primary": 55, "secondary": 45, "tertiary": 35, "unclassified": 20, "track": 15, "residential": 25}',
 0.0030, 0.0040),
(NULL, 'Pentaminhão', 'pentaminhao', 90, 11, 30, 3.2, 'secondary',
 '{tertiary}', '{track,unclassified,residential}',
 '{"primary": 50, "secondary": 40, "tertiary": 25, "unclassified": 15, "track": 10, "residential": 20}',
 0.0030, 0.0040)
ON CONFLICT DO NOTHING;

-- ============================================================
-- Configurações do sistema
-- ============================================================
CREATE TABLE IF NOT EXISTS system_config (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO system_config (key, value, description) VALUES
('fuel_model', '{"r0": 0.003, "alpha": 0.004, "slope_clip": 6.0}', 'Parâmetros do modelo de consumo'),
('fuel_price', '{"default": 6.0, "currency": "BRL"}', 'Preço do combustível'),
('climate_factors', '{"seco": 1.0, "umido": 1.08, "molhado": 1.15, "enlameado": 1.30, "severo": 1.50, "safra_mix": 1.069}', 'Fatores climáticos'),
('season', '{"days": 220, "availability": 0.85, "trips_per_day": 5}', 'Configuração de safra'),
('road_trafficability', '{"primary": {"seco": 1.0, "umido": 0.98, "molhado": 0.95, "enlameado": 0.90, "severo": 0.85}, "secondary": {"seco": 1.0, "umido": 0.95, "molhado": 0.90, "enlameado": 0.80, "severo": 0.70}, "tertiary": {"seco": 1.0, "umido": 0.90, "molhado": 0.80, "enlameado": 0.60, "severo": 0.45}, "unclassified": {"seco": 1.0, "umido": 0.80, "molhado": 0.65, "enlameado": 0.40, "severo": 0.25}, "track": {"seco": 1.0, "umido": 0.65, "molhado": 0.40, "enlameado": 0.20, "severo": 0.05}}', 'Trafegabilidade por tipo de via e clima')
ON CONFLICT DO NOTHING;
