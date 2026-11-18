def parse_age(value):
    try:
        age = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("age must be an integer") from error
    if age < 0:
        raise ValueError("age must not be negative")
    if age > 130:
        raise ValueError("age is outside the supported range")
    return age


def first_record(records):
    if records is None:
        raise TypeError("records cannot be None")
    if not records:
        raise LookupError("records are empty")
    return records[0]
