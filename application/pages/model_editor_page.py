import json
import tkinter as tk
from tkinter import messagebox, ttk

from dese.constants import (
    BUTTON_WIDTH,
    INPUT_WIDTH,
    PAD_FRAME_IN,
    PAD_WIDGET,
    SPINBOX_WIDTH,
)


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

    def generate_entity_id(self):
        existing_ids = [entity["id"] for entity in self.model_data["entities"]]

        number = 1

        while f"E{number:03d}" in existing_ids:
            number += 1

        return f"E{number:03d}"

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
        self.add_entity_name_label.grid(
            row=0, column=0, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
        )
        self.add_entity_name_entry.grid(
            row=0, column=1, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
        )
        self.add_entity_type_label.grid(
            row=1, column=0, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
        )
        self.add_entity_type_combobox.grid(
            row=1, column=1, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
        )
        self.add_entity_cancel_button.grid(
            row=2, column=1, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="e"
        )
        self.add_entity_confirm_button.grid(
            row=2, column=0, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="e"
        )

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

        for property_name, description in properties.items():
            # Widgets:
            label = ttk.Label(self.property_content, text=f"{property_name}:")
            entry = ttk.Entry(self.property_content, width=INPUT_WIDTH)
            description_label = ttk.Label(self.property_content, text=description)
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
                padx=PAD_WIDGET,
                pady=PAD_WIDGET,
                sticky="w",
            )
            entry.grid(
                row=row + 1,
                column=1,
                padx=PAD_WIDGET,
                pady=PAD_WIDGET,
                sticky="w",
            )
            description_label.grid(
                row=row,
                column=0,
                columnspan=2,
                padx=PAD_WIDGET,
                pady=PAD_WIDGET,
                sticky="w",
            )
            separator.grid(
                row=row + 2,
                column=0,
                columnspan=2,
                sticky="ew",
                padx=PAD_WIDGET,
                pady=PAD_WIDGET,
            )

            # Event binding:
            entry.bind(
                "<KeyRelease>",
                lambda event, property_name=property_name: self.update_entity_property(
                    property_name, event
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
        input_label.grid(row=0, column=0, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w")

        self.input_count_spinbox = ttk.Spinbox(
            self.input_frame,
            from_=self.input_count,
            to=input_max,
            state="readonly",
            width=SPINBOX_WIDTH,
            command=self.update_relationship_inputs,
        )
        self.input_count_spinbox.set(self.input_count)
        self.input_count_spinbox.grid(
            row=0, column=1, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
        )

        # Output count:

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
        output_label.grid(row=0, column=0, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w")

        self.output_count_spinbox = ttk.Spinbox(
            self.output_frame,
            from_=self.output_count,
            to=output_max,
            state="readonly",
            width=SPINBOX_WIDTH,
            command=self.update_relationship_outputs,
        )
        self.output_count_spinbox.set(self.output_count)
        self.output_count_spinbox.grid(
            row=0, column=1, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
        )

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

            label.grid(
                row=index + 1, column=0, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
            )
            combobox.grid(
                row=index + 1, column=1, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
            )

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

            label.grid(
                row=index, column=0, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
            )
            combobox.grid(
                row=index, column=1, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
            )

    def update_entity_editor(self):
        if self.selected_entity is None:
            return

        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, self.selected_entity["name"])
        self.type_combobox.set(self.selected_entity["type"])
        self.update_property_editor()
        self.update_relationship_editor()

    def load_model(self):
        try:
            with open(self.model_path, "r") as file:
                self.model_data = json.load(file)
            print(
                self.schema.get_entity_schema(self.model_data["domain"], "Processing")
            )

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
            self.entity_table.insert(
                "", "end", values=(entity["id"], entity["name"], entity["type"], "", "")
            )

    def refresh_entity_table(self):
        self.entity_table.delete(*self.entity_table.get_children())
        self.populate_entity_table()

    # ==========================
    # Event Callbacks
    # ==========================

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

    def get_relationships_for_entity(self, entity_id):
        return [
            relationship
            for relationship in self.model_data["relationships"]
            if (
                relationship["source"] == entity_id
                or relationship["target"] == entity_id
            )
        ]

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

    def get_relationship_at_index(self, relationships, index):
        if index < len(relationships):
            return relationships[index]

        return None

    def update_entity_name(self, event=None):
        if self.selected_entity is None:
            return

        new_name = self.name_entry.get()

        if self.selected_entity["name"] == new_name:
            return

        self.selected_entity["name"] = new_name

        selected_item = self.entity_table.selection()

        if selected_item:
            self.entity_table.item(
                selected_item[0],
                values=(
                    self.selected_entity["id"],
                    self.selected_entity["name"],
                    self.selected_entity["type"],
                    "",
                    "",
                ),
            )

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
            self.entity_table.item(
                selected_item[0],
                values=(
                    self.selected_entity["id"],
                    self.selected_entity["name"],
                    self.selected_entity["type"],
                    "",
                    "",
                ),
            )

        self.update_property_editor()
        self.update_relationship_editor()
        self.model_changed_callback(True)

    def update_entity_property(self, property_name, event=None):
        if self.selected_entity is None:
            return

        new_value = self.property_entries[property_name].get()

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

        self.model_changed_callback(True)

    def update_entity(self):
        if self.selected_entity is None:
            return

        # Get input:
        new_name = self.name_entry.get()
        new_type = self.type_combobox.get()
        new_properties = {
            property_name: entry.get()
            for property_name, entry in self.property_entries.items()
        }

        # Check for changes:
        name_changed = self.selected_entity["name"] != new_name
        type_changed = self.selected_entity["type"] != new_type
        properties_changed = self.selected_entity["properties"] != new_properties

        # Update entity:
        self.selected_entity["name"] = new_name
        self.selected_entity["type"] = new_type
        self.selected_entity["properties"] = new_properties

        # Refresh entity table:
        self.refresh_entity_table()

        # Model changed:
        if name_changed or type_changed or properties_changed:
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
            padding=PAD_FRAME_IN,
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

        # Display frame widget:
        self.entity_table_frame.grid(
            row=0, column=0, sticky="nsew", padx=PAD_WIDGET, pady=PAD_WIDGET
        )

        # Display child widgets:
        self.entity_table.grid(row=0, column=0, sticky="nsew")
        self.entity_table_scrollbar.grid(row=0, column=1, sticky="ns")
        self.entity_button_frame.grid(
            row=1, column=0, columnspan=2, sticky="w", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.add_entity_button.grid(row=0, column=0, padx=PAD_WIDGET)
        self.delete_entity_button.grid(row=0, column=1, padx=PAD_WIDGET)

        # Editor
        # ==========================

        # Frame widget:
        self.editor = ttk.LabelFrame(
            self.structure_tab,
            text="Editor",
            style="DESE.Section.TLabelframe",
            padding=PAD_FRAME_IN,
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
            padding=PAD_FRAME_IN,
        )
        self.relationship_editor = ttk.LabelFrame(
            self.editor,
            text="Relationships",
            style="DESE.Section.TLabelframe",
            padding=PAD_FRAME_IN,
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
        self.basic_editor.grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.property_editor.grid(
            row=1, column=0, sticky="nsew", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.relationship_editor.grid(
            row=1, column=1, sticky="nsew", padx=PAD_WIDGET, pady=PAD_WIDGET
        )
        self.button_frame.grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=PAD_WIDGET, pady=PAD_WIDGET
        )

        # Child widgets:
        self.name_label = ttk.Label(self.basic_editor, text="Name:")
        self.name_entry = ttk.Entry(self.basic_editor, width=INPUT_WIDTH)
        self.type_title_label = ttk.Label(self.basic_editor, text="Type:")
        self.type_combobox = ttk.Combobox(
            self.basic_editor, state="readonly", width=INPUT_WIDTH
        )

        self.save_model_button = ttk.Button(
            self.button_frame, text="Save", width=BUTTON_WIDTH, command=self.save_model
        )

        # Event binding:
        self.name_entry.bind("<KeyRelease>", self.update_entity_name)
        self.type_combobox.bind("<<ComboboxSelected>>", self.update_entity_type)

        # Display frame widget:
        self.editor.grid(
            row=1, column=0, sticky="nsew", padx=PAD_WIDGET, pady=PAD_WIDGET
        )

        # Display child widgets:
        self.name_label.grid(
            row=0, column=0, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
        )
        self.name_entry.grid(
            row=0, column=1, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
        )
        self.type_title_label.grid(
            row=0, column=2, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
        )
        self.type_combobox.grid(
            row=0, column=3, padx=PAD_WIDGET, pady=PAD_WIDGET, sticky="w"
        )
        self.save_model_button.grid(
            row=0, column=1, sticky="e", padx=PAD_WIDGET, pady=PAD_WIDGET
        )

    # ==========================
    # Model Editor Page
    # ==========================

    def create_widgets(self):
        # Grid:
        self.rowconfigure(0, weight=0)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        # Notebook
        # ==========================

        # Widget:
        self.notebook = ttk.Notebook(self)

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
        self.notebook.grid(row=1, column=0, sticky="nsew")

        # Create tab content:
        self.create_structure_tab()

        # Populate entity table:
        self.populate_entity_table()

        # Update type selector:
        self.update_type_selector()
