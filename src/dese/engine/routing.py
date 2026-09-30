from dese.core.model import get_routing_scope_candidates


def get_current_scope_value(state, entity_id, instance_id, scope, variable):
    if scope == "entity":
        return getattr(state.entity_states[entity_id], variable)

    return getattr(state.flow_object_instances[instance_id], variable)


def find_routing_target(routing_outputs, scope, variable, value):
    for output in routing_outputs:
        for condition in output.get("conditions", []):
            if (condition["scope"], condition["variable"], condition["equals"]) == (
                scope,
                variable,
                value,
            ):
                return output["target"]

    return None


def evaluate_routing(state, entity_id, instance_id):
    # Mirrors validate_model's own check_routing_completeness (same scope
    # candidates, same condition-owner lookup) -- since that check already
    # guarantees every candidate/value combination has an assigned target,
    # this should always find one for a model that passed validation.
    entity = state.simulation_model.entities_by_id[entity_id]
    domain_only_model_data = {"domain": state.simulation_model.domain}
    scope_candidates = get_routing_scope_candidates(
        entity, domain_only_model_data, state.simulation_model.schema
    )

    rule_bundle = state.simulation_model.rules_by_entity_id.get(entity_id, {})
    routing_outputs = rule_bundle.get("routing", {}).get("outputs", [])

    for scope, variable in scope_candidates:
        value = get_current_scope_value(state, entity_id, instance_id, scope, variable)
        target = find_routing_target(routing_outputs, scope, variable, value)

        if target is not None:
            return target

    return None
