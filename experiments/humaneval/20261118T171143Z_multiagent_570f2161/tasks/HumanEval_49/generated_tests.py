from solution import modp

def test_modp_large_exponent():
    assert modp(1000, 101) == 1

def test_modp_large_prime():
    assert modp(3, 1000003) == 8

def test_modp_zero_exponent():
    assert modp(0, 101) == 1

def test_modp_one_exponent():
    assert modp(1, 101) == 2

def test_modp_negative_exponent():
    assert modp(-1, 101) == 51

def test_modp_large_base():
    assert modp(100, 1000003) == 1
