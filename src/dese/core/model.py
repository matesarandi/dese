"""Schema-driven helpers over a model_data dict: loading/validating model
files, reading an entity's simulation role and rule eligibility from the
schema (never from hardcoded type names), relationship/routing-graph
queries, and the get/set accessors for every rule type's parameters. This
is the one place both the Model Editor UI and the Simulation Engine go
through to interpret model_data -- neither reads schema.json or
model_data's raw shape directly.
"""
import json

from dese.constants import (
    CURRENT_SCHEMA_VERSION,
    END_OF_PROCESS_ROUTING_TARGET,
    MAIN_HIERARCHY_ROLE,
)


# The top-level keys every model_data dict must have, and their expected
# type — checked at load time so a file that isn't a DESE model at all
# (or a real one missing/corrupting a section) fails clearly here, instead
# of loading "successfully" and then crashing later with a confusing
# KeyError deep inside the UI or the validator.
REQUIRED_MODEL_DATA_KEYS = {
    "entities": list,
    "relationships": list,
    "flow_objects": list,
    "rules": list,
}


def load_model_data(model_path, schema):
    """Loads and sanity-checks a model file from disk.

    Headless (Tkinter-independent) so a future Simulation Engine can load
    and validate a model file the same way the editor does, without
    needing to duplicate this logic or start a UI.

    Args:
        model_path: Path to the model JSON file.
        schema: The loaded SchemaLoader (used for the domain fallback below).

    Returns:
        dict: the parsed model_data.

    Raises:
        ValueError: if the file isn't a dict, has an incompatible
            ``schema_version``, or is missing/misshaped one of
            ``REQUIRED_MODEL_DATA_KEYS``.
    """
    with open(model_path, "r") as file:
        model_data = json.load(file)

    if not isinstance(model_data, dict):
        raise ValueError("This file does not contain a valid DESE model.")

    if model_data.get("schema_version") != CURRENT_SCHEMA_VERSION:
        raise ValueError(
            "This model was created with an older or incompatible "
            "schema version and cannot be opened."
        )

    for key, expected_type in REQUIRED_MODEL_DATA_KEYS.items():
        if not isinstance(model_data.get(key), expected_type):
            raise ValueError(
                f'This file does not contain a valid DESE model (missing or invalid "{key}").'
            )

    # There is no domain selector anymore — every model uses the schema's
    # default (Production) domain. Fall back to it for any model file that
    # predates this default (its "domain" is null).
    if not model_data.get("domain"):
        model_data["domain"] = schema.get_domains()[0]

    return model_data


def is_main_entity(entity, model_data, schema):
    """True if ``entity``'s schema marks it with the "main" hierarchy role
    (as opposed to a secondary entity like Process Supply/Sink)."""
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return entity_schema["hierarchy"]["role"] == MAIN_HIERARCHY_ROLE


def accepts_flow_object_entry(entity, model_data, schema):
    """True if ``entity``'s schema declares it as a Flow-Object-processing
    entity (Processing/Inspection), per ``simulation_role.accepts_flow_object_entry``."""
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return entity_schema.get("simulation_role", {}).get(
        "accepts_flow_object_entry", False
    )


def is_supply_source(entity, model_data, schema):
    """True if ``entity``'s schema declares it as a material source (Process
    Supply), per ``simulation_role.is_supply_source``."""
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return entity_schema.get("simulation_role", {}).get("is_supply_source", False)


def holds_flow_object_queue(entity, model_data, schema):
    """True if ``entity``'s schema declares it as queue-holding (Storage),
    per ``simulation_role.holds_flow_object_queue``."""
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return entity_schema.get("simulation_role", {}).get(
        "holds_flow_object_queue", False
    )


def absorbs_flow_objects(entity, model_data, schema):
    """True if ``entity``'s schema declares it as an absorbing terminus
    (Process Sink), per ``simulation_role.absorbs_flow_objects``."""
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return entity_schema.get("simulation_role", {}).get("absorbs_flow_objects", False)


def reads_flow_object_states(entity, model_data, schema):
    """True if ``entity``'s schema declares it able to read ANY Flow Object
    state (e.g. Inspection reading ``quality``), per
    ``rule_eligibility.reads_flow_object_states``."""
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return bool(entity_schema.get("rule_eligibility", {}).get("reads_flow_object_states"))


def has_quality_reading_entity(model_data, schema):
    """True if the model has at least one entity able to read Flow Object state.

    Not hardcoded to "Inspection" by name -- any entity type the schema
    declares as able to read Flow Object state (reads_flow_object_states)
    counts, so this stays correct if that capability is ever granted to
    another entity type.
    """
    return any(
        reads_flow_object_states(entity, model_data, schema) for entity in model_data["entities"]
    )


