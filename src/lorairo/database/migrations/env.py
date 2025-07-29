# Add imports for your models and db core functionality
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from lorairo.database.schema import Base  # Use absolute import from src

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata  # Set your Base's metadata here

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


# --- Function to attach tag_db (Commented out for now) ---
# def _attach_tag_database(connection):
#     """Attaches the tag database to the current connection."""
#     # TODO: Make TAG_DB_PATH dynamic from config or db_core
#     tag_db_path = "local_packages/genai-tag-db-tools/tags_v4.db" # Placeholder, adjust as needed
#     tag_db_attach_sql = f"ATTACH DATABASE '{tag_db_path}' AS tag_db;"
#     try:
#         connection.execute(text(tag_db_attach_sql))
#         print(f"Attached database: {tag_db_path} AS tag_db") # Use print or logging
#     except Exception as e:
#         print(f"Error attaching tag database: {e}")


# --- Function to ignore tag_db schema objects ---
def include_object(object, name, type_, reflected, compare_to):
    """Exclude objects belonging to the 'tag_db' schema from comparison."""
    # Only check schema for tables
    if type_ == "table" and hasattr(object, "schema") and object.schema == "tag_db":
        return False
    # For other object types (indexes, constraints, etc.), assume they should be included
    # unless specific rules are added later.
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Add include_schemas=True if using schemas like tag_db
        # include_schemas=True, # Keep or remove? Test needed.
        # Use render_as_batch for SQLite support
        render_as_batch=True,
        # Filter objects to exclude tag_db
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # --- Modified section to use engine from db_core or config ---
    # Option 1: Get engine from db_core (if it handles creation)
    # engine = get_engine() # Assuming get_engine returns the configured engine

    # Option 2: Use configuration from alembic.ini (more standard Alembic way)
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Attach the tag database here (Commented out)
        # _attach_tag_database(connection)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Add include_schemas=True if using schemas like tag_db
            # include_schemas=True, # Keep or remove? Test needed.
            # Compare type for SQLite
            compare_type=True,
            # Use render_as_batch for SQLite support
            render_as_batch=True,
            # Filter objects to exclude tag_db
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


# --- process_revision_directives removed as render_as_batch is used ---

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
