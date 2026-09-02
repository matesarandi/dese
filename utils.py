def validate_number(value):
    if value == "":
        return True

    try:
        float(value)
        return True

    except ValueError:
        return False
