"""Formatting and filtering helpers for NWU Zhengfang query results."""

from __future__ import annotations

import re
from typing import Any

WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]


def parse_weeks_spec(zcd: str) -> set[int]:
    """Parse Zhengfang week string like '1-16周(单),18周' into a set of week ints."""
    weeks: set[int] = set()
    if not zcd:
        return weeks
    for part in zcd.split(","):
        part = part.strip()
        if not part:
            continue
        odd_only = "单" in part
        even_only = "双" in part
        m_range = re.search(r"(\d+)\s*-\s*(\d+)", part)
        if m_range:
            start, end = int(m_range.group(1)), int(m_range.group(2))
            for w in range(start, end + 1):
                if odd_only and w % 2 == 0:
                    continue
                if even_only and w % 2 == 1:
                    continue
                weeks.add(w)
            continue
        for m_single in re.findall(r"\d+", part):
            weeks.add(int(m_single))
    return weeks


def format_schedule(data: dict[str, Any], weeks: list[int] | None = None) -> str:
    """Format personal schedule response into concise readable text."""
    xsxx = data.get("xsxx") or {}
    kb_list = list(data.get("kbList") or [])
    sjk_list = list(data.get("sjkList") or [])

    if weeks:
        want = set(weeks)
        kb_list = [c for c in kb_list if parse_weeks_spec(str(c.get("zcd", ""))) & want]

    header = f"{xsxx.get('XNMC', '')}学年第{xsxx.get('XQMMC', '')}学期课表"
    if weeks:
        header += f"（筛选第 {','.join(str(w) for w in weeks)} 周）"

    if not kb_list and not sjk_list:
        return f"{header}\n（没有匹配的课程）"

    lines = [header]
    by_day: dict[int, list[dict[str, Any]]] = {}
    for c in kb_list:
        try:
            day = int(c.get("xqj") or 0)
        except (TypeError, ValueError):
            day = 0
        by_day.setdefault(day, []).append(c)

    for day in sorted(by_day):
        day_label = f"周{WEEKDAYS[day - 1]}" if 1 <= day <= 7 else f"星期{day}"
        lines.append(f"\n{day_label}：")
        courses = sorted(
            by_day[day],
            key=lambda item: (
                int(re.search(r"\d+", str(item.get("jcs") or item.get("jc") or "0")).group())
                if re.search(r"\d+", str(item.get("jcs") or item.get("jc") or ""))
                else 0
            ),
        )
        for c in courses:
            jc = c.get("jc") or c.get("jcs") or ""
            name = c.get("kcmc") or ""
            zcd = c.get("zcd") or ""
            teacher = c.get("xm") or ""
            room = c.get("cdmc") or ""
            campus = c.get("xqmc") or ""
            loc = f"{campus} {room}".strip()
            lines.append(f"  {jc}  {name}  [{zcd}]  {teacher}  {loc}".rstrip())

    if sjk_list and not weeks:
        lines.append("\n实践/其他环节：")
        for s in sjk_list:
            name = s.get("kcmc") or ""
            teacher = s.get("jsxm") or ""
            qsjsz = s.get("qsjsz") or ""
            lines.append(f"  {name}  [{qsjsz}]  {teacher}".rstrip())

    return "\n".join(lines)


_XDZT_MAP = {
    "1": "在读",
    "3": "未修",
    "4": "已通过",
}


def format_academic_progress(data: dict[str, Any]) -> str:
    """Format personal academic progress tree and optional node courses."""
    lines: list[str] = ["【个人学业情况与修读进度】"]
    for s in data.get("summary") or []:
        lines.append(f"  {s}")

    nodes = data.get("nodes") or []
    if nodes:
        lines.append(f"\n学分要求模块（共 {len(nodes)} 项，可传 xfyqjd_id 查看模块内课程）：")
        for n in nodes:
            status = f" | 通过: {n['sftg']}" if n.get("sftg") else ""
            lines.append(
                f"- xfyqjd_id={n['xfyqjd_id']} | 要求学分: {n.get('yqzdxf', '')} "
                f"| 已获学分: {n.get('yxxf', '')}{status} | {n.get('label', '')}"
            )

    courses = data.get("courses") or []
    if data.get("xfyqjd_id"):
        lines.append(f"\n模块 {data['xfyqjd_id']} 课程清单（共 {len(courses)} 门）：")
        if not courses:
            lines.append("  （该模块下暂无课程明细）")
        for c in courses:
            status_code = str(c.get("XDZT") or "")
            status_str = _XDZT_MAP.get(status_code, status_code or "未知")
            term = f"{c.get('JYXDXNMC', '')}-{c.get('JYXDXQMC', '')}".strip("-")
            score = f" 成绩:{c['CJ']}" if c.get("CJ") else ""
            lines.append(
                f"- [{status_str}] {c.get('KCMC', '')} ({c.get('KCH', '')}) "
                f"| 学分: {c.get('XF', c.get('JHXF', ''))} | 建议学期: {term}{score}"
            )

    return "\n".join(lines)


