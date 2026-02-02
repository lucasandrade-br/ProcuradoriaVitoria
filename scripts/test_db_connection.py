"""Utility script to check connectivity with the configured MySQL database."""
from __future__ import annotations

from pathlib import Path
import sys

import MySQLdb
import environ


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


def load_env() -> environ.Env:
    """Load environment variables from the .env file."""
    env = environ.Env()
    if not ENV_FILE.exists():
        raise FileNotFoundError(f"Arquivo .env não encontrado em {ENV_FILE}")
    environ.Env.read_env(ENV_FILE)
    return env


def main() -> None:
    env = load_env()
    config = {
        "host": env("DB_HOST"),
        "user": env("DB_USER"),
        "passwd": env("DB_PASSWORD"),
        "db": env("DB_NAME"),
        "port": env.int("DB_PORT", default=3306),
        "connect_timeout": 10,
        "charset": "utf8mb4",
    }

    print(
        "Testando conexão MySQL em "
        f"{config['host']}:{config['port']} (database {config['db']})..."
    )

    connection = None
    try:
        connection = MySQLdb.connect(**config)
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            print("Conexão estabelecida com sucesso. SELECT 1 retornou:", result[0])
    except MySQLdb.OperationalError as exc:
        print("Erro operacional ao conectar ao banco de dados:", exc)
        sys.exit(1)
    except Exception as exc:  # pylint: disable=broad-except
        print("Erro inesperado ao testar a conexão:", exc)
        sys.exit(1)
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    main()
