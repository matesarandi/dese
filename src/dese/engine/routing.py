"""Evaluates a decision point's Routing rule at runtime: for each candidate
scope (an Entity's own state first, then any Flow Object states it's
eligible to read -- see `core.model.get_routing_scope_candidates`), checks
whether the CURRENT value has an assigned output, and returns the first
match. A scope with no condition for the current value simply falls
through to the next one -- only the LAST candidate scope needs full value
coverage (enforced by `core.validation.check_routing_completeness`), so
earlier scopes act as optional overrides.
"""
from dese.core.model import get_routing_scope_candidates


def get_current_scope_value(state, entity_id, instance_id, scope, variable):
    """Reads the current runtime value of one routing scope/variable --
    either ``entity_id``'s own state (``scope="entity"``) or
    ``instance_id``'s (``scope="flow_object"``)."""
    if scope == "entity":
        return getattr(state.entity_states[entity_id], variable)

    return getattr(state.flow_object_instances[instance_id], variable)


def find_routing_target(routing_outputs, scope, variable, value):
    """Returns the output target that owns the ``(scope, variable, value)``
    condition among ``routing_outputs``, or ``None`` if none does."""
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
    """Resolves which target ``instance_id`` should be routed to at the
    decision point ``entity_id``, given its CURRENT state.

    Mirrors validate_model's own check_routing_completeness (same scope
    candidates, same condition-owner lookup) -- since that check already
    guarantees every candidate/value combination has an assigned target,
    this should always find one for a model that passed validation.

    Args:
        state: The mutable SimulationState.
        entity_id: The decision-point Entity.
        instance_id: The Flow Object Instance being routed.

    Returns:
        The resolved target id (a real Entity id, or
        ``constants.END_OF_PROCESS_ROUTING_TARGET``), or ``None`` if no
        scope/value combination matched (should be unreachable for a
        validated model).
    """
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
