"""
Script de limpeza cirúrgica de registros de teste na base de produção (Neon Postgres).

Alvo:
  - davi.test.qa+bugcheck@viraxis.dev
  - davi-audit-a-*@test.com
  - davi-audit-b-*@test.com

Fluxo:
  1. SELECT de confirmação: lista os usuários-alvo e conta linhas relacionadas
     em TODAS as tabelas com FK para users (offices, content_decisions,
     content_items, niche_profiles, performance_metrics, raw_videos,
     social_accounts, trend_snapshots, agent_run_logs).
  2. Só prossegue para o DELETE se as tabelas com ON DELETE CASCADE não
     tiverem nenhuma linha associada (baixo risco confirmado). Se houver
     qualquer linha associada em tabela CASCADE, aborta sem deletar nada.
  3. DELETE apenas dos usuários-alvo, por email exato/prefixo (WHERE explícito,
     sem TRUNCATE, sem DELETE amplo).
  4. Reporta contagem de linhas afetadas.

Uso:
  DATABASE_URL=postgresql://... python scripts/cleanup_test_users.py           # dry-run (só SELECT)
  DATABASE_URL=postgresql://... python scripts/cleanup_test_users.py --execute # roda o DELETE de fato
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg2
import psycopg2.extras

TARGET_EXACT_EMAIL = "davi.test.qa+bugcheck@viraxis.dev"
TARGET_PREFIXES = ["davi-audit-a-", "davi-audit-b-"]

# Tabelas com FK para users.id, junto com o nome da coluna FK.
# Todas têm ON DELETE CASCADE exceto agent_run_logs (ON DELETE SET NULL).
RELATED_TABLES = [
    ("offices", "user_id", "CASCADE"),
    ("content_decisions", "user_id", "CASCADE"),
    ("content_items", "user_id", "CASCADE"),
    ("niche_profiles", "user_id", "CASCADE"),
    ("performance_metrics", "user_id", "CASCADE"),
    ("raw_videos", "user_id", "CASCADE"),
    ("social_accounts", "user_id", "CASCADE"),
    ("trend_snapshots", "user_id", "CASCADE"),
    ("agent_run_logs", "user_id", "SET NULL"),
]

WHERE_CLAUSE = "(email = %s OR email LIKE %s OR email LIKE %s)"
WHERE_PARAMS = (TARGET_EXACT_EMAIL, f"{TARGET_PREFIXES[0]}%", f"{TARGET_PREFIXES[1]}%")


def get_conn(database_url: str):
    return psycopg2.connect(database_url)


def select_targets(cur) -> list[dict]:
    cur.execute(
        f"""
        SELECT id, email, created_at
        FROM users
        WHERE {WHERE_CLAUSE}
        ORDER BY email;
        """,
        WHERE_PARAMS,
    )
    rows = cur.fetchall()
    return rows


def count_related(cur, user_ids: list) -> dict:
    """Conta linhas relacionadas em cada tabela dependente, para os user_ids dados."""
    counts = {}
    if not user_ids:
        return counts
    for table, col, on_delete in RELATED_TABLES:
        cur.execute(
            f"SELECT COUNT(*) AS n FROM {table} WHERE {col} = ANY(%s::uuid[]);",
            (user_ids,),
        )
        row = cur.fetchone()
        count = row["n"]
        counts[table] = {"count": count, "on_delete": on_delete}
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Executa o DELETE de fato. Sem essa flag, roda apenas o SELECT de confirmação (dry-run).",
    )
    parser.add_argument(
        "--allow-related-test-data",
        action="store_true",
        help=(
            "Permite prosseguir mesmo se houver linhas em tabelas CASCADE, desde que "
            "tenham sido inspecionadas manualmente e confirmadas como artefatos de teste "
            "(ex.: social_accounts sem office_id, sem tokens reais, criado no mesmo teste). "
            "Use com cautela — só depois de inspecionar o conteúdo das linhas."
        ),
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERRO: variável de ambiente DATABASE_URL não definida.", file=sys.stderr)
        return 1

    conn = get_conn(database_url)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. SELECT de confirmação
            targets = select_targets(cur)
            print(f"== SELECT de confirmação: {len(targets)} usuário(s) encontrado(s) ==")
            for row in targets:
                print(f"  - id={row['id']} email={row['email']} created_at={row['created_at']}")

            if not targets:
                print("Nenhum usuário-alvo encontrado. Nada a fazer.")
                return 0

            user_ids = [row["id"] for row in targets]

            # 2. Conferir dados relacionados em todas as tabelas dependentes
            related = count_related(cur, user_ids)
            print("\n== Contagem de registros relacionados por tabela ==")
            cascade_has_data = False
            for table, info in related.items():
                print(f"  - {table}: {info['count']} linha(s) (ON DELETE {info['on_delete']})")
                if info["on_delete"] == "CASCADE" and info["count"] > 0:
                    cascade_has_data = True

            if cascade_has_data and not args.allow_related_test_data:
                print(
                    "\nABORTADO: pelo menos uma tabela com ON DELETE CASCADE tem "
                    "linhas associadas a estes usuários. Isso contradiz a premissa "
                    "de 'sem offices/dados associados'. Nenhum DELETE foi executado. "
                    "Inspecione manualmente o conteúdo dessas linhas e, se forem "
                    "confirmadamente artefatos de teste, rode novamente com "
                    "--allow-related-test-data.",
                    file=sys.stderr,
                )
                conn.rollback()
                return 2

            if cascade_has_data and args.allow_related_test_data:
                print(
                    "\nAVISO: há linhas em tabela(s) CASCADE associadas a estes "
                    "usuários, mas --allow-related-test-data foi passado — "
                    "prosseguindo sob a premissa de que essas linhas já foram "
                    "inspecionadas manualmente e confirmadas como artefatos de teste."
                )
            else:
                print(
                    "\nConfirmado: nenhuma tabela com ON DELETE CASCADE tem dados "
                    "associados a estes usuários. Seguro prosseguir."
                )

            if not args.execute:
                print(
                    "\n[DRY-RUN] Nenhum DELETE executado. Rode novamente com --execute "
                    "para aplicar a remoção."
                )
                conn.rollback()
                return 0

            # 3. DELETE cirúrgico, apenas pelos IDs já confirmados no SELECT acima
            cur.execute(
                "DELETE FROM users WHERE id = ANY(%s::uuid[]);",
                (user_ids,),
            )
            deleted_count = cur.rowcount
            conn.commit()

            print(f"\n== DELETE executado: {deleted_count} usuário(s) removido(s) ==")
            for row in targets:
                print(f"  - removido: id={row['id']} email={row['email']}")

            return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
