def time_format(time: float) -> str:
    seconds = int(time / 1000) % (24 * 3600)  # Convert from milliseconds -> seconds
    hour = seconds // 3600
    seconds %= 3600
    minutes = seconds // 60
    seconds %= 60

    if 0 < hour:
        return f"{hour}h {minutes:02}m {hour:02}s"
    else:
        return f"{minutes:02}m {hour:02}s"