def format_training_plans(data: dict[str, Any]) -> str:
    """Format training plan list (N153540)."""
    items = list(data.get("items") or [])
    if not items:
        return "（未查询到匹配的教学执行计划）"
    lines = [f"共 {len(items)} 条教学执行计划（可传 jxzxjhxx_id 查看全部课程）："]
    for it in items:
        lines.append(
            f"- jxzxjhxx_id={it.get('jxzxjhxx_id', '')} | 年级: {it.get('njmc', it.get('njdm', ''))} "
            f"| 专业: {it.get('zymc', '')} | 课程数: {it.get('kcs', '')}"
        )
    return "\n".join(lines)


def format_training_plan_courses(data: dict[str, Any]) -> str:
    """Format curriculum courses under a training plan (N153540)."""
    items = list(data.get("items") or [])
    if not items:
        return "（该执行计划下暂无匹配的课程）"
    lines = [f"共 {len(items)} 门培养方案课程："]
    for it in items:
        term = f"{it.get('jyxdxnm', '')}-{it.get('jyxdxqm', '')}".strip("-")
        lines.append(
            f"- [{term}] {it.get('kcmc', '')} ({it.get('kch', '')}) "
            f"| 学分: {it.get('xf', '')} | {it.get('kcxzmc', '')} | {it.get('kclbmc', '')}"
        )
    return "\n".join(lines)


def format_page(data: dict[str, Any]) -> str:
    """Format generic in-site page fetch result."""
    lines = [
        f"标题: {data.get('title', '')}",
        f"URL: {data.get('url', '')}",
        f"表格数: {len(data.get('tables') or [])} | 链接数: {len(data.get('links') or [])}",
    ]
    tables = data.get("tables") or []
    if tables:
        lines.append("\n【表格摘要】")
        for idx, tbl in enumerate(tables[:3], start=1):
            lines.append(f"表格 {idx}（{len(tbl)} 行）：")
            for row in tbl[:10]:
                lines.append("  " + " | ".join(row))
    lines.append("\n【页面正文】")
    lines.append(data.get("text") or "")
    return "\n".join(lines)


def format_grades(data: dict[str, Any], course_filter: str = "") -> str:
    """Format grades jqGrid response with optional course name filter."""
    items = list(data.get("items") or [])
    if course_filter:
        kw = course_filter.strip().lower()
        items = [it for it in items if kw in str(it.get("kcmc", "")).lower()]

    if not items:
        return "（没有匹配的成绩记录）"

    lines = [f"共 {len(items)} 门课程成绩："]
    for it in items:
        term = f"{it.get('xnmmc', '')}-{it.get('xqmmc', '')}".strip("-")
        name = it.get("kcmc") or ""
        score = it.get("cj") or ""
        gpa = it.get("jd") or ""
        credit = it.get("xf") or ""
        prop = it.get("kcxzmc") or ""
        exam_type = it.get("ksxz") or ""
        extra = f" ({exam_type})" if exam_type and exam_type != "正常考试" else ""
        lines.append(
            f"- [{term}] {name}{extra} | 成绩: {score} | 绩点: {gpa} | 学分: {credit} | {prop}"
        )
    return "\n".join(lines)


_XDZT_MAP = {
    "1": "在读",
    "3": "未修",
    "4": "已通过",
}


