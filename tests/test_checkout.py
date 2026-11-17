
import pytest

from shop.checkout import (
    calculate_subtotal,
    apply_discount,
    calculate_shipping,
    create_order,
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


def test_calculate_subtotal_accepts_zero_price():
    assert calculate_subtotal([{"price": 0, "quantity": 1}]) == 0


def test_calculate_subtotal_empty_cart_error_message():
    with pytest.raises(ValueError) as error:
        calculate_subtotal([])

    assert str(error.value) == "La commande est vide"


def test_calculate_subtotal_invalid_product_error_message():
    with pytest.raises(ValueError) as error:
        calculate_subtotal([{"price": 10, "quantity": 0}])

    assert str(error.value) == "Produit invalide"


def test_apply_discount_accepts_zero_amount():
    assert apply_discount(0, 0) == 0


def test_apply_discount_negative_amount_error_message():
    with pytest.raises(ValueError) as error:
        apply_discount(-1, 10)

    assert str(error.value) == "Montant invalide"


def test_apply_discount_invalid_percentage_error_message():
    with pytest.raises(ValueError) as error:
        apply_discount(100, 101)

    assert str(error.value) == "Réduction invalide"


def test_calculate_shipping_negative_amount_error_message():
    with pytest.raises(ValueError) as error:
        calculate_shipping(-1)

    assert str(error.value) == "Montant invalide"


def test_create_order_invalid_customer_error_message():
    with pytest.raises(ValueError) as error:
        create_order([], 10, {"name": "", "email": "valid@example.com"})

    assert str(error.value) == "Client invalide"
