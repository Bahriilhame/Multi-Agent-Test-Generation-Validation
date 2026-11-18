from catalog.stock import available


def test_stock_after_reservations():
    assert available(10, 3) == 7
