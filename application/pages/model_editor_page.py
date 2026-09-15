import copy
import json
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from dese.application.pages.flow_object_editor import FlowObjectEditor
from dese.constants import (
    BUTTON_WIDTH,
    CURRENT_SCHEMA_VERSION,
    ENTITY_ID_COLUMN_WIDTH,
    ENTITY_INPUTS_COLUMN_WIDTH,
    ENTITY_NAME_COLUMN_WIDTH,
    ENTITY_OUTPUTS_COLUMN_WIDTH,
    ENTITY_ROLE_COLUMN_WIDTH,
    INPUT_WIDTH,
    MAIN_HIERARCHY_ROLE,
    NUMBER_PROPERTY_TYPE,
    PAD,
    PROPERTY_ROW_HEIGHT,
    SPINBOX_WIDTH,
)
from dese.core.model import (
    find_decision_points,
    get_failure_eligible_entity_ids,
    get_failure_parameter,
    get_maintenance_dispatch_priority,
    get_maintenance_parameter,
    get_maintenance_resource_parameter,
    get_output_relationships,
    get_routing_condition_owner,
    get_routing_scope_candidates,
    get_routing_scope_label,
    get_routing_scope_values,
    move_routing_rule_output,
    remove_entity_from_rules,
    set_failure_parameter,
    set_maintenance_dispatch_priority,
    set_maintenance_parameter,
    set_maintenance_resource_parameter,
    set_routing_condition_owner,
)
from dese.utils import (
    bind_canvas_mousewheel,
    convert_property_value,
    generate_id,
    validate_number,
)


