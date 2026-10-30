from alembic import context

from app.core import db
from app.core.models import Base

with db.engine().connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
