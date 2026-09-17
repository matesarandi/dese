from dese.constants import END_OF_PROCESS_ROUTING_TARGET, MAIN_HIERARCHY_ROLE


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


def get_input_relationships(entity_id, model_data):
    return [
        relationship
        for relationship in model_data["relationships"]
        if relationship["target"] == entity_id
    ]


def get_main_entity_input_relationships(entity_id, model_data, schema):
    entities_by_id = {entity["id"]: entity for entity in model_data["entities"]}

    return [
        relationship
        for relationship in get_input_relationships(entity_id, model_data)
        if is_main_entity(entities_by_id[relationship["source"]], model_data, schema)
    ]


def get_main_entity_output_relationships(entity_id, model_data, schema):
    entities_by_id = {entity["id"]: entity for entity in model_data["entities"]}

    return [
        relationship
        for relationship in get_output_relationships(entity_id, model_data)
        if is_main_entity(entities_by_id[relationship["target"]], model_data, schema)
    ]


def has_available_relationship_slot(
    entity_id, model_data, schema, direction, relationship_id=None
):
    entity = next(
        entity for entity in model_data["entities"] if entity["id"] == entity_id
    )

    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    relationship_field = "source" if direction == "output" else "target"

    existing_relationships = [
        relationship
        for relationship in model_data["relationships"]
        if (
            relationship[relationship_field] == entity_id
            and relationship["id"] != relationship_id
        )
    ]

    return len(existing_relationships) < entity_schema[f"{direction}_max"]


def get_allowed_entities(
    selected_entity, model_data, schema, direction, relationship_id=None
):
    # A beginning-of-process entity marks the single entry point of the main
    # process chain, so it may not receive an input from another main entity;
    # symmetrically, an end-of-process entity may not feed a main entity as
    # output. This keeps exactly one entry/exit point per process.
    selected_type = selected_entity["type"]
    selected_entity_id = selected_entity["id"]

    domain = schema.get_domain(model_data["domain"])
    relationship_allowances = domain["relationship_allowances"]

    if direction == "input":
        allowed_types = [
            source_type
            for source_type, target_types in relationship_allowances.items()
            if selected_type in target_types
        ]
        selected_boundary_flag = "beginning_of_process"
        candidate_boundary_flag = "end_of_process"
        opposite_direction = "output"
    else:
        allowed_types = relationship_allowances.get(selected_type, [])
        selected_boundary_flag = "end_of_process"
        candidate_boundary_flag = "beginning_of_process"
        opposite_direction = "input"

    return [
        entity
        for entity in model_data["entities"]
        if (
            entity["type"] in allowed_types
            and entity["id"] != selected_entity_id
            and not (
                selected_entity.get(selected_boundary_flag)
                and is_main_entity(entity, model_data, schema)
            )
            and not (
                is_main_entity(selected_entity, model_data, schema)
                and entity.get(candidate_boundary_flag)
            )
            and not any(
                (
                    (
                        relationship["source"] == entity["id"]
                        and relationship["target"] == selected_entity_id
                    )
                    or (
                        relationship["source"] == selected_entity_id
                        and relationship["target"] == entity["id"]
                    )
                )
                and relationship["id"] != relationship_id
                for relationship in model_data["relationships"]
            )
            and has_available_relationship_slot(
                entity["id"], model_data, schema, opposite_direction, relationship_id
            )
        )
    ]


def get_routing_target_ids(entity, model_data):
    # The set of possible Routing destinations for this Entity: every real
    # output relationship, plus the virtual END_OF_PROCESS_ROUTING_TARGET
    # destination if the Entity is marked end_of_process — it doesn't lead
    # to a real downstream Entity, just a completed Flow Object.
    target_ids = [
        relationship["target"]
        for relationship in get_output_relationships(entity["id"], model_data)
    ]

    if entity.get("end_of_process"):
        target_ids.append(END_OF_PROCESS_ROUTING_TARGET)

    return target_ids


