"""
Tests unitaires — SchemaGenerator + ModelSerializer (ADR-017).

Vérifie la génération DDL et la sérialisation/désérialisation
Pydantic ↔ lignes SQL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel, Field

from pyworkflow_engine.adapters.storage.schema_generator import (
    ModelSerializer,
    SchemaGenerator,
)
from pyworkflow_engine.ports.persistable import (
    ColumnDef,
    ColumnType,
    ModelRegistry,
    PersistableModel,
    TableMeta,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


class EmbeddedConfig(BaseModel):
    """Sous-modèle embedded (non persisté séparément)."""

    max_retries: int = 3
    timeout: int = 30


@pytest.fixture(autouse=True)
def _clean_registry():
    """Sauvegarde et restaure le ModelRegistry autour de chaque test."""
    saved = ModelRegistry.get_all()
    ModelRegistry.clear()
    yield
    ModelRegistry.clear()
    for model in saved.values():
        ModelRegistry.register(model)


@pytest.fixture()
def sample_meta() -> TableMeta:
    """TableMeta de référence pour les tests."""
    return TableMeta(
        table_name="test_items",
        columns=[
            ColumnDef("id", ColumnType.TEXT, primary_key=True),
            ColumnDef("name", ColumnType.TEXT, nullable=False),
            ColumnDef("score", ColumnType.REAL),
            ColumnDef("count", ColumnType.INTEGER),
            ColumnDef("is_active", ColumnType.BOOLEAN),
            ColumnDef("config", ColumnType.JSON),
            ColumnDef("tags", ColumnType.JSON),
            ColumnDef("parent_id", ColumnType.TEXT, foreign_key="parents.id"),
            ColumnDef("created_at", ColumnType.TIMESTAMP),
        ],
        indexes=[("name",), ("parent_id",), ("name", "is_active")],
    )


@pytest.fixture()
def sample_model_class(sample_meta: TableMeta) -> type[PersistableModel]:
    """Crée un modèle PersistableModel de test."""

    @ModelRegistry.register
    class TestItem(PersistableModel):
        __table_meta__: ClassVar[TableMeta] = sample_meta

        id: str = "test-1"
        name: str = "Test"
        score: float | None = 0.0
        count: int | None = 0
        is_active: bool = True
        config: EmbeddedConfig = Field(default_factory=EmbeddedConfig)
        tags: list[str] = Field(default_factory=list)
        parent_id: str | None = None
        created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    return TestItem


# ── SchemaGenerator Tests ────────────────────────────────────────────────────


class TestSchemaGenerator:
    """Tests pour SchemaGenerator."""

    def test_generate_create_table_basic(self, sample_meta: TableMeta):
        """Vérifie la génération d'un CREATE TABLE basique."""
        sql = SchemaGenerator.generate_create_table(sample_meta)

        assert 'CREATE TABLE IF NOT EXISTS "test_items"' in sql
        assert '"id" TEXT PRIMARY KEY' in sql
        assert '"name" TEXT NOT NULL' in sql
        assert '"score" REAL' in sql
        assert '"count" INTEGER' in sql
        assert '"is_active" INTEGER' in sql  # BOOLEAN → INTEGER
        assert '"config" TEXT' in sql  # JSON → TEXT
        assert '"created_at" TIMESTAMP' in sql
        assert (
            'FOREIGN KEY ("parent_id") REFERENCES "parents"("id") ON DELETE CASCADE'
            in sql
        )

    def test_generate_create_table_no_fk(self):
        """Table sans FK — pas de FOREIGN KEY dans le DDL."""
        meta = TableMeta(
            table_name="simple",
            columns=[
                ColumnDef("id", ColumnType.TEXT, primary_key=True),
                ColumnDef("value", ColumnType.TEXT),
            ],
        )
        sql = SchemaGenerator.generate_create_table(meta)
        assert "FOREIGN KEY" not in sql
        assert 'CREATE TABLE IF NOT EXISTS "simple"' in sql

    def test_generate_indexes(self, sample_meta: TableMeta):
        """Vérifie la génération des index."""
        indexes = SchemaGenerator.generate_indexes(sample_meta)

        assert len(indexes) == 3
        assert any("idx_test_items_name" in idx for idx in indexes)
        assert any("idx_test_items_parent_id" in idx for idx in indexes)
        assert any("idx_test_items_name_is_active" in idx for idx in indexes)

    def test_generate_indexes_individual_column(self):
        """Index individuel via ColumnDef.index=True."""
        meta = TableMeta(
            table_name="indexed",
            columns=[
                ColumnDef("id", ColumnType.TEXT, primary_key=True),
                ColumnDef("email", ColumnType.TEXT, index=True),
            ],
        )
        indexes = SchemaGenerator.generate_indexes(meta)
        assert len(indexes) == 1
        assert "idx_indexed_email" in indexes[0]

    def test_generate_full_schema(self, sample_model_class: type[PersistableModel]):
        """generate_full_schema() utilise le ModelRegistry."""
        ddl = SchemaGenerator.generate_full_schema()

        assert "PRAGMA foreign_keys = ON" in ddl
        assert 'CREATE TABLE IF NOT EXISTS "test_items"' in ddl
        assert "idx_test_items_name" in ddl

    def test_generate_create_table_with_default(self):
        """Colonne avec valeur par défaut."""
        meta = TableMeta(
            table_name="defaults_test",
            columns=[
                ColumnDef("id", ColumnType.TEXT, primary_key=True),
                ColumnDef("priority", ColumnType.INTEGER, default=5),
                ColumnDef("status", ColumnType.TEXT, default="active"),
            ],
        )
        sql = SchemaGenerator.generate_create_table(meta)
        assert "DEFAULT 5" in sql
        assert "DEFAULT 'active'" in sql

    def test_generate_no_cascade(self):
        """FK sans CASCADE si foreign_keys_cascade=False."""
        meta = TableMeta(
            table_name="no_cascade",
            columns=[
                ColumnDef("id", ColumnType.TEXT, primary_key=True),
                ColumnDef("ref_id", ColumnType.TEXT, foreign_key="other.id"),
            ],
            foreign_keys_cascade=False,
        )
        sql = SchemaGenerator.generate_create_table(meta)
        assert "ON DELETE CASCADE" not in sql
        assert 'FOREIGN KEY ("ref_id") REFERENCES "other"("id")' in sql


