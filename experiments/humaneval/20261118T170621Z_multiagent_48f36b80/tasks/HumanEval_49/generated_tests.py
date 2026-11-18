from solution import modp

def test_negative_exponent():
    assert modp(-1, 5) == 1

def test_negative_modulus():
    with pytest.raises(ValueError):
        modp(3, -1)

def test_zero_exponent():
    assert modp(0, 101) == 1

def test_large_exponent():
    assert modp(1000, 101) == 1

def test_large_modulus():
    assert modp(3, 1000000007) == 8

def test_one_modulus():
    assert modp(3, 1) == 0
