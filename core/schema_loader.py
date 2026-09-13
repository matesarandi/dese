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
        with open(self.schema_path, "r") as file:
            self.schema_data = json.load(file)

        # schema.json is developer-maintained, so a version mismatch here is a
        # bug to catch immediately rather than something to silently migrate.
        schema_version = self.schema_data.get("schema_version")

        if schema_version != CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema.json version: {schema_version!r} "
                f"(expected {CURRENT_SCHEMA_VERSION!r})."
            )

    def get_domains(self):
        return [domain["name"] for domain in self.schema_data["domains"]]

    def get_domain(self, domain_name):
        for domain in self.schema_data["domains"]:
            if domain["name"] == domain_name:
                return domain
            
        return None

    def get_entity_types(self, domain_name):
        domain = self.get_domain(domain_name)

        if domain is None:
            return []

        return domain["entity_types"]

    def get_entity_schema(self, domain_name, entity_type):
        domain = self.get_domain(domain_name)

        if domain is None:
            return None

        for entity_schema in domain["entity_schemas"]:
            if entity_schema["type"] == entity_type:
                return entity_schema

        return None

    def get_flow_object_schema(self):
        return self.schema_data["base_flow_object_schema"]

    def get_rule_schema(self, domain_name, rule_type):
        domain = self.get_domain(domain_name)

        if domain is None:
            return None

        return domain.get("rule_schemas", {}).get(rule_type)

    def get_relationship_allowances(self, domain_name):
        domain = self.get_domain(domain_name)

        if domain is None:
            return {}

        return domain["relationship_allowances"]
