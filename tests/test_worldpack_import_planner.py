from __future__ import annotations

from types import SimpleNamespace

from app.core.worldpack_import_planner import (
    build_preserved_attribute_warning,
    collect_ambiguous_alias_warnings,
    plan_entity_deletion,
    plan_entity_import,
    plan_relationship_import,
    plan_system_import,
)
from app.schemas import (
    WorldpackV1Entity,
    WorldpackV1Relationship,
    WorldpackV1System,
)


def test_collect_ambiguous_alias_warnings_reports_shared_aliases():
    warnings = collect_ambiguous_alias_warnings(
        [
            WorldpackV1Entity(key="e1", name="云澈", entity_type="Character", aliases=["小澈"]),
            WorldpackV1Entity(key="e2", name="楚月仙", entity_type="Character", aliases=["小澈"]),
        ]
    )

    assert [warning.code for warning in warnings] == ["ambiguous_alias"]
    assert warnings[0].path == "entities[*].aliases"


def test_plan_entity_import_links_existing_row_by_name():
    incoming = WorldpackV1Entity(key="e1", name="云澈", entity_type="Character")
    linked = SimpleNamespace(worldpack_pack_id=None, worldpack_key=None)

    decision = plan_entity_import(None, linked, incoming, pack_id="pack-1", path="entities[0].name")

    assert decision.action == "link_existing"
    assert decision.payload == {"worldpack_pack_id": "pack-1", "worldpack_key": "e1"}
    assert decision.warnings[0].code == "entity_linked_by_name"


def test_plan_entity_import_marks_preserved_manual_row_when_payload_would_change():
    incoming = WorldpackV1Entity(key="e1", name="云澈", entity_type="Character", description="pack desc")
    existing = SimpleNamespace(
        name="云澈",
        entity_type="Character",
        description="manual desc",
        aliases=[],
        origin="manual",
        status="confirmed",
        worldpack_pack_id="pack-1",
        worldpack_key="e1",
    )

    decision = plan_entity_import(existing, None, incoming, pack_id="pack-1", path="entities[0].name")

    assert decision.action == "preserve"
    assert decision.preserved_item == "e1"


def test_plan_entity_import_keeps_existing_row_when_name_missing():
    incoming = WorldpackV1Entity(key="e1", name="", entity_type="Character")

    decision = plan_entity_import(SimpleNamespace(), None, incoming, pack_id="pack-1", path="entities[0].name")

    assert decision.action == "keep_existing"
    assert decision.track_desired_item is True
    assert decision.warnings[0].code == "missing_name_preserve_existing"


def test_plan_relationship_import_preserves_promoted_relationship_signature():
    incoming = WorldpackV1Relationship(source_key="e1", target_key="e2", label="同伴", description="pack")
    existing = SimpleNamespace(
        label="同伴",
        description="manual",
        visibility="reference",
        origin="manual",
        status="confirmed",
        worldpack_pack_id="pack-1",
    )

    decision = plan_relationship_import(
        existing,
        incoming,
        pack_id="pack-1",
        source_id=1,
        target_id=2,
    )

    assert decision.action == "preserve"
    assert decision.preserved_item == "e1 --同伴--> e2"
    assert decision.payload["signature"] == (1, 2, "同伴")


def test_plan_system_import_rejects_different_pack_name_conflict():
    incoming = WorldpackV1System(name="修炼体系", display_type="list", data={})
    existing = SimpleNamespace(
        name="修炼体系",
        display_type="list",
        description="",
        data={},
        constraints=[],
        visibility="reference",
        origin="worldpack",
        status="confirmed",
        worldpack_pack_id="pack-2",
    )

    decision = plan_system_import(existing, incoming, pack_id="pack-1", path="systems[0].name")

    assert decision.action == "skip"
    assert decision.warnings[0].code == "system_name_conflict"


def test_plan_entity_deletion_keeps_rows_with_promoted_dependencies():
    decision = plan_entity_deletion(
        "e1",
        has_non_pack_attribute_dependency=True,
        has_non_pack_relationship_dependency=False,
    )

    assert decision.action == "keep"
    assert decision.warnings[0].code == "skip_delete_promoted_entity"


def test_build_preserved_attribute_warning_summarizes_sample_entities():
    warning = build_preserved_attribute_warning(
        {
            "e1": {"修为", "身份"},
            "e2": {"阵营"},
            "e3": {"别名"},
            "e4": {"武器"},
        }
    )

    assert warning is not None
    assert warning.code == "preserved_attributes_skipped"
    assert "(+1 more entities)" in warning.message
