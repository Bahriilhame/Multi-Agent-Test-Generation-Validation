
from shop.checkout import (
    calculate_subtotal,
    apply_discount
)


def test_calculate_subtotal():
    items = [
        {"price": 100, "quantity": 2},
        {"price": 50, "quantity": 1}
    ]

    result = calculate_subtotal(items)

    assert result == 250


def test_calculate_subtotal_invalid_quantity():
    items = [
        {"price": 100, "quantity": 0}
    ]

    try:
        calculate_subtotal(items)
        assert False, "Une exception était attendue"
    except ValueError:
        pass


def test_apply_discount():
    result = apply_discount(250, 10)

    assert result == 225
