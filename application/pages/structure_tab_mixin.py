import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from dese.constants import (
    BUTTON_WIDTH,
    ENTITY_ID_COLUMN_WIDTH,
    ENTITY_INPUTS_COLUMN_WIDTH,
    ENTITY_NAME_COLUMN_WIDTH,
    ENTITY_OUTPUTS_COLUMN_WIDTH,
    ENTITY_ROLE_COLUMN_WIDTH,
    INPUT_WIDTH,
    NUMBER_PROPERTY_TYPE,
    PAD,
    PROPERTY_ROW_HEIGHT,
    SPINBOX_WIDTH,
)
from dese.core.model import get_allowed_entities, is_main_entity
from dese.utils import bind_canvas_mousewheel, validate_number


class StructureTabMixin:
    """The Structure tab: the entity table, and the Name/Type/Process-boundary,
    Property and Relationship editors for the selected entity. Mixed into
    ModelEditorPage — its methods rely on attributes ModelEditorPage owns
    (model_data, schema, selected_entity, structure_tab, etc.)."""

    def measure_column_width(self, texts, font, padding=20):
        return max(font.measure(text) for text in texts) + padding

    def create_structure_tab(self):
        # Grid:
        self.structure_tab.rowconfigure(0, weight=1)
        self.structure_tab.rowconfigure(1, weight=1)
        self.structure_tab.columnconfigure(0, weight=1)

        self.build_entity_table_section()
        self.build_editor_frames()
        self.build_property_editor()
        self.build_relationship_editor()
        self.build_basic_editor_inputs()

    def build_entity_table_section(self):
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

    def build_editor_frames(self):
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

    def build_property_editor(self):
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

    def build_relationship_editor(self):
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

    def build_basic_editor_inputs(self):
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

            allowed_entities = get_allowed_entities(
                self.selected_entity,
                self.model_data,
                self.schema,
                "input",
                relationship_id,
            )
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

            allowed_entities = get_allowed_entities(
                self.selected_entity,
                self.model_data,
                self.schema,
                "output",
                relationship_id,
            )
            combobox["values"] = [""] + [entity["name"] for entity in allowed_entities]

            # Event binding:
            combobox.bind("<<ComboboxSelected>>", self.relationship_selected)

            label.grid(row=index, column=0, sticky="w")
            combobox.grid(row=index, column=1, sticky="w")

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
            is_main = is_main_entity(entity, self.model_data, self.schema)
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
