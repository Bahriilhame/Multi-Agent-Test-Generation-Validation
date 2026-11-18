from discounts import discount


def test_regular_discount():
    assert discount(100, 10) == 90