def get_processing_duration_property(entity, model_data, schema):
    """Returns the property name (e.g. ``"processing_time"``) holding how
    long ``entity`` takes per Flow Object, or ``None`` for Entities that
    don't do timed, capacity-limited processing at all (Storage, Process
    Supply/Sink)."""
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return None

    return entity_schema.get("simulation_role", {}).get("processing_duration_property")


def get_output_relationships(entity_id, model_data):
    """Returns every relationship whose source is ``entity_id``."""
    return [
        relationship
        for relationship in model_data["relationships"]
        if relationship["source"] == entity_id
    ]


def get_input_relationships(entity_id, model_data):
    """Returns every relationship whose target is ``entity_id``."""
    return [
        relationship
        for relationship in model_data["relationships"]
        if relationship["target"] == entity_id
    ]


def get_main_entity_input_relationships(entity_id, model_data, schema):
    """Returns ``entity_id``'s input relationships whose SOURCE is a main
    entity (excludes Process Supply feeds) -- what ``processing.retry_upstream``
    uses to find real upstream Flow-Object sources."""
    entities_by_id = {entity["id"]: entity for entity in model_data["entities"]}

    return [
        relationship
        for relationship in get_input_relationships(entity_id, model_data)
        if is_main_entity(entities_by_id[relationship["source"]], model_data, schema)
    ]


def get_main_entity_output_relationships(entity_id, model_data, schema):
    """Returns ``entity_id``'s output relationships whose TARGET is a main entity."""
    entities_by_id = {entity["id"]: entity for entity in model_data["entities"]}

    return [
        relationship
        for relationship in get_output_relationships(entity_id, model_data)
        if is_main_entity(entities_by_id[relationship["target"]], model_data, schema)
    ]


def has_available_relationship_slot(
    entity_id, model_data, schema, direction, relationship_id=None
):
    """True if ``entity_id`` has room for one more relationship in
    ``direction`` (``"input"``/``"output"``), per its schema's
    input_max/output_max.

    Args:
        entity_id: The entity to check.
        model_data: The full model dict.
        schema: The loaded SchemaLoader.
        direction: ``"input"`` or ``"output"``.
        relationship_id: If checking in the context of editing an existing
            relationship, its id -- excluded from the count so editing it
            doesn't count against itself.
    """
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
    """Returns every entity ``selected_entity`` could validly connect a new
    (or retargeted) relationship to, in ``direction`` -- used by the Model
    Editor's relationship comboboxes.

    Filters by relationship_allowances (source/target type compatibility),
    process-boundary rules (a beginning-of-process entity marks the single
    entry point of the main process chain, so it may not receive an input
    from another main entity; symmetrically, an end-of-process entity may
    not feed a main entity as output -- this keeps exactly one entry/exit
    point per process), no duplicate relationships between the same pair,
    and the candidate's own remaining relationship-slot capacity.

    Args:
        selected_entity: The entity the new/edited relationship attaches to.
        model_data: The full model dict.
        schema: The loaded SchemaLoader.
        direction: ``"input"`` or ``"output"``, from ``selected_entity``'s perspective.
        relationship_id: If editing an existing relationship, its id (excluded
            from the duplicate/capacity checks).

    Returns:
        list[dict]: the valid candidate entities.
    """
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
    """Returns every possible Routing destination for ``entity``: its real
    output relationships' targets, plus the virtual
    ``END_OF_PROCESS_ROUTING_TARGET`` if it's marked ``end_of_process``
    (that one doesn't lead to a real downstream Entity, just a completed
    Flow Object).
    """
    target_ids = [
        relationship["target"]
        for relationship in get_output_relationships(entity["id"], model_data)
    ]

    if entity.get("end_of_process"):
        target_ids.append(END_OF_PROCESS_ROUTING_TARGET)

    return target_ids


def find_decision_points(model_data, schema):
    """Returns the ids of every main entity that's a decision point (>1
    possible Routing destination), by traversing forward from the
    beginning-of-process entity.

    The model structure alone tells the Simulation Engine where a Routing
    Rule is required, no extra user input needed. Only main-to-main edges
    are followed onward for traversal (Process Supply/Sink attach to a
    main entity but are not part of the main process chain); the model is
    assumed to be a DAG (no rework loops).
    """
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
    """Returns the single rule bundle (Routing/Failure/Maintenance/
    BaselineScrap, whichever are set) for ``entity_id``, or ``None`` if it
    has none -- at most one bundle per Entity, keyed by ``"at"``."""
    return next(
        (rule for rule in model_data["rules"] if rule.get("at") == entity_id),
        None,
    )


def get_or_create_entity_rules(model_data, entity_id):
    """Returns ``entity_id``'s rule bundle, creating (and appending to
    ``model_data["rules"]``) an empty one first if it doesn't exist yet."""
    bundle = find_entity_rules(model_data, entity_id)

    if bundle is None:
        bundle = {"at": entity_id}
        model_data["rules"].append(bundle)

    return bundle


