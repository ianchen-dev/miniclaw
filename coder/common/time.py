import os

import pytz


ChinaTimeZone = pytz.timezone(os.environ.get("TZ", "Asia/Shanghai"))
