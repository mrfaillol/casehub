"""
CaseHub - Database Configuration
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def init_db():
    from . import user, client, case  # noqa: F401 — register core tables in metadata
    import logging
    from sqlalchemy.exc import SQLAlchemyError
    try:
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError as exc:
        # Multiple app workers run init_db() concurrently on boot. create_all's
        # check-then-create is NOT atomic across workers, so two can race to
        # CREATE the same new table/type — the loser raises (Postgres "duplicate
        # key ... pg_type_typname_nsp_index" / "relation already exists"). The
        # table ends up created by the winner; dispose the poisoned connections
        # and retry once (now a no-op via checkfirst). A boot race must never
        # crash a worker on the live alpha.
        logging.getLogger(__name__).warning("init_db create_all race; retrying once: %s", exc)
        engine.dispose()
        try:
            Base.metadata.create_all(bind=engine)
        except SQLAlchemyError as exc2:
            logging.getLogger(__name__).warning(
                "init_db create_all retry also failed (tables likely created by "
                "a peer worker — continuing): %s", exc2,
            )
