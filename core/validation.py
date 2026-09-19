from dese.constants import NUMBER_PROPERTY_TYPE
from dese.core.model import (
    accepts_flow_object_entry,
    get_baseline_scrap_eligible_entity_ids,
    get_baseline_scrap_parameter,
    get_failure_eligible_entity_ids,
    get_failure_parameter,
    get_input_relationships,
    get_maintenance_parameter,
    get_maintenance_resource_parameter,
    get_output_relationships,
    get_routing_condition_owner,
    get_routing_scope_candidates,
    get_routing_scope_label,
    get_routing_scope_values,
    get_routing_target_ids,
    is_main_entity,
    is_supply_source,
)

ENUM_PROPERTY_TYPE = "enum"
PRIORITY_LIST_PROPERTY_TYPE = "priority_list"


def check_property_value(value, property_schema, location):
    # Generic, schema-driven checks: every current and future property gets
    # these for free from its declared "type" (and "max", where present) —
    # no per-field code needed here when a new property is added to the
    # schema, which is the whole point (avoids the class of bug where a new
    # field is silently skipped by validation).
    #
    # An empty Entry widget commits "" (not None) as the stored value (see
    # ModelEditorPage.update_entity_property/utils.convert_property_value),
    # so both must be treated as "not filled in" here.
    if value is None or value == "":
        # A field with a declared schema default (e.g. dispatch_priority)
        # falls back to it when left unset, so leaving it empty isn't an
        # error — only fields without a default must be explicitly filled.
        if "default" in property_schema:
            return []

        return [{"severity": "error", "message": f"{location} is empty."}]

    property_type = property_schema.get("type")
    issues = []

    if property_type == NUMBER_PROPERTY_TYPE:
        if value < 0:
            issues.append(
                {
                    "severity": "error",
                    "message": f"{location} cannot be negative (got {value}).",
                }
            )

        max_value = property_schema.get("max")

        if max_value is not None and value > max_value:
            issues.append(
                {
                    "severity": "error",
                    "message": f"{location} cannot exceed {max_value} (got {value}).",
                }
            )

    elif property_type == ENUM_PROPERTY_TYPE:
        allowed_values = property_schema.get("values", [])

        if value not in allowed_values:
            issues.append(
                {
                    "severity": "error",
                    "message": f"{location} must be one of {allowed_values} (got {value!r}).",
                }
            )

    elif property_type == PRIORITY_LIST_PROPERTY_TYPE:
        allowed_values = property_schema.get("values", [])

        if not value or set(value) != set(allowed_values):
            issues.append(
                {
                    "severity": "error",
                    "message": f"{location} must rank exactly {allowed_values} (got {value!r}).",
                }
            )

    return issues


def check_has_entities(model_data, schema):
    if not model_data["entities"]:
        return [{"severity": "error", "message": "The model has no entities."}]

    return []


def check_has_flow_objects(model_data, schema):
    if not model_data["flow_objects"]:
        return [{"severity": "error", "message": "The model has no Flow Objects."}]

    return []


def check_has_relationships(model_data, schema):
    if len(model_data["entities"]) > 1 and not model_data["relationships"]:
        return [
            {
                "severity": "error",
                "message": "The model has more than one entity but no relationships connecting them.",
            }
        ]

    return []


def check_dangling_relationships(model_data, schema):
    # Also protects check_process_requirements (and any other check that
    # looks up a relationship's endpoint entity) from crashing on a
    # relationship left behind after its entity was deleted.
    issues = []
    entity_ids = {entity["id"] for entity in model_data["entities"]}

    for relationship in model_data["relationships"]:
        if relationship["source"] not in entity_ids:
            issues.append(
                {
                    "severity": "error",
                    "message": (
                        f'Relationship "{relationship["id"]}" references a non-existent '
                        f'source entity "{relationship["source"]}".'
                    ),
                }
            )

        if relationship["target"] not in entity_ids:
            issues.append(
                {
                    "severity": "error",
                    "message": (
                        f'Relationship "{relationship["id"]}" references a non-existent '
                        f'target entity "{relationship["target"]}".'
                    ),
                }
            )

    return issues


