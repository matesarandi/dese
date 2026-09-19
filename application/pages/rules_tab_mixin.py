import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from dese.constants import (
    BUTTON_WIDTH,
    END_OF_PROCESS_ROUTING_TARGET,
    INPUT_WIDTH,
    NUMBER_PROPERTY_TYPE,
    PAD,
)
from dese.core.model import (
    find_decision_points,
    get_baseline_scrap_eligible_entity_ids,
    get_baseline_scrap_parameter,
    get_failure_eligible_entity_ids,
    get_failure_parameter,
    get_maintenance_dispatch_priority,
    get_maintenance_parameter,
    get_maintenance_resource_parameter,
    get_routing_condition_owner,
    get_routing_scope_candidates,
    get_routing_scope_label,
    get_routing_scope_values,
    get_routing_target_ids,
    set_baseline_scrap_parameter,
    set_failure_parameter,
    set_maintenance_dispatch_priority,
    set_maintenance_parameter,
    set_maintenance_resource_parameter,
    set_routing_condition_owner,
)
from dese.utils import (
    bind_canvas_mousewheel,
    convert_property_value,
    measure_column_width,
    validate_number,
)


class RulesTabMixin:
    """The Rules tab: per-entity Routing/Failure/Maintenance/Baseline Scrap
    rule editors, plus the model-global Maintenance Resource editor. Mixed
    into ModelEditorPage — its methods rely on attributes ModelEditorPage
    owns (model_data, schema, rules_tab, etc.)."""

    def get_routing_target_label(self, target_id):
        # The virtual End of Process destination isn't a real Entity, so
        # there's no name to look up for it — its label is derived from
        # the same field name as the target value itself
        # (END_OF_PROCESS_ROUTING_TARGET), not a separately hardcoded
        # string. Title-cased word by word, except "of" — plain .title()
        # would capitalize that too ("End Of Process").
        if target_id == END_OF_PROCESS_ROUTING_TARGET:
            return " ".join(
                word if word == "of" else word.capitalize()
                for word in END_OF_PROCESS_ROUTING_TARGET.split("_")
            )

        return self.get_entity_name(target_id)

    def refresh_rules_tab(self):
        # Rebuilding destroys and recreates every widget below, which
        # briefly collapses the scrollable content to near-zero height —
        # the canvas clamps its scroll position to the top for that instant
        # and doesn't return on its own once the content regrows. Save and
        # restore it around the rebuild so a mid-scroll selection doesn't
        # visibly jump the page back to the top.
        scroll_position = self.rules_canvas.yview()[0]

        self.update_entity_rules_frame()
        self.update_maintenance_resource_frame()

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

        # Entity Rules
        # ==========================
        # One "AT ..." LabelFrame per Entity that has Routing (it's a
        # decision point) and/or Failure/Maintenance (it supports_failure)
        # — whichever apply, nested inside that one Entity's frame, added
        # in update_entity_rules_frame.

        # Frame widget:
        self.entity_rules_frame = ttk.Frame(self.rules_content)

        # Grid:
        self.entity_rules_frame.columnconfigure(0, weight=1)

        # Display frame widget:
        self.entity_rules_frame.grid(row=0, column=0, sticky="new")

        # Maintenance Resource
        # ==========================
        # Not tied to any single Entity — the shared capacity/dispatch
        # policy for the whole model's maintenance/repair work — so it
        # stays outside the per-Entity "AT ..." blocks above.

        # Frame widget:
        self.maintenance_resource_frame = ttk.LabelFrame(
            self.rules_content,
            text="Maintenance Resource",
            style="DESE.Section.TLabelframe",
            padding=PAD,
        )

        # Grid:
        self.maintenance_resource_frame.columnconfigure(3, weight=1)

        # Display frame widget:
        self.maintenance_resource_frame.grid(row=1, column=0, sticky="new")

        # Content:
        self.refresh_rules_tab()

    def update_entity_rules_frame(self):
        # Clear existing widgets:
        for widget in self.entity_rules_frame.winfo_children():
            widget.destroy()

        # An Entity gets an "AT ..." block if it's a decision point
        # (Routing applies), failure-eligible (Failure/Maintenance apply),
        # baseline-scrap-eligible (BaselineScrap applies), or any
        # combination — whichever sections are relevant appear nested
        # inside that one shared block, instead of separate top-level
        # sections each repeating the same Entity list.
        decision_point_ids = set(find_decision_points(self.model_data, self.schema))
        failure_eligible_ids = set(get_failure_eligible_entity_ids(self.model_data, self.schema))
        baseline_scrap_eligible_ids = set(
            get_baseline_scrap_eligible_entity_ids(self.model_data, self.schema)
        )
        relevant_entity_ids = [
            entity["id"]
            for entity in self.model_data["entities"]
            if entity["id"] in decision_point_ids
            or entity["id"] in failure_eligible_ids
            or entity["id"] in baseline_scrap_eligible_ids
        ]

        if not relevant_entity_ids:
            no_rules_label = ttk.Label(
                self.entity_rules_frame,
                text="No entities with Routing, Failure, Maintenance, or Baseline Scrap rules in this model yet.",
            )
            no_rules_label.grid(row=0, column=0, sticky="w")
            return

        for entity_index, entity_id in enumerate(relevant_entity_ids):
            entity = next(
                entity for entity in self.model_data["entities"] if entity["id"] == entity_id
            )

            # Widgets:
            entity_frame = ttk.LabelFrame(
                self.entity_rules_frame,
                text=f'AT "{self.get_entity_name(entity_id)}" ({entity["type"]})',
                style="DESE.Section.TLabelframe",
                padding=PAD,
            )

            # Grid:
            entity_frame.columnconfigure(0, weight=1)

            # Display widgets:
            entity_frame.grid(row=entity_index, column=0, sticky="new")

            row = 0

            if entity_id in decision_point_ids:
                # Widgets:
                routing_frame = ttk.LabelFrame(
                    entity_frame,
                    text="Routing",
                    style="DESE.Section.TLabelframe",
                    padding=PAD,
                )
                self.render_routing_matrix(routing_frame, entity, entity_id)

                # Display widgets:
                routing_frame.grid(row=row, column=0, sticky="new")

                row += 1

            if entity_id in failure_eligible_ids:
                # Widgets:
                failure_frame = ttk.LabelFrame(
                    entity_frame,
                    text="Failure",
                    style="DESE.Section.TLabelframe",
                    padding=PAD,
                )
                self.render_rule_property_form(
                    failure_frame, entity_id, "Failure", get_failure_parameter, set_failure_parameter
                )

                # Display widgets:
                failure_frame.grid(row=row, column=0, sticky="new")

                row += 1

                # Widgets:
                maintenance_frame = ttk.LabelFrame(
                    entity_frame,
                    text="Maintenance",
                    style="DESE.Section.TLabelframe",
                    padding=PAD,
                )
                self.render_rule_property_form(
                    maintenance_frame,
                    entity_id,
                    "Maintenance",
                    get_maintenance_parameter,
                    set_maintenance_parameter,
                )

                # Display widgets:
                maintenance_frame.grid(row=row, column=0, sticky="new")

                row += 1

            if entity_id in baseline_scrap_eligible_ids:
                # Widgets:
                baseline_scrap_frame = ttk.LabelFrame(
                    entity_frame,
                    text="Baseline Scrap",
                    style="DESE.Section.TLabelframe",
                    padding=PAD,
                )
                self.render_rule_property_form(
                    baseline_scrap_frame,
                    entity_id,
                    "BaselineScrap",
                    get_baseline_scrap_parameter,
                    set_baseline_scrap_parameter,
                )

                # Display widgets:
                baseline_scrap_frame.grid(row=row, column=0, sticky="new")

                row += 1

    def render_routing_matrix(self, parent_frame, entity, entity_id):
        # An Entity's own state is always a candidate; a Flow Object state
        # is only a candidate where this Entity type actually has a way to
        # read it (see get_routing_scope_candidates). Each candidate is one
        # row of the matrix below; each current output is one column, plus
        # a leading "unassigned" column.
        scope_candidates = get_routing_scope_candidates(entity, self.model_data, self.schema)

        # A real output relationship, or the virtual "End of Process"
        # destination end_of_process adds (self-referencing — see
        # get_routing_target_ids).
        target_ids = get_routing_target_ids(entity, self.model_data)

        # Grid:
        # A fixed column 0 width keeps the checkbox columns justified at
        # the same x position on every row, regardless of which value's
        # label is currently showing — same trick as the Failure/
        # Maintenance sections. It has to fit the longest text that starts
        # there, which includes the scope group labels ("Flow Object
        # Quality" etc., not just the value names) since those also start
        # in column 0, spanning across the rest — otherwise a long one
        # overflows past its own column budget into whatever sits to its
        # right.
        default_font = tkfont.nametofont("TkDefaultFont")
        label_column_width = measure_column_width(
            [get_routing_scope_label(scope, variable) for scope, variable in scope_candidates]
            + [
                value
                for scope, variable in scope_candidates
                for value in get_routing_scope_values(scope, variable, self.schema)
            ],
            default_font,
        )
        parent_frame.columnconfigure(0, minsize=label_column_width)
        # Each output column is sized to its own header text (the Entity's
        # name) the same way, instead of a guessed padding value — a short
        # name gets a narrower column, a long one a wider column, and the
        # checkbox centers within it either way.
        for column_index, target_id in enumerate(target_ids):
            parent_frame.columnconfigure(
                1 + column_index,
                minsize=measure_column_width(
                    [self.get_routing_target_label(target_id)], default_font
                ),
            )
        # The trailing column is a spacer that absorbs the extra width, so
        # the value/checkbox columns stay packed together on the left
        # instead of stretching to fill the frame.
        parent_frame.columnconfigure(1 + len(target_ids), weight=1)

        row = 0

        # Widgets:
        # Every scope here (the Entity's own state, any Flow Object state)
        # is evaluated at the same moment — when this Flow Object's cycle
        # at this Entity concludes — so it's stated once per decision
        # point instead of repeated per scope group.
        timing_note = ttk.Label(
            parent_frame, text="Values are read once the operation finishes."
        )

        # Display widgets:
        # Spans the full row (not just column 0) so this sentence, which
        # is wider than any single column, doesn't need to be folded into
        # the column-0 width measurement above.
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
            output_header = ttk.Label(
                parent_frame, text=self.get_routing_target_label(target_id)
            )

            # Display widgets:
            output_header.grid(row=row, column=1 + column_index, pady=(0, 4))

        row += 1

        for scope_index, (scope, variable) in enumerate(scope_candidates):
            if scope_index > 0:
                # Widgets:
                scope_separator = ttk.Separator(parent_frame, orient="horizontal")

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
                parent_frame, text=get_routing_scope_label(scope, variable)
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
                value_label = ttk.Label(parent_frame, text=value)

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
                        parent_frame,
                        command=lambda entity_id=entity_id, scope=scope, variable=variable, value=value, target_id=target_id: (
                            self.toggle_routing_condition_owner(
                                entity_id, scope, variable, value, target_id
                            )
                        ),
                    )

                    # A fresh Checkbutton defaults to "alternate" (a dash,
                    # neither checked nor unchecked) regardless of
                    # variable binding — clear it explicitly, or every box
                    # looks the same and clicking looks like it does
                    # nothing.
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

    def render_rule_property_form(
        self, parent_frame, entity_id, rule_type, get_parameter, set_parameter
    ):
        # Shared by Failure and Maintenance — both are just a flat list of
        # numeric fields for one Entity, read from the same rule_schemas
        # shape. Failure/Maintenance differ only in which rule_type they
        # name and which get/set pair they read and write through.
        rule_schema = self.schema.get_rule_schema(self.model_data["domain"], rule_type)
        fields = rule_schema["properties"] if rule_schema else {}

        # A fixed column 0 width (the longest field label here) keeps the
        # entry/unit columns justified at the same x position on every row,
        # regardless of which field's label is currently showing.
        default_font = tkfont.nametofont("TkDefaultFont")
        label_column_width = measure_column_width(
            [name.replace("_", " ").title() for name in fields], default_font
        )
        parent_frame.columnconfigure(0, minsize=label_column_width)
        parent_frame.columnconfigure(3, weight=1)

        row = 0

        for field_index, (field_name, field_schema) in enumerate(fields.items()):
            if field_index > 0:
                # Widgets:
                field_separator = ttk.Separator(parent_frame, orient="horizontal")

                # Display widgets:
                field_separator.grid(row=row, column=0, columnspan=4, sticky="ew")

                row += 1

            # Widgets:
            validate_command = (self.register(validate_number), "%P")

            description_label = ttk.Label(parent_frame, text=field_schema["description"])
            field_label_widget = ttk.Label(
                parent_frame, text=field_name.replace("_", " ").title()
            )
            field_entry = ttk.Entry(
                parent_frame,
                width=INPUT_WIDTH,
                validate="key",
                validatecommand=validate_command,
            )
            field_unit_label = ttk.Label(parent_frame, text=field_schema.get("unit", ""))

            value = get_parameter(self.model_data, entity_id, field_name)

            if value is not None:
                field_entry.insert(0, str(value))

            # Event binding:
            field_entry.bind(
                "<FocusOut>",
                lambda event, entity_id=entity_id, field_name=field_name, entry=field_entry, get_parameter=get_parameter, set_parameter=set_parameter: (
                    self.commit_rule_parameter(
                        entity_id, field_name, entry, get_parameter, set_parameter
                    )
                ),
            )
            field_entry.bind(
                "<Return>",
                lambda event, entity_id=entity_id, field_name=field_name, entry=field_entry, get_parameter=get_parameter, set_parameter=set_parameter: (
                    self.commit_rule_parameter(
                        entity_id, field_name, entry, get_parameter, set_parameter
                    )
                ),
            )

            # Display widgets:
            description_label.grid(row=row, column=0, columnspan=4, sticky="w")
            row += 1
            field_label_widget.grid(row=row, column=0, sticky="w")
            field_entry.grid(row=row, column=1, sticky="w")
            field_unit_label.grid(row=row, column=2, sticky="w")

            row += 1

    def commit_rule_parameter(self, entity_id, field_name, entry, get_parameter, set_parameter):
        new_value = convert_property_value(entry.get(), NUMBER_PROPERTY_TYPE)

        if get_parameter(self.model_data, entity_id, field_name) != new_value:
            set_parameter(self.model_data, entity_id, field_name, new_value)
            self.update_model_changed_state()

        entry.delete(0, "end")
        entry.insert(0, str(get_parameter(self.model_data, entity_id, field_name) or ""))

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
            minsize=measure_column_width(
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
