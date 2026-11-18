def total(prices, discount=0):
    if any(price < 0 for price in prices):
        raise ValueError("prices cannot be negative")
    if not 0 <= discount <= 100:
        raise ValueError("discount must be between 0 and 100")
    return sum(prices) * (1 - discount / 100)
