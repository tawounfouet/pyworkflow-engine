"""
Smoke test — RestConnector
==========================

Vérifie que le connecteur HTTP REST est fonctionnel en récupérant
une ressource publique depuis JSONPlaceholder.

Exécution :
    python examples/connector_http_smoke_test.py
"""

from __future__ import annotations

import json

from pyconnectors.config import ConnectorConfig
from pyconnectors.factory import ConnectorFactory

# L'import du module déclenche le décorateur @connector("http.rest")
# qui enregistre RestConnector dans le registre global.
import pyconnectors.connectors.http.rest  # noqa: F401


def main() -> None:
    config = ConnectorConfig(name="jsonplaceholder")

    # Instanciation via la factory (enregistrement @connector("http.rest"))
    http = ConnectorFactory.create("http.rest", config=config)
    print(f"Connecteur créé : {http!r}")

    # ── GET simple ────────────────────────────────────────────────────────
    print("\n[GET] https://jsonplaceholder.typicode.com/todos/1")
    result = http.safe_execute("GET", "https://jsonplaceholder.typicode.com/todos/1")

    if result.success:
        body = json.loads(result.data["body"])  # body est une chaîne JSON
        print(f"  ✓ Statut HTTP : {result.data['status']}")
        print(f"  ✓ Durée       : {result.duration:.3f}s")
        print(f"  ✓ Données     : {body}")
    else:
        print(f"  ✗ Erreur : {result.error}")

    # ── GET liste ─────────────────────────────────────────────────────────
    print(
        "\n[GET] https://jsonplaceholder.typicode.com/todos  (limit 3 via query param)"
    )
    result2 = http.safe_execute(
        "GET",
        "https://jsonplaceholder.typicode.com/todos",
        query_params={"_limit": "3"},
    )

    if result2.success:
        items = json.loads(result2.data["body"])
        print(f"  ✓ {len(items)} items reçus")
        for item in items:
            print(f"    - [{item['id']}] {item['title']}")
    else:
        print(f"  ✗ Erreur : {result2.error}")

    # ── POST ──────────────────────────────────────────────────────────────
    print("\n[POST] https://jsonplaceholder.typicode.com/posts")
    result3 = http.safe_execute(
        "POST",
        "https://jsonplaceholder.typicode.com/posts",
        data={"title": "test pyconnectors", "body": "smoke test", "userId": 1},
    )

    if result3.success:
        created = json.loads(result3.data["body"])
        print(f"  ✓ Ressource créée, id : {created.get('id')}")
    else:
        print(f"  ✗ Erreur : {result3.error}")


if __name__ == "__main__":
    main()