def is_entity_rules_bundle_empty(bundle):
    """True if ``bundle`` has nothing left in it but its ``"at"`` key.

    "at" is the only key every bundle always has — routing/failure/
    maintenance/baseline_scrap (and any future rule) are only ever set
    with actual data in them (see get_or_create_entity_rules and the
    rule-specific setters), never left behind as an empty dict. So no
    keys beyond "at" means there's genuinely nothing left in it —
    checked structurally, not by listing each rule key by name, so a
    future rule type can't be forgotten here the way baseline_scrap
    was.
    """
    return set(bundle.keys()) <= {"at"}


def get_rule_parameter(model_data, entity_id, rule_key, field_name):
    """Returns ``entity_id``'s current value for one rule field (e.g.
    ``rule_key="failure"``, ``field_name="mean_repair_time"``), or ``None``
    if unset."""
    bundle = find_entity_rules(model_data, entity_id)

    if bundle is None:
        return None

    return bundle.get(rule_key, {}).get(field_name)


def set_rule_parameter(model_data, entity_id, rule_key, field_name, value):
    """Sets ``entity_id``'s value for one rule field, creating its bundle/
    sub-dict as needed."""
    bundle = get_or_create_entity_rules(model_data, entity_id)
    bundle.setdefault(rule_key, {})[field_name] = value


def add_routing_condition(model_data, entity_id, target_id, scope, variable, equals):
    """Adds a ``(scope, variable, equals)`` Routing condition to
    ``target_id``'s output at decision point ``entity_id`` (creating the
    output entry if it doesn't exist yet)."""
    bundle = get_or_create_entity_rules(model_data, entity_id)
    outputs = bundle.setdefault("routing", {}).setdefault("outputs", [])

    output = next((output for output in outputs if output["target"] == target_id), None)
    condition = {"scope": scope, "variable": variable, "equals": equals}

    if output is None:
        outputs.append({"target": target_id, "conditions": [condition]})
    else:
        output.setdefault("conditions", []).append(condition)


def get_routing_condition_owner(model_data, entity_id, scope, variable, equals):
    """Returns which output target currently claims this
    ``(scope, variable, equals)`` condition at decision point
    ``entity_id``, or ``None`` if nothing does."""
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
    """Assigns a ``(scope, variable, equals)`` Routing condition to
    ``target_id``'s output at decision point ``entity_id``, removing it
    from wherever it was before.

    ``target_id=None`` just unassigns it. A no-op if it's already exactly
    where it should be -- the Model Editor's checkbox-matrix Routing UI
    calls this directly on every click.
    """
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
    """Moves a Routing output (and its conditions) from
    ``(old_entity_id -> old_target_id)`` to ``(new_entity_id -> new_target_id)``.

    Called when a relationship is retargeted (either end), so it doesn't
    strand the Routing conditions configured for it. A no-op if there's
    nothing configured there, or if the destination already has its own
    output (never clobbers existing configuration).
    """
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
    """Strips every reference to ``entity_id`` out of ``model_data["rules"]``
    when it's deleted -- both its own bundle (as ``"at"``) and any other
    entity's Routing output that targeted it.

    Deleting an Entity shouldn't leave Rule data referencing an ID that no
    longer exists — an orphaned Routing output could otherwise resurface
    later (e.g. if a decision point regains a second output) with
    conditions the user never meant to keep. MaintenanceResource (it has
    no "at") is never touched here — it isn't tied to any single Entity.
    """
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
    """Returns ``entity``'s candidate routing scopes, in evaluation-priority order.

    An Entity's own state is always a candidate — every Entity can
    observe itself, no matter its type; a new state added to
    base_entity_schema (now or in the future) becomes selectable
    automatically, with no code change here. A Flow Object's state is
    only a candidate where the Entity type actually has a way to read
    it (declared via rule_eligibility.reads_flow_object_states) — e.g.
    only Inspection can see Flow Object Quality, since that's the one
    that actually inspects it.

    Returns:
        list[tuple[str, str]]: ``(scope, variable)`` pairs, ``"entity"``
        scopes first, then any eligible ``"flow_object"`` scopes --
        ``engine.routing.evaluate_routing`` checks them in this exact order.
    """
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
    """Returns the human-readable label for a routing scope/variable (e.g.
    ``("entity", "status")`` -> ``"Entity Status"``), auto-generated from
    the variable name so it never drifts from a hand-written string."""
    prefix = "Entity" if scope == "entity" else "Flow Object"

    return f"{prefix} {variable.replace('_', ' ').title()}"


def get_routing_scope_values(scope, variable, schema):
    """Returns every possible value ``(scope, variable)`` can take (e.g.
    ``status``'s ``["idle", "busy", "blocked", "failed", "down"]``)."""
    if scope == "entity":
        return schema.get_base_entity_schema()["states"][variable]["values"]

    return schema.get_flow_object_schema()["states"][variable]["values"]


