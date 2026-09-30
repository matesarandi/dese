from dese.engine.event_loop import EVENT_HANDLERS, schedule_event


def get_process_requirements(state, entity_id, flow_object_type_name):
    flow_object_type = next(
        flow_object_type
        for flow_object_type in state.simulation_model.flow_object_types
        if flow_object_type["name"] == flow_object_type_name
    )
    return flow_object_type.get("process_requirements", {}).get(entity_id, {})


def has_sufficient_supply(state, entity_id, flow_object_type_name):
    requirements = get_process_requirements(state, entity_id, flow_object_type_name)

    return all(
        state.process_supply_states[supply_entity_id] >= quantity
        for supply_entity_id, quantity in requirements.items()
    )


def consume_supply(state, entity_id, flow_object_type_name):
    requirements = get_process_requirements(state, entity_id, flow_object_type_name)

    for supply_entity_id, quantity in requirements.items():
        state.process_supply_states[supply_entity_id] -= quantity


def schedule_process_supply_replenishment(state):
    for entity_id in state.process_supply_states:
        entity = state.simulation_model.entities_by_id[entity_id]
        schedule_event(
            state,
            state.clock + entity["properties"]["replenishment_interval"],
            "replenish_process_supply",
            {"entity_id": entity_id},
        )


def handle_replenish_process_supply(state, data):
    # A local import to break the mutual dependency with processing.py
    # (start_processing needs has_sufficient_supply/consume_supply from
    # here; retrying a stall needs start_processing from there).
    from dese.engine.processing import retry_stalled_slots

    entity_id = data["entity_id"]
    entity = state.simulation_model.entities_by_id[entity_id]
    properties = entity["properties"]

    state.process_supply_states[entity_id] = min(
        state.process_supply_states[entity_id] + properties["replenishment_quantity"],
        properties["capacity"],
    )

    # A replenished supply might be shared by several Processing Entities'
    # process_requirements, so retry every Entity's stalled slots, not just
    # ones known to depend on this specific supply -- simple and correct,
    # even if not the most targeted.
    for other_entity_id in state.entity_states:
        retry_stalled_slots(state, other_entity_id)

    schedule_event(
        state,
        state.clock + properties["replenishment_interval"],
        "replenish_process_supply",
        {"entity_id": entity_id},
    )


EVENT_HANDLERS["replenish_process_supply"] = handle_replenish_process_supply
