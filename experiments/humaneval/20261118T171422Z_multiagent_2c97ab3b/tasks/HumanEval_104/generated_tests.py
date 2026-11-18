from solution import unique_digits

def test_empty_list():
    assert unique_digits([]) == []

def test_single_even_digit():
    assert unique_digits([2]) == []

def test_single_odd_digit():
    assert unique_digits([1]) == [1]

def test_mixed_digits():
    assert unique_digits([123, 456, 789]) == [789]

def test_all_even_digits():
    assert unique_digits([222, 444, 666]) == []

def test_negative_numbers():
    assert unique_digits([-15, -33, -1422, -1]) == [-1]
