"""
Tests unitaires — Repository[T] CRUD générique (ADR-017).

Vérifie les opérations CRUD et les filtres dynamiques
(style Django QuerySet.filter()) avec une base SQLite en mémoire.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import ClassVar

import pytest
from pydantic import Field

from pyworkflow_engine.adapters.storage.repository import Repository
from pyworkflow_engine.adapters.storage.schema_generator import SchemaGenerator
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

_ITEM_META = TableMeta(
    table_name="items",
    columns=[
        ColumnDef("id", ColumnType.TEXT, primary_key=True),
        ColumnDef("name", ColumnType.TEXT, nullable=False),
        ColumnDef("category", ColumnType.TEXT),
        ColumnDef("score", ColumnType.REAL),
        ColumnDef("count", ColumnType.INTEGER),
        ColumnDef("is_active", ColumnType.BOOLEAN),
        ColumnDef("tags", ColumnType.JSON),
        ColumnDef("created_at", ColumnType.TIMESTAMP),
        ColumnDef("updated_at", ColumnType.TIMESTAMP),
    ],
    indexes=[("name",), ("category",)],
)


class Item(PersistableModel):
    """Modèle de test pour le Repository."""

    __table_meta__: ClassVar[TableMeta] = _ITEM_META

    id: str = "test-1"
    name: str = "Test"
    category: str | None = "default"
    score: float = 0.0
    count: int = 0
    is_active: bool = True
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@pytest.fixture(autouse=True)
def _clean_registry():
    """Sauvegarde et restaure le ModelRegistry autour de chaque test."""
    saved = ModelRegistry.get_all()
    ModelRegistry.clear()
    ModelRegistry.register(Item)
    yield
    ModelRegistry.clear()
    for model in saved.values():
        ModelRegistry.register(model)


@pytest.fixture()
def conn() -> sqlite3.Connection:
    """Connexion SQLite in-memory avec table créée."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")

    # Créer la table
    ddl = SchemaGenerator.generate_create_table(_ITEM_META)
    connection.execute(ddl)
    for idx in SchemaGenerator.generate_indexes(_ITEM_META):
        connection.execute(idx)
    connection.commit()

    yield connection
    connection.close()


@pytest.fixture()
def repo(conn: sqlite3.Connection) -> Repository[Item]:
    """Repository[Item] prêt à l'emploi."""
    return Repository(conn, Item)


def _make_item(
    id: str = "item-1",
    name: str = "Widget",
    category: str = "A",
    score: float = 5.0,
    count: int = 10,
    is_active: bool = True,
    tags: list[str] | None = None,
) -> Item:
    """Helper pour créer un Item de test."""
    return Item(
        id=id,
        name=name,
        category=category,
        score=score,
        count=count,
        is_active=is_active,
        tags=tags or [],
    )


# ── Create Tests ─────────────────────────────────────────────────────────────


class TestRepositoryCreate:
    """Tests pour create() et create_or_update()."""

    def test_create(self, repo: Repository[Item]):
        """Insertion simple."""
        item = _make_item()
        result = repo.create(item)
        assert result.id == "item-1"

        found = repo.get("item-1")
        assert found is not None
        assert found.name == "Widget"

    def test_create_duplicate_raises(self, repo: Repository[Item]):
        """Insertion d'une PK existante lève IntegrityError."""
        repo.create(_make_item(id="dup"))
        with pytest.raises(sqlite3.IntegrityError):
            repo.create(_make_item(id="dup"))

    def test_create_or_update_insert(self, repo: Repository[Item]):
        """create_or_update() insère si absent."""
        repo.create_or_update(_make_item(id="new-1"))
        assert repo.exists("new-1")

    def test_create_or_update_upsert(self, repo: Repository[Item]):
        """create_or_update() remplace si PK existe."""
        repo.create(_make_item(id="up-1", name="Old"))
        repo.create_or_update(_make_item(id="up-1", name="New"))

        found = repo.get("up-1")
        assert found is not None
        assert found.name == "New"


# ── Read Tests ───────────────────────────────────────────────────────────────


