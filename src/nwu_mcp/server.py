"""FastMCP server exposing NWU Zhengfang academic tools."""

from __future__ import annotations

import json
from typing import Literal

from mcp.server.mcpserver import MCPServer

from nwu_mcp.client import NWUJwClient
from nwu_mcp.formatters import (
    format_academic_progress,
    format_classrooms,
    format_exams,
    format_grades,
    format_notices,
    format_page,
    format_schedule,
    format_training_plan_courses,
    format_training_plans,
)

mcp = MCPServer("nwu-jw")
_client = NWUJwClient()


@mcp.tool()
def jw_schedule(
    xnm: str | None = None,
    xqm: str | None = None,
    weeks: list[int] | None = None,
    output_format: Literal["text", "json"] = "text",
) -> str:
    """查询西北大学个人课表。

    Args:
        xnm: 学年起始年份，例如 '2026' 表示 2026-2027 学年；留空则自动查询当前学期。
        xqm: 学期，'1' 表示第一学期，'2' 表示第二学期；留空则自动查询当前学期。
        weeks: 可选周次列表（如 [13] 或 [13, 14]），用于筛选特定周次的课程。
        output_format: 'text' 返回精简可读文本，'json' 返回原始结构化 JSON。
    """
    data = _client.get_schedule(xnm=xnm, xqm=xqm)
    if output_format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    return format_schedule(data, weeks=weeks)


@mcp.tool()
def jw_grades(
    xnm: str = "",
    xqm: str = "",
    course_name: str = "",
    output_format: Literal["text", "json"] = "text",
) -> str:
    """查询西北大学课程成绩。

    Args:
        xnm: 学年起始年份（如 '2025'），留空表示查询全部学年。
        xqm: 学期（'1' 第一学期，'2' 第二学期），留空表示全部学期。
        course_name: 可选课程名称关键字，用于过滤成绩。
        output_format: 'text' 返回可读文本，'json' 返回原始 JSON。
    """
    data = _client.get_grades(xnm=xnm, xqm=xqm)
    if output_format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    return format_grades(data, course_filter=course_name)


@mcp.tool()
def jw_exams(
    xnm: str | None = None,
    xqm: str | None = None,
    output_format: Literal["text", "json"] = "text",
) -> str:
    """查询西北大学考试安排（时间、校区、考场、座位号）。

    Args:
        xnm: 学年起始年份，留空则查询当前默认学年；传 '' 可查全部。
        xqm: 学期（'1' 或 '2'），留空则查询当前默认学期；传 '' 可查全部。
        output_format: 'text' 返回可读文本，'json' 返回原始 JSON。
    """
    data = _client.get_exams(xnm=xnm, xqm=xqm)
    if output_format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    return format_exams(data)


@mcp.tool()
def jw_classrooms(
    xqh_id: str = "1",
    weeks: list[int] | None = None,
    weekdays: list[int] | None = None,
    periods: list[int] | None = None,
    building: str = "",
    min_seats: str = "",
    xnm: str | None = None,
    xqm: str | None = None,
    include_meta: bool = False,
    output_format: Literal["text", "json"] = "text",
) -> str:
    """查询西北大学空闲教室。

    Args:
        xqh_id: 校区 ID（'1' 通常为长安校区，'2' 为太白校区，可通过 include_meta=True 查看楼栋列表）。
        weeks: 周次列表（如 [14]），留空则自动使用当前教学周。
        weekdays: 星期列表（1-7，如 [3] 表示周三），留空则自动使用当前星期。
        periods: 节次列表（如 [1, 2] 表示第 1-2 节），留空默认 [1, 2]。
        building: 教学楼代码（可选，通过 include_meta=True 获取 JXLDM）。
        min_seats: 最小座位数（可选，如 '50'）。
        xnm: 学年起始年份，留空自动获取。
        xqm: 学期（'1' 或 '2'），留空自动获取。
        include_meta: 为 True 时仅返回该校区的教学楼列表、节次与当前周次元数据。
        output_format: 'text' 返回可读文本，'json' 返回原始 JSON。
    """
    if include_meta:
        meta = _client.get_classroom_meta(xqh_id=xqh_id, xnm=xnm, xqm=xqm)
        return json.dumps(meta, ensure_ascii=False, indent=2)

    data = _client.get_free_classrooms(
        xqh_id=xqh_id,
        weeks=weeks,
        weekdays=weekdays,
        periods=periods,
        xnm=xnm,
        xqm=xqm,
        building=building,
        min_seats=min_seats,
    )
    if output_format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    return format_classrooms(
        data,
        xqh_id=xqh_id,
        weeks=weeks,
        weekdays=weekdays,
        periods=periods,
    )


