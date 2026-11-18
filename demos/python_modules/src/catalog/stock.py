def available(stock, reserved=0):
    if stock < 0 or reserved < 0:
        raise ValueError("counts cannot be negative")
    return max(0, stock - reserved)
