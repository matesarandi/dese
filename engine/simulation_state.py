import random
from dataclasses import dataclass, field

from dese.core.model import holds_flow_object_queue


@dataclass
class FlowObjectInstance:
    id: str
    flow_object_type: str
    created_at: float
    quality: str
    current_entity_id: str


@dataclass
class EntityState:
    # slots holds one entry per Flow Object currently at this Entity (its
    # length is checked against the Entity's own "capacity" property by the
    # event loop -- not pre-sized here, since nothing is in progress yet at
    # t=0). Each entry: {"flow_object_instance_id": ..., "last_flow_object_type": ...}
    # -- changeover_time is tracked per slot (see Processing.changeover_time),
    # not per Entity, since capacity > 1 means independent parallel resources.
    status: str = "idle"
    slots: list = field(default_factory=list)
    cycles_since_maintenance: float = 0


@dataclass
class MaintenanceResourceState:
    busy_count: int = 0
    waiting_entity_ids: list = field(default_factory=list)


@dataclass
class SimulationState:
    simulation_model: object
    simulation_request: object
    clock: float
    event_queue: list
    event_sequence_counter: int
    random_generator: object
    flow_object_instances: dict
    order_storage: list
    entity_states: dict
    storage_states: dict
    process_supply_states: dict
    maintenance_resource_state: MaintenanceResourceState


def build_simulation_state(simulation_model, simulation_request):
    domain_only_model_data = {"domain": simulation_model.domain}

    entity_states = {
        entity_id: EntityState() for entity_id in simulation_model.entities_by_id
    }

    storage_states = {
        entity_id: []
        for entity_id, entity in simulation_model.entities_by_id.items()
        if holds_flow_object_queue(entity, domain_only_model_data, simulation_model.schema)
    }

    process_supply_states = {
        entity_id: entity["properties"]["initial_quantity"]
        for entity_id, entity in simulation_model.entities_by_id.items()
        if "initial_quantity" in entity.get("properties", {})
    }

    return SimulationState(
        simulation_model=simulation_model,
        simulation_request=simulation_request,
        clock=0,
        event_queue=[],
        event_sequence_counter=0,
        random_generator=random.Random(simulation_request.random_seed),
        flow_object_instances={},
        order_storage=[],
        entity_states=entity_states,
        storage_states=storage_states,
        process_supply_states=process_supply_states,
        maintenance_resource_state=MaintenanceResourceState(),
    )
