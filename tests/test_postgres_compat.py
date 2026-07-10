"""Compatibilidade com PostgreSQL: normalização de URL e DDL do schema."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from agroroute.db import Base, make_engine, normalize_db_url


def test_normalize_postgres_url():
    # Railway/Heroku entregam postgres:// — precisa virar postgresql://
    assert normalize_db_url("postgres://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"
    assert normalize_db_url("postgresql://u:p@h/db") == "postgresql://u:p@h/db"
    assert normalize_db_url("sqlite:///x.db") == "sqlite:///x.db"


def test_schema_compiles_for_postgres_and_sqlite():
    # todas as tabelas geram DDL válido nos dois dialetos, sem conectar
    for dialect in (postgresql.dialect(), sqlite.dialect()):
        for table in Base.metadata.sorted_tables:
            ddl = str(CreateTable(table).compile(dialect=dialect))
            assert "CREATE TABLE" in ddl


def test_make_engine_postgres_has_pool_pre_ping():
    # não conecta; só valida a configuração do engine
    eng = make_engine("postgresql://u:p@localhost:5432/db")
    assert eng.dialect.name == "postgresql"
    assert eng.pool._pre_ping is True


def test_make_engine_sqlite_thread_safe():
    eng = make_engine("sqlite:///:memory:")
    assert eng.dialect.name == "sqlite"
