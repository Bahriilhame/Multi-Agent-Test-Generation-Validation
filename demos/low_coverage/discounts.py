def discount(price, percent):
    if price < 0:
        raise ValueError("price cannot be negative")
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    if percent == 100:
        return 0
    return price * (1 - percent / 100)
