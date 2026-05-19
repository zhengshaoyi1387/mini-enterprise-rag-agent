from __future__ import annotations

CALENDAR_QUERY_TERMS = (
    "日程",
    "会议",
    "安排",
    "公司日历",
    "calendar",
    "schedule",
    "meeting",
)

EVENT_TYPE_TERMS = (
    ("meeting", ("会议", "会", "meeting")),
    ("training", ("培训", "training")),
    ("activity", ("团建", "活动", "activity")),
    ("payday", ("工资", "发薪", "payday")),
    ("holiday", ("假期", "放假", "节假日", "holiday")),
    ("maintenance", ("维护", "maintenance")),
)

RELATIVE_DATE_TERMS = (
    ("day_after_tomorrow", ("后天", "day after tomorrow", "the day after tomorrow")),
    ("tomorrow", ("明天", "tomorrow")),
    ("today", ("今天", "今日", "today")),
    ("next_week", ("下周", "next week")),
    ("this_week", ("本周", "这周", "this week")),
)

ORDINAL_SELECTOR_TERMS = (
    ("first", ("第一个", "第一条", "首个", "第 1 个", "第1个")),
    ("2", ("第二个", "第二条", "第 2 个", "第2个")),
    ("last", ("最后一个", "最后一条")),
    ("all", ("全部", "所有")),
)

UPDATE_FIELD_TERMS = (
    ("location", ("地点", "位置", "location")),
    ("time", ("时间", "time")),
    ("title", ("标题", "名称", "主题", "title")),
)

UPDATE_ACTION_TERMS = ("改成", "改为", "修改为", "调整为", "设为", "更新为", "change", "update")