def check_relationship_counts(model_data, schema):
    # Purely schema-driven: every entity type's own input_min/input_max/
    # output_min/output_max already declares how many relationships it
    # needs — a new entity type gets this check for free.
    issues = []

    for entity in model_data["entities"]:
        entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

        if entity_schema is None:
            continue

        location = f'Entity "{entity["name"]}" ({entity["type"]})'
        input_count = len(get_input_relationships(entity["id"], model_data))
        output_count = len(get_output_relationships(entity["id"], model_data))

        # An end_of_process entity's virtual "End of Process" routing
        # target (see get_routing_target_ids) is a valid exit on its own —
        # it satisfies output_min without needing a real downstream
        # relationship. output_max still only counts real relationships,
        # since that's a physical connection limit, not a routing-target
        # count.
        effective_output_count = len(get_routing_target_ids(entity, model_data))

        if input_count < entity_schema["input_min"]:
            issues.append(
                {
                    "severity": "error",
                    "message": (
                        f"{location} has {input_count} input relationship(s), "
                        f'but needs at least {entity_schema["input_min"]}.'
                    ),
                }
            )
        elif input_count > entity_schema["input_max"]:
            issues.append(
                {
                    "severity": "error",
                    "message": (
                        f"{location} has {input_count} input relationship(s), "
                        f'but at most {entity_schema["input_max"]} is allowed.'
                    ),
                }
            )

        if effective_output_count < entity_schema["output_min"]:
            issues.append(
                {
                    "severity": "error",
                    "message": (
                        f"{location} has {output_count} output relationship(s), "
                        f'but needs at least {entity_schema["output_min"]}.'
                    ),
                }
            )
        elif output_count > entity_schema["output_max"]:
            issues.append(
                {
                    "severity": "error",
                    "message": (
                        f"{location} has {output_count} output relationship(s), "
                        f'but at most {entity_schema["output_max"]} is allowed.'
                    ),
                }
            )

    return issues


def check_has_process_boundary(model_data, schema):
    # The Model Editor UI only ever lets one entity be marked as the
    # beginning/end of the process (see update_process_boundary_state, which
    # disables the checkbutton for every other entity once one is set), but
    # the Simulation Engine must also work standalone, without going through
    # that UI -- so this uniqueness rule is enforced here too, not just relied
    # upon from the UI layer.
    if not model_data["entities"]:
        return []

    issues = []

    beginning_entity_ids = [
        entity["id"] for entity in model_data["entities"] if entity.get("beginning_of_process")
    ]
    end_entity_ids = [
        entity["id"] for entity in model_data["entities"] if entity.get("end_of_process")
    ]

    if not beginning_entity_ids:
        issues.append(
            {"severity": "error", "message": "No entity is marked as the beginning of the process."}
        )
    elif len(beginning_entity_ids) > 1:
        issues.append(
            {
                "severity": "error",
                "message": "More than one entity is marked as the beginning of the process.",
            }
        )

    if not end_entity_ids:
        issues.append(
            {"severity": "error", "message": "No entity is marked as the end of the process."}
        )
    elif len(end_entity_ids) > 1:
        issues.append(
            {
                "severity": "error",
                "message": "More than one entity is marked as the end of the process.",
            }
        )

    return issues


def check_process_boundary_continuity(model_data, schema):
    # Mirrors find_decision_points' own traversal: walk forward from the
    # beginning entity, following only main-to-main output relationships
    # (secondary entities like Process Supply/Sink attach to a main entity
    # but aren't part of the main process chain), and confirm the end
    # entity is actually reachable that way.
    beginning_entity = next(
        (entity for entity in model_data["entities"] if entity.get("beginning_of_process")),
        None,
    )
    end_entity = next(
        (entity for entity in model_data["entities"] if entity.get("end_of_process")),
        None,
    )

    if beginning_entity is None or end_entity is None:
        # Already reported by check_has_process_boundary -- no start and/or
        # end point to trace a path between.
        return []

    entities_by_id = {entity["id"]: entity for entity in model_data["entities"]}
    visited_ids = set()
    pending_ids = [beginning_entity["id"]]

    while pending_ids:
        entity_id = pending_ids.pop()

        if entity_id in visited_ids:
            continue

        visited_ids.add(entity_id)

        if entity_id == end_entity["id"]:
            return []

        for relationship in get_output_relationships(entity_id, model_data):
            target_entity = entities_by_id.get(relationship["target"])

            if target_entity is not None and is_main_entity(target_entity, model_data, schema):
                pending_ids.append(relationship["target"])

    return [
        {
            "severity": "error",
            "message": (
                f'No path exists from the beginning of the process ("{beginning_entity["name"]}") '
                f'to the end of the process ("{end_entity["name"]}") through main entities.'
            ),
        }
    ]


def check_entity_properties(model_data, schema):
    issues = []

    for entity in model_data["entities"]:
        entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

        if entity_schema is None:
            continue

        properties = entity.get("properties", {})

        for property_name, property_schema in entity_schema.get("properties", {}).items():
            value = properties.get(property_name)
            location = f'Entity "{entity["name"]}" ({entity["type"]}), property "{property_name}"'
            issues.extend(check_property_value(value, property_schema, location))

    return issues


def check_flow_object_properties(model_data, schema):
    issues = []
    flow_object_schema = schema.get_flow_object_schema()

    for flow_object in model_data["flow_objects"]:
        properties = flow_object.get("properties", {})

        for property_name, property_schema in flow_object_schema.get("properties", {}).items():
            value = properties.get(property_name)
            location = f'Flow Object "{flow_object["name"]}", property "{property_name}"'
            issues.extend(check_property_value(value, property_schema, location))

    return issues


