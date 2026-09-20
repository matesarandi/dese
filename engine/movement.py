def find_empty_slot(entity_state):
    for slot in entity_state.slots:
        if slot["flow_object_instance_id"] is None:
            return slot

    return None


def enter_entity(state, instance_id, entity_id):
    # Pure bookkeeping: occupies the first empty slot at entity_id with
    # instance_id and updates the instance's location. Does NOT start
    # processing there -- that's Processing/Inspection/Transport-specific
    # behavior (see processing.start_processing), kept separate so this
    # stays reusable and dependency-free. Returns False (does nothing) if
    # there's no free slot.
    entity_state = state.entity_states[entity_id]
    slot = find_empty_slot(entity_state)

    if slot is None:
        return False

    slot["flow_object_instance_id"] = instance_id
    slot["processing_started"] = False
    slot["finished"] = False
    state.flow_object_instances[instance_id].current_entity_id = entity_id

    return True


def admit_from_order_storage(state):
    # order_storage only ever feeds the beginning_of_process Entity -- it's
    # the one place with no upstream Entity of its own to occupy a slot at
    # while waiting (see FlowObjectInstance.current_entity_id staying None
    # while queued here). Admits as many waiting instances as fit, in their
    # existing (creation) order, since order_storage is itself append-only.
    # Returns the admitted instance ids, in order, so the caller can start
    # processing each of them.
    entity_id = state.simulation_model.beginning_entity_id
    admitted_instance_ids = []

    while state.order_storage and enter_entity(state, state.order_storage[0], entity_id):
        admitted_instance_ids.append(state.order_storage.pop(0))

    return admitted_instance_ids
