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


def get_routing_conditions(model_data, entity_id, target_id):
    # A list, OR-combined: an output is taken if ANY of its conditions match.
    rule = find_routing_rule(model_data, entity_id)

    if rule is None:
        return []

    output = next(
        (output for output in rule["outputs"] if output["target"] == target_id),
        None,
    )

    if output is None:
        return []

    return output.get("conditions", [])


def add_routing_condition(model_data, entity_id, target_id, scope, variable, equals):
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
        rule["outputs"].append({"target": target_id, "conditions": [condition]})
    else:
        # An output can't be "otherwise" and condition-based at once.
        output.pop("otherwise", None)
        output.setdefault("conditions", []).append(condition)


def set_routing_condition(model_data, entity_id, target_id, index, scope, variable, equals):
    rule = find_routing_rule(model_data, entity_id)

    if rule is None:
        return

    output = next(
        (output for output in rule["outputs"] if output["target"] == target_id),
        None,
    )

    if output is None or index >= len(output.get("conditions", [])):
        return

    output["conditions"][index] = {"scope": scope, "variable": variable, "equals": equals}


def remove_routing_condition(model_data, entity_id, target_id, index):
    rule = find_routing_rule(model_data, entity_id)

    if rule is None:
        return

    output = next(
        (output for output in rule["outputs"] if output["target"] == target_id),
        None,
    )

    if output is None:
        return

    conditions = output.get("conditions", [])

    if index < len(conditions):
        del conditions[index]

    # Drop the output once it has no conditions left, and the rule entirely
    # once none of its outputs have any, instead of leaving empty, orphaned
    # entries in model_data["rules"]. Not if it's "otherwise", though — that
    # legitimately has no conditions.
    if not conditions and not output.get("otherwise"):
        rule["outputs"].remove(output)

    if not rule["outputs"]:
        model_data["rules"].remove(rule)


def clear_routing_conditions(model_data, entity_id, target_id):
    rule = find_routing_rule(model_data, entity_id)

    if rule is None:
        return

    rule["outputs"] = [
        output for output in rule["outputs"] if output["target"] != target_id
    ]

    if not rule["outputs"]:
        model_data["rules"].remove(rule)


def is_routing_output_otherwise(model_data, entity_id, target_id):
    rule = find_routing_rule(model_data, entity_id)

    if rule is None:
        return False

    output = next(
        (output for output in rule["outputs"] if output["target"] == target_id),
        None,
    )

    if output is None:
        return False

    return output.get("otherwise", False)


def set_routing_output_otherwise(model_data, entity_id, target_id):
    # Only one output per decision point may be "otherwise" — unmark any
    # other output at this same entity that currently has it.
    rule = find_routing_rule(model_data, entity_id)

    if rule is None:
        rule = {"type": "Routing", "at": entity_id, "outputs": []}
        model_data["rules"].append(rule)

    # Unmark and, if that leaves it empty, drop any other output that
    # currently has "otherwise" — instead of leaving a dangling, empty entry.
    for output in list(rule["outputs"]):
        if output["target"] != target_id:
            output.pop("otherwise", None)

            if not output.get("conditions"):
                rule["outputs"].remove(output)

    output = next(
        (output for output in rule["outputs"] if output["target"] == target_id),
        None,
    )

    if output is None:
        output = {"target": target_id}
        rule["outputs"].append(output)

    # An output can't be "otherwise" and condition-based at once.
    output.pop("conditions", None)
    output["otherwise"] = True


def clear_routing_output_otherwise(model_data, entity_id, target_id):
    rule = find_routing_rule(model_data, entity_id)

    if rule is None:
        return

    output = next(
        (output for output in rule["outputs"] if output["target"] == target_id),
        None,
    )

    if output is None:
        return

    output.pop("otherwise", None)

    if not output.get("conditions"):
        rule["outputs"].remove(output)

    if not rule["outputs"]:
        model_data["rules"].remove(rule)


def supports_failure(entity, model_data, schema):
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return entity_schema.get("supports_failure", False)


def get_failure_eligible_entity_ids(model_data, schema):
    return [
        entity["id"]
        for entity in model_data["entities"]
        if supports_failure(entity, model_data, schema)
    ]


def find_failure_rule(model_data, entity_id):
    return next(
        (
            rule
            for rule in model_data["rules"]
            if rule.get("type") == "Failure" and rule.get("at") == entity_id
        ),
        None,
    )


def get_failure_parameter(model_data, entity_id, field_name):
    rule = find_failure_rule(model_data, entity_id)

    if rule is None:
        return None

    return rule.get(field_name)


def set_failure_parameter(model_data, entity_id, field_name, value):
    rule = find_failure_rule(model_data, entity_id)

    if rule is None:
        rule = {"type": "Failure", "at": entity_id}
        model_data["rules"].append(rule)

    rule[field_name] = value


def find_maintenance_rule(model_data, entity_id):
    return next(
        (
            rule
            for rule in model_data["rules"]
            if rule.get("type") == "Maintenance" and rule.get("at") == entity_id
        ),
        None,
    )


def get_maintenance_parameter(model_data, entity_id, field_name):
    rule = find_maintenance_rule(model_data, entity_id)

    if rule is None:
        return None

    return rule.get(field_name)


def set_maintenance_parameter(model_data, entity_id, field_name, value):
    rule = find_maintenance_rule(model_data, entity_id)

    if rule is None:
        rule = {"type": "Maintenance", "at": entity_id}
        model_data["rules"].append(rule)

    rule[field_name] = value


def find_maintenance_resource_rule(model_data):
    return next(
        (rule for rule in model_data["rules"] if rule.get("type") == "MaintenanceResource"),
        None,
    )


def get_maintenance_resource_parameter(model_data, field_name):
    rule = find_maintenance_resource_rule(model_data)

    if rule is None:
        return None

    return rule.get(field_name)


def set_maintenance_resource_parameter(model_data, field_name, value):
    rule = find_maintenance_resource_rule(model_data)

    if rule is None:
        rule = {"type": "MaintenanceResource"}
        model_data["rules"].append(rule)

    rule[field_name] = value


def get_maintenance_dispatch_priority(model_data, schema):
    dispatch_priority = get_maintenance_resource_parameter(model_data, "dispatch_priority")

    if dispatch_priority is not None:
        return dispatch_priority

    rule_schema = schema.get_rule_schema(model_data["domain"], "MaintenanceResource")

    return list(rule_schema["properties"]["dispatch_priority"]["values"])


def set_maintenance_dispatch_priority(model_data, ordered_criteria):
    set_maintenance_resource_parameter(model_data, "dispatch_priority", ordered_criteria)
