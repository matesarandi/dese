"""Loads and exposes `schemas/schema.json`: the single, versioned source of
truth for every domain's entity types, property definitions, rule schemas,
and relationship allowances. Both the Model Editor UI and the Simulation
Engine read the schema exclusively through this class, never by parsing
the JSON file themselves.
"""
import json

from dese.constants import CURRENT_SCHEMA_VERSION


class SchemaLoader:
    """Read-only, Tkinter-independent access to schema.json: domains, entity
    types, entity/flow-object property schemas, and relationship allowances."""

    def __init__(self, schema_path):
        self.schema_path = schema_path
        self.schema_data = None
        self.load_schema()

    # ==========================
    # Methods
    # ==========================

    def load_schema(self):
        """Reads and parses ``schema_path`` into ``self.schema_data``.

        Raises:
            ValueError: if the file's ``schema_version`` doesn't match
                ``constants.CURRENT_SCHEMA_VERSION`` -- schema.json is
                developer-maintained, so a mismatch is a bug to catch
                immediately rather than something to silently migrate.
        """
        with open(self.schema_path, "r") as file:
            self.schema_data = json.load(file)

        schema_version = self.schema_data.get("schema_version")

        if schema_version != CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema.json version: {schema_version!r} "
                f"(expected {CURRENT_SCHEMA_VERSION!r})."
            )

    def get_domains(self):
        """Returns every domain's name (e.g. ``["Production"]``)."""
        return [domain["name"] for domain in self.schema_data["domains"]]

    def get_domain(self, domain_name):
        """Returns the raw domain dict for ``domain_name``, or ``None`` if unknown."""
        for domain in self.schema_data["domains"]:
            if domain["name"] == domain_name:
                return domain

        return None

    def get_entity_types(self, domain_name):
        """Returns the list of entity type names available in ``domain_name``
        (``[]`` if the domain is unknown)."""
        domain = self.get_domain(domain_name)

        if domain is None:
            return []

        return domain["entity_types"]

    def get_entity_schema(self, domain_name, entity_type):
        """Returns the schema dict (properties, rule_eligibility, input/output
        limits, ...) for one entity type in ``domain_name``, or ``None`` if
        either is unknown."""
        domain = self.get_domain(domain_name)

        if domain is None:
            return None

        for entity_schema in domain["entity_schemas"]:
            if entity_schema["type"] == entity_type:
                return entity_schema

        return None

    def get_base_entity_schema(self):
        """Returns the domain-independent base entity schema (every entity's
        own runtime states, e.g. ``status``)."""
        return self.schema_data["base_entity_schema"]

    def get_flow_object_schema(self):
        """Returns the base Flow Object schema (its own runtime states, e.g.
        ``quality``)."""
        return self.schema_data["base_flow_object_schema"]

    def get_simulation_request_schema(self):
        """Returns the schema for a simulation run's own request parameters
        (run duration, random seed, control strategy)."""
        return self.schema_data["simulation_request_schema"]

    def get_rule_schema(self, domain_name, rule_type):
        """Returns the property schema for one rule type (e.g. ``"Failure"``)
        in ``domain_name``, or ``None`` if either is unknown."""
        domain = self.get_domain(domain_name)

        if domain is None:
            return None

        return domain.get("rule_schemas", {}).get(rule_type)

    def get_relationship_allowances(self, domain_name):
        """Returns ``{source_entity_type: [allowed_target_entity_types]}``
        for ``domain_name`` (``{}`` if the domain is unknown)."""
        domain = self.get_domain(domain_name)

        if domain is None:
            return {}

        return domain["relationship_allowances"]
