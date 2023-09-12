from datetime import datetime, timedelta


def time_group(dt):
    now = datetime.now()
    today = datetime(now.year, now.month, now.day)
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)
    last_30_days = today - timedelta(days=30)
    
    if dt >= today:
        return "Today"
    elif dt >= yesterday:
        return "Yesterday"
    elif dt >= last_week:
        return "Previous 7 days"
    elif dt >= last_30_days:
        return "Previous 30 days"
    elif dt.year == now.year:
        return dt.strftime("%B")  # Return the month name
    else:
        return dt.strftime("%B %Y")  # Return the month and year


def human_readable_time(seconds):
    seconds = round(seconds)
    if seconds >= 86400:  # 1 day = 86400 seconds
        days = round(seconds / 86400)
        return f"{days} day" if days == 1 else f"{days} days"
    elif seconds >= 3600:  # 1 hour = 3600 seconds
        hours = round(seconds / 3600)
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    elif seconds >= 60:  # 1 minute = 60 seconds
        minutes = round(seconds / 60)
        return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"
    else:
        return f"{seconds} second" if seconds == 1 else f"{seconds} seconds"