def format_academic_progress(data: dict[str, Any]) -> str:
    """Format personal academic progress tree and optional node courses."""
    lines: list[str] = ["【个人学业情况与修读进度】"]
    for s in data.get("summary") or []:
        lines.append(f"  {s}")

    nodes = data.get("nodes") or []
    if nodes:
        lines.append(f"\n学分要求模块（共 {len(nodes)} 项，可传 xfyqjd_id 查看模块内课程）：")
        for n in nodes:
            status = f" | 通过: {n['sftg']}" if n.get("sftg") else ""
            lines.append(
                f"- xfyqjd_id={n['xfyqjd_id']} | 要求学分: {n.get('yqzdxf', '')} "
                f"| 已获学分: {n.get('yxxf', '')}{status} | {n.get('label', '')}"
            )

    courses = data.get("courses") or []
    if data.get("xfyqjd_id"):
        lines.append(f"\n模块 {data['xfyqjd_id']} 课程清单（共 {len(courses)} 门）：")
        if not courses:
            lines.append("  （该模块下暂无课程明细）")
        for c in courses:
            status_code = str(c.get("XDZT") or "")
            status_str = _XDZT_MAP.get(status_code, status_code or "未知")
            term = f"{c.get('JYXDXNMC', '')}-{c.get('JYXDXQMC', '')}".strip("-")
            score = f" 成绩:{c['CJ']}" if c.get("CJ") else ""
            lines.append(
                f"- [{status_str}] {c.get('KCMC', '')} ({c.get('KCH', '')}) "
                f"| 学分: {c.get('XF', c.get('JHXF', ''))} | 建议学期: {term}{score}"
            )

    return "\n".join(lines)


def format_training_plans(data: dict[str, Any]) -> str:
    """Format training plan list (N153540)."""
    items = list(data.get("items") or [])
    if not items:
        return "（未查询到匹配的教学执行计划）"
    lines = [f"共 {len(items)} 条教学执行计划（可传 jxzxjhxx_id 查看全部课程）："]
    for it in items:
        lines.append(
            f"- jxzxjhxx_id={it.get('jxzxjhxx_id', '')} | 年级: {it.get('njmc', it.get('njdm', ''))} "
            f"| 专业: {it.get('zymc', '')} | 课程数: {it.get('kcs', '')}"
        )
    return "\n".join(lines)


def format_training_plan_courses(data: dict[str, Any]) -> str:
    """Format curriculum courses under a training plan (N153540)."""
    items = list(data.get("items") or [])
    if not items:
        return "（该执行计划下暂无匹配的课程）"
    lines = [f"共 {len(items)} 门培养方案课程："]
    for it in items:
        term = f"{it.get('jyxdxnm', '')}-{it.get('jyxdxqm', '')}".strip("-")
        lines.append(
            f"- [{term}] {it.get('kcmc', '')} ({it.get('kch', '')}) "
            f"| 学分: {it.get('xf', '')} | {it.get('kcxzmc', '')} | {it.get('kclbmc', '')}"
        )
    return "\n".join(lines)


def format_page(data: dict[str, Any]) -> str:
    """Format generic in-site page fetch result."""
    lines = [
        f"标题: {data.get('title', '')}",
        f"URL: {data.get('url', '')}",
        f"表格数: {len(data.get('tables') or [])} | 链接数: {len(data.get('links') or [])}",
    ]
    tables = data.get("tables") or []
    if tables:
        lines.append("\n【表格摘要】")
        for idx, tbl in enumerate(tables[:3], start=1):
            lines.append(f"表格 {idx}（{len(tbl)} 行）：")
            for row in tbl[:10]:
                lines.append("  " + " | ".join(row))
    lines.append("\n【页面正文】")
    lines.append(data.get("text") or "")
    return "\n".join(lines)


def format_exams(data: dict[str, Any]) -> str:
    """Format exam arrangement jqGrid response."""
    items = list(data.get("items") or [])
    if not items:
        return "（当前条件暂无考试安排）"

    lines = [f"共 {len(items)} 场考试安排："]
    for it in items:
        name = it.get("kcmc") or ""
        ksmc = it.get("ksmc") or ""
        date = it.get("ksrq") or ""
        time_str = it.get("kssj") or ""
        campus = it.get("xqmc") or it.get("cdxqmc") or ""
        room = it.get("cdmc") or ""
        seat = it.get("zwh") or ""
        seat_part = f" 座位 {seat}" if seat else ""
        batch_part = f"（{ksmc}）" if ksmc else ""
        lines.append(
            f"- {name}{batch_part} | {date} {time_str} | {campus} {room}{seat_part}".strip()
        )
    return "\n".join(lines)


_XDZT_MAP = {
    "1": "在读",
    "3": "未修",
    "4": "已通过",
}


