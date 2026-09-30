"""Low-level, reusable slot/queue occupancy primitives shared by every
behavior layer: placing a Flow Object Instance into an Entity's slot array
or a Storage's FIFO queue, clearing it back out, and deriving an Entity's
idle/busy/blocked status from current occupancy. Deliberately has no
knowledge of Processing/Inspection-specific concerns (starting work,
changeover) -- see `engine.processing` for that.
"""
from dese.engine.event_log import get_entity_log_fields, get_flow_object_log_fields, log_event


def find_empty_slot(entity_state):
    """Returns the first unoccupied slot dict in ``entity_state.slots``, or
    ``None`` if every slot is occupied."""
    for slot in entity_state.slots:
        if slot["flow_object_instance_id"] is None:
            return slot

    return None


def update_entity_status(state, entity_id):
    """Recomputes and, if changed, logs ``entity_id``'s idle/busy/blocked status.

    Must only be called while the Entity is NOT "failed"/"down" -- callers
    that could run in that state (e.g. ``enter_entity``, admitting a Flow
    Object into a broken-down Entity) are responsible for guarding the call
    themselves.
    """
    # Derives "idle"/"busy"/"blocked" purely from current occupancy -- the
    # single place that keeps entity_state.status truthful after any slot
    # (or, for Storage, queue) change, instead of it being set once
    # (start_processing) and never updated again. "blocked" (a slot holds a
    # finished instance that couldn't move on, or a Storage is at capacity)
    # takes priority over plain "busy", since it's the more actionable
    # signal. Callers that could run while the Entity is genuinely "failed"/
    # "down" (e.g. enter_entity, admitting a Flow Object into a broken-down
    # Entity) must guard the call themselves -- this function unconditionally
    # overwrites status, since the one place that legitimately clears
    # failed/down (maintenance.handle_maintenance_resource_job_finished)
    # needs exactly that. Since it's never invoked while failed/down (every
    # call site guards that), the value it computes here is always one of
    # idle/busy/blocked -- entity_failed/entity_repaired/entity_maintenance_*
    # remain the sole source for the failed/down transitions, so logging a
    # status change here can never duplicate those.
    entity_state = state.entity_states[entity_id]
    previous_status = entity_state.status
    storage_queue = state.storage_states.get(entity_id)

    if storage_queue is not None:
        entity = state.simulation_model.entities_by_id[entity_id]

        if len(storage_queue) >= entity["properties"]["capacity"]:
            new_status = "blocked"
        elif storage_queue:
            new_status = "busy"
        else:
            new_status = "idle"
    else:
        # "blocked" covers BOTH ways a seated occupant can fail to be
        # actively processed: finished but the target is full (can't push
        # out), or seated but never started (e.g. insufficient Process
        # Supply -- can't pull in the material it needs). Either way, the
        # machine isn't producing, which is the actionable fact -- WHY it's
        # stuck is on whatever caused it (a full downstream slot vs. an
        # empty supply), not on this status value.
        if any(
            slot["flow_object_instance_id"] is not None and (slot["finished"] or not slot["processing_started"])
            for slot in entity_state.slots
        ):
            new_status = "blocked"
        elif any(slot["flow_object_instance_id"] is not None for slot in entity_state.slots):
            new_status = "busy"
        else:
            new_status = "idle"

    entity_state.status = new_status

    if new_status != previous_status:
        log_event(state, "entity_status_changed", **get_entity_log_fields(state, entity_id), status=new_status)


def enter_entity(state, instance_id, entity_id):
    """Seats ``instance_id`` into the first empty slot at ``entity_id``, if any.

    Pure bookkeeping: occupies the slot and updates the instance's
    location. Does NOT start processing there -- that's Processing/
    Inspection-specific behavior (see ``processing.start_processing``),
    kept separate so this stays reusable and dependency-free.

    Returns:
        bool: True if a slot was free and the instance was seated; False
        (no-op) if every slot was already occupied.
    """
    entity_state = state.entity_states[entity_id]
    slot = find_empty_slot(entity_state)

    if slot is None:
        return False

    slot["flow_object_instance_id"] = instance_id
    slot["processing_started"] = False
    slot["finished"] = False
    state.flow_object_instances[instance_id].current_entity_id = entity_id

    # Logged HERE (physical placement), not when processing actually
    # starts -- a seated-but-stalled occupant (e.g. waiting on Process
    # Supply) genuinely occupies this Entity from this instant, even
    # before it does any work; that stall itself shows up as the Entity's
    # own status going "blocked" below, not as a delayed log entry.
    log_event(
        state,
        "flow_object_entered",
        **get_entity_log_fields(state, entity_id),
        **get_flow_object_log_fields(state, instance_id),
    )

    # Deliberately does NOT call update_entity_status here -- right after
    # placement, processing_started is always still False, which would
    # read as "blocked" even for an Entity that's about to start working on
    # it immediately (e.g. Inspection, no Process Supply to wait on) --
    # a spurious blocked-then-busy pair logged in the same instant, with
    # nothing in between ever actually observing "blocked". Callers always
    # follow this with processing.start_processing synchronously, which is
    # the one place that knows the ACTUAL outcome (started -> busy, still
    # waiting on failed/down or insufficient supply -> stays whatever it
    # already was, or genuinely blocked) and updates status itself.
    return True