class TestRepositoryRead:
    """Tests pour get(), get_or_raise(), filter(), all(), count(), exists()."""

    def test_get_found(self, repo: Repository[Item]):
        repo.create(_make_item(id="r-1"))
        assert repo.get("r-1") is not None

    def test_get_not_found(self, repo: Repository[Item]):
        assert repo.get("nonexistent") is None

    def test_get_or_raise_found(self, repo: Repository[Item]):
        repo.create(_make_item(id="r-2"))
        item = repo.get_or_raise("r-2")
        assert item.id == "r-2"

    def test_get_or_raise_not_found(self, repo: Repository[Item]):
        with pytest.raises(LookupError, match="not found"):
            repo.get_or_raise("nonexistent")

    def test_all(self, repo: Repository[Item]):
        repo.create(_make_item(id="a-1"))
        repo.create(_make_item(id="a-2"))
        repo.create(_make_item(id="a-3"))
        assert len(repo.all()) == 3

    def test_all_order_by(self, repo: Repository[Item]):
        repo.create(_make_item(id="o-1", name="Charlie"))
        repo.create(_make_item(id="o-2", name="Alice"))
        repo.create(_make_item(id="o-3", name="Bob"))

        results = repo.all(order_by="name")
        names = [r.name for r in results]
        assert names == ["Alice", "Bob", "Charlie"]

    def test_all_order_by_desc(self, repo: Repository[Item]):
        repo.create(_make_item(id="d-1", score=1.0))
        repo.create(_make_item(id="d-2", score=3.0))
        repo.create(_make_item(id="d-3", score=2.0))

        results = repo.all(order_by="-score")
        scores = [r.score for r in results]
        assert scores == [3.0, 2.0, 1.0]

    def test_count(self, repo: Repository[Item]):
        assert repo.count() == 0
        repo.create(_make_item(id="c-1"))
        repo.create(_make_item(id="c-2"))
        assert repo.count() == 2

    def test_count_with_filter(self, repo: Repository[Item]):
        repo.create(_make_item(id="cf-1", category="A"))
        repo.create(_make_item(id="cf-2", category="B"))
        repo.create(_make_item(id="cf-3", category="A"))
        assert repo.count(category="A") == 2

    def test_exists(self, repo: Repository[Item]):
        repo.create(_make_item(id="e-1"))
        assert repo.exists("e-1") is True
        assert repo.exists("nope") is False


# ── Filter Tests ─────────────────────────────────────────────────────────────