def format_academic_progress(data: dict[str, Any]) -> str:
    """Format personal academic progress tree and optional node courses."""
    lines: list[str] = ["【个人学业情况与修读进度】"]
    for s in data.get("summary") or []:
        lines.append(f"  {s}")

    nodes = data.get("nodes") or []
    if nodes:
        lines.append(f"\n学分要求模块（共 {len(nodes)} 项，可传 xfyqjd_id 查看模块内课程）：")
        for n in nodes:
            status = f" | 通过: {n['sftg']}" if n.get("sftg") else ""
            lines.append(
                f"- xfyqjd_id={n['xfyqjd_id']} | 要求学分: {n.get('yqzdxf', '')} "
                f"| 已获学分: {n.get('yxxf', '')}{status} | {n.get('label', '')}"
            )

    courses = data.get("courses") or []
    if data.get("xfyqjd_id"):
        lines.append(f"\n模块 {data['xfyqjd_id']} 课程清单（共 {len(courses)} 门）：")
        if not courses:
            lines.append("  （该模块下暂无课程明细）")
        for c in courses:
            status_code = str(c.get("XDZT") or "")
            status_str = _XDZT_MAP.get(status_code, status_code or "未知")
            term = f"{c.get('JYXDXNMC', '')}-{c.get('JYXDXQMC', '')}".strip("-")
            score = f" 成绩:{c['CJ']}" if c.get("CJ") else ""
            lines.append(
                f"- [{status_str}] {c.get('KCMC', '')} ({c.get('KCH', '')}) "
                f"| 学分: {c.get('XF', c.get('JHXF', ''))} | 建议学期: {term}{score}"
            )

    return "\n".join(lines)


def format_training_plans(data: dict[str, Any]) -> str:
    """Format training plan list (N153540)."""
    items = list(data.get("items") or [])
    if not items:
        return "（未查询到匹配的教学执行计划）"
    lines = [f"共 {len(items)} 条教学执行计划（可传 jxzxjhxx_id 查看全部课程）："]
    for it in items:
        lines.append(
            f"- jxzxjhxx_id={it.get('jxzxjhxx_id', '')} | 年级: {it.get('njmc', it.get('njdm', ''))} "
            f"| 专业: {it.get('zymc', '')} | 课程数: {it.get('kcs', '')}"
        )
    return "\n".join(lines)


def format_training_plan_courses(data: dict[str, Any]) -> str:
    """Format curriculum courses under a training plan (N153540)."""
    items = list(data.get("items") or [])
    if not items:
        return "（该执行计划下暂无匹配的课程）"
    lines = [f"共 {len(items)} 门培养方案课程："]
    for it in items:
        term = f"{it.get('jyxdxnm', '')}-{it.get('jyxdxqm', '')}".strip("-")
        lines.append(
            f"- [{term}] {it.get('kcmc', '')} ({it.get('kch', '')}) "
            f"| 学分: {it.get('xf', '')} | {it.get('kcxzmc', '')} | {it.get('kclbmc', '')}"
        )
    return "\n".join(lines)


def format_page(data: dict[str, Any]) -> str:
    """Format generic in-site page fetch result."""
    lines = [
        f"标题: {data.get('title', '')}",
        f"URL: {data.get('url', '')}",
        f"表格数: {len(data.get('tables') or [])} | 链接数: {len(data.get('links') or [])}",
    ]
    tables = data.get("tables") or []
    if tables:
        lines.append("\n【表格摘要】")
        for idx, tbl in enumerate(tables[:3], start=1):
            lines.append(f"表格 {idx}（{len(tbl)} 行）：")
            for row in tbl[:10]:
                lines.append("  " + " | ".join(row))
    lines.append("\n【页面正文】")
    lines.append(data.get("text") or "")
    return "\n".join(lines)


def format_classrooms(
    data: dict[str, Any],
    *,
    xqh_id: str,
    weeks: list[int] | None,
    weekdays: list[int] | None,
    periods: list[int] | None,
) -> str:
    """Format free classroom jqGrid response."""
    items = list(data.get("items") or [])
    total = data.get("totalCount", len(items))
    header = (
        f"空闲教室查询结果（校区={xqh_id}, 周次={weeks}, 星期={weekdays}, 节次={periods}，"
        f"共 {total} 间，当前显示 {len(items)} 间）："
    )
    if not items:
        return f"{header}\n（该时段暂无符合条件的空闲教室）"

    lines = [header]
    for it in items:
        room = it.get("cdmc") or it.get("cdbh") or ""
        building = it.get("jxlmc") or ""
        campus = it.get("xqmc") or ""
        room_type = it.get("cdlbmc") or ""
        seats = it.get("zws") or ""
        exam_seats = it.get("kszws1") or ""
        lines.append(
            f"- {campus} {building} {room} | 类型: {room_type} | 座位数: {seats} (考试座: {exam_seats})"
        )
    return "\n".join(lines)


