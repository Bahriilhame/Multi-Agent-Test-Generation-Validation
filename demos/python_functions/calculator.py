"""Small standalone project for the SmartTest-AI demo."""


def average(values):
    if not values:
        raise ValueError("values cannot be empty")
    return sum(values) / len(values)


def clamp(value, lower, upper):
    if lower > upper:
        raise ValueError("lower must not exceed upper")
    return max(lower, min(value, upper))
