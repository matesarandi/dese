from dese.engine.event_loop import EVENT_HANDLERS, schedule_event
from dese.engine.movement import admit_from_order_storage
from dese.engine.processing import start_processing
from dese.engine.simulation_state import FlowObjectInstance
from dese.utils import generate_id


def schedule_flow_object_generation(state):
    # Called once, before the run starts, to kick off each Flow Object
    # type's own independent, recurring generation schedule -- the first
    # batch of each type generates immediately, at the current clock.
    for flow_object_type in state.simulation_model.flow_object_types:
        schedule_event(
            state,
            state.clock,
            "generate_flow_objects",
            {"flow_object_type": flow_object_type["name"]},
        )


def handle_generate_flow_objects(state, data):
    flow_object_type_name = data["flow_object_type"]
    flow_object_type = next(
        flow_object_type
        for flow_object_type in state.simulation_model.flow_object_types
        if flow_object_type["name"] == flow_object_type_name
    )
    properties = flow_object_type["properties"]

    for _ in range(int(properties["batch_size"])):
        instance_id = generate_id(state.flow_object_instances.keys(), "FO")
        state.flow_object_instances[instance_id] = FlowObjectInstance(
            id=instance_id,
            flow_object_type=flow_object_type_name,
            created_at=state.clock,
            quality="good",
            current_entity_id=None,
        )
        state.order_storage.append(instance_id)

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
