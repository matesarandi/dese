from dataclasses import dataclass

from dese.core.validation import check_property_value


class SimulationRequestValidationError(Exception):
    # Raised instead of building a SimulationRequest from incomplete/invalid
    # input -- carries the same issue list a caller would get from the
    # Simulation page's form, so a non-UI caller sees the exact same errors.
    def __init__(self, issues):
        self.issues = issues
        super().__init__(f"Cannot build a Simulation Request: {len(issues)} validation issue(s).")


@dataclass
class SimulationRequest:
    run_duration: float
    random_seed: float
    control_strategy: str


def validate_simulation_request(run_duration, random_seed, control_strategy, schema):
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
    issues = validate_simulation_request(run_duration, random_seed, control_strategy, schema)

    if issues:
        raise SimulationRequestValidationError(issues)

    return SimulationRequest(
        run_duration=run_duration,
        random_seed=random_seed,
        control_strategy=control_strategy,
    )
