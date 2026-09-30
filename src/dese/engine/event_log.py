import csv


def get_entity_log_fields(state, entity_id):
    entity = state.simulation_model.entities_by_id[entity_id]
    return {"entity_id": entity_id, "entity_name": entity["name"], "entity_type": entity["type"]}


def get_flow_object_log_fields(state, instance_id):
    # quality/cause reflect the instance's CURRENT state, whatever it is at
    # the moment this is called -- e.g. an instance that became scrap at an
    # earlier Entity still shows quality="scrap" when it later enters/exits
    # a completely different one. This is the one place that decides what a
    # Flow-Object-related log row shows for these, used by every event type
    # involving an instance (generated, entered, exited, completed).
    instance = state.flow_object_instances[instance_id]
    return {
        "instance_id": instance_id,
        "flow_object_type": instance.flow_object_type,
        "created_at": instance.created_at,
        "quality": instance.quality,
        "cause": instance.scrap_cause,
    }


def log_event(state, event_type, **details):
    # Records WHAT happened and WHEN -- not a state snapshot. The full state
    # at any point is reconstructible by replaying these in order, which is
    # the whole point of keeping them as discrete events rather than
    # periodic dumps (see the SimulationState/SimulationModel design notes).
    #
    # sequence has its own counter, separate from the event QUEUE's tie-
    # breaker (event_loop.schedule_event) -- so it starts cleanly at 1
    # regardless of how many events were already scheduled beforehand. Still
    # a single monotonic ordering across everything actually logged, which
    # the future Event Replay (DESE-54) can step through.
    state.log_sequence_counter += 1
    state.event_log.append(
        {"sequence": state.log_sequence_counter, "time": state.clock, "event_type": event_type, **details}
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
