"""HTTP client for NWU Zhengfang (jwglxt V-9.0) with RSA login and auto-relogin."""

from __future__ import annotations

import base64
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from nwu_mcp.config import (
    get_base_url,
    load_cookies,
    load_credentials,
    save_cookies,
)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class LoginError(RuntimeError):
    """Raised when Zhengfang authentication fails."""


class RequestError(RuntimeError):
    """Raised when a Zhengfang HTTP or API request fails."""


def encrypt_password_rsa(password: str, modulus_b64: str, exponent_b64: str) -> str:
    """Encrypt password using Zhengfang's RSA PKCS#1 v1.5 scheme."""
    n = int.from_bytes(base64.b64decode(modulus_b64), "big")
    e = int.from_bytes(base64.b64decode(exponent_b64), "big")
    key = RSA.construct((n, e))
    cipher = PKCS1_v1_5.new(key)
    encrypted = cipher.encrypt(password.encode("utf-8"))
    return base64.b64encode(encrypted).decode("ascii")


def encode_bitmask(indices: list[int]) -> int:
    """Encode 1-based week or period indices into Zhengfang's integer bitmask."""
    mask = 0
    for idx in set(indices):
        if idx < 1:
            raise ValueError(f"周次或节次必须 >= 1，收到: {idx}")
        mask |= 1 << (idx - 1)
    return mask


def semester_to_xqm(semester: str | int | None) -> str:
    """Normalize user-friendly semester ('1'/'2'/'3'/'12') to Zhengfang xqm."""
    if semester is None:
        return ""
    s = str(semester).strip()
    if s in ("", "0", "all", "全部"):
        return ""
    if s in ("1", "第一学期", "秋"):
        return "3"
    if s in ("2", "第二学期", "春"):
        return "12"
    if s in ("3", "12", "16"):
        return s
    raise ValueError(f"不支持的学期参数: {semester}（请使用 1 或 2，或留空查全部）")


def _extract_input_value(soup: BeautifulSoup, elem_id: str, default: str = "") -> str:
    tag = soup.find(id=elem_id)
    if tag and tag.has_attr("value"):
        return str(tag["value"])
    return default


def _is_login_response(resp: httpx.Response) -> bool:
    """Detect whether Zhengfang redirected to or rendered the login page."""
    if resp.status_code in (301, 302, 303, 307, 308):
        loc = resp.headers.get("location", "")
        if "login_slogin" in loc:
            return True
    if "login_slogin" in str(resp.url):
        return True
    content_type = resp.headers.get("content-type", "")
    if "html" in content_type.lower():
        text = resp.text
        if "login_slogin.html" in text and ('id="yhm"' in text or "top.location" in text):
            return True
    return False


