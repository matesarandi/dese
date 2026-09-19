from dataclasses import dataclass

from dese.core.model import (
    find_decision_points,
    find_entity_rules,
    find_maintenance_resource_rule,
    get_input_relationships,
    get_output_relationships,
)
from dese.core.validation import validate_model


class ModelValidationError(Exception):
    # Raised instead of building a SimulationModel from an incomplete/invalid
    # model_data -- carries the same issue list validate_model would show in
    # the Model Editor, so a caller that bypasses the UI entirely (a script,
    # a future headless API) still gets the exact same, single source of
    # truth for "what's wrong", not a second, drifted-apart error path.
    def __init__(self, issues):
        self.issues = issues
        super().__init__(
            f"Cannot build a Simulation Model: the model has {len(issues)} validation issue(s)."
        )


@dataclass
class SimulationModel:
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
    issues = validate_model(model_data, schema)

    if issues:
        raise ModelValidationError(issues)

    entities_by_id = {entity["id"]: entity for entity in model_data["entities"]}

    input_relationships_by_id = {
        entity_id: get_input_relationships(entity_id, model_data)
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
