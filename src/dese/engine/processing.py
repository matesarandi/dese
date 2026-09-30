from dese.constants import END_OF_PROCESS_ROUTING_TARGET
from dese.core.model import (
    absorbs_flow_objects,
    get_processing_duration_property,
    holds_flow_object_queue,
)
from dese.engine.event_log import get_entity_log_fields, get_flow_object_log_fields, log_event
from dese.engine.event_loop import EVENT_HANDLERS, schedule_event
from dese.engine.maintenance import apply_wear_and_rules
from dese.engine.movement import (
    admit_from_order_storage,
    clear_slot,
    enter_entity,
    enter_storage,
    find_empty_slot,
    leave_storage,
    update_entity_status,
)
from dese.engine.process_supply import consume_supply, has_sufficient_supply
from dese.engine.routing import evaluate_routing


def find_occupied_slot(entity_state, instance_id):
    return next(
        slot for slot in entity_state.slots if slot["flow_object_instance_id"] == instance_id
    )


def start_processing(state, entity_id, instance_id, update_status=True):
    # update_status=False is for retry_stalled_slots only: with capacity >
    # 1, it retries every stalled slot on the same Entity in one pass, and
    # each call succeeding/failing independently would recompute and log
    # status per slot -- e.g. slot A resuming reads as "busy" for an
    # instant, even though slot B (retried a moment later, same instant)
    # hasn't resumed yet, so the truthful reading is still "blocked". That
    # produced the exact same kind of premature, wrong-a-moment-later log
    # entry as the enter_entity and handle_maintenance_resource_job_finished
    # cases -- retry_stalled_slots instead computes/logs the real, settled
    # outcome itself, once, after every slot has had its turn.
    entity_state = state.entity_states[entity_id]

    if entity_state.status in ("failed", "down"):
        # Stays seated, un-started -- retried by retry_stalled_slots once
        # the Entity's repair/maintenance job finishes.
        return

    instance = state.flow_object_instances[instance_id]

    if not has_sufficient_supply(state, entity_id, instance.flow_object_type):
        # Stays seated with processing_started still False -- retried by
        # retry_stalled_slots whenever a relevant Process Supply replenishes.
        # This IS the moment the stall becomes real (movement.enter_entity
        # deliberately doesn't update status itself), so it's the one place
        # that marks the Entity "blocked" for it.
        if update_status:
            update_entity_status(state, entity_id)
        return

    consume_supply(state, entity_id, instance.flow_object_type)

    entity = state.simulation_model.entities_by_id[entity_id]
    domain_only_model_data = {"domain": state.simulation_model.domain}
    duration_property = get_processing_duration_property(
        entity, domain_only_model_data, state.simulation_model.schema
    )
    duration = entity["properties"][duration_property]
    slot = find_occupied_slot(entity_state, instance_id)

    # changeover_time only exists on Processing -- Inspection gets None here
    # and never pays it.
    changeover_time = entity["properties"].get("changeover_time")
    changeover = 0

    if (
        changeover_time is not None
        and slot["last_flow_object_type"] is not None
        and slot["last_flow_object_type"] != instance.flow_object_type
    ):
        changeover = changeover_time

    slot["processing_started"] = True
    # entered was already logged when the instance was first placed here
    # (movement.enter_entity) -- this only needs to recompute status, since
    # a previously "blocked" (seated-but-stalled, e.g. on Process Supply)
    # Entity genuinely becomes "busy" now that it's actually working.
    if update_status:
        update_entity_status(state, entity_id)

    schedule_event(
        state,
        state.clock + duration + changeover,
        "finish_processing",
        {"entity_id": entity_id, "instance_id": instance_id},
    )


