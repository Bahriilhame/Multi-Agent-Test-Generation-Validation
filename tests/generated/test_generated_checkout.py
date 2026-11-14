import pytest
from shop.checkout import (
    calculate_subtotal,
    apply_discount,
    calculate_shipping,
    validate_customer,
    create_order
)

def test_calculate_subtotal_empty_cart():
    with pytest.raises(ValueError):
        calculate_subtotal([])

def test_calculate_subtotal_negative_price():
    items = [
        {"price": -100, "quantity": 2}
    ]
    with pytest.raises(ValueError):
        calculate_subtotal(items)

def test_calculate_subtotal_zero_quantity():
    items = [
        {"price": 100, "quantity": 0}
    ]
    with pytest.raises(ValueError):
        calculate_subtotal(items)

def test_calculate_shipping_negative_amount():
    with pytest.raises(ValueError):
        calculate_shipping(-1)

def test_calculate_shipping_zero_amount():
    assert calculate_shipping(0) == 30

def test_calculate_shipping_499_amount():
    assert calculate_shipping(499) == 30

def test_calculate_shipping_500_amount():
    assert calculate_shipping(500) == 0

def test_calculate_shipping_501_amount():
    assert calculate_shipping(501) == 0

def test_validate_customer_empty_name():
    customer = {
        "name": "",
        "email": "test@example.com"
    }
    assert not validate_customer(customer["name"], customer["email"])

def test_validate_customer_whitespace_name():
    customer = {
        "name": "   ",
        "email": "test@example.com"
    }
    assert not validate_customer(customer["name"], customer["email"])

def test_validate_customer_invalid_email():
    customer = {
        "name": "John Doe",
        "email": "testexample.com"
    }
    assert not validate_customer(customer["name"], customer["email"])

def test_validate_customer_valid_customer():
    customer = {
        "name": "John Doe",
        "email": "test@example.com"
    }
    assert validate_customer(customer["name"], customer["email"])

def test_create_order_invalid_customer():
    customer = {
        "name": "",
        "email": "test@example.com"
    }
    with pytest.raises(ValueError):
        create_order([], 10, customer)

def test_create_order_valid_order():
    items = [
        {"price": 100, "quantity": 2},
        {"price": 50, "quantity": 1}
    ]
    customer = {
        "name": "John Doe",
        "email": "test@example.com"
    }
    order = create_order(items, 10, customer)
    assert order["subtotal"] == 250
    assert order["discounted_total"] == 225
    assert order["shipping"] == 30
    assert order["final_total"] == 255

def test_apply_discount_negative_amount():
    with pytest.raises(ValueError):
        apply_discount(-1, 10)

def test_apply_discount_negative_discount():
    with pytest.raises(ValueError):
        apply_discount(100, -1)

def test_apply_discount_high_discount():
    with pytest.raises(ValueError):
        apply_discount(100, 101)

def test_apply_discount_zero_discount():
    assert apply_discount(100, 0) == 100

def test_apply_discount_full_discount():
    assert apply_discount(100, 100) == 0

def test_apply_discount_normal_discount():
    assert apply_discount(250, 10) == 225