def find_decision_points(model_data, schema):
    # A decision point is a main entity with more than one possible
    # Routing destination — real output relationships, plus the virtual
    # "End of Process" destination end_of_process adds (see
    # get_routing_target_ids) — the model structure alone tells the
    # Simulation Engine where a Routing Rule is required, no extra user
    # input needed. Only main-to-main edges are followed onward for
    # traversal (Process Supply/Sink attach to a main entity but are not
    # part of the main process chain); the model is assumed to be a DAG
    # (no rework loops) — see project_product_vision memory for that
    # decision.
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

        if is_main_entity(entity, model_data, schema) and len(
            get_routing_target_ids(entity, model_data)
        ) > 1:
            decision_points.append(entity_id)

        for relationship in output_relationships:
            target_entity = entities_by_id.get(relationship["target"])

            if target_entity is not None and is_main_entity(
                target_entity, model_data, schema
            ):
                traverse(relationship["target"])

    traverse(beginning_entity["id"])

    return decision_points


def find_entity_rules(model_data, entity_id):
    # The single bundle holding everything Routing/Failure/Maintenance-
    # related for one Entity — at most one per Entity, keyed by "at".
    return next(
        (rule for rule in model_data["rules"] if rule.get("at") == entity_id),
        None,
    )


def get_or_create_entity_rules(model_data, entity_id):
    bundle = find_entity_rules(model_data, entity_id)

    if bundle is None:
        bundle = {"at": entity_id}
        model_data["rules"].append(bundle)

    return bundle


def is_entity_rules_bundle_empty(bundle):
    # "at" is the only key every bundle always has — routing/failure/
    # maintenance/baseline_scrap (and any future rule) are only ever set
    # with actual data in them (see get_or_create_entity_rules and the
    # rule-specific setters), never left behind as an empty dict. So no
    # keys beyond "at" means there's genuinely nothing left in it —
    # checked structurally, not by listing each rule key by name, so a
    # future rule type can't be forgotten here the way baseline_scrap
    # was.
    return set(bundle.keys()) <= {"at"}


def get_rule_parameter(model_data, entity_id, rule_key, field_name):
    bundle = find_entity_rules(model_data, entity_id)

    if bundle is None:
        return None

    return bundle.get(rule_key, {}).get(field_name)


def set_rule_parameter(model_data, entity_id, rule_key, field_name, value):
    bundle = get_or_create_entity_rules(model_data, entity_id)
    bundle.setdefault(rule_key, {})[field_name] = value


def add_routing_condition(model_data, entity_id, target_id, scope, variable, equals):
    bundle = get_or_create_entity_rules(model_data, entity_id)
    outputs = bundle.setdefault("routing", {}).setdefault("outputs", [])

    output = next((output for output in outputs if output["target"] == target_id), None)
    condition = {"scope": scope, "variable": variable, "equals": equals}

    if output is None:
        outputs.append({"target": target_id, "conditions": [condition]})
    else:
        output.setdefault("conditions", []).append(condition)


def get_routing_condition_owner(model_data, entity_id, scope, variable, equals):
    # Which output target currently claims this (scope, variable, equals)
    # condition at this decision point, or None if nothing does.
    bundle = find_entity_rules(model_data, entity_id)

    if bundle is None:
        return None

    for output in bundle.get("routing", {}).get("outputs", []):
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
        bundle = find_entity_rules(model_data, entity_id)
        outputs = bundle["routing"]["outputs"]
        output = next(output for output in outputs if output["target"] == current_owner)
        output["conditions"] = [
            condition
            for condition in output["conditions"]
            if (condition["scope"], condition["variable"], condition["equals"])
            != (scope, variable, equals)
        ]

        if not output["conditions"]:
            outputs.remove(output)

        if not outputs:
            bundle.pop("routing", None)

        if is_entity_rules_bundle_empty(bundle):
            model_data["rules"].remove(bundle)

    if target_id is not None:
        add_routing_condition(model_data, entity_id, target_id, scope, variable, equals)