def supports_failure(entity, model_data, schema):
    """True if ``entity``'s schema declares it Failure/Maintenance-eligible,
    per ``rule_eligibility.supports_failure``."""
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return entity_schema.get("rule_eligibility", {}).get("supports_failure", False)


def get_failure_eligible_entity_ids(model_data, schema):
    """Returns the ids of every entity eligible for Failure/Maintenance rules."""
    return [
        entity["id"]
        for entity in model_data["entities"]
        if supports_failure(entity, model_data, schema)
    ]


def get_failure_parameter(model_data, entity_id, field_name):
    """Returns ``entity_id``'s current value for one Failure rule field."""
    return get_rule_parameter(model_data, entity_id, "failure", field_name)


def set_failure_parameter(model_data, entity_id, field_name, value):
    """Sets ``entity_id``'s value for one Failure rule field."""
    set_rule_parameter(model_data, entity_id, "failure", field_name, value)


def produces_baseline_scrap(entity, model_data, schema):
    """True if ``entity``'s schema declares it able to produce ``quality``
    on its own (BaselineScrap-eligible), per
    ``rule_eligibility.produces_flow_object_states``."""
    entity_schema = schema.get_entity_schema(model_data["domain"], entity["type"])

    if entity_schema is None:
        return False

    return "quality" in entity_schema.get("rule_eligibility", {}).get(
        "produces_flow_object_states", []
    )


def get_baseline_scrap_eligible_entity_ids(model_data, schema):
    """Returns the ids of every entity eligible for a BaselineScrap rule."""
    return [
        entity["id"]
        for entity in model_data["entities"]
        if produces_baseline_scrap(entity, model_data, schema)
    ]


def get_baseline_scrap_parameter(model_data, entity_id, field_name):
    """Returns ``entity_id``'s current value for one BaselineScrap rule field."""
    return get_rule_parameter(model_data, entity_id, "baseline_scrap", field_name)


def set_baseline_scrap_parameter(model_data, entity_id, field_name, value):
    """Sets ``entity_id``'s value for one BaselineScrap rule field."""
    set_rule_parameter(model_data, entity_id, "baseline_scrap", field_name, value)


def get_maintenance_parameter(model_data, entity_id, field_name):
    """Returns ``entity_id``'s current value for one Maintenance rule field."""
    return get_rule_parameter(model_data, entity_id, "maintenance", field_name)


def set_maintenance_parameter(model_data, entity_id, field_name, value):
    """Sets ``entity_id``'s value for one Maintenance rule field."""
    set_rule_parameter(model_data, entity_id, "maintenance", field_name, value)


def find_maintenance_resource_rule(model_data):
    """Returns the model-wide MaintenanceResource rule entry, or ``None`` if unset.

    Unlike per-entity rules, this one has no ``"at"`` -- it's keyed by
    ``"type": "MaintenanceResource"`` instead, since it isn't tied to any
    single Entity.
    """
    return next(
        (rule for rule in model_data["rules"] if rule.get("type") == "MaintenanceResource"),
        None,
    )


def get_maintenance_resource_parameter(model_data, field_name):
    """Returns the model-wide MaintenanceResource's current value for one
    field (``capacity`` or ``dispatch_priority``), or ``None`` if unset."""
    rule = find_maintenance_resource_rule(model_data)

    if rule is None:
        return None

    return rule.get(field_name)


def set_maintenance_resource_parameter(model_data, field_name, value):
    """Sets the model-wide MaintenanceResource's value for one field,
    creating the rule entry first if it doesn't exist yet."""
    rule = find_maintenance_resource_rule(model_data)

    if rule is None:
        rule = {"type": "MaintenanceResource"}
        model_data["rules"].append(rule)

    rule[field_name] = value


def get_maintenance_dispatch_priority(model_data, schema):
    """Returns the model's current dispatch_priority ranking, falling back
    to the schema's own declared default if unset."""
    dispatch_priority = get_maintenance_resource_parameter(model_data, "dispatch_priority")

    if dispatch_priority is not None:
        return dispatch_priority

    rule_schema = schema.get_rule_schema(model_data["domain"], "MaintenanceResource")

    return list(rule_schema["properties"]["dispatch_priority"]["values"])


def set_maintenance_dispatch_priority(model_data, ordered_criteria):
    """Sets the model's dispatch_priority ranking -- must be a permutation
    of all the schema's allowed criteria (e.g.
    ``["unplanned_first", "most_worn_first", "fifo"]``), enforced by
    ``validation.check_property_value``'s ``priority_list`` handling."""
    set_maintenance_resource_parameter(model_data, "dispatch_priority", ordered_criteria)
