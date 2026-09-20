import csv


def get_entity_log_fields(state, entity_id):
    entity = state.simulation_model.entities_by_id[entity_id]
    return {"entity_id": entity_id, "entity_name": entity["name"], "entity_type": entity["type"]}


def get_flow_object_log_fields(state, instance_id):
    instance = state.flow_object_instances[instance_id]
    return {
        "instance_id": instance_id,
        "flow_object_type": instance.flow_object_type,
        "created_at": instance.created_at,
    }


def log_event(state, event_type, **details):
    # Records WHAT happened and WHEN -- not a state snapshot. The full state
    # at any point is reconstructible by replaying these in order, which is
    # the whole point of keeping them as discrete events rather than
    # periodic dumps (see the SimulationState/SimulationModel design notes).
    #
    # sequence reuses the same counter the event queue itself uses for tie-
    # breaking (event_loop.schedule_event) -- one shared, monotonic sense of
    # "what happened in what order" across both scheduled events and logged
    # facts, which the future Event Replay (DESE-54) can step through.
    state.event_sequence_counter += 1
    state.event_log.append(
        {"sequence": state.event_sequence_counter, "time": state.clock, "event_type": event_type, **details}
    )


def export_event_log_to_csv(state, file_path):
    # Column set is the union of keys actually used across all entries,
    # rather than a fixed schema -- different event_types carry different
    # details (e.g. "entity_failed" has no flow_object_type), and a new
    # event_type introduced later needs no changes here to be exported.
    fieldnames = ["sequence", "time", "event_type"]
    seen_fieldnames = set(fieldnames)

    for entry in state.event_log:
        for key in entry:
            if key not in seen_fieldnames:
                fieldnames.append(key)
                seen_fieldnames.add(key)

    with open(file_path, "w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()

        for entry in state.event_log:
            writer.writerow(entry)