def move_routing_rule_output(model_data, old_entity_id, old_target_id, new_entity_id, new_target_id):
    # Retargeting a relationship (either end) must not strand the Routing
    # conditions configured for it — move the output (and its conditions)
    # from (old_entity_id -> old_target_id) to (new_entity_id ->
    # new_target_id) instead. A no-op if there's nothing configured there,
    # or if the destination already has its own output (never clobber
    # existing configuration).
    old_bundle = find_entity_rules(model_data, old_entity_id)

    if old_bundle is None:
        return

    old_outputs = old_bundle.get("routing", {}).get("outputs", [])
    old_output = next(
        (output for output in old_outputs if output["target"] == old_target_id), None
    )

    if old_output is None:
        return

    # Same entity on both ends (an output-side retarget) means old_bundle
    # and new_bundle are the same object — look it up once to avoid
    # operating on a stale copy after mutation below.
    new_bundle = (
        old_bundle
        if new_entity_id == old_entity_id
        else find_entity_rules(model_data, new_entity_id)
    )
    new_outputs = (
        new_bundle.get("routing", {}).get("outputs", []) if new_bundle is not None else []
    )

    if any(output["target"] == new_target_id for output in new_outputs):
        return

    old_outputs.remove(old_output)
    old_output["target"] = new_target_id

    if not old_outputs:
        old_bundle.pop("routing", None)

    if new_bundle is None:
        new_bundle = get_or_create_entity_rules(model_data, new_entity_id)

    new_bundle.setdefault("routing", {}).setdefault("outputs", []).append(old_output)

    if old_bundle is not new_bundle and is_entity_rules_bundle_empty(old_bundle):
        model_data["rules"].remove(old_bundle)


def remove_entity_from_rules(model_data, entity_id):
    # Deleting an Entity shouldn't leave Rule data referencing an ID that no
    # longer exists — an orphaned Routing output could otherwise resurface
    # later (e.g. if a decision point regains a second output) with
    # conditions the user never meant to keep. MaintenanceResource (it has
    # no "at") is never touched here — it isn't tied to any single Entity.
    remaining_rules = []

    for rule_entry in model_data["rules"]:
        if rule_entry.get("at") == entity_id:
            continue

        if "at" in rule_entry:
            routing = rule_entry.get("routing")

            if routing is not None:
                routing["outputs"] = [
                    output for output in routing["outputs"] if output["target"] != entity_id
                ]

                if not routing["outputs"]:
                    rule_entry.pop("routing", None)

            if is_entity_rules_bundle_empty(rule_entry):
                continue

        remaining_rules.append(rule_entry)

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


def get_failure_parameter(model_data, entity_id, field_name):
    return get_rule_parameter(model_data, entity_id, "failure", field_name)


def set_failure_parameter(model_data, entity_id, field_name, value):
    set_rule_parameter(model_data, entity_id, "failure", field_name, value)


def produces_baseline_scrap(entity, model_data, schema):
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return "quality" in entity_schema.get("rule_eligibility", {}).get(
        "produces_flow_object_states", []
    )


def get_baseline_scrap_eligible_entity_ids(model_data, schema):
    return [
        entity["id"]
        for entity in model_data["entities"]
        if produces_baseline_scrap(entity, model_data, schema)
    ]


def get_baseline_scrap_parameter(model_data, entity_id, field_name):
    return get_rule_parameter(model_data, entity_id, "baseline_scrap", field_name)


def set_baseline_scrap_parameter(model_data, entity_id, field_name, value):
    set_rule_parameter(model_data, entity_id, "baseline_scrap", field_name, value)


def get_maintenance_parameter(model_data, entity_id, field_name):
    return get_rule_parameter(model_data, entity_id, "maintenance", field_name)


def set_maintenance_parameter(model_data, entity_id, field_name, value):
    set_rule_parameter(model_data, entity_id, "maintenance", field_name, value)


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
