import pytest

from calculator import average


def test_average_of_values():
    assert average([2, 4, 6]) == 4


def test_average_rejects_empty_input():
    with pytest.raises(ValueError):
        average([])
