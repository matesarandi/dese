import copy
import json
import tkinter as tk
from tkinter import messagebox, ttk

from dese.application.pages.flow_object_editor import FlowObjectEditor
from dese.application.pages.rules_tab_mixin import RulesTabMixin
from dese.application.pages.structure_tab_mixin import StructureTabMixin
from dese.constants import BUTTON_WIDTH, INPUT_WIDTH, PAD
from dese.core.model import (
    get_input_relationships,
    get_main_entity_input_relationships,
    get_main_entity_output_relationships,
    get_output_relationships,
    is_main_entity,
    load_model_data,
    move_routing_rule_output,
    remove_entity_from_rules,
)
from dese.utils import bind_canvas_mousewheel, convert_property_value, generate_id


class ModelEditorPage(ttk.Frame, StructureTabMixin, RulesTabMixin):
    """Structure/Visualization/Rules tabs for a single model: owns model_data and
    the schema-driven entity, property and relationship editors built on top of it.

    StructureTabMixin and RulesTabMixin supply the Structure and Rules tabs'
    rendering/event-handling methods, each kept in its own file since both are
    large and self-contained."""

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
        self.add_entity_window = None
        self.flow_object_editor = None
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

    def open_flow_object_editor(self):
        if (
            self.flow_object_editor is not None
            and self.flow_object_editor.window.winfo_exists()
        ):
            self.flow_object_editor.window.lift()
            self.flow_object_editor.window.focus_set()
            return

        self.flow_object_editor = FlowObjectEditor(
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

        elif self.selected_entity is not None and not is_main_entity(
            self.selected_entity, self.model_data, self.schema
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

        elif self.selected_entity is not None and not is_main_entity(
            self.selected_entity, self.model_data, self.schema
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
        if self.add_entity_window is not None and self.add_entity_window.winfo_exists():
            self.add_entity_window.lift()
            self.add_entity_window.focus_set()
            return

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
            self.model_data = load_model_data(self.model_path, self.schema)
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

    # ==========================
    # Event Callbacks
    # ==========================

    def apply_process_boundary_flag(
        self,
        direction,
        is_marked,
        variable,
        get_conflicting_relationships,
        relationship_entity_field,
        connection_description,
    ):
        boundary_key = f"{direction}_of_process"

        if not is_marked:
            self.selected_entity.pop(boundary_key, None)
            return True

        conflicting_relationships = get_conflicting_relationships()

        if conflicting_relationships:
            descriptions = [
                self.get_entity_name(relationship[relationship_entity_field])
                for relationship in conflicting_relationships
            ]

            messagebox.showwarning(
                f"Invalid {direction.capitalize()} of Process",
                f"This Entity has existing {connection_description}: "
                + ", ".join(descriptions)
                + ". Delete the relationship(s) to mark this Entity "
                f"as the {direction} of the process.",
            )

            variable.set(False)

            return False

        self.selected_entity[boundary_key] = True

        return True

    def update_process_boundary(self):
        # The process can only have one entry and one exit point among its
        # "main" entities, so an entity can't be marked beginning/end of
        # process while it already has a main-entity input/output relationship.
        if self.selected_entity is None:
            return

        if not self.apply_process_boundary_flag(
            direction="beginning",
            is_marked=self.beginning_of_process_variable.get(),
            variable=self.beginning_of_process_variable,
            get_conflicting_relationships=lambda: get_main_entity_input_relationships(
                self.selected_entity["id"], self.model_data, self.schema
            ),
            relationship_entity_field="source",
            connection_description="input relationships from",
        ):
            return

        if not self.apply_process_boundary_flag(
            direction="end",
            is_marked=self.end_of_process_variable.get(),
            variable=self.end_of_process_variable,
            get_conflicting_relationships=lambda: get_main_entity_output_relationships(
                self.selected_entity["id"], self.model_data, self.schema
            ),
            relationship_entity_field="target",
            connection_description="output relationships to",
        ):
            return

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

        return get_input_relationships(self.selected_entity["id"], self.model_data)

    def get_output_relationships(self):
        if self.selected_entity is None:
            return []

        return get_output_relationships(self.selected_entity["id"], self.model_data)

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
        self.create_rules_tab()

        # Initialize editor state:
        self.populate_entity_table()
        self.update_type_selector()
        self.update_editor_state()
        self.update_process_boundary_state()
