from catalog.pricing import total


def test_total_without_discount():
    assert total([5, 7]) == 12
