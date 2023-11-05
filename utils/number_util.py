def is_float(n):
    try:
        float(n)
    except Exception:
        return False
    return True