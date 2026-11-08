from alembic import command


def test_migrations_go_down_and_up_cleanly(alembic_config):
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")


def test_models_match_migrations(alembic_config):
    command.check(alembic_config)
