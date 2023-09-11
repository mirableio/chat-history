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
