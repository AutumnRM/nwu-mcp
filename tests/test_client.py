"""Unit tests for nwu-mcp RSA encryption, bitmask helpers, and formatters."""

from __future__ import annotations

import base64

from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from nwu_mcp.client import NWUJwClient, RequestError, encode_bitmask, encrypt_password_rsa, semester_to_xqm
from nwu_mcp.formatters import (
    format_academic_progress,
    format_grades,
    format_page,
    format_schedule,
    parse_weeks_spec,
)


def test_encrypt_password_rsa_roundtrip() -> None:
    key = RSA.generate(1024)
    n_bytes = key.n.to_bytes((key.n.bit_length() + 7) // 8, "big")
    e_bytes = key.e.to_bytes((key.e.bit_length() + 7) // 8, "big")
    modulus_b64 = base64.b64encode(n_bytes).decode("ascii")
    exponent_b64 = base64.b64encode(e_bytes).decode("ascii")

    ct_b64 = encrypt_password_rsa("Secret#123", modulus_b64, exponent_b64)
    cipher = PKCS1_v1_5.new(key)
    decrypted = cipher.decrypt(base64.b64decode(ct_b64), b"ERR")
    assert decrypted == b"Secret#123"


def test_encode_bitmask() -> None:
    assert encode_bitmask([1]) == 1
    assert encode_bitmask([1, 2]) == 3
    assert encode_bitmask([3, 4]) == 12
    assert encode_bitmask([1, 1, 3]) == 5


def test_semester_to_xqm() -> None:
    assert semester_to_xqm("1") == "3"
    assert semester_to_xqm("2") == "12"
    assert semester_to_xqm("") == ""
    assert semester_to_xqm(None) == ""


def test_parse_weeks_spec() -> None:
    assert parse_weeks_spec("1-4周") == {1, 2, 3, 4}
    assert parse_weeks_spec("1-5周(单)") == {1, 3, 5}
    assert parse_weeks_spec("2-6周(双),8周") == {2, 4, 6, 8}


def test_format_schedule_filters_weeks() -> None:
    sample = {
        "xsxx": {"XNMC": "2026-2027", "XQMMC": "1"},
        "kbList": [
            {
                "xqj": "1",
                "jc": "1-2节",
                "jcs": "1-2",
                "kcmc": "数据结构",
                "zcd": "1-8周",
                "xm": "张老师",
                "cdmc": "1-201",
                "xqmc": "长安校区",
            },
            {
                "xqj": "3",
                "jc": "3-4节",
                "jcs": "3-4",
                "kcmc": "操作系统",
                "zcd": "9-16周",
                "xm": "李老师",
                "cdmc": "2-305",
                "xqmc": "长安校区",
            },
        ],
    }
    text_w2 = format_schedule(sample, weeks=[2])
    assert "数据结构" in text_w2
    assert "操作系统" not in text_w2


def test_format_grades_filter() -> None:
    sample = {
        "items": [
            {
                "xnmmc": "2025-2026",
                "xqmmc": "1",
                "kcmc": "高等数学A",
                "cj": "92",
                "jd": "4.0",
                "xf": "5.0",
                "kcxzmc": "必修",
                "ksxz": "正常考试",
            },
            {
                "xnmmc": "2025-2026",
                "xqmmc": "1",
                "kcmc": "大学英语",
                "cj": "85",
                "jd": "3.5",
                "xf": "2.0",
                "kcxzmc": "必修",
                "ksxz": "正常考试",
            },
        ]
    }
    out = format_grades(sample, course_filter="高数")
    assert "没有匹配的成绩记录" in out
    out2 = format_grades(sample, course_filter="高等数学")
    assert "高等数学A" in out2
    assert "大学英语" not in out2


def test_format_academic_progress_and_page() -> None:
    progress = format_academic_progress(
        {
            "summary": ["平均学分绩点：3.85"],
            "nodes": [{"xfyqjd_id": "node1", "yqzdxf": "20", "yxxf": "16", "sftg": "否", "label": "专业必修"}],
            "xfyqjd_id": "node1",
            "courses": [
                {"KCH": "CS101", "KCMC": "程序设计", "XF": "4", "XDZT": "4", "JYXDXNMC": "2025-2026", "JYXDXQMC": "1", "CJ": "90"}
            ],
        }
    )
    assert "node1" in progress
    assert "[已通过] 程序设计" in progress

    page = format_page(
        {
            "title": "测试页",
            "url": "https://jwgl.nwu.edu.cn/jwglxt/test.html",
            "tables": [[["列1", "列2"], ["A", "B"]]],
            "links": [{"text": "首页", "href": "/xtgl/index_initMenu.html"}],
            "text": "正文内容",
        }
    )
    assert "标题: 测试页" in page
    assert "A | B" in page


def test_fetch_page_blocks_external_origin() -> None:
    import pytest

    client = NWUJwClient(base_url="https://jwgl.nwu.edu.cn/jwglxt")
    try:
        with pytest.raises(RequestError):
            client.fetch_page("https://example.com/evil")
    finally:
        client.close()