def clear_slot(state, entity_id, slot, flow_object_type):
    """Frees ``slot`` at ``entity_id`` and recomputes its status.

    The shared "a slot's occupant just left" bookkeeping -- used whether
    the instance exited the system (End of Process), got absorbed by a
    Process Sink, or moved on to a real downstream Entity. Deliberately
    does NOT touch the instance's own current_entity_id -- callers that
    move the instance elsewhere (``enter_entity``) already set that
    themselves; callers where the instance truly leaves the system set it
    to None right after calling this.

    Args:
        state: The mutable SimulationState.
        entity_id: The Entity the slot belongs to.
        slot: The specific slot dict being vacated.
        flow_object_type: The type of the instance that just left, recorded
            as the slot's ``last_flow_object_type`` for the next occupant's
            changeover comparison.
    """
    slot["flow_object_instance_id"] = None
    slot["last_flow_object_type"] = flow_object_type
    slot["finished"] = False

    entity_state = state.entity_states[entity_id]

    if entity_state.status not in ("failed", "down"):
        update_entity_status(state, entity_id)


def enter_storage(state, entity_id, instance_id):
    """Appends ``instance_id`` to the back of ``entity_id``'s Storage queue, if there's room.

    Mirrors ``enter_entity``, but for a Storage's capacity-bounded FIFO
    queue instead of a fixed-position slot array -- Storage has no per-slot
    identity to track (no changeover, no single occupant to point at), so
    a plain list is enough.

    Returns:
        bool: True if there was room and the instance was queued; False
        (no-op) if the Storage was already at capacity.
    """
    storage_queue = state.storage_states[entity_id]
    entity = state.simulation_model.entities_by_id[entity_id]

    if len(storage_queue) >= entity["properties"]["capacity"]:
        return False

    storage_queue.append(instance_id)
    state.flow_object_instances[instance_id].current_entity_id = entity_id

    log_event(
        state,
        "flow_object_entered",
        **get_entity_log_fields(state, entity_id),
        **get_flow_object_log_fields(state, instance_id),
    )

    entity_state = state.entity_states[entity_id]

    if entity_state.status not in ("failed", "down"):
        update_entity_status(state, entity_id)

    return True


def leave_storage(state, entity_id, instance_id):
    """Removes ``instance_id`` from ``entity_id``'s Storage queue and recomputes its status.

    Mirrors ``clear_slot`` for a Storage's queue -- instance_id is always
    the front of the queue in practice (release order is FIFO, the only
    release order Storage supports), but this removes it by value rather
    than assuming index 0, so a future non-FIFO release order wouldn't
    silently remove the wrong one.
    """
    state.storage_states[entity_id].remove(instance_id)

    entity_state = state.entity_states[entity_id]

    if entity_state.status not in ("failed", "down"):
        update_entity_status(state, entity_id)


def admit_from_order_storage(state):
    """Admits as many waiting Flow Objects from ``state.order_storage`` into
    the beginning Entity as there's room for.

    order_storage only ever feeds the beginning_of_process Entity -- it's
    the one place with no upstream Entity of its own to occupy a slot at
    while waiting (see FlowObjectInstance.current_entity_id staying None
    while queued here). Admits in existing (creation) order, since
    order_storage is itself append-only.

    Returns:
        list[str]: the admitted instance ids, in order, so the caller can
        start processing each of them.
    """
    entity_id = state.simulation_model.beginning_entity_id
    admitted_instance_ids = []

    while state.order_storage and enter_entity(state, state.order_storage[0], entity_id):
        admitted_instance_ids.append(state.order_storage.pop(0))

    return admitted_instance_ids
