#!/usr/bin/env python3
"""
CanaRoute - Script de Seed Data
Popula o banco com dados iniciais: veículos padrão, pedágios SP, zonas urbanas.
"""
import asyncio
import sys
sys.path.insert(0, '/app')

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://canaroute:canaroute@localhost:5432/canaroute")


async def seed():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # ===== VEÍCULOS PADRÃO =====
        await db.execute(text("""
            INSERT INTO vehicles (name, slug, pbt_tons, axles, length_m, width_m, fuel_r0, fuel_alpha, speed_by_road_class, allowed_highways, created_at)
            VALUES
            ('Treminhão', 'treminhao', 55, 7, 20, 2.6, 0.0030, 0.0040,
             '{"primary":60,"secondary":50,"tertiary":40,"unclassified":30,"track":20}',
             '["primary","secondary","tertiary","unclassified","track"]', NOW()),
            ('Rodotrem', 'rodotrem', 70, 9, 25, 2.6, 0.0030, 0.0040,
             '{"primary":55,"secondary":45,"tertiary":35,"unclassified":25,"track":15}',
             '["primary","secondary","tertiary","unclassified"]', NOW()),
            ('Pentaminhão', 'pentaminhao', 90, 11, 30, 3.2, 0.0030, 0.0040,
             '{"primary":50,"secondary":40,"tertiary":25,"unclassified":20,"track":10}',
             '["primary","secondary"]', NOW())
            ON CONFLICT (slug) DO NOTHING;
        """))

        # ===== PEDÁGIOS REGIÃO SP (Jaboticabal/Pradópolis) =====
        await db.execute(text("""
            INSERT INTO toll_plazas (name, latitude, longitude, highway, km_marker, cost_per_axle, bidirectional, active, created_at)
            VALUES
            ('Guariba (SP-322)', -21.3550, -48.2300, 'SP-322', 345, 7.80, true, true, NOW()),
            ('Jaboticabal (SP-322)', -21.2550, -48.3220, 'SP-322', 312, 7.80, true, true, NOW()),
            ('Taquaritinga (SP-326)', -21.4050, -48.5050, 'SP-326', 278, 6.50, true, true, NOW()),
            ('Matão (SP-326)', -21.6030, -48.3660, 'SP-326', 245, 6.50, true, true, NOW()),
            ('Bebedouro (SP-310)', -20.9490, -48.4790, 'SP-310', 432, 8.20, true, true, NOW()),
            ('Araraquara (SP-310)', -21.7940, -48.1760, 'SP-310', 285, 8.20, true, true, NOW()),
            ('Monte Azul Paulista (SP-333)', -20.9060, -48.6410, 'SP-333', 156, 5.90, true, true, NOW()),
            ('Itápolis (SP-318)', -21.5960, -48.8130, 'SP-318', 189, 6.10, true, true, NOW())
            ON CONFLICT DO NOTHING;
        """))

        # ===== ZONAS URBANAS REGIÃO SP =====
        await db.execute(text("""
            INSERT INTO urban_zones (name, latitude, longitude, radius_m, restriction_level, active, created_at)
            VALUES
            ('Guariba', -21.3550, -48.2280, 2500, 'blocked', true, NOW()),
            ('Jaboticabal', -21.2550, -48.3220, 4000, 'blocked', true, NOW()),
            ('Pradópolis', -21.3630, -48.0660, 2000, 'blocked', true, NOW()),
            ('Bebedouro', -20.9490, -48.4790, 3500, 'blocked', true, NOW()),
            ('Taquaritinga', -21.4050, -48.5050, 3000, 'blocked', true, NOW()),
            ('Monte Azul Paulista', -20.9060, -48.6410, 2500, 'blocked', true, NOW()),
            ('Matão', -21.6030, -48.3660, 3500, 'blocked', true, NOW()),
            ('Araraquara', -21.7940, -48.1760, 5000, 'blocked', true, NOW()),
            ('Itápolis', -21.5960, -48.8130, 2500, 'blocked', true, NOW()),
            ('Viradouro', -20.8730, -48.2950, 2000, 'caution', true, NOW()),
            ('Barrinha', -21.1930, -48.1640, 2000, 'caution', true, NOW()),
            ('Pitangueiras', -21.0090, -48.2210, 2500, 'blocked', true, NOW())
            ON CONFLICT DO NOTHING;
        """))

        # ===== CLIENTE DEMO (SAJB) =====
        await db.execute(text("""
            INSERT INTO clients (name, slug, state, created_at)
            VALUES ('São José da Boa Vista (SAJB)', 'sajb', 'SP', NOW())
            ON CONFLICT (slug) DO NOTHING;
        """))

        # ===== USINA DEMO =====
        await db.execute(text("""
            INSERT INTO plants (client_id, name, latitude, longitude, capacity_tons_day, created_at)
            SELECT id, 'COA (Usina)', -21.3436637, -48.3050909, 15000, NOW()
            FROM clients WHERE slug = 'sajb'
            ON CONFLICT DO NOTHING;
        """))

        await db.commit()
        print("✅ Seed data inserido com sucesso!")
        print("   - 3 veículos (Treminhão, Rodotrem, Pentaminhão)")
        print("   - 8 praças de pedágio (SP)")
        print("   - 12 zonas urbanas")
        print("   - 1 cliente demo (SAJB)")
        print("   - 1 usina (COA)")


if __name__ == "__main__":
    asyncio.run(seed())