def retry_stalled_slots(state, entity_id):
    # Retries every stalled slot silently (update_status=False), then
    # computes/logs the real, settled outcome exactly once, after every
    # slot's had its turn -- see start_processing's own comment for why.
    for slot in state.entity_states[entity_id].slots:
        instance_id = slot["flow_object_instance_id"]

        if instance_id is not None and not slot["processing_started"]:
            start_processing(state, entity_id, instance_id, update_status=False)

    # Guarded like every other update_entity_status call site: this can be
    # called for an Entity that's still genuinely failed/down (e.g.
    # handle_replenish_process_supply retries EVERY Entity on any
    # replenishment, not just ones known to be affected) -- every
    # start_processing call above would have refused and returned
    # immediately for those, so nothing here should overwrite that status.
    entity_state = state.entity_states[entity_id]

    if entity_state.status not in ("failed", "down"):
        update_entity_status(state, entity_id)


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
    # Tries to move an instance that's ready to leave entity_id -- either a
    # just-finished (or previously blocked) slot occupant, or the front of a
    # Storage's queue (Storage has no "processing" of its own, so anything
    # sitting there is always ready to move on) -- to its resolved target,
    # or out of the system (End of Process). Called right when an instance
    # finishes/enters a Storage, and when retrying a previously-blocked one
    # (retry_upstream) -- the same resolution/movement logic applies either
    # way, regardless of whether the source is slot- or queue-based.
    entity = state.simulation_model.entities_by_id[entity_id]
    instance = state.flow_object_instances[instance_id]
    entity_state = state.entity_states[entity_id]
    domain_only_model_data = {"domain": state.simulation_model.domain}
    source_storage_queue = state.storage_states.get(entity_id)
    slot = None if source_storage_queue is not None else find_occupied_slot(entity_state, instance_id)

    def release_from_source(log_exited=True):
        if source_storage_queue is None:
            clear_slot(state, entity_id, slot, instance.flow_object_type)
        else:
            leave_storage(state, entity_id, instance_id)
            # Slot-based Entities log their own flow_object_exited in
            # handle_finish_processing, right before this function ever
            # runs. Storage has no equivalent "finish" step -- items are
            # ready to leave the instant they're queued -- so this is the
            # one place that can log it, keeping entered/exited symmetric
            # for every Entity a Flow Object passes through (Utilization/WIP
            # both assume that pairing, per 08-kpi-definitions.md) --
            # EXCEPT when this Storage is itself where the journey ends
            # (log_exited=False, passed by the End of Process branch below):
            # a Storage that's the model's own designated end_of_process
            # never has a next hop either, exactly like a Process Sink, so
            # "exited" would be just as meaningless there.
            if log_exited:
                log_event(
                    state,
                    "flow_object_exited",
                    **get_entity_log_fields(state, entity_id),
                    **get_flow_object_log_fields(state, instance_id),
                )

    def mark_source_blocked():
        if source_storage_queue is None:
            # Blocked: stays put, still occupying this slot, marked so
            # retry_upstream can find and retry it once the target frees up.
            slot["finished"] = True

            if entity_state.status not in ("failed", "down"):
                update_entity_status(state, entity_id)
        # A Storage source needs no extra bookkeeping here -- its own queue
        # occupancy already drives update_entity_status's "blocked", and the
        # instance simply stays at the front, retried by retry_upstream the
        # next time its target frees up.

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
        # Exits the system via the main path (End of Process). If entity_id
        # is itself a Storage, this is a Warehouse-as-terminus -- it never
        # moves on either, so no flow_object_exited (mirrors the Process
        # Sink case below); for a slot-based Entity this has no effect,
        # since its own flow_object_exited already logged separately, in
        # handle_finish_processing, before this function ever ran.
        release_from_source(log_exited=False)
        instance.current_entity_id = None
        log_event(
            state,
            "flow_object_completed",
            **get_entity_log_fields(state, entity_id),
            **get_flow_object_log_fields(state, instance_id),
            lead_time=state.clock - instance.created_at,
        )
        retry_upstream(state, entity_id)
        return

    target_entity = state.simulation_model.entities_by_id[target_id]

    if absorbs_flow_objects(target_entity, domain_only_model_data, state.simulation_model.schema):
        # A Process Sink: no slots/capacity of its own -- every arrival is
        # absorbed immediately, never queued, and never moves on to
        # anything else -- permanently, not just "for now". Logged as
        # exactly one flow_object_entered (confirms arrival), the same as
        # entering any other Entity -- no exited (never a next hop, no
        # busy-time interpretation) and deliberately no flow_object_completed
        # either: "completed" means the instance finished the process via a
        # real exit point, which absorption by a Sink isn't. instance stays
        # sitting at the Sink (current_entity_id keeps pointing at it,
        # exactly like an instance sitting in a Storage) -- a reader tells
        # it's done by this being its last logged row, at an Entity whose
        # entity_type is "Process Sink".
        release_from_source()
        instance.current_entity_id = target_id
        log_event(
            state,
            "flow_object_entered",
            **get_entity_log_fields(state, target_id),
            **get_flow_object_log_fields(state, instance_id),
        )
        retry_upstream(state, entity_id)
        return

    if holds_flow_object_queue(target_entity, domain_only_model_data, state.simulation_model.schema):
        # A Storage: enters its FIFO queue if there's room (enter_storage
        # logs flow_object_entered itself), else blocks the source exactly
        # like a full downstream slot would.
        if not enter_storage(state, target_id, instance_id):
            mark_source_blocked()
            return

        release_from_source()
        retry_upstream(state, entity_id)
        # The instance we just placed at the back of the queue might itself
        # be at the front (an empty Storage) and its own target might
        # already have room -- a real buffer that's immediately handed off
        # again spends 0 time "in storage", which is the correct behavior,
        # not a special case.
        try_release_from_storage(state, target_id)
        return

    if find_empty_slot(state.entity_states[target_id]) is None:
        mark_source_blocked()
        return

    release_from_source()
    enter_entity(state, instance_id, target_id)
    start_processing(state, target_id, instance_id)

    # entity_id just freed a slot -- proactively see whether ITS upstream
    # has something finished-but-blocked waiting for exactly this, instead
    # of leaving it stuck until an unrelated event happens to retry it.
    retry_upstream(state, entity_id)