class ModelEditorPage(ttk.Frame):
    """Structure/Visualization/Rules tabs for a single model: owns model_data and
    the schema-driven entity, property and relationship editors built on top of it."""

    def __init__(self, parent, model_path, schema, model_changed_callback):
        super().__init__(parent)
        self.model_path = model_path
        self.schema = schema
        self.model_changed_callback = model_changed_callback
        self.model_data = None
        self.saved_model_data = None
        self.selected_entity = None
        self.input_count = 0
        self.output_count = 0
        self.property_entries = {}
        self.input_comboboxes = []
        self.output_comboboxes = []
        self.input_relationship_ids = []
        self.output_relationship_ids = []
        self.load_model()

        if self.model_data is not None:
            self.create_widgets()

    # ==========================
    # Methods
    # ==========================

    def get_domain(self):
        return self.model_data["domain"]

    def move_entity_up(self):
        selected_item = self.entity_table.selection()

        if not selected_item:
            return

        item = selected_item[0]
        index = self.entity_table.index(item)

        if index == 0:
            return

        self.model_data["entities"][index - 1], self.model_data["entities"][index] = (
            self.model_data["entities"][index],
            self.model_data["entities"][index - 1],
        )

        self.refresh_entity_table()
        self.entity_table.selection_set(self.entity_table.get_children()[index - 1])

        self.update_model_changed_state()

    def move_entity_down(self):
        selected_item = self.entity_table.selection()

        if not selected_item:
            return

        item = selected_item[0]
        index = self.entity_table.index(item)
        last_index = len(self.model_data["entities"]) - 1

        if index == last_index:
            return

        self.model_data["entities"][index], self.model_data["entities"][index + 1] = (
            self.model_data["entities"][index + 1],
            self.model_data["entities"][index],
        )

        self.refresh_entity_table()
        self.entity_table.selection_set(self.entity_table.get_children()[index + 1])

        self.update_model_changed_state()

    def update_editor_state(self):
        # Every model now has a domain from creation onward (no domain
        # selector to wait for), so the editor controls are always enabled.
        self.add_entity_button.config(state="normal")
        self.delete_entity_button.config(state="normal")
        self.move_entity_up_button.config(state="normal")
        self.move_entity_down_button.config(state="normal")

        self.name_entry.config(state="normal")
        self.type_combobox.config(state="normal")
        self.save_model_button.config(state="normal")
        self.beginning_of_process_checkbutton.config(state="normal")
        self.end_of_process_checkbutton.config(state="normal")
        self.flow_objects_button.config(state="normal")

    def update_model_changed_state(self):
        # Comparing full snapshots (instead of an explicit dirty flag) avoids
        # missing a `set_model_changed(True)` call after any of the many places
        # that mutate model_data in place.
        self.model_changed_callback(self.model_data != self.saved_model_data)

    def is_main_entity(self, entity):
        entity_schema = self.schema.get_entity_schema(
            self.model_data["domain"], entity["type"]
        )

        if entity_schema is None:
            return False

        return entity_schema["hierarchy"]["role"] == MAIN_HIERARCHY_ROLE

    def open_flow_object_editor(self):
        FlowObjectEditor(
            self,
            self.model_data,
            self.schema,
            self.update_model_changed_state,
            self.save_model,
        )

    def generate_entity_id(self):
        existing_ids = [entity["id"] for entity in self.model_data["entities"]]

        return generate_id(existing_ids, "E")

    def is_entity_name_unique(self, entity, name):
        return all(
            other_entity is entity or other_entity["name"] != name
            for other_entity in self.model_data["entities"]
        )

    def generate_relationship_id(self):
        existing_ids = [
            relationship["id"] for relationship in self.model_data["relationships"]
        ]

        return generate_id(existing_ids, "R")

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

        # Beginning of process:
        if beginning_entity is not None:
            if self.selected_entity is beginning_entity:
                self.beginning_of_process_checkbutton.config(
                    state="normal", text="Marks the beginning of the process."
                )

            else:
                self.beginning_of_process_checkbutton.config(
                    state="disabled", text=f"Selected: {beginning_entity['name']}"
                )

        elif self.selected_entity is not None and not self.is_main_entity(
            self.selected_entity
        ):
            self.beginning_of_process_checkbutton.config(
                state="disabled", text="Only main entities can be selected."
            )

        else:
            self.beginning_of_process_checkbutton.config(
                state="normal", text="Marks the beginning of the process."
            )

        # End of process:
        if end_entity is not None:
            if self.selected_entity is end_entity:
                self.end_of_process_checkbutton.config(
                    state="normal", text="Marks the end of the process."
                )

            else:
                self.end_of_process_checkbutton.config(
                    state="disabled", text=f"Selected: {end_entity['name']}"
                )

        elif self.selected_entity is not None and not self.is_main_entity(
            self.selected_entity
        ):
            self.end_of_process_checkbutton.config(
                state="disabled", text="Only main entities can be selected."
            )

        else:
            self.end_of_process_checkbutton.config(
                state="normal", text="Marks the end of the process."
            )

    # ==========================
    # Add Entity Window
    # ==========================

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
        self.update_model_changed_state()

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

        # Delete rules referencing the entity (as "at" or as a Routing
        # output target) — otherwise they'd linger as dead data, or
        # resurface unexpectedly (e.g. a Routing rule reappearing if a
        # decision point regains a second output later).
        remove_entity_from_rules(self.model_data, entity_id)

        # Refresh entity table:
        self.refresh_entity_table()

        # Clear selection:
        self.selected_entity = None

        # Clear entity editor:
        self.clear_entity_editor()

        # Model changed:
        self.update_model_changed_state()

    def update_type_selector(self):
        self.type_combobox["values"] = self.schema.get_entity_types(
            self.model_data["domain"]
        )

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

            if description["type"] == NUMBER_PROPERTY_TYPE:
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
            row = len(self.property_entries) * PROPERTY_ROW_HEIGHT
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

        bind_canvas_mousewheel(self.property_canvas)

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

        bind_canvas_mousewheel(self.relationship_canvas)

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
        # A beginning-of-process entity marks the single entry point of the main
        # process chain, so it may not receive an input from another main entity;
        # symmetrically, an end-of-process entity may not feed a main entity as
        # output. This keeps exactly one entry/exit point per process.
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
                and not (
                    self.is_main_entity(self.selected_entity)
                    and entity.get("end_of_process")
                )
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
                and not (
                    self.is_main_entity(self.selected_entity)
                    and entity.get("beginning_of_process")
                )
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

            if self.model_data.get("schema_version") != CURRENT_SCHEMA_VERSION:
                raise ValueError(
                    "This model was created with an older or incompatible "
                    "schema version and cannot be opened."
                )

            # There is no domain selector anymore — every model uses the
            # schema's default (Production) domain. Fall back to it for any
            # model file that predates this default (its "domain" is null).
            if not self.model_data.get("domain"):
                self.model_data["domain"] = self.schema.get_domains()[0]

            self.saved_model_data = copy.deepcopy(self.model_data)

        except Exception as error:
            messagebox.showerror(
                "Model loading error", f"Could not load model:\n{error}"
            )
            self.model_data = None

    def save_model(self):
        with open(self.model_path, "w") as file:
            json.dump(self.model_data, file, indent=4)

        self.saved_model_data = copy.deepcopy(self.model_data)
        self.update_model_changed_state()

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
            is_main = self.is_main_entity(entity)
            role = "Main" if is_main else "Secondary"

            self.entity_table.insert(
                "",
                "end",
                values=(
                    entity["id"],
                    entity["name"],
                    entity["type"],
                    role,
                    inputs,
                    outputs,
                ),
                tags=("main",) if is_main else (),
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

        self.update_process_boundary_state()
        self.update_relationship_inputs()
        self.update_relationship_outputs()
        self.update_model_changed_state()

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

        self.update_model_changed_state()

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
        self.update_model_changed_state()

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
        self.update_model_changed_state()

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
                    self.update_model_changed_state()

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

                old_source_id = relationship["source"]
                relationship["source"] = entity_id

                # If the old source no longer reaches this Entity at all,
                # its Routing conditions for this target should follow
                # onto the new source rather than being stranded on a
                # connection that's gone.
                old_source_still_connected = any(
                    other["source"] == old_source_id
                    and other["target"] == selected_entity_id
                    for other in self.model_data["relationships"]
                )

                if not old_source_still_connected:
                    move_routing_rule_output(
                        self.model_data,
                        old_source_id,
                        selected_entity_id,
                        entity_id,
                        selected_entity_id,
                    )

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
                    self.update_model_changed_state()

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

                old_target_id = relationship["target"]
                relationship["target"] = entity_id

                # If this decision point no longer reaches the old target
                # at all, its Routing conditions for that output should
                # follow onto the new target rather than being stranded on
                # a connection that's gone.
                old_target_still_connected = any(
                    other["source"] == selected_entity_id
                    and other["target"] == old_target_id
                    for other in self.model_data["relationships"]
                )

                if not old_target_still_connected:
                    move_routing_rule_output(
                        self.model_data,
                        selected_entity_id,
                        old_target_id,
                        selected_entity_id,
                        entity_id,
                    )

        else:
            return

        self.refresh_entity_table()
        self.update_model_changed_state()

    # ==========================
    # Structure Tab
    # ==========================

    def measure_column_width(self, texts, font, padding=20):
        return max(font.measure(text) for text in texts) + padding

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
            columns=("id", "name", "type", "role", "inputs", "outputs"),
            show="headings",
        )

        # Bold the name of main entities to set them visually apart from
        # secondary ones (in addition to the explicit Role column).
        default_font = tkfont.nametofont("TkDefaultFont")
        bold_font = default_font.copy()
        bold_font.configure(weight="bold")
        self.entity_table.tag_configure("main", font=bold_font)

        # Size the Type column to the longest entity type name actually
        # defined in the schema, rather than a guessed fixed width.
        type_column_width = self.measure_column_width(
            self.schema.get_entity_types(self.model_data["domain"]) + ["Type"],
            default_font,
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
        self.move_entity_up_button = ttk.Button(
            self.entity_button_frame,
            text="Move up ↑",
            width=BUTTON_WIDTH,
            command=self.move_entity_up,
        )
        self.move_entity_down_button = ttk.Button(
            self.entity_button_frame,
            text="Move down ↓",
            width=BUTTON_WIDTH,
            command=self.move_entity_down,
        )

        # Event binding:
        self.entity_table.bind("<<TreeviewSelect>>", self.entity_selected)

        # Column headings:
        self.entity_table.heading("id", text="ID")
        self.entity_table.heading("name", text="Name")
        self.entity_table.heading("type", text="Type")
        self.entity_table.heading("role", text="Role")
        self.entity_table.heading("inputs", text="Inputs")
        self.entity_table.heading("outputs", text="Outputs")

        self.entity_table.column("id", width=ENTITY_ID_COLUMN_WIDTH, stretch=False)
        self.entity_table.column("name", width=ENTITY_NAME_COLUMN_WIDTH)
        self.entity_table.column("type", width=type_column_width, stretch=False)
        self.entity_table.column("role", width=ENTITY_ROLE_COLUMN_WIDTH, stretch=False)
        self.entity_table.column("inputs", width=ENTITY_INPUTS_COLUMN_WIDTH)
        self.entity_table.column("outputs", width=ENTITY_OUTPUTS_COLUMN_WIDTH)

        # Display frame widget:
        self.entity_table_frame.grid(row=0, column=0, sticky="nsew")

        # Display child widgets:
        self.entity_table.grid(row=0, column=0, sticky="nsew")
        self.entity_table_scrollbar.grid(row=0, column=1, sticky="ns")
        self.entity_button_frame.grid(row=1, column=0, columnspan=2, sticky="w")
        self.add_entity_button.grid(row=0, column=0)
        self.delete_entity_button.grid(row=0, column=1)
        self.move_entity_up_button.grid(row=0, column=2)
        self.move_entity_down_button.grid(row=0, column=3)

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

        # Grid (property editor):
        self.property_editor.rowconfigure(0, weight=1)
        self.property_editor.columnconfigure(0, weight=1)

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

        # Grid (end of process editor):
        self.end_of_process_editor.columnconfigure(0, weight=1)

        # Property editor widgets:
        self.property_canvas = tk.Canvas(self.property_editor)
        self.property_scrollbar = ttk.Scrollbar(
            self.property_editor, orient="vertical", command=self.property_canvas.yview
        )
        self.property_content = ttk.Frame(self.property_canvas)
        self.property_canvas.configure(yscrollcommand=self.property_scrollbar.set)
        bind_canvas_mousewheel(self.property_canvas)

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
        bind_canvas_mousewheel(self.relationship_canvas)

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
            variable=self.beginning_of_process_variable,
            command=self.update_process_boundary,
        )
        self.end_of_process_checkbutton = ttk.Checkbutton(
            self.end_of_process_editor,
            variable=self.end_of_process_variable,
            command=self.update_process_boundary,
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
        bind_canvas_mousewheel(self.visualization_canvas)

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
    # Rules Tab
    # ==========================

    def on_tab_changed(self, event=None):
        # The Rules tab's sections can go stale if entities/relationships
        # change on the Structure tab — refresh them whenever the user
        # actually switches to the Rules tab, rather than hooking every
        # entity/relationship mutation site.
        if self.notebook.select() == str(self.rules_tab):
            self.refresh_rules_tab()

    def refresh_rules_tab(self):
        # Rebuilding destroys and recreates every widget below, which
        # briefly collapses the scrollable content to near-zero height —
        # the canvas clamps its scroll position to the top for that instant
        # and doesn't return on its own once the content regrows. Save and
        # restore it around the rebuild so a mid-scroll selection doesn't
        # visibly jump the page back to the top.
        scroll_position = self.rules_canvas.yview()[0]

        self.update_routing_frame()
        self.update_failure_frame()
        self.update_maintenance_frame()

        bind_canvas_mousewheel(self.rules_canvas)

        self.rules_canvas.update_idletasks()
        self.rules_canvas.yview_moveto(scroll_position)

    def create_rules_tab(self):
        # Grid:
        self.rules_tab.rowconfigure(0, weight=1)
        self.rules_tab.columnconfigure(0, weight=1)

        # Scrollable content, same pattern as the Structure tab's property
        # editor — Routing/Failure/Maintenance can together exceed the
        # visible tab height once a model has several entities.
        self.rules_canvas = tk.Canvas(self.rules_tab)
        self.rules_scrollbar = ttk.Scrollbar(
            self.rules_tab, orient="vertical", command=self.rules_canvas.yview
        )
        self.rules_content = ttk.Frame(self.rules_canvas)
        self.rules_canvas.configure(yscrollcommand=self.rules_scrollbar.set)
        bind_canvas_mousewheel(self.rules_canvas)

        self.rules_window = self.rules_canvas.create_window(
            (0, 0), window=self.rules_content, anchor="nw"
        )

        # Event binding:
        self.rules_content.bind(
            "<Configure>",
            lambda event: self.rules_canvas.configure(
                scrollregion=self.rules_canvas.bbox("all")
            ),
        )
        self.rules_canvas.bind(
            "<Configure>",
            lambda event: self.rules_canvas.itemconfigure(
                self.rules_window, width=event.width
            ),
        )

        # Display widgets:
        self.rules_canvas.grid(row=0, column=0, sticky="nsew")
        self.rules_scrollbar.grid(row=0, column=1, sticky="ns")

        # Grid (content):
        self.rules_content.columnconfigure(0, weight=1)

        # Routing Frame
        # ==========================

        # Frame widget:
        self.routing_frame = ttk.LabelFrame(
            self.rules_content,
            text="Routing",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Grid:
        # Each decision point gets its own nested "AT ..." LabelFrame
        # (added in update_routing_frame) — column 0 stretches so those
        # fill the Routing frame's full width.
        self.routing_frame.columnconfigure(0, weight=1)

        # Display frame widget:
        self.routing_frame.grid(row=0, column=0, sticky="new")

        # Failure Frame
        # ==========================
        # The unplanned, stochastic side of entity breakdown — what happens
        # to the Entity. The planned countermeasure lives in Maintenance
        # below.

        # Frame widget:
        self.failure_frame = ttk.LabelFrame(
            self.rules_content,
            text="Failure",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Grid:
        # Each Entity gets its own nested "AT ..." LabelFrame (added in
        # update_failure_frame) — column 0 stretches so those fill the
        # Failure frame's full width.
        self.failure_frame.columnconfigure(0, weight=1)

        # Display frame widget:
        self.failure_frame.grid(row=1, column=0, sticky="new")

        # Maintenance Frame
        # ==========================
        # The planned countermeasure side: Plan is the per-Entity timing/
        # duration policy, Resource is the shared capacity/dispatch setup
        # both Plan and unplanned Failure repairs compete for.

        # Frame widget:
        self.maintenance_frame = ttk.LabelFrame(
            self.rules_content,
            text="Maintenance",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Grid:
        self.maintenance_frame.columnconfigure(0, weight=1)

        # Display frame widget:
        self.maintenance_frame.grid(row=2, column=0, sticky="new")

        # Child widgets:
        self.maintenance_plan_frame = ttk.LabelFrame(
            self.maintenance_frame,
            text="Plan",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )
        self.maintenance_resource_frame = ttk.LabelFrame(
            self.maintenance_frame,
            text="Resource",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Grid (child widgets):
        # Plan gets a nested "AT ..." LabelFrame per Entity (column 0
        # stretches for those); Resource isn't per-Entity, so it keeps its
        # own trailing spacer column for the Capacity/Dispatch Priority rows.
        self.maintenance_plan_frame.columnconfigure(0, weight=1)
        self.maintenance_resource_frame.columnconfigure(3, weight=1)

        # Display child widgets:
        self.maintenance_plan_frame.grid(row=0, column=0, sticky="new")
        self.maintenance_resource_frame.grid(row=1, column=0, sticky="new")

        # Content:
        self.refresh_rules_tab()

    def update_routing_frame(self):
        # Clear existing widgets:
        for widget in self.routing_frame.winfo_children():
            widget.destroy()

        decision_point_ids = find_decision_points(self.model_data, self.schema)

        if not decision_point_ids:
            no_decision_points_label = ttk.Label(
                self.routing_frame,
                text="No decision points found in this model yet.",
            )
            no_decision_points_label.grid(row=0, column=0, sticky="w")
            return

        for decision_point_index, entity_id in enumerate(decision_point_ids):
            entity = next(
                entity for entity in self.model_data["entities"] if entity["id"] == entity_id
            )

            # An Entity's own state is always a candidate; a Flow Object
            # state is only a candidate where this Entity type actually has
            # a way to read it (see get_routing_scope_candidates). Each
            # candidate is one row of the matrix below; each current output
            # is one column, plus a leading "unassigned" column.
            scope_candidates = get_routing_scope_candidates(entity, self.model_data, self.schema)

            target_ids = [
                relationship["target"]
                for relationship in get_output_relationships(entity_id, self.model_data)
            ]

            # Widgets:
            entity_frame = ttk.LabelFrame(
                self.routing_frame,
                text=f'AT "{self.get_entity_name(entity_id)}"',
                style="DESE.Section.TLabelframe",
                padding=PAD,
            )

            # Grid:
            # A fixed column 0 width keeps the checkbox columns justified
            # at the same x position on every row, regardless of which
            # value's label is currently showing — same trick as the
            # Failure/Maintenance sections. It has to fit the longest text
            # that starts there, which includes the scope group labels
            # ("Flow Object Quality" etc., not just the value names) since
            # those also start in column 0, spanning across the rest —
            # otherwise a long one overflows past its own column budget
            # into whatever sits to its right.
            default_font = tkfont.nametofont("TkDefaultFont")
            label_column_width = self.measure_column_width(
                [
                    get_routing_scope_label(scope, variable)
                    for scope, variable in scope_candidates
                ]
                + [
                    value
                    for scope, variable in scope_candidates
                    for value in get_routing_scope_values(scope, variable, self.schema)
                ],
                default_font,
            )
            entity_frame.columnconfigure(0, minsize=label_column_width)
            # Each output column is sized to its own header text (the
            # Entity's name) the same way, instead of a guessed padding
            # value — a short name gets a narrower column, a long one a
            # wider column, and the checkbox centers within it either way.
            for column_index, target_id in enumerate(target_ids):
                entity_frame.columnconfigure(
                    1 + column_index,
                    minsize=self.measure_column_width(
                        [self.get_entity_name(target_id)], default_font
                    ),
                )
            # The trailing column is a spacer that absorbs the extra width,
            # so the value/checkbox columns stay packed together on the
            # left instead of stretching to fill the frame.
            entity_frame.columnconfigure(1 + len(target_ids), weight=1)

            # Display widgets:
            entity_frame.grid(row=decision_point_index, column=0, sticky="new")

            row = 0

            # Widgets:
            # Every scope here (the Entity's own state, any Flow Object
            # state) is evaluated at the same moment — when this Flow
            # Object's cycle at this Entity concludes — so it's stated
            # once per decision point instead of repeated per scope group.
            timing_note = ttk.Label(
                entity_frame, text="Values are read once the operation finishes."
            )

            # Display widgets:
            # Spans the full row (not just column 0) so this sentence,
            # which is wider than any single column, doesn't need to be
            # folded into the column-0 width measurement below.
            timing_note.grid(
                row=row,
                column=0,
                columnspan=1 + len(target_ids),
                sticky="w",
                pady=(0, 4),
            )

            row += 1

            for column_index, target_id in enumerate(target_ids):
                # Widgets:
                output_header = ttk.Label(entity_frame, text=self.get_entity_name(target_id))

                # Display widgets:
                output_header.grid(row=row, column=1 + column_index, pady=(0, 4))

            row += 1

            for scope_index, (scope, variable) in enumerate(scope_candidates):
                if scope_index > 0:
                    # Widgets:
                    scope_separator = ttk.Separator(entity_frame, orient="horizontal")

                    # Display widgets:
                    scope_separator.grid(
                        row=row,
                        column=0,
                        columnspan=1 + len(target_ids),
                        sticky="ew",
                        pady=6,
                    )

                    row += 1

                # Widgets:
                scope_label = ttk.Label(
                    entity_frame, text=get_routing_scope_label(scope, variable)
                )

                # Display widgets:
                scope_label.grid(
                    row=row,
                    column=0,
                    columnspan=1 + len(target_ids),
                    sticky="w",
                    pady=(0, 2),
                )

                row += 1

                for value in get_routing_scope_values(scope, variable, self.schema):
                    # Widgets:
                    value_label = ttk.Label(entity_frame, text=value)

                    # Display widgets:
                    value_label.grid(row=row, column=0, sticky="w", pady=2)

                    # A value with no box checked in its row is simply
                    # unassigned — no separate "unassigned" column needed.
                    owner_id = get_routing_condition_owner(
                        self.model_data, entity_id, scope, variable, value
                    )

                    for column_index, target_id in enumerate(target_ids):
                        # Widgets:
                        checkbutton = ttk.Checkbutton(
                            entity_frame,
                            command=lambda entity_id=entity_id, scope=scope, variable=variable, value=value, target_id=target_id: (
                                self.toggle_routing_condition_owner(
                                    entity_id, scope, variable, value, target_id
                                )
                            ),
                        )

                        # A fresh Checkbutton defaults to "alternate" (a
                        # dash, neither checked nor unchecked) regardless
                        # of variable binding — clear it explicitly, or
                        # every box looks the same and clicking looks like
                        # it does nothing.
                        if target_id == owner_id:
                            checkbutton.state(["!alternate", "selected"])
                        else:
                            checkbutton.state(["!alternate", "!selected"])

                        # Display widgets:
                        checkbutton.grid(row=row, column=1 + column_index, pady=2)

                    row += 1

    def toggle_routing_condition_owner(self, entity_id, scope, variable, equals, target_id):
        # Checking a box makes that output the owner (taking it away from
        # wherever it was); checking the box that's already checked
        # unassigns it — there's no separate "unassigned" control, the box
        # itself is the whole interaction.
        current_owner = get_routing_condition_owner(
            self.model_data, entity_id, scope, variable, equals
        )
        new_owner = None if current_owner == target_id else target_id

        self.commit_routing_condition_owner(entity_id, scope, variable, equals, new_owner)

    def commit_routing_condition_owner(self, entity_id, scope, variable, equals, target_id):
        set_routing_condition_owner(
            self.model_data, entity_id, scope, variable, equals, target_id
        )

        # Re-render (and re-bind scrolling on the fresh widgets — this
        # rebuilds the frame, so a plain update_routing_frame() would leave
        # the new widgets without a mousewheel binding until the next tab
        # switch) so every row immediately reflects the assignment that
        # was just made.
        self.refresh_rules_tab()
        self.update_model_changed_state()

    def update_failure_frame(self):
        # Clear existing widgets:
        for widget in self.failure_frame.winfo_children():
            widget.destroy()

        entity_ids = get_failure_eligible_entity_ids(self.model_data, self.schema)

        if not entity_ids:
            no_entities_label = ttk.Label(
                self.failure_frame,
                text="No entities that support failure in this model yet.",
            )
            no_entities_label.grid(row=0, column=0, sticky="w")
            return

        rule_schema = self.schema.get_rule_schema(self.model_data["domain"], "Failure")
        fields = rule_schema["properties"] if rule_schema else {}

        # A fixed column 0 width (the longest field label here) keeps the
        # entry/unit columns justified at the same x position on every row,
        # regardless of which field's label is currently showing.
        default_font = tkfont.nametofont("TkDefaultFont")
        label_column_width = self.measure_column_width(
            [name.replace("_", " ").title() for name in fields], default_font
        )

        for entity_index, entity_id in enumerate(entity_ids):
            # Widgets:
            entity_frame = ttk.LabelFrame(
                self.failure_frame,
                text=f'AT "{self.get_entity_name(entity_id)}"',
                style="DESE.Section.TLabelframe",
                padding=PAD,
            )

            # Grid:
            entity_frame.columnconfigure(0, minsize=label_column_width)
            entity_frame.columnconfigure(3, weight=1)

            # Display widgets:
            entity_frame.grid(row=entity_index, column=0, sticky="new")

            row = 0

            for field_index, (field_name, field_schema) in enumerate(fields.items()):
                if field_index > 0:
                    # Widgets:
                    field_separator = ttk.Separator(entity_frame, orient="horizontal")

                    # Display widgets:
                    field_separator.grid(row=row, column=0, columnspan=4, sticky="ew")

                    row += 1

                # Widgets:
                validate_command = (self.register(validate_number), "%P")

                description_label = ttk.Label(
                    entity_frame, text=field_schema["description"]
                )
                field_label_widget = ttk.Label(
                    entity_frame, text=field_name.replace("_", " ").title()
                )
                field_entry = ttk.Entry(
                    entity_frame,
                    width=INPUT_WIDTH,
                    validate="key",
                    validatecommand=validate_command,
                )
                field_unit_label = ttk.Label(
                    entity_frame, text=field_schema.get("unit", "")
                )

                value = get_failure_parameter(self.model_data, entity_id, field_name)

                if value is not None:
                    field_entry.insert(0, str(value))

                # Event binding:
                field_entry.bind(
                    "<FocusOut>",
                    lambda event, entity_id=entity_id, field_name=field_name, entry=field_entry: (
                        self.commit_failure_parameter(entity_id, field_name, entry)
                    ),
                )
                field_entry.bind(
                    "<Return>",
                    lambda event, entity_id=entity_id, field_name=field_name, entry=field_entry: (
                        self.commit_failure_parameter(entity_id, field_name, entry)
                    ),
                )

                # Display widgets:
                description_label.grid(row=row, column=0, columnspan=4, sticky="w")
                row += 1
                field_label_widget.grid(row=row, column=0, sticky="w")
                field_entry.grid(row=row, column=1, sticky="w")
                field_unit_label.grid(row=row, column=2, sticky="w")

                row += 1

    def commit_failure_parameter(self, entity_id, field_name, entry):
        new_value = convert_property_value(entry.get(), NUMBER_PROPERTY_TYPE)

        if get_failure_parameter(self.model_data, entity_id, field_name) != new_value:
            set_failure_parameter(self.model_data, entity_id, field_name, new_value)
            self.update_model_changed_state()

        entry.delete(0, "end")
        entry.insert(
            0, str(get_failure_parameter(self.model_data, entity_id, field_name) or "")
        )

    def update_maintenance_frame(self):
        self.update_maintenance_plan_frame()
        self.update_maintenance_resource_frame()

    def update_maintenance_plan_frame(self):
        # Clear existing widgets:
        for widget in self.maintenance_plan_frame.winfo_children():
            widget.destroy()

        entity_ids = get_failure_eligible_entity_ids(self.model_data, self.schema)

        if not entity_ids:
            no_entities_label = ttk.Label(
                self.maintenance_plan_frame,
                text="No entities that support failure in this model yet.",
            )
            no_entities_label.grid(row=0, column=0, sticky="w")
            return

        rule_schema = self.schema.get_rule_schema(self.model_data["domain"], "Maintenance")
        fields = rule_schema["properties"] if rule_schema else {}

        default_font = tkfont.nametofont("TkDefaultFont")
        label_column_width = self.measure_column_width(
            [name.replace("_", " ").title() for name in fields], default_font
        )

        for entity_index, entity_id in enumerate(entity_ids):
            # Widgets:
            entity_frame = ttk.LabelFrame(
                self.maintenance_plan_frame,
                text=f'AT "{self.get_entity_name(entity_id)}"',
                style="DESE.Section.TLabelframe",
                padding=PAD,
            )

            # Grid:
            entity_frame.columnconfigure(0, minsize=label_column_width)
            entity_frame.columnconfigure(3, weight=1)

            # Display widgets:
            entity_frame.grid(row=entity_index, column=0, sticky="new")

            row = 0

            for field_index, (field_name, field_schema) in enumerate(fields.items()):
                if field_index > 0:
                    # Widgets:
                    field_separator = ttk.Separator(entity_frame, orient="horizontal")

                    # Display widgets:
                    field_separator.grid(row=row, column=0, columnspan=4, sticky="ew")

                    row += 1

                # Widgets:
                validate_command = (self.register(validate_number), "%P")

                description_label = ttk.Label(
                    entity_frame, text=field_schema["description"]
                )
                field_label_widget = ttk.Label(
                    entity_frame, text=field_name.replace("_", " ").title()
                )
                field_entry = ttk.Entry(
                    entity_frame,
                    width=INPUT_WIDTH,
                    validate="key",
                    validatecommand=validate_command,
                )
                field_unit_label = ttk.Label(
                    entity_frame, text=field_schema.get("unit", "")
                )

                value = get_maintenance_parameter(self.model_data, entity_id, field_name)

                if value is not None:
                    field_entry.insert(0, str(value))

                # Event binding:
                field_entry.bind(
                    "<FocusOut>",
                    lambda event, entity_id=entity_id, field_name=field_name, entry=field_entry: (
                        self.commit_maintenance_parameter(entity_id, field_name, entry)
                    ),
                )
                field_entry.bind(
                    "<Return>",
                    lambda event, entity_id=entity_id, field_name=field_name, entry=field_entry: (
                        self.commit_maintenance_parameter(entity_id, field_name, entry)
                    ),
                )

                # Display widgets:
                description_label.grid(row=row, column=0, columnspan=4, sticky="w")
                row += 1
                field_label_widget.grid(row=row, column=0, sticky="w")
                field_entry.grid(row=row, column=1, sticky="w")
                field_unit_label.grid(row=row, column=2, sticky="w")

                row += 1

    def commit_maintenance_parameter(self, entity_id, field_name, entry):
        new_value = convert_property_value(entry.get(), NUMBER_PROPERTY_TYPE)

        if get_maintenance_parameter(self.model_data, entity_id, field_name) != new_value:
            set_maintenance_parameter(self.model_data, entity_id, field_name, new_value)
            self.update_model_changed_state()

        entry.delete(0, "end")
        entry.insert(
            0,
            str(get_maintenance_parameter(self.model_data, entity_id, field_name) or ""),
        )

    def update_maintenance_resource_frame(self):
        # Clear existing widgets:
        for widget in self.maintenance_resource_frame.winfo_children():
            widget.destroy()

        entity_ids = get_failure_eligible_entity_ids(self.model_data, self.schema)

        if not entity_ids:
            no_entities_label = ttk.Label(
                self.maintenance_resource_frame,
                text="No entities that support failure in this model yet.",
            )
            no_entities_label.grid(row=0, column=0, sticky="w")
            return

        rule_schema = self.schema.get_rule_schema(
            self.model_data["domain"], "MaintenanceResource"
        )
        fields = rule_schema["properties"] if rule_schema else {}

        # Grid:
        default_font = tkfont.nametofont("TkDefaultFont")
        self.maintenance_resource_frame.columnconfigure(
            0,
            minsize=self.measure_column_width(
                [name.replace("_", " ").title() for name in fields], default_font
            ),
        )

        row = 0

        for field_index, (field_name, field_schema) in enumerate(fields.items()):
            if field_index > 0:
                # Widgets:
                field_separator = ttk.Separator(
                    self.maintenance_resource_frame, orient="horizontal"
                )

                # Display widgets:
                field_separator.grid(row=row, column=0, columnspan=4, sticky="ew")

                row += 1

            # Widgets:
            description_label = ttk.Label(
                self.maintenance_resource_frame, text=field_schema["description"]
            )

            # Display widgets:
            description_label.grid(row=row, column=0, columnspan=4, sticky="w")

            row += 1

            if field_schema["type"] == "priority_list":
                # Widgets:
                priority_label = ttk.Label(
                    self.maintenance_resource_frame,
                    text=field_name.replace("_", " ").title(),
                )
                self.dispatch_priority_listbox = tk.Listbox(
                    self.maintenance_resource_frame,
                    height=len(field_schema["values"]),
                    exportselection=False,
                )

                labels = field_schema["labels"]

                for criterion in get_maintenance_dispatch_priority(
                    self.model_data, self.schema
                ):
                    self.dispatch_priority_listbox.insert(tk.END, labels[criterion])

                self.dispatch_priority_listbox.selection_set(0)

                # Same style as the Structure tab's entity table Move up/down
                # buttons — text label, BUTTON_WIDTH, side by side.
                move_button_frame = ttk.Frame(self.maintenance_resource_frame)
                move_up_button = ttk.Button(
                    move_button_frame,
                    text="Move up ↑",
                    width=BUTTON_WIDTH,
                    command=lambda: self.move_dispatch_priority(-1),
                )
                move_down_button = ttk.Button(
                    move_button_frame,
                    text="Move down ↓",
                    width=BUTTON_WIDTH,
                    command=lambda: self.move_dispatch_priority(1),
                )

                # Display widgets:
                priority_label.grid(row=row, column=0, sticky="nw")
                self.dispatch_priority_listbox.grid(row=row, column=1, sticky="w")
                # Column 3 is the trailing spacer — placing the buttons there
                # with "se" sticky pins them to the Resource frame's bottom-
                # right corner instead of floating mid-row next to the list.
                move_button_frame.grid(row=row, column=3, sticky="se")
                move_up_button.grid(row=0, column=0)
                move_down_button.grid(row=0, column=1)
            else:
                # Widgets:
                validate_command = (self.register(validate_number), "%P")

                field_label_widget = ttk.Label(
                    self.maintenance_resource_frame,
                    text=field_name.replace("_", " ").title(),
                )
                field_entry = ttk.Entry(
                    self.maintenance_resource_frame,
                    width=INPUT_WIDTH,
                    validate="key",
                    validatecommand=validate_command,
                )
                field_unit_label = ttk.Label(
                    self.maintenance_resource_frame, text=field_schema.get("unit", "")
                )

                value = get_maintenance_resource_parameter(self.model_data, field_name)

                if value is not None:
                    field_entry.insert(0, str(value))

                # Event binding:
                field_entry.bind(
                    "<FocusOut>",
                    lambda event, field_name=field_name, entry=field_entry: (
                        self.commit_maintenance_resource_parameter(field_name, entry)
                    ),
                )
                field_entry.bind(
                    "<Return>",
                    lambda event, field_name=field_name, entry=field_entry: (
                        self.commit_maintenance_resource_parameter(field_name, entry)
                    ),
                )

                # Display widgets:
                field_label_widget.grid(row=row, column=0, sticky="w")
                field_entry.grid(row=row, column=1, sticky="w")
                field_unit_label.grid(row=row, column=2, sticky="w")

            row += 1

    def commit_maintenance_resource_parameter(self, field_name, entry):
        new_value = convert_property_value(entry.get(), NUMBER_PROPERTY_TYPE)

        if get_maintenance_resource_parameter(self.model_data, field_name) != new_value:
            set_maintenance_resource_parameter(self.model_data, field_name, new_value)
            self.update_model_changed_state()

        entry.delete(0, "end")
        entry.insert(
            0, str(get_maintenance_resource_parameter(self.model_data, field_name) or "")
        )

    def move_dispatch_priority(self, direction):
        selection = self.dispatch_priority_listbox.curselection()

        if not selection:
            return

        index = selection[0]
        new_index = index + direction

        if new_index < 0 or new_index >= self.dispatch_priority_listbox.size():
            return

        dispatch_priority = get_maintenance_dispatch_priority(self.model_data, self.schema)
        dispatch_priority[index], dispatch_priority[new_index] = (
            dispatch_priority[new_index],
            dispatch_priority[index],
        )

        set_maintenance_dispatch_priority(self.model_data, dispatch_priority)
        self.update_model_changed_state()

        # refresh_rules_tab (not just update_maintenance_resource_frame) so
        # the freshly rebuilt widgets get their mousewheel binding back too.
        self.refresh_rules_tab()

        self.dispatch_priority_listbox.selection_set(new_index)

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
        self.main_frame.rowconfigure(1, weight=0)
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

        # Event binding:
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)

        # Button Frame
        # ==========================
        # Shared across every tab (Save/Flow Objects apply to the whole
        # model, not just the Structure tab), so it lives below the
        # notebook rather than inside one tab's content.

        # Frame widget:
        self.button_frame = ttk.Frame(self.main_frame, padding=PAD)

        # Grid:
        self.button_frame.columnconfigure(0, weight=1)

        # Display frame widget:
        self.button_frame.grid(row=1, column=0, sticky="ew")

        # Child widgets:
        self.save_model_button = ttk.Button(
            self.button_frame, text="Save", width=BUTTON_WIDTH, command=self.save_model
        )
        self.flow_objects_button = ttk.Button(
            self.button_frame,
            text="Flow Objects",
            width=BUTTON_WIDTH,
            command=self.open_flow_object_editor,
        )

        # Display child widgets:
        self.flow_objects_button.grid(row=0, column=0, sticky="e")
        self.save_model_button.grid(row=0, column=1, sticky="e")

        # Create tab content:
        self.create_structure_tab()
        # NOTE(DESE-34): the Visualization tab's scroll infrastructure is set up
        # here but not yet populated with a diagram — work in progress.
        self.create_visualization_tab()
        # TODO(DESE-35): the Routing frame is empty so far — it still needs to
        # list find_decision_points() results and let the user define a rule
        # for each. Not a bug.
        self.create_rules_tab()

        # Initialize editor state:
        self.populate_entity_table()
        self.update_type_selector()
        self.update_editor_state()
        self.update_process_boundary_state()
