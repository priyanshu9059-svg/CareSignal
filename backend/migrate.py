"""Versioned schema migrations. Safe to run repeatedly.

Uses Alembic when available. Falls back to ordered SQLAlchemy steps for local/demo
and stamps Alembic when upgrading an existing 0001 database.
"""
from pathlib import Path
from sqlalchemy import text, inspect
from app.database import Base, engine, RevokedToken

ROOT = Path(__file__).resolve().parent

STEPS = [
    ('0001', 'Initial schema', lambda conn: Base.metadata.create_all(bind=conn)),
    ('0002', 'Revoked JWT tokens', lambda conn: RevokedToken.__table__.create(bind=conn, checkfirst=True)),
]

def _ensure_table(connection):
    connection.execute(text(
        'CREATE TABLE IF NOT EXISTS schema_migrations ('
        'version VARCHAR(30) PRIMARY KEY, '
        'applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'
    ))

def migrate():
    with engine.begin() as connection:
        _ensure_table(connection)
        applied = {row[0] for row in connection.execute(text('SELECT version FROM schema_migrations'))}
        for version, label, apply in STEPS:
            if version in applied:
                continue
            apply(connection)
            connection.execute(text('INSERT INTO schema_migrations(version) VALUES (:v)'), {'v': version})
            print(f'Schema migration {version} applied ({label}).')
        if not any(version not in applied for version, _, _ in STEPS):
            print('Schema migrations up to date.')
    _sync_alembic_stamp()

def _sync_alembic_stamp():
    """Keep alembic_version aligned so `alembic upgrade` is usable going forward."""
    try:
        from alembic.config import Config
        from alembic import command
    except ImportError:
        return
    cfg = Config(str(ROOT / 'alembic.ini'))
    cfg.set_main_option('script_location', str(ROOT / 'alembic'))
    with engine.begin() as connection:
        inspector = inspect(connection)
        if 'alembic_version' not in inspector.get_table_names():
            command.stamp(cfg, '0002_revoked_tokens')
            print('Alembic stamped at 0002_revoked_tokens.')
            return
        current = connection.execute(text('SELECT version_num FROM alembic_version')).scalar()
        if not current:
            command.stamp(cfg, '0002_revoked_tokens')

if __name__ == '__main__':
    migrate()
