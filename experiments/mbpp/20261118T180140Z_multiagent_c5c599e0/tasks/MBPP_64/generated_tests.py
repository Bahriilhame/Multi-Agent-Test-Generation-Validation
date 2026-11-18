from solution import subject_marks

def test_mbpp_empty_list():
    assert subject_marks([]) == []

def test_mbpp_single_element():
    assert subject_marks([('Maths', 97)]) == [('Maths', 97)]

def test_mbpp_reversed_order():
    assert subject_marks([('Maths', 97), ('English', 88)]) == [('English', 88), ('Maths', 97)]

def test_mbpp_negative_values():
    assert subject_marks([('Maths', -97), ('English', -88)]) == [('English', -88), ('Maths', -97)]

def test_mbpp_float_values():
    assert subject_marks([('Maths', 97.5), ('English', 88.2)]) == [('English', 88.2), ('Maths', 97.5)]

def test_mbpp_mixed_types():
    assert subject_marks([('Maths', 97), ('English', '88')]) == [('English', '88'), ('Maths', 97)]
