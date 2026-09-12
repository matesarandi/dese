from dese.constants import MAIN_HIERARCHY_ROLE


def is_main_entity(entity, model_data, schema):
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return entity_schema["hierarchy"]["role"] == MAIN_HIERARCHY_ROLE


def get_output_relationships(entity_id, model_data):
    return [
        relationship
        for relationship in model_data["relationships"]
        if relationship["source"] == entity_id
    ]


def find_decision_points(model_data, schema):
    # A decision point is a main entity with more than one actual output
    # relationship — the model structure alone tells the Simulation Engine
    # where a Routing Rule is required, no extra user input needed. Only
    # main-to-main edges are followed onward (Process Supply/Sink attach to a
    # main entity but are not part of the main process chain); the model is
    # assumed to be a DAG (no rework loops) — see project_product_vision
    # memory for that decision.
    entities_by_id = {entity["id"]: entity for entity in model_data["entities"]}

    beginning_entity = next(
        (
            entity
            for entity in model_data["entities"]
            if entity.get("beginning_of_process")
        ),
        None,
    )

    if beginning_entity is None:
        return []

    decision_points = []
    visited_ids = set()

    def traverse(entity_id):
        if entity_id in visited_ids:
            return

        visited_ids.add(entity_id)

        entity = entities_by_id[entity_id]
        output_relationships = get_output_relationships(entity_id, model_data)

        if is_main_entity(entity, model_data, schema) and len(output_relationships) > 1:
            decision_points.append(entity_id)

        for relationship in output_relationships:
            target_entity = entities_by_id.get(relationship["target"])

            if target_entity is not None and is_main_entity(
                target_entity, model_data, schema
            ):
                traverse(relationship["target"])

    traverse(beginning_entity["id"])

    return decision_points


def find_routing_rule(model_data, entity_id):
    return next(
        (
            rule
            for rule in model_data["rules"]
            if rule.get("type") == "Routing" and rule.get("at") == entity_id
        ),
        None,
    )


def get_routing_condition(model_data, entity_id, target_id):
    rule = find_routing_rule(model_data, entity_id)

    if rule is None:
        return None

    output = next(
        (output for output in rule["outputs"] if output["target"] == target_id),
        None,
    )

    if output is None:
        return None

    return output.get("condition")


def set_routing_condition(model_data, entity_id, target_id, scope, variable, equals):
    rule = find_routing_rule(model_data, entity_id)

    if rule is None:
        rule = {"type": "Routing", "at": entity_id, "outputs": []}
        model_data["rules"].append(rule)

    output = next(
        (output for output in rule["outputs"] if output["target"] == target_id),
        None,
    )

    condition = {"scope": scope, "variable": variable, "equals": equals}

    if output is None:
        rule["outputs"].append({"target": target_id, "condition": condition})
    else:
        output["condition"] = condition


def clear_routing_condition(model_data, entity_id, target_id):
    rule = find_routing_rule(model_data, entity_id)

    if rule is None:
        return

    rule["outputs"] = [
        output for output in rule["outputs"] if output["target"] != target_id
    ]

    # Drop the rule entirely once none of its outputs have a condition left,
    # instead of leaving an empty, orphaned rule in model_data["rules"].
    if not rule["outputs"]:
        model_data["rules"].remove(rule)
