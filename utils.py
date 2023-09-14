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


def human_readable_time(seconds, short=False):
    if short:
        s_title = s_title_plural = "s"
        m_title = m_title_plural = "m"
        h_title = h_title_plural = "h"
        d_title = d_title_plural = "d"
    else:
        s_title = " second"
        s_title_plural = " seconds"
        m_title = " minute"
        m_title_plural = " minutes"
        h_title = " hour"
        h_title_plural = " hours"
        d_title = " day"
        d_title_plural = " days"

    seconds = round(seconds)
    if seconds >= 86400:  # 1 day = 86400 seconds
        days = round(seconds / 86400)
        return f"{days}{d_title}" if days == 1 else f"{days}{d_title_plural}"
    elif seconds >= 3600:  # 1 hour = 3600 seconds
        hours = round(seconds / 3600)
        return f"{hours}{h_title}" if hours == 1 else f"{hours}{h_title_plural}"
    elif seconds >= 60:  # 1 minute = 60 seconds
        minutes = round(seconds / 60)
        return f"{minutes}{m_title}" if minutes == 1 else f"{minutes}{m_title_plural}"
    else:
        return f"{seconds}{s_title}" if seconds == 1 else f"{seconds}{s_title_plural}"
