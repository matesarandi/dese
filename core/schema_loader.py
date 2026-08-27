import json


class SchemaLoader:
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

    def get_relationship_allowances(self, domain_name):
        domain = self.get_domain(domain_name)

        if domain is None:
            return {}

        return domain["relationship_allowances"]
