import json
import tkinter as tk
from tkinter import messagebox, ttk

from dese.application.pages.flow_object_editor import FlowObjectEditor
from dese.constants import (
    BUTTON_WIDTH,
    INPUT_WIDTH,
    PAD,
    SPINBOX_WIDTH,
)
from dese.utils import convert_property_value, validate_number


class ModelEditorPage(ttk.Frame):
    def __init__(self, parent, model_path, schema, model_changed_callback):
        super().__init__(parent)
        self.model_path = model_path
        self.schema = schema
        self.model_changed_callback = model_changed_callback
        self.model_data = None
        self.selected_entity = None
        self.input_count = 0
        self.output_count = 0
        self.property_entries = {}
        self.input_comboboxes = []
        self.output_comboboxes = []
        self.input_relationship_ids = []
        self.output_relationship_ids = []
        self.load_model()
        self.create_widgets()

    # ==========================
    # Methods
    # ==========================

    def is_main_entity(self, entity):
        entity_schema = self.schema.get_entity_schema(
            self.model_data["domain"], entity["type"]
        )

        if entity_schema is None:
            return False

        return entity_schema["hierarchy"]["role"] == "main"

    def open_flow_object_editor(self):
        FlowObjectEditor(
            self, self.model_data, self.schema, self.model_changed_callback
        )

    def generate_entity_id(self):
        existing_ids = [entity["id"] for entity in self.model_data["entities"]]

        number = 1

        while f"E{number:03d}" in existing_ids:
            number += 1

        return f"E{number:03d}"

    def is_entity_name_unique(self, entity, name):
        return all(
            other_entity is entity or other_entity["name"] != name
            for other_entity in self.model_data["entities"]
        )

    def generate_relationship_id(self):
        existing_ids = [
            relationship["id"] for relationship in self.model_data["relationships"]
        ]

        number = 1

        while f"R{number:03d}" in existing_ids:
            number += 1

        return f"R{number:03d}"

    # ==========================
    # Add Entity Window
    # ==========================

    def update_process_boundary_state(self):
        beginning_entity = next(
            (
                entity
                for entity in self.model_data["entities"]
                if entity.get("beginning_of_process")
            ),
            None,
        )

        end_entity = next(
            (
                entity
                for entity in self.model_data["entities"]
                if entity.get("end_of_process")
            ),
            None,
        )

        if beginning_entity is not None:
            if self.selected_entity is beginning_entity:
                self.beginning_of_process_checkbutton.config(state="normal")

            else:
                self.beginning_of_process_checkbutton.config(state="disabled")

        else:
            self.beginning_of_process_checkbutton.config(state="normal")

        if end_entity is not None:
            if self.selected_entity is end_entity:
                self.end_of_process_checkbutton.config(state="normal")

            else:
                self.end_of_process_checkbutton.config(state="disabled")

        else:
            self.end_of_process_checkbutton.config(state="normal")

    def add_entity(self):
        # Window:
        self.add_entity_window = tk.Toplevel(self)
        self.add_entity_window.title("Add Entity")
        self.add_entity_window.resizable(False, False)

        # Widgets:
        self.add_entity_name_label = ttk.Label(self.add_entity_window, text="Name:")
        self.add_entity_name_entry = ttk.Entry(
            self.add_entity_window, width=INPUT_WIDTH
        )
        self.add_entity_type_label = ttk.Label(self.add_entity_window, text="Type:")
        self.add_entity_type_combobox = ttk.Combobox(
            self.add_entity_window,
            state="readonly",
            values=self.schema.get_entity_types(self.model_data["domain"]),
            width=INPUT_WIDTH,
        )
        self.add_entity_cancel_button = ttk.Button(
            self.add_entity_window,
            text="Cancel",
            width=BUTTON_WIDTH,
            command=self.add_entity_window.destroy,
        )
        self.add_entity_confirm_button = ttk.Button(
            self.add_entity_window,
            text="Add",
            width=BUTTON_WIDTH,
            command=self.confirm_add_entity,
        )

        # Display widgets:
        self.add_entity_name_label.grid(row=0, column=0, sticky="w")
        self.add_entity_name_entry.grid(row=0, column=1, sticky="w")
        self.add_entity_type_label.grid(row=1, column=0, sticky="w")
        self.add_entity_type_combobox.grid(row=1, column=1, sticky="w")
        self.add_entity_cancel_button.grid(row=2, column=1, sticky="e")
        self.add_entity_confirm_button.grid(row=2, column=0, sticky="e")

    def confirm_add_entity(self):
        # Get input:
        name = self.add_entity_name_entry.get()
        entity_type = self.add_entity_type_combobox.get()

        # Validate input:
        if not name:
            messagebox.showwarning("Invalid Entity", "Name is required.")
            return

        if not entity_type:
            messagebox.showwarning("Invalid Entity", "Type is required.")
            return

        if any(entity["name"] == name for entity in self.model_data["entities"]):
            messagebox.showwarning("Duplicate name", "Cannot use the same name.")
            return

        # Get entity schema:
        entity_schema = self.schema.get_entity_schema(
            self.model_data["domain"], entity_type
        )

        # Create properties:
        properties = {
            property_name: None for property_name in entity_schema["properties"]
        }

        # Create entity:
        entity = {
            "id": self.generate_entity_id(),
            "name": name,
            "type": entity_type,
            "properties": properties,
        }

        # Add entity:
        self.model_data["entities"].append(entity)

        # Refresh entity table:
        self.refresh_entity_table()

        # Clear name:
        self.add_entity_name_entry.delete(0, "end")
        self.add_entity_name_entry.focus_set()

        # Model changed:
        self.model_changed_callback(True)

    def clear_entity_editor(self):
        # Clear basic fields:
        self.name_entry.delete(0, "end")
        self.type_combobox.set("")

        # Clear property widgets:
        for widget in self.property_content.winfo_children():
            widget.destroy()

        self.property_entries.clear()

        # Clear relationship widgets:
        for widget in self.relationship_content.winfo_children():
            widget.destroy()

    def delete_entity(self):
        # Get selection:
        selected_item = self.entity_table.selection()

        if not selected_item:
            return

        # Get entity ID:
        item_data = self.entity_table.item(selected_item[0])
        entity_id = item_data["values"][0]

        # Delete entity:
        self.model_data["entities"] = [
            entity
            for entity in self.model_data["entities"]
            if entity["id"] != entity_id
        ]

        # Delete relationships:
        self.model_data["relationships"] = [
            relationship
            for relationship in self.model_data["relationships"]
            if (
                relationship["source"] != entity_id
                and relationship["target"] != entity_id
            )
        ]

        # Refresh entity table:
        self.refresh_entity_table()

        # Clear selection:
        self.selected_entity = None

        # Clear entity editor:
        self.clear_entity_editor()

        # Model changed:
        self.model_changed_callback(True)

    def update_domain(self, selected_domain):
        if not selected_domain:
            return

        self.model_data["domain"] = selected_domain
        self.update_type_selector()
        self.model_changed_callback(True)

    def update_type_selector(self):
        domain = self.model_data["domain"]

        if not domain:
            self.type_combobox["values"] = []
            return

        self.type_combobox["values"] = self.schema.get_entity_types(domain)

    def update_property_editor(self):
        if self.selected_entity is None:
            return

        # Clear existing widgets:
        for widget in self.property_content.winfo_children():
            widget.destroy()

        self.property_entries.clear()

        entity_schema = self.schema.get_entity_schema(
            self.model_data["domain"], self.selected_entity["type"]
        )

        if entity_schema is None:
            return

        properties = entity_schema["properties"]

        # Grid:
        self.property_content.columnconfigure(0, weight=1)
        self.property_content.columnconfigure(1, weight=0)
        self.property_content.columnconfigure(2, weight=0)

        for property_name, description in properties.items():
            # Widgets:
            label = ttk.Label(
                self.property_content, text=property_name.replace("_", " ").title()
            )

            if description["type"] == "number":
                validate_command = (self.register(validate_number), "%P")

                entry = ttk.Entry(
                    self.property_content,
                    width=INPUT_WIDTH,
                    validate="key",
                    validatecommand=validate_command,
                )

            else:
                entry = ttk.Entry(self.property_content, width=INPUT_WIDTH)

            description_label = ttk.Label(
                self.property_content, text=description["description"]
            )
            unit_label = ttk.Label(
                self.property_content, text=description.get("unit", "")
            )
            separator = ttk.Separator(self.property_content, orient="horizontal")
            property_value = self.selected_entity.get("properties", {}).get(
                property_name
            )

            if property_value is not None:
                entry.insert(0, str(property_value))

            # Display widgets:
            row = len(self.property_entries) * 3
            label.grid(
                row=row + 1,
                column=0,
                sticky="w",
            )
            entry.grid(
                row=row + 1,
                column=1,
                sticky="e",
            )
            unit_label.grid(row=row + 1, column=2, sticky="w")
            description_label.grid(
                row=row,
                column=0,
                columnspan=2,
                sticky="w",
            )
            separator.grid(
                row=row + 2,
                column=0,
                columnspan=3,
                sticky="ew",
            )

            # Event binding:
            entry.bind(
                "<FocusOut>",
                lambda event, property_name=property_name, entry=entry: (
                    self.commit_entity_property(property_name, entry)
                ),
            )

            entry.bind(
                "<Return>",
                lambda event, property_name=property_name, entry=entry: (
                    self.commit_entity_property(property_name, entry)
                ),
            )

            self.property_entries[property_name] = entry

    def update_relationship_editor(self):
        # Clear existing relationship widgets:
        for widget in self.relationship_content.winfo_children():
            widget.destroy()

        if self.selected_entity is None:
            return

        entity_schema = self.schema.get_entity_schema(
            self.model_data["domain"], self.selected_entity["type"]
        )

        if entity_schema is None:
            return

        input_min = entity_schema["input_min"]
        input_max = entity_schema["input_max"]
        output_min = entity_schema["output_min"]
        output_max = entity_schema["output_max"]

        input_relationships = self.get_input_relationships()
        output_relationships = self.get_output_relationships()

        self.input_count = max(input_min, len(input_relationships))
        self.output_count = max(output_min, len(output_relationships))

        # Input count:
        # ==========================

        # Widgets:
        self.input_frame = ttk.Frame(self.relationship_content)
        self.input_list_frame = ttk.Frame(self.input_frame)
        input_label = ttk.Label(self.input_frame, text="Number of inputs:")

        # Grid:
        self.input_frame.columnconfigure(0, weight=0)
        self.input_frame.columnconfigure(1, weight=1)

        # Display widgets:
        self.input_frame.grid(row=0, column=0, sticky="nsew")
        self.input_list_frame.grid(row=1, column=0, columnspan=2, sticky="nw")
        input_label.grid(row=0, column=0, sticky="w")

        self.input_count_spinbox = ttk.Spinbox(
            self.input_frame,
            from_=self.input_count,
            to=input_max,
            state="readonly",
            width=SPINBOX_WIDTH,
            command=self.update_relationship_inputs,
        )
        self.input_count_spinbox.set(self.input_count)
        self.input_count_spinbox.grid(row=0, column=1, sticky="w")

        # Output count:
        # ==========================

        # Widgets:
        self.output_frame = ttk.Frame(self.relationship_content)
        self.output_list_frame = ttk.Frame(self.output_frame)
        output_label = ttk.Label(self.output_frame, text="Number of outputs:")

        # Grid:
        self.output_frame.columnconfigure(0, weight=0)
        self.output_frame.columnconfigure(1, weight=1)

        # Display widgets:
        self.output_frame.grid(row=0, column=1, sticky="nsew")
        self.output_list_frame.grid(row=1, column=0, columnspan=2, sticky="nw")
        output_label.grid(row=0, column=0, sticky="w")

        self.output_count_spinbox = ttk.Spinbox(
            self.output_frame,
            from_=self.output_count,
            to=output_max,
            state="readonly",
            width=SPINBOX_WIDTH,
            command=self.update_relationship_outputs,
        )
        self.output_count_spinbox.set(self.output_count)
        self.output_count_spinbox.grid(row=0, column=1, sticky="w")

        # Relationship Frame Layout
        # ==========================

        # Grid:
        self.relationship_content.columnconfigure(0, weight=1, uniform="relationship")
        self.relationship_content.columnconfigure(1, weight=1, uniform="relationship")

        # Create relationships:
        self.update_relationship_inputs()
        self.update_relationship_outputs()

    def has_available_output(self, entity_id, relationship_id=None):
        entity = next(
            entity
            for entity in self.model_data["entities"]
            if entity["id"] == entity_id
        )

        entity_schema = self.schema.get_entity_schema(
            self.model_data["domain"], entity["type"]
        )

        output_relationships = [
            relationship
            for relationship in self.model_data["relationships"]
            if (
                relationship["source"] == entity_id
                and relationship["id"] != relationship_id
            )
        ]

        return len(output_relationships) < entity_schema["output_max"]

    def has_available_input(self, entity_id, relationship_id=None):
        entity = next(
            entity
            for entity in self.model_data["entities"]
            if entity["id"] == entity_id
        )

        entity_schema = self.schema.get_entity_schema(
            self.model_data["domain"], entity["type"]
        )

        input_relationships = [
            relationship
            for relationship in self.model_data["relationships"]
            if (
                relationship["target"] == entity_id
                and relationship["id"] != relationship_id
            )
        ]

        return len(input_relationships) < entity_schema["input_max"]

    def get_allowed_input_entities(self, relationship_id=None):
        selected_type = self.selected_entity["type"]
        selected_entity_id = self.selected_entity["id"]

        domain = self.schema.get_domain(self.model_data["domain"])
        relationship_allowances = domain["relationship_allowances"]

        allowed_source_types = [
            source_type
            for source_type, target_types in relationship_allowances.items()
            if selected_type in target_types
        ]

        return [
            entity
            for entity in self.model_data["entities"]
            if (
                entity["type"] in allowed_source_types
                and entity["id"] != selected_entity_id
                and not (
                    self.selected_entity.get("beginning_of_process")
                    and self.is_main_entity(entity)
                )
                and not entity.get("end_of_process")
                and not any(
                    (
                        (
                            relationship["source"] == entity["id"]
                            and relationship["target"] == selected_entity_id
                        )
                        or (
                            relationship["source"] == selected_entity_id
                            and relationship["target"] == entity["id"]
                        )
                    )
                    and relationship["id"] != relationship_id
                    for relationship in self.model_data["relationships"]
                )
                and self.has_available_output(entity["id"], relationship_id)
            )
        ]

    def get_allowed_output_entities(self, relationship_id=None):
        selected_type = self.selected_entity["type"]
        selected_entity_id = self.selected_entity["id"]

        domain = self.schema.get_domain(self.model_data["domain"])
        relationship_allowances = domain["relationship_allowances"]

        allowed_target_types = relationship_allowances.get(selected_type, [])

        return [
            entity
            for entity in self.model_data["entities"]
            if (
                entity["type"] in allowed_target_types
                and entity["id"] != selected_entity_id
                and not (
                    self.selected_entity.get("end_of_process")
                    and self.is_main_entity(entity)
                )
                and not entity.get("beginning_of_process")
                and not any(
                    (
                        (
                            relationship["source"] == selected_entity_id
                            and relationship["target"] == entity["id"]
                        )
                        or (
                            relationship["source"] == entity["id"]
                            and relationship["target"] == selected_entity_id
                        )
                    )
                    and relationship["id"] != relationship_id
                    for relationship in self.model_data["relationships"]
                )
                and self.has_available_input(entity["id"], relationship_id)
            )
        ]

    def update_relationship_inputs(self):
        # Clear existing input widgets:
        for widget in self.input_list_frame.winfo_children():
            widget.destroy()

        self.input_comboboxes.clear()
        self.input_relationship_ids.clear()

        if self.selected_entity is None:
            return

        input_relationships = self.get_input_relationships()

        minimum_input_count = max(
            self.schema.get_entity_schema(
                self.model_data["domain"], self.selected_entity["type"]
            )["input_min"],
            len(input_relationships),
        )

        input_count = max(int(self.input_count_spinbox.get()), minimum_input_count)

        input_relationships = self.get_input_relationships()

        for index in range(input_count):
            label = ttk.Label(self.input_list_frame, text=f"Input {index + 1}:")
            combobox = ttk.Combobox(
                self.input_list_frame,
                state="readonly",
                width=INPUT_WIDTH,
            )

            self.input_comboboxes.append(combobox)

            if index < len(input_relationships):
                relationship = input_relationships[index]
                relationship_id = relationship["id"]

                self.input_relationship_ids.append(relationship_id)

                source_entity_name = self.get_entity_name(relationship["source"])
                combobox.set(source_entity_name)

            else:
                relationship_id = None
                self.input_relationship_ids.append(None)

            allowed_entities = self.get_allowed_input_entities(relationship_id)
            combobox["values"] = [""] + [entity["name"] for entity in allowed_entities]

            # Event binding:
            combobox.bind("<<ComboboxSelected>>", self.relationship_selected)

            label.grid(row=index + 1, column=0, sticky="w")
            combobox.grid(row=index + 1, column=1, sticky="w")

    def update_relationship_outputs(self):
        # Clear existing output widgets:
        for widget in self.output_list_frame.winfo_children():
            widget.destroy()

        self.output_comboboxes.clear()
        self.output_relationship_ids.clear()

        if self.selected_entity is None:
            return

        output_relationships = self.get_output_relationships()

        minimum_output_count = max(
            self.schema.get_entity_schema(
                self.model_data["domain"], self.selected_entity["type"]
            )["output_min"],
            len(output_relationships),
        )

        output_count = max(int(self.output_count_spinbox.get()), minimum_output_count)

        output_relationships = self.get_output_relationships()

        for index in range(output_count):
            label = ttk.Label(self.output_list_frame, text=f"Output {index + 1}:")
            combobox = ttk.Combobox(
                self.output_list_frame,
                state="readonly",
                width=INPUT_WIDTH,
            )

            self.output_comboboxes.append(combobox)

            if index < len(output_relationships):
                relationship = output_relationships[index]
                relationship_id = relationship["id"]

                self.output_relationship_ids.append(relationship_id)

                target_entity_name = self.get_entity_name(relationship["target"])
                combobox.set(target_entity_name)

            else:
                relationship_id = None
                self.output_relationship_ids.append(None)

            allowed_entities = self.get_allowed_output_entities(relationship_id)
            combobox["values"] = [""] + [entity["name"] for entity in allowed_entities]

            # Event binding:
            combobox.bind("<<ComboboxSelected>>", self.relationship_selected)

            label.grid(row=index, column=0, sticky="w")
            combobox.grid(row=index, column=1, sticky="w")

    def update_entity_editor(self):
        if self.selected_entity is None:
            return

        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, self.selected_entity["name"])
        self.type_combobox.set(self.selected_entity["type"])

        self.beginning_of_process_variable.set(
            self.selected_entity.get("beginning_of_process", False)
        )
        self.end_of_process_variable.set(
            self.selected_entity.get("end_of_process", False)
        )

        self.update_property_editor()
        self.update_relationship_editor()

    def load_model(self):
        try:
            with open(self.model_path, "r") as file:
                self.model_data = json.load(file)

        except Exception as error:
            messagebox.showerror(
                "Model loading error", f"Could not load model:\n{error}"
            )
            self.model_data = None

    def save_model(self):
        with open(self.model_path, "w") as file:
            json.dump(self.model_data, file, indent=4)
        self.model_changed_callback(False)

    def populate_entity_table(self):
        for entity in self.model_data["entities"]:
            input_names = [
                self.get_entity_name(relationship["source"])
                for relationship in self.model_data["relationships"]
                if relationship["target"] == entity["id"]
            ]

            output_names = [
                self.get_entity_name(relationship["target"])
                for relationship in self.model_data["relationships"]
                if relationship["source"] == entity["id"]
            ]

            inputs = ", ".join(input_names)
            outputs = ", ".join(output_names)

            self.entity_table.insert(
                "",
                "end",
                values=(entity["id"], entity["name"], entity["type"], inputs, outputs),
            )

    def refresh_entity_table(self):
        selected_entity_id = None

        selected_item = self.entity_table.selection()

        if selected_item:
            selected_entity_id = self.entity_table.item(selected_item[0])["values"][0]

        self.entity_table.delete(*self.entity_table.get_children())
        self.populate_entity_table()

        if selected_entity_id:
            for item in self.entity_table.get_children():
                if self.entity_table.item(item)["values"][0] == selected_entity_id:
                    self.entity_table.selection_set(item)
                    self.entity_table.focus(item)
                    break

    # ==========================
    # Event Callbacks
    # ==========================

    def update_process_boundary(self):
        if self.selected_entity is None:
            return

        beginning = self.beginning_of_process_variable.get()
        end = self.end_of_process_variable.get()

        if beginning:
            input_relationships = [
                relationship
                for relationship in self.get_input_relationships()
                if self.is_main_entity(
                    next(
                        entity
                        for entity in self.model_data["entities"]
                        if entity["id"] == relationship["source"]
                    )
                )
            ]

            if input_relationships:
                input_descriptions = []

                for relationship in input_relationships:
                    source_entity_name = self.get_entity_name(relationship["source"])
                    input_descriptions.append(source_entity_name)

                messagebox.showwarning(
                    "Invalid Beginning of Process",
                    "This Entity has existing input relationships from: "
                    + ", ".join(input_descriptions)
                    + ". Delete the relationship(s) to mark this Entity "
                    "as the beginning of the process.",
                )

                self.beginning_of_process_variable.set(False)

                return

            self.selected_entity["beginning_of_process"] = True

        else:
            self.selected_entity.pop("beginning_of_process", None)

        if end:
            output_relationships = [
                relationship
                for relationship in self.get_output_relationships()
                if self.is_main_entity(
                    next(
                        entity
                        for entity in self.model_data["entities"]
                        if entity["id"] == relationship["target"]
                    )
                )
            ]

            if output_relationships:
                output_descriptions = []

                for relationship in output_relationships:
                    target_entity_name = self.get_entity_name(relationship["target"])
                    output_descriptions.append(target_entity_name)

                messagebox.showwarning(
                    "Invalid End of Process",
                    "This Entity has existing output relationships to: "
                    + ", ".join(output_descriptions)
                    + ". Delete the relationship(s) to mark this Entity "
                    "as the end of the process.",
                )

                self.end_of_process_variable.set(False)

                return

            self.selected_entity["end_of_process"] = True

        else:
            self.selected_entity.pop("end_of_process", None)

        self.model_changed_callback(True)
        self.update_process_boundary_state()
        self.update_relationship_inputs()
        self.update_relationship_outputs()

    def entity_selected(self, event):
        selected_item = self.entity_table.selection()

        if selected_item:
            item_data = self.entity_table.item(
                selected_item[0]
            )  # The first item (selected_item[0]), because it could allow multiple line selection.
            entity_id = item_data["values"][0]

            for entity in self.model_data["entities"]:
                if entity["id"] == entity_id:
                    self.selected_entity = entity
                    self.update_entity_editor()
                    self.update_process_boundary_state()
                    break

    def get_entity_name(self, entity_id):
        for entity in self.model_data["entities"]:
            if entity["id"] == entity_id:
                return entity["name"]

        return ""

    def get_entity_id(self, entity_name):
        for entity in self.model_data["entities"]:
            if entity["name"] == entity_name:
                return entity["id"]

        return None

    def get_input_relationships(self):
        if self.selected_entity is None:
            return []

        entity_id = self.selected_entity["id"]

        return [
            relationship
            for relationship in self.model_data["relationships"]
            if relationship["target"] == entity_id
        ]

    def get_output_relationships(self):
        if self.selected_entity is None:
            return []

        entity_id = self.selected_entity["id"]

        return [
            relationship
            for relationship in self.model_data["relationships"]
            if relationship["source"] == entity_id
        ]

    def update_entity_name(self, event=None):
        if self.selected_entity is None:
            return

        new_name = self.name_entry.get()

        if self.selected_entity["name"] == new_name:
            return

        if not self.is_entity_name_unique(self.selected_entity, new_name):
            messagebox.showwarning("Duplicate name", "Cannot use the same name.")
            self.name_entry.delete(0, "end")
            self.name_entry.insert(0, self.selected_entity["name"])
            return

        self.selected_entity["name"] = new_name

        selected_item = self.entity_table.selection()

        if selected_item:
            self.refresh_entity_table()

        self.model_changed_callback(True)

    def update_entity_type(self, event=None):
        if self.selected_entity is None:
            return

        new_type = self.type_combobox.get()

        if self.selected_entity["type"] == new_type:
            return

        self.selected_entity["type"] = new_type

        selected_item = self.entity_table.selection()

        if selected_item:
            self.refresh_entity_table()

        self.update_property_editor()
        self.update_relationship_editor()
        self.model_changed_callback(True)

    def commit_entity_property(self, property_name, entry):
        self.update_entity_property(property_name)

        entry.delete(0, "end")
        entry.insert(0, str(self.selected_entity["properties"].get(property_name, "")))

    def update_entity_property(self, property_name, event=None):
        if self.selected_entity is None:
            return

        new_value = self.property_entries[property_name].get()

        property_schema = self.schema.get_entity_schema(
            self.model_data["domain"], self.selected_entity["type"]
        )["properties"][property_name]

        new_value = convert_property_value(new_value, property_schema["type"])

        if self.selected_entity["properties"].get(property_name) == new_value:
            return

        self.selected_entity["properties"][property_name] = new_value
        self.model_changed_callback(True)

    def relationship_selected(self, event):
        entity_name = event.widget.get()

        if self.selected_entity is None:
            return

        selected_entity_id = self.selected_entity["id"]

        if event.widget in self.input_comboboxes:
            index = self.input_comboboxes.index(event.widget)
            relationship_id = self.input_relationship_ids[index]

            if not entity_name:
                if relationship_id is not None:
                    self.model_data["relationships"] = [
                        relationship
                        for relationship in self.model_data["relationships"]
                        if relationship["id"] != relationship_id
                    ]

                    self.input_relationship_ids[index] = None
                    self.refresh_entity_table()
                    self.model_changed_callback(True)

                return

            entity_id = self.get_entity_id(entity_name)

            if entity_id is None:
                return

            if relationship_id is None:
                relationship = {
                    "id": self.generate_relationship_id(),
                    "source": entity_id,
                    "target": selected_entity_id,
                }

                self.model_data["relationships"].append(relationship)
                self.input_relationship_ids[index] = relationship["id"]

            else:
                relationship = next(
                    relationship
                    for relationship in self.model_data["relationships"]
                    if relationship["id"] == relationship_id
                )

                relationship["source"] = entity_id

        elif event.widget in self.output_comboboxes:
            index = self.output_comboboxes.index(event.widget)
            relationship_id = self.output_relationship_ids[index]

            if not entity_name:
                if relationship_id is not None:
                    self.model_data["relationships"] = [
                        relationship
                        for relationship in self.model_data["relationships"]
                        if relationship["id"] != relationship_id
                    ]

                    self.output_relationship_ids[index] = None
                    self.refresh_entity_table()
                    self.model_changed_callback(True)

                return

            entity_id = self.get_entity_id(entity_name)

            if entity_id is None:
                return

            if relationship_id is None:
                relationship = {
                    "id": self.generate_relationship_id(),
                    "source": selected_entity_id,
                    "target": entity_id,
                }

                self.model_data["relationships"].append(relationship)
                self.output_relationship_ids[index] = relationship["id"]

            else:
                relationship = next(
                    relationship
                    for relationship in self.model_data["relationships"]
                    if relationship["id"] == relationship_id
                )

                relationship["target"] = entity_id

        else:
            return

        self.refresh_entity_table()
        self.model_changed_callback(True)

    # ==========================
    # Structure Tab
    # ==========================

    def create_structure_tab(self):
        # Grid:
        self.structure_tab.rowconfigure(0, weight=1)
        self.structure_tab.rowconfigure(1, weight=1)
        self.structure_tab.columnconfigure(0, weight=1)

        # Entity Table
        # ==========================

        # Frame widget:
        self.entity_table_frame = ttk.LabelFrame(
            self.structure_tab,
            text="Entities",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Grid:
        self.entity_table_frame.rowconfigure(0, weight=1)
        self.entity_table_frame.columnconfigure(0, weight=1)

        # Child widgets:
        self.entity_table = ttk.Treeview(
            self.entity_table_frame,
            columns=("id", "name", "type", "inputs", "outputs"),
            show="headings",
        )
        self.entity_table_scrollbar = ttk.Scrollbar(
            self.entity_table_frame, orient="vertical", command=self.entity_table.yview
        )
        self.entity_table.configure(yscrollcommand=self.entity_table_scrollbar.set)
        self.entity_button_frame = ttk.Frame(self.entity_table_frame)
        self.add_entity_button = ttk.Button(
            self.entity_button_frame,
            text="Add",
            width=BUTTON_WIDTH,
            command=self.add_entity,
        )
        self.delete_entity_button = ttk.Button(
            self.entity_button_frame,
            text="Delete",
            width=BUTTON_WIDTH,
            command=self.delete_entity,
        )

        # Event binding:
        self.entity_table.bind("<<TreeviewSelect>>", self.entity_selected)

        # Column headings:
        self.entity_table.heading("id", text="ID")
        self.entity_table.heading("name", text="Name")
        self.entity_table.heading("type", text="Type")
        self.entity_table.heading("inputs", text="Inputs")
        self.entity_table.heading("outputs", text="Outputs")

        self.entity_table.column("id", width=50, stretch=False)
        self.entity_table.column("name", width=110)
        self.entity_table.column("type", width=110)
        self.entity_table.column("inputs", width=250)
        self.entity_table.column("outputs", width=250)

        # Display frame widget:
        self.entity_table_frame.grid(row=0, column=0, sticky="nsew")

        # Display child widgets:
        self.entity_table.grid(row=0, column=0, sticky="nsew")
        self.entity_table_scrollbar.grid(row=0, column=1, sticky="ns")
        self.entity_button_frame.grid(row=1, column=0, columnspan=2, sticky="w")
        self.add_entity_button.grid(row=0, column=0)
        self.delete_entity_button.grid(row=0, column=1)

        # Editor
        # ==========================

        # Frame widget:
        self.editor = ttk.LabelFrame(
            self.structure_tab,
            text="Editor",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Grid:
        self.editor.rowconfigure(1, weight=1)
        self.editor.columnconfigure(0, weight=1)
        self.editor.columnconfigure(1, weight=1)

        # Editor Sections
        # ==========================

        # Section frames:
        self.basic_editor = ttk.Frame(self.editor)
        self.property_editor = ttk.LabelFrame(
            self.editor,
            text="Properties",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )
        self.relationship_editor = ttk.LabelFrame(
            self.editor,
            text="Relationships",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )
        self.button_frame = ttk.Frame(self.editor)

        # Grid (property editor):
        self.property_editor.rowconfigure(0, weight=1)
        self.property_editor.columnconfigure(0, weight=1)

        # Grid (button frame):
        self.button_frame.columnconfigure(0, weight=1)

        # Grid (relationship editor):
        self.relationship_editor.rowconfigure(0, weight=1)
        self.relationship_editor.columnconfigure(0, weight=1)

        # Grid (basic editor):
        self.basic_editor.columnconfigure(0, weight=1, uniform="basic")
        self.basic_editor.columnconfigure(1, weight=1, uniform="basic")
        self.basic_editor.columnconfigure(2, weight=1, uniform="basic")
        self.basic_editor.columnconfigure(3, weight=1, uniform="basic")

        # Basic editor widgets:
        self.name_editor = ttk.LabelFrame(
            self.basic_editor,
            text="Name",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )
        self.type_editor = ttk.LabelFrame(
            self.basic_editor,
            text="Type",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )
        self.beginning_of_process_editor = ttk.LabelFrame(
            self.basic_editor,
            text="Beginning of Process",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )
        self.end_of_process_editor = ttk.LabelFrame(
            self.basic_editor,
            text="End of Process",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Grid (name editor):
        self.name_editor.columnconfigure(0, weight=1)

        # Grid (type editor):
        self.type_editor.columnconfigure(0, weight=1)

        # Grid (beginning of process editor):
        self.beginning_of_process_editor.columnconfigure(0, weight=1)

        # Grid (beginning of process editor):
        self.end_of_process_editor.columnconfigure(0, weight=1)

        # Property editor widgets:
        self.property_canvas = tk.Canvas(self.property_editor)
        self.property_scrollbar = ttk.Scrollbar(
            self.property_editor, orient="vertical", command=self.property_canvas.yview
        )
        self.property_content = ttk.Frame(self.property_canvas)
        self.property_canvas.configure(yscrollcommand=self.property_scrollbar.set)

        # Property content:
        self.property_window = self.property_canvas.create_window(
            (0, 0), window=self.property_content, anchor="nw"
        )

        # Event binding:
        self.property_content.bind(
            "<Configure>",
            lambda event: self.property_canvas.configure(
                scrollregion=self.property_canvas.bbox("all")
            ),
        )
        self.property_canvas.bind(
            "<Configure>",
            lambda event: self.property_canvas.itemconfigure(
                self.property_window, width=event.width
            ),
        )

        # Display basic editor widgets:
        self.name_editor.grid(row=0, column=0, sticky="nsew")
        self.type_editor.grid(row=0, column=1, sticky="nsew")
        self.beginning_of_process_editor.grid(row=0, column=2, sticky="nsew")
        self.end_of_process_editor.grid(row=0, column=3, sticky="nsew")

        # Display property editor widgets:
        self.property_canvas.grid(row=0, column=0, sticky="nsew")
        self.property_scrollbar.grid(row=0, column=1, sticky="ns")

        # Relationship editor widgets:
        self.relationship_canvas = tk.Canvas(self.relationship_editor)
        self.relationship_scrollbar = ttk.Scrollbar(
            self.relationship_editor,
            orient="vertical",
            command=self.relationship_canvas.yview,
        )
        self.relationship_content = ttk.Frame(self.relationship_canvas)
        self.relationship_canvas.configure(
            yscrollcommand=self.relationship_scrollbar.set
        )

        # Relationship content:
        self.relationship_window = self.relationship_canvas.create_window(
            (0, 0), window=self.relationship_content, anchor="nw"
        )

        # Event binding:
        self.relationship_content.bind(
            "<Configure>",
            lambda event: self.relationship_canvas.configure(
                scrollregion=self.relationship_canvas.bbox("all")
            ),
        )
        self.relationship_canvas.bind(
            "<Configure>",
            lambda event: self.relationship_canvas.itemconfigure(
                self.relationship_window, width=event.width
            ),
        )

        # Display relationship editor widgets:
        self.relationship_canvas.grid(row=0, column=0, sticky="nsew")
        self.relationship_scrollbar.grid(row=0, column=1, sticky="ns")

        # Display section frames:
        self.basic_editor.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.property_editor.grid(row=1, column=0, sticky="nsew")
        self.relationship_editor.grid(row=1, column=1, sticky="nsew")
        self.button_frame.grid(row=2, column=0, columnspan=2, sticky="ew")

        # Process boundary variables:
        self.beginning_of_process_variable = tk.BooleanVar()
        self.end_of_process_variable = tk.BooleanVar()

        # Name, type, beginning of process, end of process editor widgets:
        self.name_entry = ttk.Entry(self.name_editor, width=INPUT_WIDTH)
        self.type_combobox = ttk.Combobox(
            self.type_editor, state="readonly", width=INPUT_WIDTH
        )
        self.beginning_of_process_checkbutton = ttk.Checkbutton(
            self.beginning_of_process_editor,
            text="Marks the beginning of the process.",
            variable=self.beginning_of_process_variable,
            command=self.update_process_boundary,
        )
        self.end_of_process_checkbutton = ttk.Checkbutton(
            self.end_of_process_editor,
            text="Marks the end of the process.",
            variable=self.end_of_process_variable,
            command=self.update_process_boundary,
        )

        # Button frame widgets:
        self.save_model_button = ttk.Button(
            self.button_frame, text="Save", width=BUTTON_WIDTH, command=self.save_model
        )
        self.flow_objects_button = ttk.Button(
            self.button_frame,
            text="Flow Objects",
            width=BUTTON_WIDTH,
            command=self.open_flow_object_editor,
        )

        # Event binding:
        self.name_entry.bind("<FocusOut>", self.update_entity_name)
        self.name_entry.bind("<Return>", self.update_entity_name)
        self.type_combobox.bind("<<ComboboxSelected>>", self.update_entity_type)

        # Display frame widget:
        self.editor.grid(row=1, column=0, sticky="nsew")

        # Display name, type, beginning of process, end of process editor widgets:
        self.name_entry.grid(row=0, column=0, sticky="ew")
        self.type_combobox.grid(row=0, column=0, sticky="ew")
        self.beginning_of_process_checkbutton.grid(row=0, column=0, sticky="w")
        self.end_of_process_checkbutton.grid(row=0, column=0, sticky="w")

        # Display button frame widgets:
        self.save_model_button.grid(row=0, column=1, sticky="e")
        self.flow_objects_button.grid(row=0, column=0, sticky="e")

    # ==========================
    # Visualization Tab
    # ==========================

    def create_visualization_tab(self):
        # Grid:
        self.visualization_tab.rowconfigure(0, weight=1)
        self.visualization_tab.columnconfigure(0, weight=1)

        # Canvas
        # ==========================

        # Widgets:
        self.visualization_canvas = tk.Canvas(self.visualization_tab)
        self.visualization_content_frame = ttk.Frame(self.visualization_canvas)
        self.visualization_horizontal_scrollbar = ttk.Scrollbar(
            self.visualization_tab,
            orient="horizontal",
            command=self.visualization_canvas.xview,
        )
        self.visualization_vertical_scrollbar = ttk.Scrollbar(
            self.visualization_tab,
            orient="vertical",
            command=self.visualization_canvas.yview,
        )

        # Configuration:
        self.visualization_canvas.configure(
            xscrollcommand=self.visualization_horizontal_scrollbar.set,
            yscrollcommand=self.visualization_vertical_scrollbar.set,
        )

        # Display widgets:
        self.visualization_canvas.grid(row=0, column=0, sticky="nsew")
        self.visualization_horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        self.visualization_vertical_scrollbar.grid(row=0, column=1, sticky="ns")

        # Embed content frame in canvas:
        self.visualization_window = self.visualization_canvas.create_window(
            0, 0, window=self.visualization_content_frame, anchor="nw"
        )

        # Event binding:
        self.visualization_content_frame.bind(
            "<Configure>",
            lambda event: self.visualization_canvas.configure(
                scrollregion=self.visualization_canvas.bbox("all")
            ),
        )

    # ==========================
    # Model Editor Page
    # ==========================

    def create_widgets(self):
        # Grid:
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # Main Frame
        # ==========================

        # Frame widget:
        self.main_frame = ttk.Frame(self)

        # Grid:
        self.main_frame.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=1)

        # Display frame widget:
        self.main_frame.grid(row=0, column=0, sticky="nsew")

        # Notebook
        # ==========================

        # Widget:
        self.notebook = ttk.Notebook(self.main_frame, padding=0)

        # Tabs
        # ==========================

        # Child widgets:
        self.structure_tab = ttk.Frame(self.notebook)
        self.visualization_tab = ttk.Frame(self.notebook)
        self.rules_tab = ttk.Frame(self.notebook)

        # Configuration:
        self.notebook.add(self.structure_tab, text="Structure")
        self.notebook.add(self.visualization_tab, text="Visualization")
        self.notebook.add(self.rules_tab, text="Rules")

        # Display widgets:
        self.notebook.grid(row=0, column=0, sticky="nsew")

        # Create tab content:
        self.create_structure_tab()
        self.create_visualization_tab()

        # Populate entity table:
        self.populate_entity_table()

        # Update type selector:
        self.update_type_selector()
