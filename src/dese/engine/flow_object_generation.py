"""Flow Object generation: each Flow Object type's own independent,
recurring batch-generation schedule, feeding newly-created instances into
`order_storage` and immediately trying to admit them into the
beginning-of-process Entity.
"""
from dese.engine.event_log import get_flow_object_log_fields, log_event
from dese.engine.event_loop import EVENT_HANDLERS, schedule_event
from dese.engine.movement import admit_from_order_storage
from dese.engine.processing import start_processing
from dese.engine.simulation_state import FlowObjectInstance


def schedule_flow_object_generation(state):
    """Schedules each Flow Object type's first generation event, at the
    current clock (so the first batch of every type generates immediately
    when the run starts).

    Called once, before the run starts, to kick off each Flow Object
    type's own independent, recurring generation schedule.
    """
    for flow_object_type in state.simulation_model.flow_object_types:
        schedule_event(
            state,
            state.clock,
            "generate_flow_objects",
            {"flow_object_type": flow_object_type["name"]},
        )


def handle_generate_flow_objects(state, data):
    """Event handler for ``"generate_flow_objects"``: creates one batch of
    a Flow Object type, tries to admit them into the beginning Entity, and
    reschedules this same type's next batch.

    Args:
        state: The mutable SimulationState.
        data: ``{"flow_object_type": <name>}`` identifying which type's
            batch to generate.
    """
    flow_object_type_name = data["flow_object_type"]
    flow_object_type = next(
        flow_object_type
        for flow_object_type in state.simulation_model.flow_object_types
        if flow_object_type["name"] == flow_object_type_name
    )
    properties = flow_object_type["properties"]

    for _ in range(int(properties["batch_size"])):
        state.flow_object_instance_counter += 1
        instance_id = f"FO{state.flow_object_instance_counter:03d}"
        state.flow_object_instances[instance_id] = FlowObjectInstance(
            id=instance_id,
            flow_object_type=flow_object_type_name,
            created_at=state.clock,
            quality="good",
            current_entity_id=None,
        )
        state.order_storage.append(instance_id)
        log_event(state, "flow_object_generated", **get_flow_object_log_fields(state, instance_id))

    beginning_entity_id = state.simulation_model.beginning_entity_id

    for admitted_instance_id in admit_from_order_storage(state):
        start_processing(state, beginning_entity_id, admitted_instance_id)

    # Reschedule the same type's own next batch -- generation_interval is
    # per Flow Object type, so each type keeps its own independent cadence.
    schedule_event(
        state,
        state.clock + properties["generation_interval"],
        "generate_flow_objects",
        {"flow_object_type": flow_object_type_name},
    )


EVENT_HANDLERS["generate_flow_objects"] = handle_generate_flow_objects