@mcp.tool()
def jw_notices(
    sfyy: Literal["1", "2"] = "1",
    keyword: str = "",
    announcement_id: str = "",
    output_format: Literal["text", "json"] = "text",
) -> str:
    """查询西北大学教务个人消息（含调停补课通知）与系统公告。

    Args:
        sfyy: 个人消息状态，'1' 为未读/待阅，'2' 为已读/已阅。
        keyword: 可选个人消息标题过滤关键字。
        announcement_id: 可选系统公告编号 (xwbh)；传入时直接抓取并返回该公告的正文详情。
        output_format: 'text' 返回可读文本，'json' 返回原始 JSON。
    """
    if announcement_id:
        detail = _client.get_announcement_detail(announcement_id)
        if output_format == "json":
            return json.dumps(detail, ensure_ascii=False, indent=2)
        return f"【{detail['title']}】\n\n{detail['content']}"

    messages = _client.get_messages(sfyy=sfyy, keyword=keyword)
    announcements = _client.get_announcements()
    if output_format == "json":
        return json.dumps(
            {"messages": messages, "announcements": announcements},
            ensure_ascii=False,
            indent=2,
        )
    return format_notices(messages, announcements)


@mcp.tool()
def jw_plan(
    xfyqjd_id: str = "",
    jxzxjhxx_id: str = "",
    njdm_id: str = "",
    zyh_id: str = "",
    jyxdxnm: str = "",
    jyxdxqm: str = "",
    output_format: Literal["text", "json"] = "text",
) -> str:
    """查询西北大学培养方案、教学执行计划与个人学业修读进度。

    默认不传参数时返回个人学业情况摘要及各学分模块树（含 xfyqjd_id）。

    Args:
        xfyqjd_id: 学分要求节点 ID（传入时展开该模块下的个人课程清单与修读状态）。
        jxzxjhxx_id: 教学执行计划 ID（传入时查询该培养方案的完整课程清单）。
        njdm_id: 年级代码（如 '2025'），与 jxzxjhxx_id 为空时配合使用可检索全校执行计划列表。
        zyh_id: 专业代码，配合 njdm_id 检索执行计划列表。
        jyxdxnm: 配合 jxzxjhxx_id 过滤建议修读学年。
        jyxdxqm: 配合 jxzxjhxx_id 过滤建议修读学期（'1' 或 '2'）。
        output_format: 'text' 返回可读文本，'json' 返回原始 JSON。
    """
    if jxzxjhxx_id:
        data = _client.get_training_plan_courses(
            jxzxjhxx_id, jyxdxnm=jyxdxnm, jyxdxqm=jyxdxqm
        )
        if output_format == "json":
            return json.dumps(data, ensure_ascii=False, indent=2)
        return format_training_plan_courses(data)

    if njdm_id or zyh_id:
        data = _client.get_training_plans(njdm_id=njdm_id, zyh_id=zyh_id)
        if output_format == "json":
            return json.dumps(data, ensure_ascii=False, indent=2)
        return format_training_plans(data)

    data = _client.get_academic_progress(xfyqjd_id=xfyqjd_id)
    if output_format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    return format_academic_progress(data)


@mcp.tool()
def jw_page(
    path: str,
    max_text_chars: int = 6000,
    output_format: Literal["text", "json"] = "text",
) -> str:
    """通用站内页面抓取工具，用于探查或读取教务系统内任意页面（如菜单、学籍等）。

    Args:
        path: 站内相对路径（例如 '/xtgl/index_initMenu.html'）或同源完整 URL。
        max_text_chars: 返回正文的最大字符数，默认 6000。
        output_format: 'text' 返回可读摘要，'json' 返回包含 tables/links/text 的完整 JSON。
    """
    data = _client.fetch_page(path=path, max_text_chars=max_text_chars)
    if output_format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2)
    return format_page(data)


@mcp.tool()
def jw_refresh_login() -> str:
    """强制重新执行纯 HTTP RSA 登录并刷新本地保存的教务会话 Cookie。"""
    cookies = _client.login(force=True)
    keys = ", ".join(sorted(cookies.keys()))
    return f"教务登录态已刷新，当前会话 Cookie 字段：{keys or '（无）'}"


def main() -> None:
    """Run the FastMCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
