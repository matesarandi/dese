def validate_number(value):
    if value == "":
        return True

    try:
        float(value)
        return True

    except ValueError:
        return False


def convert_property_value(value, property_type):
    if property_type == "number" and value != "":
        return float(value)

    return value