_XDZT_MAP = {
    "1": "在读",
    "3": "未修",
    "4": "已通过",
}


def format_academic_progress(data: dict[str, Any]) -> str:
    """Format personal academic progress tree and optional node courses."""
    lines: list[str] = ["【个人学业情况与修读进度】"]
    for s in data.get("summary") or []:
        lines.append(f"  {s}")

    nodes = data.get("nodes") or []
    if nodes:
        lines.append(f"\n学分要求模块（共 {len(nodes)} 项，可传 xfyqjd_id 查看模块内课程）：")
        for n in nodes:
            status = f" | 通过: {n['sftg']}" if n.get("sftg") else ""
            lines.append(
                f"- xfyqjd_id={n['xfyqjd_id']} | 要求学分: {n.get('yqzdxf', '')} "
                f"| 已获学分: {n.get('yxxf', '')}{status} | {n.get('label', '')}"
            )

    courses = data.get("courses") or []
    if data.get("xfyqjd_id"):
        lines.append(f"\n模块 {data['xfyqjd_id']} 课程清单（共 {len(courses)} 门）：")
        if not courses:
            lines.append("  （该模块下暂无课程明细）")
        for c in courses:
            status_code = str(c.get("XDZT") or "")
            status_str = _XDZT_MAP.get(status_code, status_code or "未知")
            term = f"{c.get('JYXDXNMC', '')}-{c.get('JYXDXQMC', '')}".strip("-")
            score = f" 成绩:{c['CJ']}" if c.get("CJ") else ""
            lines.append(
                f"- [{status_str}] {c.get('KCMC', '')} ({c.get('KCH', '')}) "
                f"| 学分: {c.get('XF', c.get('JHXF', ''))} | 建议学期: {term}{score}"
            )

    return "\n".join(lines)


def format_training_plans(data: dict[str, Any]) -> str:
    """Format training plan list (N153540)."""
    items = list(data.get("items") or [])
    if not items:
        return "（未查询到匹配的教学执行计划）"
    lines = [f"共 {len(items)} 条教学执行计划（可传 jxzxjhxx_id 查看全部课程）："]
    for it in items:
        lines.append(
            f"- jxzxjhxx_id={it.get('jxzxjhxx_id', '')} | 年级: {it.get('njmc', it.get('njdm', ''))} "
            f"| 专业: {it.get('zymc', '')} | 课程数: {it.get('kcs', '')}"
        )
    return "\n".join(lines)


def format_training_plan_courses(data: dict[str, Any]) -> str:
    """Format curriculum courses under a training plan (N153540)."""
    items = list(data.get("items") or [])
    if not items:
        return "（该执行计划下暂无匹配的课程）"
    lines = [f"共 {len(items)} 门培养方案课程："]
    for it in items:
        term = f"{it.get('jyxdxnm', '')}-{it.get('jyxdxqm', '')}".strip("-")
        lines.append(
            f"- [{term}] {it.get('kcmc', '')} ({it.get('kch', '')}) "
            f"| 学分: {it.get('xf', '')} | {it.get('kcxzmc', '')} | {it.get('kclbmc', '')}"
        )
    return "\n".join(lines)


def format_page(data: dict[str, Any]) -> str:
    """Format generic in-site page fetch result."""
    lines = [
        f"标题: {data.get('title', '')}",
        f"URL: {data.get('url', '')}",
        f"表格数: {len(data.get('tables') or [])} | 链接数: {len(data.get('links') or [])}",
    ]
    tables = data.get("tables") or []
    if tables:
        lines.append("\n【表格摘要】")
        for idx, tbl in enumerate(tables[:3], start=1):
            lines.append(f"表格 {idx}（{len(tbl)} 行）：")
            for row in tbl[:10]:
                lines.append("  " + " | ".join(row))
    lines.append("\n【页面正文】")
    lines.append(data.get("text") or "")
    return "\n".join(lines)