def try_release_from_storage(state, entity_id):
    # A Storage's front-of-queue item is always ready to move on the instant
    # its resolved target has room -- there's no processing of its own
    # gating it. Loops (rather than a single attempt) because releasing one
    # item can immediately free room for the new front item to also leave,
    # in the same instant.
    storage_queue = state.storage_states[entity_id]

    while storage_queue:
        instance_id = storage_queue[0]
        length_before = len(storage_queue)
        try_advance_finished_instance(state, entity_id, instance_id)

        if len(storage_queue) == length_before:
            # Still there -- blocked on its resolved target, stop trying.
            break


def retry_upstream(state, entity_id):
    if entity_id == state.simulation_model.beginning_entity_id:
        # order_storage is beginning_of_process's own "upstream" -- no real
        # Entity to look at instead.
        for admitted_instance_id in admit_from_order_storage(state):
            start_processing(state, entity_id, admitted_instance_id)
        return

    input_relationships = state.simulation_model.input_relationships_by_id[entity_id]

    # entity_id just freed exactly one slot, so at most one waiting
    # instance can move into it right now -- gather the oldest-waiting
    # candidate from EACH upstream source (a Storage's front-of-queue
    # item, or a slot-based Entity's oldest finished-but-blocked item),
    # then advance only the overall oldest one. Same "earliest created
    # goes first" fairness rule already used within a single Entity's own
    # slots (see below) and by order_storage admission, generalized across
    # potentially MULTIPLE upstream sources -- a genuine merge point (e.g.
    # two branches feeding one downstream Processing entity; Processing's
    # own input_max is 7, so this is a fully valid, reachable topology,
    # not just the single-input case this used to be limited to).
    candidates = []

    for relationship in input_relationships:
        upstream_entity_id = relationship["source"]
        upstream_storage_queue = state.storage_states.get(upstream_entity_id)

        if upstream_storage_queue is not None:
            if upstream_storage_queue:
                instance_id = upstream_storage_queue[0]
                candidates.append((upstream_entity_id, instance_id, True))
            continue

        upstream_entity_state = state.entity_states.get(upstream_entity_id)

        if upstream_entity_state is None:
            continue

        # With capacity > 1, more than one slot at the SAME upstream
        # Entity can be finished-but-blocked at once -- picking by slot
        # INDEX (whichever happens to come first in the array) rather than
        # by how long each has actually been waiting lets a slot that
        # keeps getting freshly refilled (and re-blocked) perpetually win
        # the race over one that's been stuck since much earlier, starving
        # it indefinitely.
        blocked_instance_ids = [
            slot["flow_object_instance_id"]
            for slot in upstream_entity_state.slots
            if slot["flow_object_instance_id"] is not None and slot["finished"]
        ]

        if blocked_instance_ids:
            oldest_instance_id = min(
                blocked_instance_ids, key=lambda iid: state.flow_object_instances[iid].created_at
            )
            candidates.append((upstream_entity_id, oldest_instance_id, False))

    if not candidates:
        return

    upstream_entity_id, instance_id, is_storage = min(
        candidates, key=lambda candidate: state.flow_object_instances[candidate[1]].created_at
    )

    if is_storage:
        try_release_from_storage(state, upstream_entity_id)
    else:
        try_advance_finished_instance(state, upstream_entity_id, instance_id)


def handle_finish_processing(state, data):
    entity_id = data["entity_id"]
    instance_id = data["instance_id"]

    # One completed cycle -- may put the Entity into "failed"/"down" (see
    # maintenance.apply_wear_and_rules), which blocks NEW work from starting
    # here, and/or may mark THIS instance as scrap -- neither affects this
    # already-finished instance moving on normally below. Logged after, so
    # cycles_since_maintenance reflects this cycle's own increment.
    apply_wear_and_rules(state, entity_id, instance_id)
    log_event(
        state,
        "flow_object_exited",
        **get_entity_log_fields(state, entity_id),
        **get_flow_object_log_fields(state, instance_id),
        cycles_since_maintenance=state.entity_states[entity_id].cycles_since_maintenance,
    )
    try_advance_finished_instance(state, entity_id, instance_id)


EVENT_HANDLERS["finish_processing"] = handle_finish_processing
