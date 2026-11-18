import pytest
from solution import modp

def test_modp_negative_exponent():
    assert modp(-1, 5) == 1, "2^(-1) % 5 should be 1"

def test_modp_negative_modulus():
    assert modp(3, -5) == -2

def test_modp_zero_exponent():
    assert modp(0, 101) == 1, "2^0 % 101 should be 1"

def test_modp_large_exponent():
    assert modp(1000, 101) == 1, "2^1000 % 101 should be 1"

def test_modp_large_modulus():
    assert modp(3, 1000000007) == 8, "2^3 % 1000000007 should be 8"

def test_modp_one_modulus():
    assert modp(3, 1) == 0, "2^3 % 1 should be 0"

def test_modp_one_exponent():
    assert modp(1, 5) == 2, "2^1 % 5 should be 2"

def test_modp_zero_modulus():
    with pytest.raises(ZeroDivisionError):
        modp(3, 0)

def test_modp_one_argument():
    try:
        modp(3)
    except TypeError as e:
        assert str(e) == "modp() missing 1 required positional argument: 'p'", "Missing second argument should raise TypeError"

def test_modp_non_integer_arguments():
    with pytest.raises(TypeError):
        modp(3.5, 5)

def test_modp_large_numbers():
    # Keep this as a bounded performance case: modp iterates once per exponent.
    assert modp(10000, 1000000007) == pow(2, 10000, 1000000007)
