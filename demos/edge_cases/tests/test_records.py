import pytest

from records import first_record, parse_age


@pytest.mark.parametrize("value", ["not an age", None, -1, 131])
def test_invalid_ages_raise(value):
    with pytest.raises(ValueError):
        parse_age(value)


def test_first_record_rejects_none():
    with pytest.raises(TypeError):
        first_record(None)
