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

def test_calculate_subtotal_valid_items():
    items = [
        {"price": 100, "quantity": 2},
        {"price": 50, "quantity": 1}
    ]
    assert calculate_subtotal(items) == 250

def test_apply_discount_negative_total():
    with pytest.raises(ValueError):
        apply_discount(-250, 10)

def test_apply_discount_invalid_discount():
    with pytest.raises(ValueError):
        apply_discount(250, 105)

def test_apply_discount_zero_discount():
    assert apply_discount(250, 0) == 250

def test_apply_discount_full_discount():
    assert apply_discount(250, 100) == 0

def test_calculate_shipping_free_shipping():
    assert calculate_shipping(500) == 0

def test_calculate_shipping_standard_shipping():
    assert calculate_shipping(499) == 30

def test_calculate_shipping_free_shipping_limit():
    assert calculate_shipping(500) == 0

def test_calculate_shipping_standard_shipping_limit():
    assert calculate_shipping(499) == 30

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