def check_rule_properties(model_data, schema, rule_type, eligible_entity_ids, get_parameter):
    issues = []
    rule_schema = schema.get_rule_schema(model_data["domain"], rule_type)
    # A domain that doesn't declare this rule_type at all (see
    # RulesTabMixin.render_rule_property_form's own "if rule_schema else {}"
    # fallback) has nothing to check here, rather than crashing.
    fields = rule_schema["properties"] if rule_schema else {}
    entities_by_id = {entity["id"]: entity for entity in model_data["entities"]}

    for entity_id in eligible_entity_ids:
        entity = entities_by_id[entity_id]

        for field_name, field_schema in fields.items():
            value = get_parameter(model_data, entity_id, field_name)
            location = f'Entity "{entity["name"]}" {rule_type} rule, field "{field_name}"'
            issues.extend(check_property_value(value, field_schema, location))

    return issues


def check_failure_properties(model_data, schema):
    return check_rule_properties(
        model_data,
        schema,
        "Failure",
        get_failure_eligible_entity_ids(model_data, schema),
        get_failure_parameter,
    )


def check_maintenance_properties(model_data, schema):
    # Maintenance shares the same eligibility as Failure (both apply to any
    # entity whose schema declares supports_failure).
    return check_rule_properties(
        model_data,
        schema,
        "Maintenance",
        get_failure_eligible_entity_ids(model_data, schema),
        get_maintenance_parameter,
    )


def check_baseline_scrap_properties(model_data, schema):
    return check_rule_properties(
        model_data,
        schema,
        "BaselineScrap",
        get_baseline_scrap_eligible_entity_ids(model_data, schema),
        get_baseline_scrap_parameter,
    )


def check_maintenance_resource_properties(model_data, schema):
    if not get_failure_eligible_entity_ids(model_data, schema):
        return []

    rule_schema = schema.get_rule_schema(model_data["domain"], "MaintenanceResource")
    fields = rule_schema["properties"] if rule_schema else {}
    issues = []

    for field_name, field_schema in fields.items():
        value = get_maintenance_resource_parameter(model_data, field_name)
        location = f'Maintenance Resource, field "{field_name}"'
        issues.extend(check_property_value(value, field_schema, location))

    return issues


def check_routing_completeness(model_data, schema):
    issues = []

    for entity in model_data["entities"]:
        entity_id = entity["id"]
        target_ids = get_routing_target_ids(entity, model_data)

        if len(target_ids) <= 1:
            continue

        scope_candidates = get_routing_scope_candidates(entity, model_data, schema)

        for scope, variable in scope_candidates:
            for value in get_routing_scope_values(scope, variable, schema):
                owner = get_routing_condition_owner(model_data, entity_id, scope, variable, value)

                if owner is None:
                    scope_label = get_routing_scope_label(scope, variable)
                    issues.append(
                        {
                            "severity": "error",
                            "message": (
                                f'Entity "{entity["name"]}" Routing: no output assigned '
                                f'for {scope_label} = "{value}".'
                            ),
                        }
                    )

    return issues


def check_process_requirements(model_data, schema):
    issues = []
    entities_by_id = {entity["id"]: entity for entity in model_data["entities"]}
    processing_entities = [
        entity
        for entity in model_data["entities"]
        if accepts_flow_object_entry(entity, model_data, schema)
    ]

    for flow_object in model_data["flow_objects"]:
        process_requirements = flow_object.get("process_requirements", {})

        for processing_entity in processing_entities:
            supply_relationships = []

            for relationship in get_input_relationships(processing_entity["id"], model_data):
                # A dangling relationship (source entity deleted without
                # cleaning up the relationship) is already reported by
                # check_dangling_relationships -- skip it here rather than
                # crashing on the missing lookup.
                supply_entity = entities_by_id.get(relationship["source"])

                if supply_entity is not None and is_supply_source(
                    supply_entity, model_data, schema
                ):
                    supply_relationships.append(relationship)

            for relationship in supply_relationships:
                supply_entity = entities_by_id[relationship["source"]]
                value = process_requirements.get(processing_entity["id"], {}).get(
                    supply_entity["id"]
                )
                location = (
                    f'Flow Object "{flow_object["name"]}" process requirement at '
                    f'"{processing_entity["name"]}" from "{supply_entity["name"]}"'
                )

                if value is None:
                    issues.append({"severity": "error", "message": f"{location} is empty."})
                elif value <= 0:
                    issues.append(
                        {
                            "severity": "error",
                            "message": f"{location} must be greater than 0 (got {value}).",
                        }
                    )

    return issues


CHECKS = [
    check_has_entities,
    check_has_flow_objects,
    check_has_relationships,
    check_dangling_relationships,
    check_relationship_counts,
    check_has_process_boundary,
    check_process_boundary_continuity,
    check_entity_properties,
    check_flow_object_properties,
    check_failure_properties,
    check_maintenance_properties,
    check_baseline_scrap_properties,
    check_maintenance_resource_properties,
    check_routing_completeness,
    check_process_requirements,
]


def validate_model(model_data, schema):
    # Each check is self-contained and independently registered above, so
    # adding a new rule type or property later only means adding one more
    # function to CHECKS — nothing else here needs to change, which avoids
    # the class of bug where a new field is silently missed by validation.
    issues = []

    for check in CHECKS:
        issues.extend(check(model_data, schema))

    return issues
