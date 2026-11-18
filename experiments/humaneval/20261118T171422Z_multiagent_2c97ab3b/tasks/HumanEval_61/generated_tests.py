from solution import correct_bracketing

def test_empty_string():
    assert correct_bracketing("") == True

def test_single_opening_bracket():
    assert correct_bracketing("(") == False

def test_single_closing_bracket():
    assert correct_bracketing(")") == False

def test_mixed_brackets():
    assert correct_bracketing("(()))(") == False

def test_single_pair():
    assert correct_bracketing("()") == True

def test_nested_brackets():
    assert correct_bracketing("((()))") == True