class TestRepositoryFilter:
    """Tests pour les filtres dynamiques style Django."""

    def test_filter_exact(self, repo: Repository[Item]):
        repo.create(_make_item(id="f-1", category="X"))
        repo.create(_make_item(id="f-2", category="Y"))
        repo.create(_make_item(id="f-3", category="X"))

        results = repo.filter(category="X")
        assert len(results) == 2

    def test_filter_gte(self, repo: Repository[Item]):
        repo.create(_make_item(id="g-1", score=1.0))
        repo.create(_make_item(id="g-2", score=5.0))
        repo.create(_make_item(id="g-3", score=10.0))

        results = repo.filter(score__gte=5.0)
        assert len(results) == 2

    def test_filter_lte(self, repo: Repository[Item]):
        repo.create(_make_item(id="l-1", score=1.0))
        repo.create(_make_item(id="l-2", score=5.0))
        repo.create(_make_item(id="l-3", score=10.0))

        results = repo.filter(score__lte=5.0)
        assert len(results) == 2

    def test_filter_gt(self, repo: Repository[Item]):
        repo.create(_make_item(id="gt-1", count=5))
        repo.create(_make_item(id="gt-2", count=10))

        results = repo.filter(count__gt=5)
        assert len(results) == 1
        assert results[0].id == "gt-2"

    def test_filter_lt(self, repo: Repository[Item]):
        repo.create(_make_item(id="lt-1", count=5))
        repo.create(_make_item(id="lt-2", count=10))

        results = repo.filter(count__lt=10)
        assert len(results) == 1
        assert results[0].id == "lt-1"

    def test_filter_like(self, repo: Repository[Item]):
        repo.create(_make_item(id="lk-1", name="Hello World"))
        repo.create(_make_item(id="lk-2", name="Goodbye World"))
        repo.create(_make_item(id="lk-3", name="Hello There"))

        results = repo.filter(name__like="Hello%")
        assert len(results) == 2

    def test_filter_in(self, repo: Repository[Item]):
        repo.create(_make_item(id="in-1", category="A"))
        repo.create(_make_item(id="in-2", category="B"))
        repo.create(_make_item(id="in-3", category="C"))

        results = repo.filter(category__in=["A", "C"])
        assert len(results) == 2
        categories = {r.category for r in results}
        assert categories == {"A", "C"}

    def test_filter_isnull_true(self, repo: Repository[Item]):
        """__isnull=True → IS NULL (pour les champs NULL en DB)."""
        # Item always has category set, so this tests the mechanism.
        # We need to insert a row with NULL category directly.
        repo._conn.execute(
            "INSERT INTO items (id, name, category, score, count, is_active, tags, created_at, updated_at) "
            "VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)",
            (
                "null-1",
                "NullCat",
                0.0,
                0,
                1,
                "[]",
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
            ),
        )
        repo._conn.commit()

        results = repo.filter(category__isnull=True)
        assert len(results) == 1
        assert results[0].id == "null-1"

    def test_filter_isnull_false(self, repo: Repository[Item]):
        """__isnull=False → IS NOT NULL."""
        repo.create(_make_item(id="nn-1", category="A"))
        results = repo.filter(category__isnull=False)
        assert len(results) == 1

    def test_filter_boolean(self, repo: Repository[Item]):
        """Filtrage sur booléen."""
        repo.create(_make_item(id="b-1", is_active=True))
        repo.create(_make_item(id="b-2", is_active=False))

        active = repo.filter(is_active=True)
        assert len(active) == 1
        assert active[0].id == "b-1"

        inactive = repo.filter(is_active=False)
        assert len(inactive) == 1
        assert inactive[0].id == "b-2"

    def test_filter_multiple_conditions(self, repo: Repository[Item]):
        """Conditions multiples (AND)."""
        repo.create(_make_item(id="m-1", category="A", score=5.0))
        repo.create(_make_item(id="m-2", category="A", score=10.0))
        repo.create(_make_item(id="m-3", category="B", score=5.0))

        results = repo.filter(category="A", score__gte=7.0)
        assert len(results) == 1
        assert results[0].id == "m-2"

    def test_filter_limit_offset(self, repo: Repository[Item]):
        """Pagination avec limit + offset."""
        for i in range(5):
            repo.create(_make_item(id=f"p-{i}", name=f"Item {i}"))

        page1 = repo.filter(limit=2, offset=0, order_by="id")
        assert len(page1) == 2

        page2 = repo.filter(limit=2, offset=2, order_by="id")
        assert len(page2) == 2

        page3 = repo.filter(limit=2, offset=4, order_by="id")
        assert len(page3) == 1

    def test_filter_invalid_column_raises(self, repo: Repository[Item]):
        """Colonne invalide → ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            repo.filter(nonexistent_col="x")

    def test_filter_in_invalid_type_raises(self, repo: Repository[Item]):
        """__in avec une non-list → ValueError."""
        with pytest.raises(ValueError, match="expects a list"):
            repo.filter(category__in="not_a_list")


# ── Update Tests ─────────────────────────────────────────────────────────────


class TestRepositoryUpdate:
    """Tests pour update()."""

    def test_update(self, repo: Repository[Item]):
        item = _make_item(id="u-1", name="Original")
        repo.create(item)

        updated = item.model_copy(update={"name": "Updated"})
        repo.update(updated)

        found = repo.get("u-1")
        assert found is not None
        assert found.name == "Updated"

    def test_update_not_found_raises(self, repo: Repository[Item]):
        item = _make_item(id="ghost")
        with pytest.raises(LookupError, match="not found"):
            repo.update(item)


# ── Delete Tests ─────────────────────────────────────────────────────────────


class TestRepositoryDelete:
    """Tests pour delete() et delete_where()."""

    def test_delete(self, repo: Repository[Item]):
        repo.create(_make_item(id="d-1"))
        assert repo.delete("d-1") is True
        assert repo.get("d-1") is None

    def test_delete_not_found(self, repo: Repository[Item]):
        assert repo.delete("nope") is False

    def test_delete_where(self, repo: Repository[Item]):
        repo.create(_make_item(id="dw-1", category="X"))
        repo.create(_make_item(id="dw-2", category="Y"))
        repo.create(_make_item(id="dw-3", category="X"))

        deleted = repo.delete_where(category="X")
        assert deleted == 2
        assert repo.count() == 1

    def test_delete_where_no_match(self, repo: Repository[Item]):
        repo.create(_make_item(id="dw-4"))
        deleted = repo.delete_where(category="ZZZ")
        assert deleted == 0
