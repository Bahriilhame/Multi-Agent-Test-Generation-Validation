from solution import check_tuplex

def test_mbpp_empty_tuple():
    assert check_tuplex((), 'a') == False

def test_mbpp_single_element_tuple():
    assert check_tuplex(('a',), 'a') == True

def test_mbpp_tuple_with_mixed_types():
    assert check_tuplex((1, 'b', 3.14, 'd'), 'd') == True

def test_mbpp_tuple_with_nested_tuple():
    assert check_tuplex((1, (2, 3), 4), (2, 3)) == True

def test_mbpp_tuple_with_repeated_elements():
    assert check_tuplex(('a', 'a', 'a'), 'a') == True

def test_mbpp_tuple_with_large_elements():
    large_element = 'a' * 1000
    assert check_tuplex((large_element,), large_element) == True
