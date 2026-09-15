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
        output.setdefault("conditions", []).append(condition)


def get_routing_condition_owner(model_data, entity_id, scope, variable, equals):
    # Which output target currently claims this (scope, variable, equals)
    # condition at this decision point, or None if nothing does.
    rule = find_routing_rule(model_data, entity_id)

    if rule is None:
        return None

    for output in rule["outputs"]:
        for condition in output.get("conditions", []):
            if (condition["scope"], condition["variable"], condition["equals"]) == (
                scope,
                variable,
                equals,
            ):
                return output["target"]

    return None


def set_routing_condition_owner(model_data, entity_id, scope, variable, equals, target_id):
    # Assigns this (scope, variable, equals) condition to target_id's
    # output, removing it from wherever it was before. target_id=None just
    # unassigns it. A no-op if it's already exactly where it should be.
    current_owner = get_routing_condition_owner(model_data, entity_id, scope, variable, equals)

    if current_owner == target_id:
        return

    if current_owner is not None:
        rule = find_routing_rule(model_data, entity_id)
        output = next(
            output for output in rule["outputs"] if output["target"] == current_owner
        )
        output["conditions"] = [
            condition
            for condition in output["conditions"]
            if (condition["scope"], condition["variable"], condition["equals"])
            != (scope, variable, equals)
        ]

        if not output["conditions"]:
            rule["outputs"].remove(output)

        if not rule["outputs"]:
            model_data["rules"].remove(rule)

    if target_id is not None:
        add_routing_condition(model_data, entity_id, target_id, scope, variable, equals)


def move_routing_rule_output(model_data, old_entity_id, old_target_id, new_entity_id, new_target_id):
    # Retargeting a relationship (either end) must not strand the Routing
    # conditions configured for it — move the output (and its conditions)
    # from (old_entity_id -> old_target_id) to (new_entity_id ->
    # new_target_id) instead. A no-op if there's nothing configured there,
    # or if the destination already has its own output (never clobber
    # existing configuration).
    old_rule = find_routing_rule(model_data, old_entity_id)

    if old_rule is None:
        return

    old_output = next(
        (output for output in old_rule["outputs"] if output["target"] == old_target_id),
        None,
    )

    if old_output is None:
        return

    # Same entity on both ends (an output-side retarget) means old_rule and
    # new_rule are the same object — look it up once to avoid operating on
    # a stale copy after it's removed from model_data["rules"] below.
    new_rule = old_rule if new_entity_id == old_entity_id else find_routing_rule(
        model_data, new_entity_id
    )

    if new_rule is not None and any(
        output["target"] == new_target_id for output in new_rule["outputs"]
    ):
        return

    old_rule["outputs"].remove(old_output)
    old_output["target"] = new_target_id

    if new_rule is None:
        new_rule = {"type": "Routing", "at": new_entity_id, "outputs": []}
        model_data["rules"].append(new_rule)

    new_rule["outputs"].append(old_output)

    if not old_rule["outputs"] and old_rule is not new_rule:
        model_data["rules"].remove(old_rule)


def remove_entity_from_rules(model_data, entity_id):
    # Deleting an Entity shouldn't leave Rule data referencing an ID that no
    # longer exists — an orphaned Routing rule could otherwise resurface
    # later (e.g. if a decision point regains a second output) with
    # conditions the user never meant to keep.
    remaining_rules = []

    for rule in model_data["rules"]:
        if rule.get("at") == entity_id:
            continue

        if rule.get("type") == "Routing":
            rule["outputs"] = [
                output for output in rule["outputs"] if output["target"] != entity_id
            ]

            if not rule["outputs"]:
                continue

        remaining_rules.append(rule)

    model_data["rules"] = remaining_rules


def get_routing_scope_candidates(entity, model_data, schema):
    # An Entity's own state is always a candidate — every Entity can
    # observe itself, no matter its type; a new state added to
    # base_entity_schema (now or in the future) becomes selectable
    # automatically, with no code change here. A Flow Object's state is
    # only a candidate where the Entity type actually has a way to read
    # it (declared via rule_eligibility.reads_flow_object_states) — e.g.
    # only Inspection can see Flow Object Quality, since that's the one
    # that actually inspects it.
    candidates = [
        ("entity", variable) for variable in schema.get_base_entity_schema()["states"]
    ]

    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])
    readable_flow_object_states = (
        entity_schema.get("rule_eligibility", {}).get("reads_flow_object_states", [])
        if entity_schema is not None
        else []
    )

    for variable in schema.get_flow_object_schema()["states"]:
        if variable in readable_flow_object_states:
            candidates.append(("flow_object", variable))

    return candidates


def get_routing_scope_label(scope, variable):
    prefix = "Entity" if scope == "entity" else "Flow Object"

    return f"{prefix} {variable.replace('_', ' ').title()}"


def get_routing_scope_values(scope, variable, schema):
    if scope == "entity":
        return schema.get_base_entity_schema()["states"][variable]["values"]

    return schema.get_flow_object_schema()["states"][variable]["values"]


def supports_failure(entity, model_data, schema):
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return entity_schema.get("rule_eligibility", {}).get("supports_failure", False)


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
