"""SimulationModel: the read-only, resolved view of a validated model_data
dict that the rest of the engine actually runs against -- entities keyed by
id, relationships split into input/output and further into "main" (Flow-
Object-carrying) vs. Process Supply feeds, decision points, and rules, all
pre-computed once per run by `build_simulation_model` instead of being
re-derived from model_data on every event.
"""
from dataclasses import dataclass

from dese.core.model import (
    find_decision_points,
    find_entity_rules,
    find_maintenance_resource_rule,
    get_main_entity_input_relationships,
    get_output_relationships,
)
from dese.core.validation import validate_model


class ModelValidationError(Exception):
    """Raised by `build_simulation_model` instead of building a SimulationModel
    from an incomplete/invalid model_data.

    Carries the same issue list ``validate_model`` would show in the Model
    Editor, so a caller that bypasses the UI entirely (a script, a future
    headless API) still gets the exact same, single source of truth for
    "what's wrong", not a second, drifted-apart error path.
    """

    def __init__(self, issues):
        self.issues = issues
        super().__init__(
            f"Cannot build a Simulation Model: the model has {len(issues)} validation issue(s)."
        )


@dataclass
class SimulationModel:
    """The resolved, run-ready view of a model -- everything
    `build_simulation_model` precomputes once so the event loop never has
    to re-derive it per event."""

    domain: str
    schema: object
    entities_by_id: dict
    input_relationships_by_id: dict
    output_relationships_by_id: dict
    beginning_entity_id: str
    end_entity_id: str
    decision_point_ids: list
    rules_by_entity_id: dict
    maintenance_resource_rule: dict
    flow_object_types: list


def build_simulation_model(model_data, schema):
    """Validates ``model_data`` and builds the SimulationModel the engine runs against.

    Args:
        model_data: The full model dict (entities, relationships, flow
            objects, rules) as produced by the Model Editor.
        schema: The loaded SchemaLoader.

    Returns:
        SimulationModel: the resolved, run-ready view.

    Raises:
        ModelValidationError: if ``model_data`` fails ``validate_model``.
    """
    issues = validate_model(model_data, schema)

    if issues:
        raise ModelValidationError(issues)

    entities_by_id = {entity["id"]: entity for entity in model_data["entities"]}

    # Main-entity-only (excludes Process Supply feeds) -- this is what
    # processing.retry_upstream uses to find every real upstream Entity
    # whose finished-but-blocked items might want to move into a slot that
    # just freed up. A Process Supply relationship carries material, not
    # Flow Objects, so it must not count as an "upstream" here -- retry_upstream
    # now correctly handles any number of main upstream sources (a genuine
    # merge topology, e.g. two branches feeding one downstream Processing
    # entity, is schema-valid since Processing's input_max is 7), picking
    # the oldest-created candidate across all of them; only Process Supply
    # feeds are excluded from this count, not real multi-input merges.
    input_relationships_by_id = {
        entity_id: get_main_entity_input_relationships(entity_id, model_data, schema)
        for entity_id in entities_by_id
    }
    output_relationships_by_id = {
        entity_id: get_output_relationships(entity_id, model_data)
        for entity_id in entities_by_id
    }

    beginning_entity_id = next(
        entity["id"]
        for entity in model_data["entities"]
        if entity.get("beginning_of_process")
    )
    end_entity_id = next(
        entity["id"] for entity in model_data["entities"] if entity.get("end_of_process")
    )

    rules_by_entity_id = {}
    for entity_id in entities_by_id:
        rule_bundle = find_entity_rules(model_data, entity_id)

        if rule_bundle is not None:
            rules_by_entity_id[entity_id] = rule_bundle

    return SimulationModel(
        domain=model_data["domain"],
        schema=schema,
        entities_by_id=entities_by_id,
        input_relationships_by_id=input_relationships_by_id,
        output_relationships_by_id=output_relationships_by_id,
        beginning_entity_id=beginning_entity_id,
        end_entity_id=end_entity_id,
        decision_point_ids=find_decision_points(model_data, schema),
        rules_by_entity_id=rules_by_entity_id,
        maintenance_resource_rule=find_maintenance_resource_rule(model_data),
        flow_object_types=model_data["flow_objects"],
    )
