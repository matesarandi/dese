from dese.core.model import get_processing_duration_property
from dese.engine.event_loop import EVENT_HANDLERS, schedule_event
from dese.engine.movement import enter_entity, find_empty_slot


def find_occupied_slot(entity_state, instance_id):
    return next(
        slot for slot in entity_state.slots if slot["flow_object_instance_id"] == instance_id
    )


def start_processing(state, entity_id, instance_id):
    # Process Supply consumption (process_requirements) isn't checked here
    # yet -- that's its own, not-yet-built layer; for now, starting only
    # depends on the Entity already having a free slot for instance_id.
    entity = state.simulation_model.entities_by_id[entity_id]
    domain_only_model_data = {"domain": state.simulation_model.domain}
    duration_property = get_processing_duration_property(
        entity, domain_only_model_data, state.simulation_model.schema
    )
    duration = entity["properties"][duration_property]

    entity_state = state.entity_states[entity_id]
    slot = find_occupied_slot(entity_state, instance_id)
    instance = state.flow_object_instances[instance_id]

    # changeover_time only exists on Processing -- Inspection/Transport get
    # None here and never pay it.
    changeover_time = entity["properties"].get("changeover_time")
    changeover = 0

    if (
        changeover_time is not None
        and slot["last_flow_object_type"] is not None
        and slot["last_flow_object_type"] != instance.flow_object_type
    ):
        changeover = changeover_time

    entity_state.status = "busy"

    schedule_event(
        state,
        state.clock + duration + changeover,
        "finish_processing",
        {"entity_id": entity_id, "instance_id": instance_id},
    )


def handle_finish_processing(state, data):
    entity_id = data["entity_id"]
    instance_id = data["instance_id"]
    entity = state.simulation_model.entities_by_id[entity_id]
    instance = state.flow_object_instances[instance_id]
    entity_state = state.entity_states[entity_id]
    slot = find_occupied_slot(entity_state, instance_id)

    output_relationships = state.simulation_model.output_relationships_by_id[entity_id]
    is_end_of_process = entity_id == state.simulation_model.end_entity_id

    if is_end_of_process and not output_relationships:
        # Exits the system. Completion bookkeeping (lead time, quality
        # outcome, KPIs) is a later layer -- for now just vacate the slot.
        slot["flow_object_instance_id"] = None
        slot["last_flow_object_type"] = instance.flow_object_type
        instance.current_entity_id = None
        return

    if len(output_relationships) != 1 or is_end_of_process:
        # Either a genuine decision point (>1 real output) or an
        # end_of_process Entity that ALSO has a real output relationship --
        # both need Routing rule evaluation, not implemented yet.
        raise NotImplementedError(
            f'Entity "{entity["name"]}" has {len(output_relationships)} possible output(s) '
            f"(end_of_process={is_end_of_process}) -- Routing/decision points aren't "
            "implemented yet."
        )

    next_entity_id = output_relationships[0]["target"]

    if find_empty_slot(state.entity_states[next_entity_id]) is None:
        # Blocked: stays put, still occupying this slot -- nothing else to
        # do here. Un-blocking when the next Entity later frees up a slot
        # isn't implemented yet (same as order_storage's own retry, this
        # needs its own follow-up pass).
        return

    enter_entity(state, instance_id, next_entity_id)
    start_processing(state, next_entity_id, instance_id)

    slot["flow_object_instance_id"] = None
    slot["last_flow_object_type"] = instance.flow_object_type


EVENT_HANDLERS["finish_processing"] = handle_finish_processing
