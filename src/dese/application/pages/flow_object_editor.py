import tkinter as tk
from tkinter import messagebox, ttk

from dese.constants import (
    BUTTON_WIDTH,
    FLOW_OBJECT_WINDOW_SIZE,
    INPUT_WIDTH,
    NUMBER_PROPERTY_TYPE,
    PAD,
    PROPERTY_ROW_HEIGHT,
)
from dese.core.model import accepts_flow_object_entry, is_supply_source
from dese.utils import bind_canvas_mousewheel, convert_property_value, validate_number


class FlowObjectEditor:
    """Popup window for editing the model's Flow Objects: their properties and
    their Process Requirements towards Processing entities."""

    def __init__(self, parent, model_data, schema, update_model_changed_state, save_callback):
        self.window = tk.Toplevel(parent)
        self.window.title("Flow Objects")
        self.window.geometry(FLOW_OBJECT_WINDOW_SIZE)
        self.model_data = model_data
        self.schema = schema
        self.update_model_changed_state = update_model_changed_state
        self.save_callback = save_callback

        # Grid:
        self.window.rowconfigure(0, weight=1)
        self.window.columnconfigure(0, weight=1)

        self.create_widgets()

    # ==========================
    # Methods
    # ==========================

    def is_flow_object_name_unique(self, flow_object, name):
        return all(
            other_flow_object is flow_object or other_flow_object["name"] != name
            for other_flow_object in self.model_data["flow_objects"]
        )

    def validate_flow_object_name(self, flow_object, name, variable):
        if not self.is_flow_object_name_unique(flow_object, name):
            messagebox.showwarning("Duplicate name", "Cannot use the same name.")

            variable.set(flow_object["name"])
            return False

        self.update_flow_object_property(flow_object, "name", name, "string")
        return True

    def add_flow_object(self):
        flow_object_schema = self.schema.get_flow_object_schema()

        flow_object = {}

        # Required properties:
        for property_name in flow_object_schema["required_properties"]:
            flow_object[property_name] = None

        number = 1

        while any(
            flow_object["name"] == f"Flow Object {number}"
            for flow_object in self.model_data["flow_objects"]
        ):
            number += 1

        flow_object["name"] = f"Flow Object {number}"

        # Properties:
        flow_object["properties"] = {}

        for property_name in flow_object_schema["properties"]:
            flow_object["properties"][property_name] = None

        # Process requirements:
        flow_object["process_requirements"] = {}

        self.model_data["flow_objects"].append(flow_object)

        self.update_model_changed_state()

        self.flow_object_listbox.insert(tk.END, flow_object["name"])

        self.flow_object_listbox.selection_clear(0, tk.END)
        self.flow_object_listbox.selection_set(tk.END)

    def select_flow_object(self, event=None):
        selected_index = self.flow_object_listbox.curselection()

        if not selected_index:
            return

        flow_object = self.model_data["flow_objects"][selected_index[0]]

        self.display_flow_object_properties(flow_object)

    def update_flow_object_property(
        self, flow_object, property_name, value, property_type
    ):
        value = convert_property_value(value, property_type)

        flow_object[property_name] = value

        if property_name == "name":
            flow_object_index = next(
                index
                for index, item in enumerate(self.model_data["flow_objects"])
                if item is flow_object
            )

            self.flow_object_listbox.delete(flow_object_index)
            self.flow_object_listbox.insert(flow_object_index, flow_object["name"])
            self.flow_object_listbox.selection_set(flow_object_index)

        self.update_model_changed_state()

    def commit_property_value(self, container, property_name, property_type, variable):
        self.update_flow_object_property(
            container, property_name, variable.get(), property_type
        )

        variable.set(str(container[property_name]))

    def commit_process_requirement(
        self, flow_object, processing_entity_id, process_supply_entity_id, variable
    ):
        new_value = convert_property_value(variable.get(), NUMBER_PROPERTY_TYPE)

        flow_object["process_requirements"].setdefault(processing_entity_id, {})[
            process_supply_entity_id
        ] = new_value

        variable.set(str(new_value))

        self.update_model_changed_state()

    def get_processing_entities(self):
        return [
            entity
            for entity in self.model_data["entities"]
            if accepts_flow_object_entry(entity, self.model_data, self.schema)
        ]

    def display_flow_object_properties(self, flow_object):
        for widget in self.right_content_frame.winfo_children():
            widget.destroy()

        flow_object_schema = self.schema.get_flow_object_schema()

        row = 0

        # Flow object properties frame widget:
        flow_object_properties_frame = ttk.LabelFrame(
            self.right_content_frame,
            text="Flow Object Properties",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Grid:
        flow_object_properties_frame.columnconfigure(0, weight=1)
        flow_object_properties_frame.columnconfigure(1, weight=0)
        flow_object_properties_frame.columnconfigure(2, weight=0)

        # Display flow object properties frame widget:
        flow_object_properties_frame.grid(row=0, column=0, columnspan=3, sticky="ew")

        # Required Properties
        # ==========================

        for property_name, property_schema in flow_object_schema[
            "required_properties"
        ].items():
            # Widgets:
            label = ttk.Label(
                flow_object_properties_frame,
                text=property_name.replace("_", " ").title(),
            )
            variable = tk.StringVar(value=str(flow_object[property_name] or ""))
            entry = ttk.Entry(
                flow_object_properties_frame, width=INPUT_WIDTH, textvariable=variable
            )

            # Display widgets:
            entry.grid(row=row, column=1, sticky="w")
            label.grid(row=row, column=0, sticky="w")

            # Event binding:
            if property_name == "name":
                entry.bind(
                    "<FocusOut>",
                    lambda event, flow_object=flow_object, variable=variable: (
                        self.validate_flow_object_name(
                            flow_object, variable.get(), variable
                        )
                    ),
                )

                entry.bind(
                    "<Return>",
                    lambda event, flow_object=flow_object, variable=variable: (
                        self.validate_flow_object_name(
                            flow_object, variable.get(), variable
                        )
                    ),
                )

            else:
                variable.trace_add(
                    "write",
                    lambda *args, property_name=property_name, property_type=property_schema["type"], variable=variable: (
                        self.update_flow_object_property(
                            flow_object, property_name, variable.get(), property_type
                        )
                    ),
                )

        row += 1

        # Separator widget bw. sections:
        section_separator = ttk.Separator(
            flow_object_properties_frame, orient="horizontal"
        )

        # Display separator widget bw. sections:
        section_separator.grid(
            row=row,
            column=0,
            columnspan=3,
            sticky="ew",
        )

        row += 1

        # Properties
        # ==========================

        # Widgets:

        for property_index, (property_name, property_description) in enumerate(
            flow_object_schema["properties"].items()
        ):
            if property_index > 0:
                # Widgets:
                separator = ttk.Separator(
                    flow_object_properties_frame, orient="horizontal"
                )

                # Display widgets:
                separator.grid(
                    row=row,
                    column=0,
                    columnspan=3,
                    sticky="ew",
                )

                row += 1

            # Widgets:
            label = ttk.Label(
                flow_object_properties_frame,
                text=property_name.replace("_", " ").title(),
            )

            description_label = ttk.Label(
                flow_object_properties_frame, text=property_description["description"]
            )

            unit_label = ttk.Label(
                flow_object_properties_frame, text=property_description.get("unit", "")
            )

            variable = tk.StringVar(
                value=str(flow_object["properties"][property_name] or "")
            )

            if property_description["type"] == NUMBER_PROPERTY_TYPE:
                validate_command = (
                    self.window.register(validate_number),
                    "%P",
                )

                entry = ttk.Entry(
                    flow_object_properties_frame,
                    width=INPUT_WIDTH,
                    textvariable=variable,
                    validate="key",
                    validatecommand=validate_command,
                )

            else:
                entry = ttk.Entry(
                    flow_object_properties_frame,
                    width=INPUT_WIDTH,
                    textvariable=variable,
                )

            # Event binding:
            entry.bind(
                "<FocusOut>",
                lambda event, flow_object=flow_object, property_name=property_name, property_type=property_description["type"], variable=variable: (
                    self.commit_property_value(
                        flow_object["properties"],
                        property_name,
                        property_type,
                        variable,
                    )
                ),
            )

            entry.bind(
                "<Return>",
                lambda event, flow_object=flow_object, property_name=property_name, property_type=property_description["type"], variable=variable: (
                    self.commit_property_value(
                        flow_object["properties"],
                        property_name,
                        property_type,
                        variable,
                    )
                ),
            )

            # Display widgets:
            description_label.grid(
                row=row,
                column=0,
                columnspan=2,
                sticky="w",
            )
            label.grid(row=row + 1, column=0, sticky="w")
            entry.grid(row=row + 1, column=1, sticky="w")
            unit_label.grid(row=row + 1, column=2, sticky="w")

            row += PROPERTY_ROW_HEIGHT

        # Process Requirements
        # ==========================

        # Frame widget:
        process_requirements_frame = ttk.LabelFrame(
            self.right_content_frame,
            text="Process Requirements",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Display frame widget:
        process_requirements_frame.grid(
            row=row,
            column=0,
            columnspan=3,
            sticky="ew",
        )

        # Grid:
        process_requirements_frame.columnconfigure(0, weight=1)
        process_requirements_frame.columnconfigure(1, weight=0)
        process_requirements_frame.columnconfigure(2, weight=0)

        # Processing entities:
        process_requirements_row = 0
        processing_entities = self.get_processing_entities()

        if not processing_entities:
            # No processing entities message:
            no_processing_entities_label = ttk.Label(
                process_requirements_frame, text="No Processing Entities defined."
            )

            # Display no processing entities message:
            no_processing_entities_label.grid(
                row=process_requirements_row,
                column=0,
                columnspan=3,
                sticky="w",
            )

            process_requirements_row += 1

        else:
            for processing_entity_index, processing_entity in enumerate(
                processing_entities
            ):
                if processing_entity_index > 0:
                    # Widgets:
                    processing_entity_separator = ttk.Separator(
                        process_requirements_frame, orient="horizontal"
                    )

                    # Display widgets:
                    processing_entity_separator.grid(
                        row=process_requirements_row,
                        column=0,
                        columnspan=3,
                        sticky="ew",
                    )

                    process_requirements_row += 1

                # Widgets:
                processing_entity_label = ttk.Label(
                    process_requirements_frame,
                    text=f'Consumption at "{processing_entity["name"]}":',
                )

                # Display widgets:
                processing_entity_label.grid(
                    row=process_requirements_row,
                    column=0,
                    columnspan=3,
                    sticky="w",
                )

                process_requirements_row += 1

                # Process supply relationships:
                process_supply_relationships = []

                for relationship in self.model_data["relationships"]:
                    if relationship["target"] != processing_entity["id"]:
                        continue

                    process_supply_entity = next(
                        entity
                        for entity in self.model_data["entities"]
                        if entity["id"] == relationship["source"]
                    )

                    if is_supply_source(process_supply_entity, self.model_data, self.schema):
                        process_supply_relationships.append(relationship)

                if not process_supply_relationships:
                    # No process supplies message:
                    no_process_supplies_label = ttk.Label(
                        process_requirements_frame, text="No Process Supplies defined."
                    )

                    # Display no process supplies message:
                    no_process_supplies_label.grid(
                        row=process_requirements_row,
                        column=0,
                        columnspan=3,
                        sticky="w",
                    )

                    process_requirements_row += 1

                else:
                    # Process supplies:
                    for relationship in process_supply_relationships:
                        process_supply_entity = next(
                            entity
                            for entity in self.model_data["entities"]
                            if entity["id"] == relationship["source"]
                        )

                        # Widgets:
                        process_supply_label = ttk.Label(
                            process_requirements_frame,
                            text=process_supply_entity["name"],
                        )
                        quantity_variable = tk.StringVar(
                            value=str(
                                flow_object["process_requirements"]
                                .get(processing_entity["id"], {})
                                .get(process_supply_entity["id"], "")
                            )
                        )
                        quantity_validate_command = (
                            self.window.register(validate_number),
                            "%P",
                        )
                        quantity_entry = ttk.Entry(
                            process_requirements_frame,
                            width=INPUT_WIDTH,
                            textvariable=quantity_variable,
                            validate="key",
                            validatecommand=quantity_validate_command,
                        )

                        # Event binding:
                        quantity_entry.bind(
                            "<FocusOut>",
                            lambda event, flow_object=flow_object, processing_entity_id=processing_entity["id"], process_supply_entity_id=process_supply_entity["id"], variable=quantity_variable: (
                                self.commit_process_requirement(
                                    flow_object,
                                    processing_entity_id,
                                    process_supply_entity_id,
                                    variable,
                                )
                            ),
                        )

                        quantity_entry.bind(
                            "<Return>",
                            lambda event, flow_object=flow_object, processing_entity_id=processing_entity["id"], process_supply_entity_id=process_supply_entity["id"], variable=quantity_variable: (
                                self.commit_process_requirement(
                                    flow_object,
                                    processing_entity_id,
                                    process_supply_entity_id,
                                    variable,
                                )
                            ),
                        )

                        # Display widgets:
                        process_supply_label.grid(
                            row=process_requirements_row,
                            column=0,
                            sticky="w",
                        )
                        quantity_entry.grid(
                            row=process_requirements_row,
                            column=1,
                            sticky="w",
                        )

                        process_requirements_row += 1

        bind_canvas_mousewheel(self.right_canvas)

    def load_flow_objects(self):
        self.flow_object_listbox.delete(0, tk.END)

        for flow_object in self.model_data["flow_objects"]:
            self.flow_object_listbox.insert(tk.END, flow_object["name"])

    def delete_flow_object(self):
        selected_index = self.flow_object_listbox.curselection()

        if not selected_index:
            return

        del self.model_data["flow_objects"][selected_index[0]]
        self.flow_object_listbox.delete(selected_index[0])

        # Clear editor:
        for widget in self.right_content_frame.winfo_children():
            widget.destroy()

        self.update_model_changed_state()

    def create_widgets(self):

        # Main Frame
        # ==========================

        # Widgets:
        self.main_frame = ttk.Frame(self.window, padding=PAD)

        # Grid:
        self.main_frame.rowconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=0)
        self.main_frame.columnconfigure(0, weight=0)
        self.main_frame.columnconfigure(1, weight=1)

        # Display widgets:
        self.main_frame.grid(row=0, column=0, sticky="nsew")

        # Left Frame
        # ==========================

        # Frame widget:
        self.left_frame = ttk.LabelFrame(
            self.main_frame,
            text="Existing",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Grid:
        self.left_frame.rowconfigure(0, weight=1)
        self.left_frame.columnconfigure(0, weight=1)

        # Child widgets:
        self.flow_object_listbox = tk.Listbox(self.left_frame)

        # Event binding:
        self.flow_object_listbox.bind("<<ListboxSelect>>", self.select_flow_object)

        # Display frame widget:
        self.left_frame.grid(row=0, column=0, sticky="nsew")

        # Display child widgets:
        self.flow_object_listbox.grid(row=0, column=0, sticky="nsew")

        # Right Frame
        # ==========================

        # Frame widget:
        self.right_frame = ttk.LabelFrame(
            self.main_frame,
            text="Editor",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Child widgets:
        self.right_canvas = tk.Canvas(self.right_frame, highlightthickness=0)
        self.right_scrollbar = ttk.Scrollbar(
            self.right_frame, orient="vertical", command=self.right_canvas.yview
        )

        # Configure canvas:
        self.right_canvas.configure(yscrollcommand=self.right_scrollbar.set)
        bind_canvas_mousewheel(self.right_canvas)

        # Grid:
        self.right_frame.rowconfigure(0, weight=1)
        self.right_frame.columnconfigure(0, weight=1)

        # Display frame widget:
        self.right_frame.grid(row=0, column=1, sticky="nsew")

        # Display child widgets:
        self.right_canvas.grid(row=0, column=0, sticky="nsew")
        self.right_scrollbar.grid(row=0, column=1, sticky="ns")

        # Content frame:
        self.right_content_frame = ttk.Frame(self.right_canvas)

        # Grid:
        self.right_content_frame.columnconfigure(0, weight=1)

        # Display content frame:
        self.right_canvas.create_window(
            (0, 0), window=self.right_content_frame, anchor="nw"
        )

        # Event binding:
        self.right_canvas.bind(
            "<Configure>",
            lambda event: self.right_canvas.itemconfigure(
                self.right_canvas.find_withtag("all")[0], width=event.width
            ),
        )

        # Update scroll region:
        self.right_content_frame.bind(
            "<Configure>",
            lambda event: self.right_canvas.configure(
                scrollregion=self.right_canvas.bbox("all")
            ),
        )

        # Button Frame
        # ==========================

        # Frame widget:
        self.button_frame = ttk.Frame(self.main_frame)

        # Grid:
        self.button_frame.columnconfigure(2, weight=1)

        # Display frame widget:
        self.button_frame.grid(row=1, column=0, columnspan=2, sticky="ew")

        # Child widgets:
        self.add_button = ttk.Button(
            self.button_frame,
            width=BUTTON_WIDTH,
            text="Add",
            command=self.add_flow_object,
        )
        self.delete_button = ttk.Button(
            self.button_frame,
            width=BUTTON_WIDTH,
            text="Delete",
            command=self.delete_flow_object,
        )
        self.save_button = ttk.Button(
            self.button_frame,
            width=BUTTON_WIDTH,
            text="Save",
            command=self.save_callback,
        )

        # Display child widgets:
        self.add_button.grid(row=0, column=0, sticky="w")
        self.delete_button.grid(row=0, column=1, sticky="w")
        self.save_button.grid(row=0, column=2, sticky="e")

        # Load existing Flow Objects:
        self.load_flow_objects()
