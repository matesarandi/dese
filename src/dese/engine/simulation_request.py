"""SimulationRequest: the small, validated set of per-run parameters (how
long to run, which random seed, which control strategy) a caller supplies
on top of a SimulationModel -- the "request" half of the engine's
request/model/state trio.
"""
from dataclasses import dataclass

from dese.core.validation import check_property_value


class SimulationRequestValidationError(Exception):
    """Raised by `build_simulation_request` instead of building a
    SimulationRequest from incomplete/invalid input.

    Carries the same issue list a caller would get from the Simulation
    page's form, so a non-UI caller sees the exact same errors.
    """

    def __init__(self, issues):
        self.issues = issues
        super().__init__(f"Cannot build a Simulation Request: {len(issues)} validation issue(s).")


@dataclass
class SimulationRequest:
    """One run's parameters: how long to simulate, which random seed
    drives Failure/BaselineScrap rolls, and which control strategy to use."""

    run_duration: float
    random_seed: float
    control_strategy: str


def validate_simulation_request(run_duration, random_seed, control_strategy, schema):
    """Checks the three request fields against the schema's simulation-request
    property definitions.

    Args:
        run_duration: Requested run length, in hours.
        random_seed: Seed for the run's single ``random.Random`` instance.
        control_strategy: Which control strategy to simulate under.
        schema: The loaded SchemaLoader.

    Returns:
        list[dict]: validation issues (empty if the request is valid), in
        the same ``{"severity": ..., "message": ...}`` shape ``validate_model``
        uses.
    """
    values_by_field_name = {
        "run_duration": run_duration,
        "random_seed": random_seed,
        "control_strategy": control_strategy,
    }

    issues = []

    for field_name, field_schema in schema.get_simulation_request_schema()["properties"].items():
        location = field_name.replace("_", " ").title()
        issues.extend(
            check_property_value(values_by_field_name[field_name], field_schema, location)
        )

    return issues


def build_simulation_request(run_duration, random_seed, control_strategy, schema):
    """Validates and builds a SimulationRequest.

    Args:
        run_duration: Requested run length, in hours.
        random_seed: Seed for the run's single ``random.Random`` instance.
        control_strategy: Which control strategy to simulate under.
        schema: The loaded SchemaLoader.

    Returns:
        SimulationRequest: the validated request.

    Raises:
        SimulationRequestValidationError: if any field fails validation.
    """
    issues = validate_simulation_request(run_duration, random_seed, control_strategy, schema)

    if issues:
        raise SimulationRequestValidationError(issues)

    return SimulationRequest(
        run_duration=run_duration,
        random_seed=random_seed,
        control_strategy=control_strategy,
    )