# ── ModelSerializer Tests ────────────────────────────────────────────────────


class TestModelSerializer:
    """Tests pour ModelSerializer."""

    def test_to_row_basic(self, sample_model_class: type[PersistableModel]):
        """Vérifie la sérialisation basique."""
        instance = sample_model_class(
            id="item-1",
            name="Widget",
            score=9.5,
            count=42,
            is_active=True,
            tags=["a", "b"],
            parent_id="p-1",
        )
        row = ModelSerializer.to_row(instance)

        assert row["id"] == "item-1"
        assert row["name"] == "Widget"
        assert row["score"] == 9.5
        assert row["count"] == 42
        assert row["is_active"] == 1  # bool → int
        assert isinstance(row["tags"], str)  # list → JSON string
        assert '"a"' in row["tags"]
        assert row["parent_id"] == "p-1"
        assert isinstance(row["created_at"], str)  # datetime → isoformat

    def test_to_row_embedded_model(self, sample_model_class: type[PersistableModel]):
        """Les BaseModel embedded sont sérialisés en JSON."""
        instance = sample_model_class(
            config=EmbeddedConfig(max_retries=5, timeout=60),
        )
        row = ModelSerializer.to_row(instance)

        config_str = row["config"]
        assert isinstance(config_str, str)
        assert "max_retries" in config_str
        assert "5" in config_str

    def test_to_row_none_values(self, sample_model_class: type[PersistableModel]):
        """Les valeurs None restent None."""
        instance = sample_model_class(parent_id=None)
        row = ModelSerializer.to_row(instance)
        assert row["parent_id"] is None

    def test_from_row_basic(self, sample_model_class: type[PersistableModel]):
        """Vérifie la désérialisation basique."""
        now = datetime.now(UTC)
        row = {
            "id": "item-2",
            "name": "Gadget",
            "score": 8.0,
            "count": 10,
            "is_active": 1,
            "config": '{"max_retries": 5, "timeout": 60}',
            "tags": '["x", "y"]',
            "parent_id": "p-2",
            "created_at": now.isoformat(),
        }
        obj = ModelSerializer.from_row(sample_model_class, row)

        assert obj.id == "item-2"
        assert obj.name == "Gadget"
        assert obj.score == 8.0
        assert obj.count == 10
        assert obj.is_active is True
        assert obj.tags == ["x", "y"]
        assert obj.parent_id == "p-2"

    def test_from_row_none_values(self, sample_model_class: type[PersistableModel]):
        """Les NULL SQL deviennent None."""
        row = {
            "id": "item-3",
            "name": "Thing",
            "score": None,
            "count": None,
            "is_active": 1,
            "config": "{}",
            "tags": "[]",
            "parent_id": None,
            "created_at": datetime.now(UTC).isoformat(),
        }
        obj = ModelSerializer.from_row(sample_model_class, row)
        assert obj.parent_id is None

    def test_roundtrip(self, sample_model_class: type[PersistableModel]):
        """Vérifie un aller-retour complet to_row → from_row."""
        original = sample_model_class(
            id="rt-1",
            name="Roundtrip",
            score=3.14,
            count=7,
            is_active=False,
            config=EmbeddedConfig(max_retries=1, timeout=10),
            tags=["tag1", "tag2"],
            parent_id="p-99",
        )
        row = ModelSerializer.to_row(original)
        restored = ModelSerializer.from_row(sample_model_class, row)

        assert restored.id == original.id
        assert restored.name == original.name
        assert restored.score == original.score
        assert restored.count == original.count
        assert restored.is_active == original.is_active
        assert restored.tags == original.tags
        assert restored.parent_id == original.parent_id

    def test_from_row_boolean_false(self, sample_model_class: type[PersistableModel]):
        """BOOLEAN 0 → False."""
        row = {
            "id": "bool-test",
            "name": "X",
            "score": 0.0,
            "count": 0,
            "is_active": 0,
            "config": "{}",
            "tags": "[]",
            "parent_id": None,
            "created_at": datetime.now(UTC).isoformat(),
        }
        obj = ModelSerializer.from_row(sample_model_class, row)
        assert obj.is_active is False
