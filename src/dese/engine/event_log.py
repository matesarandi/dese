"""The event log: the simulation's single, append-only record of everything
that happened, and the one data contract every downstream consumer (the
Results tab's CSV export, future Dashboard/Decision Support layers) reads
instead of poking at engine internals directly. `log_event` is the only
way an entry is ever added; `get_entity_log_fields`/`get_flow_object_log_fields`
are shared helpers every event-emitting module uses so entity/Flow-Object
columns stay identical across event types.
"""
import csv


def get_entity_log_fields(state, entity_id):
    """Returns the standard ``entity_id``/``entity_name``/``entity_type`` columns
    for a log row about ``entity_id``, read from the model (not the engine's
    own dynamic ``entity_states``)."""
    entity = state.simulation_model.entities_by_id[entity_id]
    return {"entity_id": entity_id, "entity_name": entity["name"], "entity_type": entity["type"]}


def get_flow_object_log_fields(state, instance_id):
    """Returns the standard Flow-Object columns (``instance_id``,
    ``flow_object_type``, ``created_at``, ``quality``, ``cause``) for a log
    row about ``instance_id``.

    quality/cause reflect the instance's CURRENT state, whatever it is at
    the moment this is called -- e.g. an instance that became scrap at an
    earlier Entity still shows quality="scrap" when it later enters/exits
    a completely different one. This is the one place that decides what a
    Flow-Object-related log row shows for these, used by every event type
    involving an instance (generated, entered, exited, completed).
    """
    instance = state.flow_object_instances[instance_id]
    return {
        "instance_id": instance_id,
        "flow_object_type": instance.flow_object_type,
        "created_at": instance.created_at,
        "quality": instance.quality,
        "cause": instance.scrap_cause,
    }


def log_event(state, event_type, **details):
    """Appends one row to ``state.event_log``.

    Records WHAT happened and WHEN -- not a state snapshot. The full state
    at any point is reconstructible by replaying these in order, which is
    the whole point of keeping them as discrete events rather than
    periodic dumps (see the SimulationState/SimulationModel design notes).

    Args:
        state: The mutable SimulationState; ``event_log`` is appended to
            and ``log_sequence_counter`` is incremented.
        event_type: A short string identifying the kind of event (e.g.
            ``"flow_object_entered"``, ``"entity_failed"``).
        **details: Arbitrary extra columns for this row -- typically the
            dicts returned by ``get_entity_log_fields``/
            ``get_flow_object_log_fields``, plus event-specific fields
            (e.g. ``lead_time`` on ``flow_object_completed``).
    """
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
    """Writes ``state.event_log`` to ``file_path`` as CSV, one row per event.

    Column set is the union of keys actually used across all entries,
    rather than a fixed schema -- different event_types carry different
    details (e.g. "entity_failed" has no flow_object_type), and a new
    event_type introduced later needs no changes here to be exported.

    Args:
        state: The SimulationState whose ``event_log`` to export.
        file_path: Destination path for the CSV file (overwritten if it
            already exists).
    """
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