def format_notices(
    messages: dict[str, Any],
    announcements: list[dict[str, str]],
) -> str:
    """Format personal messages and system announcements."""
    lines: list[str] = []
    msg_items = list(messages.get("items") or [])
    lines.append(f"【个人消息 / 调停补课通知】（共 {len(msg_items)} 条）：")
    if not msg_items:
        lines.append("  （暂无个人消息）")
    else:
        for m in msg_items:
            title = m.get("xxbt") or ""
            content = m.get("xxnr") or ""
            ts = m.get("cjsj") or ""
            status = "已读" if str(m.get("sfyd")) == "1" else "未读"
            lines.append(f"- [{status}] {ts} {title}: {content}".strip())

    lines.append(f"\n【系统通知公告】（共 {len(announcements)} 条）：")
    if not announcements:
        lines.append("  （暂无系统公告）")
    else:
        for a in announcements:
            date_part = f"[{a['date']}] " if a.get("date") else ""
            lines.append(f"- {date_part}{a.get('title', '')} (xwbh={a.get('xwbh', '')})")

    return "\n".join(lines)


_XDZT_MAP = {
    "1": "在读",
    "3": "未修",
    "4": "已通过",
}


def format_academic_progress(data: dict[str, Any]) -> str:
    """Format personal academic progress tree and optional node courses."""
    lines: list[str] = ["【个人学业情况与修读进度】"]
    for s in data.get("summary") or []:
        lines.append(f"  {s}")

    nodes = data.get("nodes") or []
    if nodes:
        lines.append(f"\n学分要求模块（共 {len(nodes)} 项，可传 xfyqjd_id 查看模块内课程）：")
        for n in nodes:
            status = f" | 通过: {n['sftg']}" if n.get("sftg") else ""
            lines.append(
                f"- xfyqjd_id={n['xfyqjd_id']} | 要求学分: {n.get('yqzdxf', '')} "
                f"| 已获学分: {n.get('yxxf', '')}{status} | {n.get('label', '')}"
            )

    courses = data.get("courses") or []
    if data.get("xfyqjd_id"):
        lines.append(f"\n模块 {data['xfyqjd_id']} 课程清单（共 {len(courses)} 门）：")
        if not courses:
            lines.append("  （该模块下暂无课程明细）")
        for c in courses:
            status_code = str(c.get("XDZT") or "")
            status_str = _XDZT_MAP.get(status_code, status_code or "未知")
            term = f"{c.get('JYXDXNMC', '')}-{c.get('JYXDXQMC', '')}".strip("-")
            score = f" 成绩:{c['CJ']}" if c.get("CJ") else ""
            lines.append(
                f"- [{status_str}] {c.get('KCMC', '')} ({c.get('KCH', '')}) "
                f"| 学分: {c.get('XF', c.get('JHXF', ''))} | 建议学期: {term}{score}"
            )

    return "\n".join(lines)


def format_training_plans(data: dict[str, Any]) -> str:
    """Format training plan list (N153540)."""
    items = list(data.get("items") or [])
    if not items:
        return "（未查询到匹配的教学执行计划）"
    lines = [f"共 {len(items)} 条教学执行计划（可传 jxzxjhxx_id 查看全部课程）："]
    for it in items:
        lines.append(
            f"- jxzxjhxx_id={it.get('jxzxjhxx_id', '')} | 年级: {it.get('njmc', it.get('njdm', ''))} "
            f"| 专业: {it.get('zymc', '')} | 课程数: {it.get('kcs', '')}"
        )
    return "\n".join(lines)


def format_training_plan_courses(data: dict[str, Any]) -> str:
    """Format curriculum courses under a training plan (N153540)."""
    items = list(data.get("items") or [])
    if not items:
        return "（该执行计划下暂无匹配的课程）"
    lines = [f"共 {len(items)} 门培养方案课程："]
    for it in items:
        term = f"{it.get('jyxdxnm', '')}-{it.get('jyxdxqm', '')}".strip("-")
        lines.append(
            f"- [{term}] {it.get('kcmc', '')} ({it.get('kch', '')}) "
            f"| 学分: {it.get('xf', '')} | {it.get('kcxzmc', '')} | {it.get('kclbmc', '')}"
        )
    return "\n".join(lines)


def format_page(data: dict[str, Any]) -> str:
    """Format generic in-site page fetch result."""
    lines = [
        f"标题: {data.get('title', '')}",
        f"URL: {data.get('url', '')}",
        f"表格数: {len(data.get('tables') or [])} | 链接数: {len(data.get('links') or [])}",
    ]
    tables = data.get("tables") or []
    if tables:
        lines.append("\n【表格摘要】")
        for idx, tbl in enumerate(tables[:3], start=1):
            lines.append(f"表格 {idx}（{len(tbl)} 行）：")
            for row in tbl[:10]:
                lines.append("  " + " | ".join(row))
    lines.append("\n【页面正文】")
    lines.append(data.get("text") or "")
    return "\n".join(lines)