class NWUJwClient:
    """Stateful HTTP client for NWU's Zhengfang academic system."""

    def __init__(self, base_url: str | None = None, timeout: float = 20.0) -> None:
        self.base_url = (base_url or get_base_url()).rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(
            headers={"User-Agent": DEFAULT_UA},
            timeout=self.timeout,
            follow_redirects=True,
        )
        saved = load_cookies()
        if saved:
            self._client.cookies.update(saved)

    def close(self) -> None:
        self._client.close()

    def _persist_cookies(self) -> None:
        cookies = {c.name: c.value for c in self._client.cookies.jar if c.value is not None}
        if cookies:
            save_cookies(cookies)

    def ensure_logged_in(self) -> None:
        """Ensure the client holds a valid session, logging in if cookies are missing."""
        if not self._client.cookies:
            self.login()

    def login(self, force: bool = False) -> dict[str, str]:
        """Authenticate via pure HTTP using RSA-encrypted password."""
        creds = load_credentials()
        if force:
            self._client.cookies.clear()

        login_url = f"{self.base_url}/xtgl/login_slogin.html"
        try:
            page_resp = self._client.get(login_url)
            page_resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RequestError(
                f"无法连接教务系统 ({login_url})，请检查网络或校园网/VPN 连接: {exc}"
            ) from exc

        soup = BeautifulSoup(page_resp.text, "html.parser")
        csrftoken = _extract_input_value(soup, "csrftoken")
        language = _extract_input_value(soup, "language", "zh_CN")
        yd_type = _extract_input_value(soup, "ydType", "")
        mmsfjm = _extract_input_value(soup, "mmsfjm", "1")

        if not csrftoken:
            raise LoginError("登录页未找到 csrftoken，页面结构可能已变更。")

        password_payload = creds.password
        if mmsfjm != "0":
            ts = int(time.time() * 1000)
            pk_url = f"{self.base_url}/xtgl/login_getPublicKey.html?time={ts}&_={ts}"
            pk_resp = self._client.get(pk_url, headers={"Referer": login_url})
            pk_resp.raise_for_status()
            pk_data = pk_resp.json()
            modulus = pk_data.get("modulus")
            exponent = pk_data.get("exponent")
            if not modulus or not exponent:
                raise LoginError("获取 RSA 公钥失败，返回缺少 modulus 或 exponent。")
            password_payload = encrypt_password_rsa(creds.password, modulus, exponent)

        ts_submit = int(time.time() * 1000)
        post_url = f"{login_url}?time={ts_submit}"
        form_data = {
            "csrftoken": csrftoken,
            "language": language,
            "ydType": yd_type,
            "yhm": creds.student_no,
            "mm": password_payload,
        }

        # Do not follow redirects on POST so we can reliably inspect 302 vs 200 #tips.
        post_resp = self._client.post(
            post_url,
            data=form_data,
            headers={"Referer": login_url},
            follow_redirects=False,
        )

        if post_resp.status_code in (301, 302, 303, 307, 308):
            location = post_resp.headers.get("location", "")
            target = (
                location
                if location.startswith("http")
                else f"{urlparse(self.base_url).scheme}://{urlparse(self.base_url).netloc}{location}"
            )
            init_resp = self._client.get(target, follow_redirects=True)
            init_resp.raise_for_status()
            if "login_slogin" in str(init_resp.url):
                err_soup = BeautifulSoup(init_resp.text, "html.parser")
                tips = err_soup.find(id="tips")
                tips_text = tips.get_text(" ", strip=True) if tips else ""
                raise LoginError(tips_text or "登录后仍停留在登录页，请检查账号或是否触发验证码。")
            self._persist_cookies()
            return {c.name: c.value for c in self._client.cookies.jar if c.value is not None}

        err_soup = BeautifulSoup(post_resp.text, "html.parser")
        tips = err_soup.find(id="tips")
        tips_text = tips.get_text(" ", strip=True) if tips else ""
        raise LoginError(tips_text or f"登录失败（HTTP {post_resp.status_code}），请检查学号或密码。")

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry: bool = True,
    ) -> httpx.Response:
        """Send an authenticated request and transparently re-login once if expired."""
        self.ensure_logged_in()
        url = f"{self.base_url}{path}" if path.startswith("/") else path
        req_headers = {"Referer": f"{self.base_url}/xtgl/index_initMenu.html"}
        if headers:
            req_headers.update(headers)

        try:
            resp = self._client.request(
                method,
                url,
                params=params,
                data=data,
                headers=req_headers,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            raise RequestError(f"请求教务接口失败 ({url}): {exc}") from exc

        if _is_login_response(resp):
            if not retry:
                raise LoginError("会话已过期且自动重登后仍无法访问。")
            self.login(force=True)
            return self._request(
                method, path, params=params, data=data, headers=headers, retry=False
            )

        resp.raise_for_status()
        self._persist_cookies()
        return resp

    def _post_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        referer: str | None = None,
    ) -> dict[str, Any]:
        headers = {"X-Requested-With": "XMLHttpRequest"}
        if referer:
            headers["Referer"] = referer
        resp = self._request("POST", path, params=params, data=data, headers=headers)
        try:
            return resp.json()
        except ValueError as exc:
            # Some endpoints return HTML login/error snippets with HTTP 200.
            if "login_slogin" in resp.text:
                self.login(force=True)
                resp = self._request(
                    "POST", path, params=params, data=data, headers=headers, retry=False
                )
                return resp.json()
            raise RequestError(
                f"接口 {path} 未返回有效 JSON（状态码 {resp.status_code}）。"
            ) from exc

    def _detect_current_term(self, page_path: str) -> tuple[str, str]:
        """Scrape the default selected xnm and xqm from a query page."""
        resp = self._request("GET", page_path)
        soup = BeautifulSoup(resp.text, "html.parser")
        xnm = ""
        xqm = ""
        for select_id, target in (("xnm", "xnm"), ("xqm", "xqm"), ("cx_xnm", "xnm"), ("cx_xqm", "xqm")):
            sel = soup.find("select", id=select_id)
            if not sel:
                continue
            opt = sel.find("option", selected=True) or sel.find("option")
            if opt and opt.has_attr("value"):
                val = str(opt["value"]).strip()
                if target == "xnm" and not xnm and val:
                    xnm = val
                elif target == "xqm" and not xqm and val:
                    xqm = val
        return xnm, xqm

    def _resolve_term(
        self,
        xnm: str | None,
        xqm: str | int | None,
        page_path: str,
        allow_empty: bool = False,
    ) -> tuple[str, str]:
        resolved_xnm = str(xnm).strip() if xnm is not None else ""
        resolved_xqm = semester_to_xqm(xqm) if xqm is not None else ""
        if allow_empty and xnm == "" and (xqm is None or xqm == ""):
            return "", ""
        if not resolved_xnm or (not resolved_xqm and not allow_empty):
            def_xnm, def_xqm = self._detect_current_term(page_path)
            if (not def_xnm or not def_xqm) and "xskbcx" not in page_path:
                kb_xnm, kb_xqm = self._detect_current_term(
                    "/kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N253508&layout=default"
                )
                def_xnm = def_xnm or kb_xnm
                def_xqm = def_xqm or kb_xqm
            if not resolved_xnm and not allow_empty:
                resolved_xnm = def_xnm
            if not resolved_xqm and not allow_empty:
                resolved_xqm = def_xqm
        return resolved_xnm, resolved_xqm

    # ------------------------------------------------------------------
    # 1. Schedule (个人课表查询)
    # ------------------------------------------------------------------
    def get_schedule(self, xnm: str | None = None, xqm: str | int | None = None) -> dict[str, Any]:
        page_path = "/kbcx/xskbcx_cxXskbcxIndex.html?gnmkdm=N253508&layout=default"
        use_xnm, use_xqm = self._resolve_term(xnm, xqm, page_path, allow_empty=False)
        return self._post_json(
            "/kbcx/xskbcx_cxXsgrkb.html",
            params={"gnmkdm": "N253508"},
            data={
                "xnm": use_xnm,
                "xqm": use_xqm,
                "kzlx": "ck",
                "xsdm": "",
                "kclbdm": "",
                "kclxdm": "",
            },
            referer=f"{self.base_url}{page_path}",
        )

    # ------------------------------------------------------------------
    # 2. Grades (学生成绩查询)
    # ------------------------------------------------------------------
    def get_grades(
        self,
        xnm: str | None = "",
        xqm: str | int | None = "",
        show_count: int = 200,
    ) -> dict[str, Any]:
        page_path = "/cjcx/cjcx_cxDgXscj.html?gnmkdm=N305005&layout=default"
        use_xnm = str(xnm).strip() if xnm is not None else ""
        use_xqm = semester_to_xqm(xqm) if xqm is not None else ""
        return self._post_json(
            "/cjcx/cjcx_cxXsgrcj.html",
            params={"doType": "query", "gnmkdm": "N305005"},
            data={
                "xnm": use_xnm,
                "xqm": use_xqm,
                "sy_id": "",
                "sq_id": "",
                "queryModel.showCount": str(show_count),
                "queryModel.currentPage": "1",
                "queryModel.sortName": "",
                "queryModel.sortOrder": "asc",
                "time": str(int(time.time() * 1000)),
            },
            referer=f"{self.base_url}{page_path}",
        )

    # ------------------------------------------------------------------
    # 3. Exams (考试信息查询)
    # ------------------------------------------------------------------
    def get_exams(
        self,
        xnm: str | None = None,
        xqm: str | int | None = None,
        show_count: int = 100,
    ) -> dict[str, Any]:
        page_path = "/kwgl/kscx_cxXsksxxIndex.html?gnmkdm=N358105&layout=default"
        use_xnm, use_xqm = self._resolve_term(xnm, xqm, page_path, allow_empty=True)
        if xnm is None and xqm is None:
            def_xnm, def_xqm = self._detect_current_term(page_path)
            use_xnm, use_xqm = def_xnm, def_xqm
        return self._post_json(
            "/kwgl/kscx_cxXsksxxIndex.html",
            params={"doType": "query", "gnmkdm": "N358105"},
            data={
                "xnm": use_xnm,
                "xqm": use_xqm,
                "ksmcdmb_id": "",
                "kch": "",
                "kc": "",
                "ksrq": "",
                "kkbm_id": "",
                "queryModel.showCount": str(show_count),
                "queryModel.currentPage": "1",
                "queryModel.sortName": "",
                "queryModel.sortOrder": "asc",
                "time": str(int(time.time() * 1000)),
            },
            referer=f"{self.base_url}{page_path}",
        )

    # ------------------------------------------------------------------
    # 4. Free Classrooms (空闲教室查询)
    # ------------------------------------------------------------------
    def get_classroom_meta(
        self,
        xqh_id: str = "1",
        xnm: str | None = None,
        xqm: str | int | None = None,
    ) -> dict[str, Any]:
        page_path = "/cdjy/cdjy_cxKxcdlb.html?gnmkdm=N2155&layout=default"
        use_xnm, use_xqm = self._resolve_term(xnm, xqm, page_path, allow_empty=False)
        referer = f"{self.base_url}{page_path}"
        xqjc_resp = self._request(
            "GET",
            "/cdjy/cdjy_cxXqjc.html",
            params={"xqh_id": xqh_id, "xnm": use_xnm, "xqm": use_xqm, "gnmkdm": "N2155"},
            headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"},
        )
        qtlb_data = self._post_json(
            "/cdjy/cdjy_cxQtlb.html",
            data={"xnm": use_xnm, "xqm": use_xqm, "xqh_id": xqh_id, "flag": "0"},
            referer=referer,
        )
        return {
            "xnm": use_xnm,
            "xqm": use_xqm,
            "xqh_id": xqh_id,
            "xqjc": xqjc_resp.json(),
            "qtlb": qtlb_data,
        }

    def get_free_classrooms(
        self,
        *,
        xqh_id: str = "1",
        weeks: list[int] | None = None,
        weekdays: list[int] | None = None,
        periods: list[int] | None = None,
        xnm: str | None = None,
        xqm: str | int | None = None,
        building: str = "",
        min_seats: str = "",
        show_count: int = 100,
    ) -> dict[str, Any]:
        page_path = "/cdjy/cdjy_cxKxcdlb.html?gnmkdm=N2155&layout=default"
        use_xnm, use_xqm = self._resolve_term(xnm, xqm, page_path, allow_empty=False)

        if not weeks or not weekdays or not periods:
            meta = self.get_classroom_meta(xqh_id=xqh_id, xnm=use_xnm, xqm=use_xqm)
            qtlb = meta.get("qtlb")
            dqzcxq = qtlb.get("dqzcxq", {}) if isinstance(qtlb, dict) else {}
            if not weeks:
                cur_week = int(dqzcxq.get("DQZC") or 1)
                weeks = [cur_week]
            if not weekdays:
                cur_wd = int(dqzcxq.get("DQXQ") or 1)
                weekdays = [cur_wd]
            if not periods:
                periods = [1, 2]

        zcd = encode_bitmask(weeks)
        jcd = encode_bitmask(periods)
        xqj = ",".join(str(d) for d in weekdays)

        return self._post_json(
            "/cdjy/cdjy_cxKxcdlb.html",
            params={"doType": "query", "gnmkdm": "N2155"},
            data={
                "fwzt": "cx",
                "xqh_id": str(xqh_id),
                "xnm": use_xnm,
                "xqm": use_xqm,
                "cdlb_id": "",
                "cdejlb_id": "",
                "qszws": min_seats,
                "jszws": "",
                "cdmc": "",
                "lh": building,
                "jyfs": "0",
                "cdjylx": "",
                "sfbhkc": "",
                "zcd": str(zcd),
                "xqj": xqj,
                "jcd": str(jcd),
                "queryModel.showCount": str(show_count),
                "queryModel.currentPage": "1",
                "queryModel.sortName": "cdbh",
                "queryModel.sortOrder": "asc",
                "time": str(int(time.time() * 1000)),
            },
            referer=f"{self.base_url}{page_path}",
        )

    # ------------------------------------------------------------------
    # 5. Notices & Messages (消息通知 / 系统公告)
    # ------------------------------------------------------------------
    def get_messages(
        self,
        *,
        sfyy: str = "1",
        flag: str = "1",
        keyword: str = "",
        show_count: int = 30,
    ) -> dict[str, Any]:
        """Fetch personal messages / class-adjustment notices (sfyy: '1'=unread, '2'=read)."""
        return self._post_json(
            "/xtgl/index_cxDbsy.html",
            params={"doType": "query"},
            data={
                "flag": flag,
                "sfyy": sfyy,
                "gnmkmc": keyword,
                "queryModel.showCount": str(show_count),
                "queryModel.currentPage": "1",
                "queryModel.sortName": "cjsj",
                "queryModel.sortOrder": "desc",
                "time": str(int(time.time() * 1000)),
            },
            referer=f"{self.base_url}/xtgl/index_cxDbsy.html?flag={flag}",
        )

    def get_announcements(self) -> list[dict[str, str]]:
        """Scrape system announcement links from the portal home page."""
        resp = self._request("GET", "/xtgl/index_initMenu.html")
        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for link in soup.select('a[href*="xwck_ckXw.html"]'):
            href = str(link.get("href", ""))
            parsed = urlparse(href)
            qs = parse_qs(parsed.query)
            xwbh = (qs.get("xwbh") or [""])[0]
            if not xwbh or xwbh in seen:
                continue
            seen.add(xwbh)
            title = link.get_text(" ", strip=True)
            date_text = ""
            parent = link.parent
            if parent:
                span = parent.find("span")
                if span:
                    date_text = span.get_text(strip=True)
            results.append({"xwbh": xwbh, "title": title, "date": date_text, "href": href})
        return results

    def get_announcement_detail(self, xwbh: str) -> dict[str, str]:
        """Fetch the full text of a system announcement by xwbh."""
        resp = self._request(
            "GET",
            "/xtgl/xwck_ckXw.html",
            params={"xwbh": xwbh, "doType": "save"},
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        title_el = soup.find(["h1", "h2", "h3", "h4"]) or soup.find(class_="xwbt")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        body_el = soup.find(id="xwnr") or soup.find(class_="xwnr") or soup.find("body")
        body = body_el.get_text("\n", strip=True) if body_el else ""
        return {"xwbh": xwbh, "title": title, "content": body}

    # ------------------------------------------------------------------
    # 6. Study Plan & Academic Progress (培养方案 / 学业情况)
    # ------------------------------------------------------------------
    def get_academic_progress(self, xfyqjd_id: str = "") -> dict[str, Any]:
        """Fetch personal credit-requirement tree and optionally a node's courses (N105515)."""
        page_path = "/xsxy/xsxyqk_cxXsxyqkIndex.html?echarts=1&gnmkdm=N105515&layout=default"
        resp = self._request("GET", page_path)
        soup = BeautifulSoup(resp.text, "html.parser")

        hidden_keys = (
            "xh_id",
            "cjlrxn",
            "cjlrxq",
            "bkcjlrxn",
            "bkcjlrxq",
            "xscjcxkz",
            "cjcxkzzt",
            "cjztkz",
            "cjzt",
        )
        form_ctx = {k: _extract_input_value(soup, k) for k in hidden_keys}

        # Extract top summary text (GPA / course counts)
        summary_lines: list[str] = []
        for el in soup.select(".xsxyqk-top, .panel-heading, .alert, .tj-item, p"):
            txt = el.get_text(" ", strip=True)
            if any(kw in txt for kw in ("平均学分绩点", "GPA", "要求学分", "已获学分", "计划总课程")):
                if txt not in summary_lines:
                    summary_lines.append(txt)

        # Extract credit requirement tree nodes containing xfyqjd_id (inline JS or DOM)
        nodes: list[dict[str, str]] = []
        seen_nodes: set[str] = set()
        js_pattern = re.compile(
            r"xfyqjd_id='([A-Za-z0-9_]+)'[^>\n]*?leaf='([^']*)'[^>\n]*?>"
            r"\s*<p[^>]*?yxxf='([^']*)'[^>]*?yqzdxf='([^']*)'[^>]*?sftg='([^']*)'[^>]*>"
            r"\s*\"([^\"]+)",
            re.S,
        )
        for m in js_pattern.finditer(resp.text):
            node_id, leaf, yxxf, yqzdxf, sftg, raw_label = m.groups()
            if node_id in seen_nodes:
                continue
            seen_nodes.add(node_id)
            label = raw_label.replace("&nbsp;", " ").strip()
            if leaf:
                label = f"{label} [leaf={leaf}]"
            nodes.append(
                {
                    "xfyqjd_id": node_id,
                    "yqzdxf": yqzdxf,
                    "yxxf": yxxf,
                    "sftg": "是" if sftg == "1" else "否" if sftg == "0" else sftg,
                    "label": label[:120],
                }
            )
        if not nodes:
            for el in soup.select("[xfyqjd_id], [data-xfyqjd_id]"):
                node_id = str(el.get("xfyqjd_id") or el.get("data-xfyqjd_id") or "").strip()
                if not node_id or node_id in seen_nodes:
                    continue
                seen_nodes.add(node_id)
                nodes.append(
                    {
                        "xfyqjd_id": node_id,
                        "yqzdxf": str(el.get("yqzdxf") or ""),
                        "yxxf": str(el.get("yxxf") or ""),
                        "sftg": str(el.get("sftg") or ""),
                        "label": el.get_text(" ", strip=True)[:120],
                    }
                )

        courses: list[dict[str, Any]] = []
        if xfyqjd_id:
            payload = {**form_ctx, "xfyqjd_id": xfyqjd_id}
            courses_resp = self._post_json(
                "/xsxy/xsxyqk_cxJxzxjhxfyqKcxx.html",
                params={"gnmkdm": "N105515"},
                data=payload,
                referer=f"{self.base_url}{page_path}",
            )
            if isinstance(courses_resp, list):
                courses = courses_resp
            elif isinstance(courses_resp, dict):
                courses = list(courses_resp.get("items") or [])

        return {
            "summary": summary_lines[:10],
            "nodes": nodes,
            "xfyqjd_id": xfyqjd_id,
            "courses": courses,
        }

    def get_training_plans(
        self,
        *,
        njdm_id: str = "",
        jg_id: str = "",
        zyh_id: str = "",
        show_count: int = 50,
    ) -> dict[str, Any]:
        """Query major training plans list (N153540) to obtain jxzxjhxx_id."""
        page_path = "/jxzxjhgl/jxzxjhck_cxJxzxjhckIndex.html?gnmkdm=N153540&layout=default"
        return self._post_json(
            "/jxzxjhgl/jxzxjhck_cxJxzxjhckIndex.html",
            params={"doType": "query", "gnmkdm": "N153540"},
            data={
                "jg_id": jg_id,
                "njdm_id": njdm_id,
                "dlbs": "",
                "zyh_id": zyh_id,
                "currentPage_cx": "1",
                "queryModel.showCount": str(show_count),
                "queryModel.currentPage": "1",
                "queryModel.sortName": "",
                "queryModel.sortOrder": "asc",
                "time": str(int(time.time() * 1000)),
            },
            referer=f"{self.base_url}{page_path}",
        )

    def get_training_plan_courses(
        self,
        jxzxjhxx_id: str,
        *,
        jyxdxnm: str = "",
        jyxdxqm: str | int | None = "",
        show_count: int = 200,
    ) -> dict[str, Any]:
        """Query curriculum course list for a specific jxzxjhxx_id (N153540)."""
        page_path = "/jxzxjhgl/jxzxjhck_cxJxzxjhckIndex.html?gnmkdm=N153540&layout=default"
        use_xqm = semester_to_xqm(jyxdxqm) if jyxdxqm else ""
        return self._post_json(
            "/jxzxjhgl/jxzxjhkcxx_cxJxzxjhkcxxIndex.html",
            params={"doType": "query", "gnmkdm": "N153540"},
            data={
                "jxzxjhxx_id": jxzxjhxx_id,
                "jyxdxnm": jyxdxnm,
                "jyxdxqm": use_xqm,
                "yxxdxnm": "",
                "yxxdxqm": "",
                "shzt": "",
                "kch": "",
                "xdlx": "",
                "queryModel.showCount": str(show_count),
                "queryModel.currentPage": "1",
                "queryModel.sortName": "",
                "queryModel.sortOrder": "asc",
                "time": str(int(time.time() * 1000)),
            },
            referer=f"{self.base_url}{page_path}",
        )

    # ------------------------------------------------------------------
    # 7. Generic In-Site Page Fetcher (通用站内页面抓取)
    # ------------------------------------------------------------------
    def fetch_page(self, path: str, max_text_chars: int = 6000) -> dict[str, Any]:
        """Fetch an arbitrary in-site jwglxt page and extract title, tables, links, and text."""
        clean_path = path.strip()
        if clean_path.startswith("http"):
            parsed_target = urlparse(clean_path)
            parsed_base = urlparse(self.base_url)
            if parsed_target.netloc != parsed_base.netloc:
                raise RequestError(
                    f"安全限制：仅允许抓取站内页面 ({parsed_base.netloc})，禁止访问 {parsed_target.netloc}"
                )
        elif not clean_path.startswith("/"):
            clean_path = f"/{clean_path}"

        resp = self._request("GET", clean_path)
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""

        tables: list[list[list[str]]] = []
        for tbl in soup.find_all("table")[:10]:
            rows: list[list[str]] = []
            for tr in tbl.find_all("tr")[:60]:
                cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
                if any(cells):
                    rows.append(cells)
            if rows:
                tables.append(rows)

        links: list[dict[str, str]] = []
        for a in soup.find_all("a", href=True)[:50]:
            href = str(a["href"]).strip()
            text = a.get_text(" ", strip=True)
            if href and not href.startswith("javascript:") and text:
                links.append({"text": text, "href": href})

        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        body_text = soup.get_text("\n", strip=True)
        if len(body_text) > max_text_chars:
            body_text = body_text[:max_text_chars] + "\n...（已截断）"

        return {
            "url": str(resp.url),
            "title": title,
            "tables": tables,
            "links": links,
            "text": body_text,
        }
