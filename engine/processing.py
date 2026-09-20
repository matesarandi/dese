from dese.constants import END_OF_PROCESS_ROUTING_TARGET
from dese.core.model import get_processing_duration_property
from dese.engine.event_loop import EVENT_HANDLERS, schedule_event
from dese.engine.maintenance import apply_wear_and_rules
from dese.engine.movement import admit_from_order_storage, enter_entity, find_empty_slot
from dese.engine.process_supply import consume_supply, has_sufficient_supply
from dese.engine.routing import evaluate_routing


def find_occupied_slot(entity_state, instance_id):
    return next(
        slot for slot in entity_state.slots if slot["flow_object_instance_id"] == instance_id
    )


def start_processing(state, entity_id, instance_id):
    entity_state = state.entity_states[entity_id]

    if entity_state.status in ("failed", "down"):
        # Stays seated, un-started -- retried by retry_stalled_slots once
        # the Entity's repair/maintenance job finishes.
        return

    instance = state.flow_object_instances[instance_id]

    if not has_sufficient_supply(state, entity_id, instance.flow_object_type):
        # Stays seated with processing_started still False -- retried by
        # retry_stalled_slots whenever a relevant Process Supply replenishes.
        return

    consume_supply(state, entity_id, instance.flow_object_type)

    entity = state.simulation_model.entities_by_id[entity_id]
    domain_only_model_data = {"domain": state.simulation_model.domain}
    duration_property = get_processing_duration_property(
        entity, domain_only_model_data, state.simulation_model.schema
    )
    duration = entity["properties"][duration_property]
    slot = find_occupied_slot(entity_state, instance_id)

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

    slot["processing_started"] = True
    entity_state.status = "busy"

    schedule_event(
        state,
        state.clock + duration + changeover,
        "finish_processing",
        {"entity_id": entity_id, "instance_id": instance_id},
    )


def retry_stalled_slots(state, entity_id):
    for slot in state.entity_states[entity_id].slots:
        instance_id = slot["flow_object_instance_id"]

        if instance_id is not None and not slot["processing_started"]:
            start_processing(state, entity_id, instance_id)


def get_possible_target_ids(state, entity_id):
    entity = state.simulation_model.entities_by_id[entity_id]
    target_ids = [
        relationship["target"]
        for relationship in state.simulation_model.output_relationships_by_id[entity_id]
    ]

    if entity.get("end_of_process"):
        target_ids.append(END_OF_PROCESS_ROUTING_TARGET)

    return target_ids


def try_advance_finished_instance(state, entity_id, instance_id):
    # Tries to move an already-finished instance out of entity_id, either to
    # its resolved target or out of the system (End of Process). Called both
    # right when an instance finishes (handle_finish_processing) and when
    # retrying a previously-blocked one (retry_upstream) -- the same
    # resolution/movement logic applies either way.
    entity = state.simulation_model.entities_by_id[entity_id]
    instance = state.flow_object_instances[instance_id]
    entity_state = state.entity_states[entity_id]
    slot = find_occupied_slot(entity_state, instance_id)

    possible_target_ids = get_possible_target_ids(state, entity_id)

    if len(possible_target_ids) == 1:
        target_id = possible_target_ids[0]
    else:
        # A genuine decision point (real output(s) plus, for end_of_process
        # Entities, the virtual End of Process target) -- validate_model's
        # check_routing_completeness already guarantees a Routing rule
        # assigns every possible current state to one of these targets.
        target_id = evaluate_routing(state, entity_id, instance_id)

        if target_id is None:
            raise RuntimeError(
                f'Entity "{entity["name"]}" has no matching Routing rule for the current '
                "state -- this should be impossible for a model that passed validate_model."
            )

    if target_id == END_OF_PROCESS_ROUTING_TARGET:
        # Exits the system. Completion bookkeeping (lead time, quality
        # outcome, KPIs) is a later layer -- for now just vacate the slot.
        slot["flow_object_instance_id"] = None
        slot["last_flow_object_type"] = instance.flow_object_type
        slot["finished"] = False
        instance.current_entity_id = None
        retry_upstream(state, entity_id)
        return

    if find_empty_slot(state.entity_states[target_id]) is None:
        # Blocked: stays put, still occupying this slot, marked so
        # retry_upstream can find and retry it once target_id frees a slot.
        slot["finished"] = True
        return

    enter_entity(state, instance_id, target_id)
    start_processing(state, target_id, instance_id)

    slot["flow_object_instance_id"] = None
    slot["last_flow_object_type"] = instance.flow_object_type
    slot["finished"] = False

    # entity_id just freed a slot -- proactively see whether ITS upstream
    # has something finished-but-blocked waiting for exactly this, instead
    # of leaving it stuck until an unrelated event happens to retry it.
    retry_upstream(state, entity_id)


def retry_upstream(state, entity_id):
    if entity_id == state.simulation_model.beginning_entity_id:
        # order_storage is beginning_of_process's own "upstream" -- no real
        # Entity to look at instead.
        for admitted_instance_id in admit_from_order_storage(state):
            start_processing(state, entity_id, admitted_instance_id)
        return

    input_relationships = state.simulation_model.input_relationships_by_id[entity_id]

    if len(input_relationships) != 1:
        # No single real upstream Entity to retry (e.g. a Storage merging
        # several inputs) -- not handled yet, same scope limit as elsewhere.
        return

    upstream_entity_id = input_relationships[0]["source"]
    upstream_entity_state = state.entity_states.get(upstream_entity_id)

    if upstream_entity_state is None:
        return

    for slot in upstream_entity_state.slots:
        if slot["flow_object_instance_id"] is not None and slot["finished"]:
            try_advance_finished_instance(state, upstream_entity_id, slot["flow_object_instance_id"])
            break


def handle_finish_processing(state, data):
    entity_id = data["entity_id"]
    instance_id = data["instance_id"]

    # One completed cycle -- may put the Entity into "failed"/"down" (see
    # maintenance.apply_wear_and_rules), which blocks NEW work from starting
    # here, and/or may mark THIS instance as scrap -- neither affects this
    # already-finished instance moving on normally below.
    apply_wear_and_rules(state, entity_id, instance_id)
    try_advance_finished_instance(state, entity_id, instance_id)


EVENT_HANDLERS["finish_processing"] = handle_finish_processing
