# ==========================
# Constants
# ==========================

PAD = 4

BUTTON_WIDTH = 12

INPUT_WIDTH = 12

SPINBOX_WIDTH = 4

# ==========================
# Window Sizes
# ==========================

START_WINDOW_SIZE = "500x500"

MODEL_EDITOR_WINDOW_SIZE = "1100x750"

FLOW_OBJECT_WINDOW_SIZE = "800x600"

# ==========================
# Entity Table Column Widths
# ==========================

ENTITY_ID_COLUMN_WIDTH = 50

ENTITY_NAME_COLUMN_WIDTH = 110

# Type column width is computed at runtime from the schema's actual entity
# type names (see ModelEditorPage.measure_column_width) — there is no fixed
# constant for it.

ENTITY_ROLE_COLUMN_WIDTH = 85

ENTITY_INPUTS_COLUMN_WIDTH = 250

ENTITY_OUTPUTS_COLUMN_WIDTH = 250

# ==========================
# Typography
# ==========================

TITLE_FONT = ("Arial", 16, "bold")

WRAP_LENGTH = 400

# ==========================
# Property Editor Layout
# ==========================

# Number of grid rows each property occupies (description, input, separator).
PROPERTY_ROW_HEIGHT = 3

# ==========================
# Schema Versioning
# ==========================

# schema.json and model files must declare this exact version. Bump this and
# add migration/compatibility handling in SchemaLoader/ModelEditorPage.load_model
# whenever the schema or model file format changes in a breaking way.
CURRENT_SCHEMA_VERSION = "1.0"

# ==========================
# Schema Vocabulary
# ==========================

# Property type recognized by validate_number/convert_property_value.
NUMBER_PROPERTY_TYPE = "number"

# Entity hierarchy role recognized by SchemaLoader-provided entity schemas.
MAIN_HIERARCHY_ROLE = "main"

# Entity types with simulation-specific behaviour in the Flow Object editor.
ENTITY_TYPE_PROCESSING = "Processing"

ENTITY_TYPE_PROCESS_SUPPLY = "Process Supply"

# Routing output target for the virtual "End of Process" destination an
# end_of_process Entity gets, alongside any real output relationships — not
# a real Entity id (those are always "E001" etc.), so it can never collide.
# Its display label is derived from this same field name, not a separate
# hardcoded string — see ModelEditorPage.get_routing_target_label.
END_OF_PROCESS_ROUTING_TARGET = "end_of_process"
