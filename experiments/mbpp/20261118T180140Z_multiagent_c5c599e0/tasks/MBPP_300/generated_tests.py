from solution import count_binary_seq

def test_mbpp_zero():
    assert count_binary_seq(0) == 1.0

def test_mbpp_small():
    assert count_binary_seq(1) == 2.0

def test_mbpp_even():
    assert count_binary_seq(4) == 70.0

def test_mbpp_odd():
    assert count_binary_seq(5) == 252.0

def test_mbpp_large():
    assert count_binary_seq(10) == 184756.0

def test_mbpp_negative():
    assert count_binary_seq(-1) == 0.0
