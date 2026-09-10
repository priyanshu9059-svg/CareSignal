"""Versioned initial schema migration; safe to run repeatedly."""
from sqlalchemy import text
from app.database import Base, engine

def migrate():
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(30) PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'))
        if not connection.execute(text("SELECT version FROM schema_migrations WHERE version='0001'")).first():
            Base.metadata.create_all(connection)
            connection.execute(text("INSERT INTO schema_migrations(version) VALUES ('0001')"))
    print('Schema migration 0001 applied or already present.')

if __name__=='__main__': migrate()
