#!/usr/bin/env python3
"""
HTML-first Vietnamese road-traffic legal corpus filler.

Policy:
  1. Prefer official full-text HTML on chinhphu.vn / xaydungchinhsach.chinhphu.vn.
  2. If the official Government page only exposes scanned PDF, use a verified
     secondary HTML transcription from luatvietnam.vn.
  3. Keep the official Government URL as evidence/provenance.
  4. Do NOT OCR by default. Legal OCR can corrupt article numbers, amounts,
     punctuation and Vietnamese diacritics.
  5. Missing target files are created automatically.
  6. Old FAILED stubs are automatically retried.
  7. A failed fetch never overwrites an already-valid file.

Dependencies:
  .venv/bin/python -m pip install requests beautifulsoup4

Typical:
  .venv/bin/python scripts/fill_traffic_corpus.py \
      --dir data/corpus/mds \
      --include-recommended \
      --include-current-2026

Audit only:
  .venv/bin/python scripts/fill_traffic_corpus.py \
      --dir data/corpus/mds \
      --include-recommended \
      --include-current-2026 \
      --audit-only
"""
from __future__ import annotations

import argparse
import hashlib
import html
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0 Safari/537.36"
)
CONNECT_TIMEOUT = 20
READ_TIMEOUT = 90
MIN_TEXT_CHARS = 1800
MIN_ARTICLE_COUNT = 2


@dataclass(frozen=True)
class LegalDoc:
    filename: str
    number: str
    official_url: str
    tier: str = "base"
    status: str = "unknown"
    note: str = ""
    official_fulltext_url: str | None = None


BASE_DOCS = [
    LegalDoc(
        "nd-67-2023.md", "67/2023/NĐ-CP",
        "https://vanban.chinhphu.vn/?classid=1&docid=208599&orggroupid=2&pageid=27160",
    ),
    LegalDoc(
        "nd-100-2019.md", "100/2019/NĐ-CP",
        "https://chinhphu.vn/default.aspx?docid=198733&pageid=27160",
        status="legacy",
        note="Historical penalty regime. Do not treat as current road-traffic penalty law.",
    ),
    LegalDoc(
        "nd-44-2024.md", "44/2024/NĐ-CP",
        "https://vanban.chinhphu.vn/?classid=1&docid=210145&orggroupid=2&pageid=27160",
        note="Quản lý, sử dụng và khai thác tài sản kết cấu hạ tầng giao thông đường bộ.",
    ),
    LegalDoc(
        "nd-119-2024.md", "119/2024/NĐ-CP",
        "https://vanban.chinhphu.vn/?classid=1&docid=211303&orggroupid=2&pageid=27160",
        official_fulltext_url="https://xaydungchinhsach.chinhphu.vn/toan-van-nghi-dinh-119-2024-nd-cp-quy-dinh-ve-thanh-toan-dien-tu-giao-thong-duong-bo-119240930194034842.htm",
    ),
    LegalDoc(
        "nd-158-2024.md", "158/2024/NĐ-CP",
        "https://vanban.chinhphu.vn/?classid=1&docid=212082&pageid=27160&typegroupid=4",
    ),
    LegalDoc(
        "nd-160-2024.md", "160/2024/NĐ-CP",
        "https://chinhphu.vn/?classid=1&docid=212126&pageid=27160&typegroupid=4",
        status="repealed",
        note="Repealed from 2026-07-01 by Decree 94/2026/NĐ-CP.",
    ),
    LegalDoc(
        "nd-161-2024.md", "161/2024/NĐ-CP",
        "https://chinhphu.vn/default.aspx?classid=1&docid=212127&pageid=27160",
    ),
    LegalDoc(
        "nd-165-2024.md", "165/2024/NĐ-CP",
        "https://chinhphu.vn/?classid=1&docid=212168&orggroupid=2&pageid=27160",
    ),
    LegalDoc(
        "nd-166-2024.md", "166/2024/NĐ-CP",
        "https://vanban.chinhphu.vn/?classid=1&docid=212253&pageid=27160&typegroupid=4",
    ),
    LegalDoc(
        "nd-168-2024.md", "168/2024/NĐ-CP",
        "https://chinhphu.vn/default.aspx?classid=1&docid=212167&orggroupid=2&pageid=27160",
        status="amended",
        note="Amended by Decree 238/2026/NĐ-CP effective 2026-08-15.",
        official_fulltext_url="https://xaydungchinhsach.chinhphu.vn/toan-van-nghi-dinh-168-2024-nd-cp-quy-dinh-xu-phat-vi-pham-hanh-chinh-ve-trat-tu-atgt-duong-bo-119241231164556785.htm",
    ),
    LegalDoc(
        "tt-05-2024.md", "05/2024/TT-BGTVT",
        "https://vanban.chinhphu.vn/?classid=1&docid=210025&pageid=27160",
        status="legacy",
    ),
    LegalDoc(
        "tt-16-2024.md", "16/2024/TT-BGTVT",
        "https://chinhphu.vn/?docid=210404&pageid=27160",
    ),
    LegalDoc(
        "tt-18-2024.md", "18/2024/TT-BGTVT",
        "https://vanban.chinhphu.vn/?classid=1&docid=210351&pageid=27160&typegroupid=6",
        status="repealed",
    ),
    LegalDoc(
        "tt-24-2023.md", "24/2023/TT-BCA",
        "https://vanban.chinhphu.vn/?classid=1&docid=208348&orggroupid=4&pageid=27160",
        status="repealed",
        note="Replaced by the newer vehicle-registration regime.",
    ),
    LegalDoc(
        "tt-39-2024.md", "39/2024/TT-BGTVT",
        "https://chinhphu.vn/?classid=1&docid=211874&orggroupid=4&pageid=27160",
        status="repealed",
    ),
    LegalDoc(
        "tt-51-2024.md", "51/2024/TT-BGTVT",
        "https://vanban.chinhphu.vn/?classid=1&docid=211908&orggroupid=4&pageid=27160",
        note="QCVN 41:2024/BGTVT attachment should ideally be stored as a separate corpus document.",
    ),
    LegalDoc(
        "tt-79-2024.md", "79/2024/TT-BCA",
        "https://vanban.chinhphu.vn/?classid=1&docid=211945&pageid=27160&typegroupid=6",
        status="amended",
        note="Amended after issuance; keep amendment documents in current corpus.",
    ),
]

RECOMMENDED_DOCS = [
    LegalDoc(
        "luat-35-2024.md", "35/2024/QH15",
        "https://chinhphu.vn/default.aspx?classid=1&docid=211193&pageid=27160&typegroupid=3",
        tier="recommended",
    ),
    LegalDoc(
        "luat-36-2024.md", "36/2024/QH15",
        "https://vanban.chinhphu.vn/?classid=1&docid=211194&pageid=27160",
        tier="recommended", status="amended",
        note="Amended by later legislation including Law 118/2025/QH15.",
    ),
    LegalDoc(
        "nd-151-2024.md", "151/2024/NĐ-CP",
        "https://vanban.chinhphu.vn/?classid=1&docid=211956&pageid=27160",
        tier="recommended", status="amended",
        note="Amended by 184/2025/NĐ-CP and 236/2026/NĐ-CP.",
    ),
    LegalDoc(
        "tt-38-2024.md", "38/2024/TT-BGTVT",
        "https://chinhphu.vn/?classid=1&docid=211873&orggroupid=4&pageid=27160",
        tier="recommended",
    ),
    LegalDoc(
        "tt-36-2024.md", "36/2024/TT-BGTVT",
        "https://congbao.chinhphu.vn/van-ban/thong-tu-so-36-2024-tt-bgtvt-43364.htm",
        tier="recommended",
    ),
    LegalDoc(
        "tt-47-2024.md", "47/2024/TT-BGTVT",
        "https://vanban.chinhphu.vn/?docid=212078&pageid=27160",
        tier="recommended",
    ),
    LegalDoc(
        "tt-35-2024.md", "35/2024/TT-BGTVT",
        "https://vanban.chinhphu.vn/?docid=211984&pageid=27160",
        tier="recommended", status="legacy",
    ),
    LegalDoc(
        "tt-12-2025-bca.md", "12/2025/TT-BCA",
        "https://xaydungchinhsach.chinhphu.vn/toan-van-thong-tu-12-2025-tt-bca-cua-bo-cong-an-quy-dinh-ve-sat-hach-cap-giay-phep-lai-xe-119250303174347028.htm",
        tier="recommended", status="repealed",
        note="Replaced by 108/2026/TT-BCA from 2026-07-01.",
        official_fulltext_url="https://xaydungchinhsach.chinhphu.vn/toan-van-thong-tu-12-2025-tt-bca-cua-bo-cong-an-quy-dinh-ve-sat-hach-cap-giay-phep-lai-xe-119250303174347028.htm",
    ),
    LegalDoc(
        "tt-13-2025-bca.md", "13/2025/TT-BCA",
        "https://congbao.chinhphu.vn/van-ban/thong-tu-so-13-2025-tt-bca-44372/55293.htm",
        tier="recommended",
    ),
    LegalDoc(
        "tt-73-2024-bca.md", "73/2024/TT-BCA",
        "https://vanban.chinhphu.vn/?classid=1&docid=211864&orggroupid=4&pageid=27160",
        tier="recommended",
    ),
    LegalDoc(
        "tt-71-2024-bca.md", "71/2024/TT-BCA",
        "https://vanban.chinhphu.vn/?classid=0&docid=211711&pageid=27160",
        tier="recommended",
    ),
    LegalDoc(
        "tt-72-2024-bca.md", "72/2024/TT-BCA",
        "https://vanban.chinhphu.vn/?docid=211819&pageid=27160",
        tier="recommended",
    ),
    LegalDoc(
        "tt-83-2024-bca.md", "83/2024/TT-BCA",
        "https://congbao.chinhphu.vn/van-ban/thong-tu-so-83-2024-tt-bca-43231.htm",
        tier="recommended",
    ),
    LegalDoc(
        "nd-336-2025.md", "336/2025/NĐ-CP",
        "https://xaydungchinhsach.chinhphu.vn/toan-van-nghi-dinh-so-336-2025-nd-cp-quy-dinh-xu-phat-vi-pham-hanh-chinh-trong-hoat-dong-duong-bo-119251224105604556.htm",
        tier="recommended",
        official_fulltext_url="https://xaydungchinhsach.chinhphu.vn/toan-van-nghi-dinh-so-336-2025-nd-cp-quy-dinh-xu-phat-vi-pham-hanh-chinh-trong-hoat-dong-duong-bo-119251224105604556.htm",
    ),
    LegalDoc(
        "luat-118-2025.md", "118/2025/QH15",
        "https://chinhphu.vn/?classid=1&docid=216534&pageid=27160&typegroupid=3",
        tier="recommended",
    ),
]

CURRENT_2026_DOCS = [
    LegalDoc(
        "nd-94-2026.md", "94/2026/NĐ-CP",
        "https://xaydungchinhsach.chinhphu.vn/",
        tier="current-2026", status="current",
        note="Current training/testing decree from 2026-07-01; replaces 160/2024/NĐ-CP.",
    ),
    LegalDoc(
        "tt-108-2026-bca.md", "108/2026/TT-BCA",
        "https://xaydungchinhsach.chinhphu.vn/nhung-diem-moi-trong-sat-hach-lai-xe-119260703113320777.htm",
        tier="current-2026", status="current",
        note="Current driving-test/licensing circular from 2026-07-01; replaces 12/2025/TT-BCA.",
    ),
    LegalDoc(
        "nd-184-2025.md", "184/2025/NĐ-CP",
        "https://chinhphu.vn/",
        tier="current-2026", status="amendment",
        note="Amends 151/2024/NĐ-CP.",
    ),
    LegalDoc(
        "nd-236-2026.md", "236/2026/NĐ-CP",
        "https://xaydungchinhsach.chinhphu.vn/nghi-dinh-so-236-2026-nd-cp-sua-doi-cac-nghi-dinh-quy-dinh-chi-tiet-luat-trat-tu-an-toan-giao-thong-duong-bo-119260629195808271.htm",
        tier="current-2026", status="current-amendment",
        official_fulltext_url="https://xaydungchinhsach.chinhphu.vn/nghi-dinh-so-236-2026-nd-cp-sua-doi-cac-nghi-dinh-quy-dinh-chi-tiet-luat-trat-tu-an-toan-giao-thong-duong-bo-119260629195808271.htm",
    ),
    LegalDoc(
        "nd-238-2026.md", "238/2026/NĐ-CP",
        "https://xaydungchinhsach.chinhphu.vn/nghi-dinh-so-238-2026-nd-cp-sua-doi-quy-dinh-xu-phat-vi-pham-giao-thong-duong-bo-tru-diem-phuc-hoi-diem-giay-phep-lai-xe-119260630142033452.htm",
        tier="current-2026", status="current-amendment",
        official_fulltext_url="https://xaydungchinhsach.chinhphu.vn/nghi-dinh-so-238-2026-nd-cp-sua-doi-quy-dinh-xu-phat-vi-pham-giao-thong-duong-bo-tru-diem-phuc-hoi-diem-giay-phep-lai-xe-119260630142033452.htm",
    ),
]



# Direct secondary HTML URLs verified by web search.
# These avoid runtime search endpoints that commonly return 403.
LUATVIETNAM_DIRECT = {
    "44/2024/NĐ-CP": "https://luatvietnam.vn/giao-thong/nghi-dinh-44-2024-nd-cp-quy-dinh-quan-ly-va-khai-thac-tai-san-ket-cau-ha-tang-giao-thong-duong-bo-320616-d1.html",
    "67/2023/NĐ-CP": "https://luatvietnam.vn/xay-dung/nghi-dinh-67-2023-nd-cp-bao-hiem-bat-buoc-cua-chu-xe-co-gioi-bao-hiem-chay-no-266177-d1.html",
    "100/2019/NĐ-CP": "https://luatvietnam.vn/vi-pham-hanh-chinh/nghi-dinh-100-2019-nd-cp-xu-phat-vi-pham-giao-thong-179619-d1.html",
    "158/2024/NĐ-CP": "https://luatvietnam.vn/dau-tu/nghi-dinh-158-2024-nd-cp-cua-chinh-phu-quy-dinh-ve-hoat-dong-van-tai-duong-bo-381392-d1.html",
    "160/2024/NĐ-CP": "https://luatvietnam.vn/giao-thong/nghi-dinh-160-2024-nd-cp-quy-dinh-hoat-dong-dao-tao-va-sat-hach-lai-xe-381852-d1.html",
    "161/2024/NĐ-CP": "https://luatvietnam.vn/cong-nghiep/nghi-dinh-161-2024-nd-cp-quy-dinh-danh-muc-hang-hoa-nguy-hiem-van-chuyen-hang-hoa-nguy-hiem-381863-d1.html",
    "165/2024/NĐ-CP": "https://luatvietnam.vn/dat-dai/nghi-dinh-165-2024-nd-cp-quy-dinh-chi-tiet-mot-so-dieu-cua-luat-duong-bo-dieu-77-luat-trat-tu-atgt-duong-bo-383553-d1.html",
    "166/2024/NĐ-CP": "https://luatvietnam.vn/giao-thong/nghi-dinh-166-2024-nd-cp-cua-chinh-phu-quy-dinh-ve-dieu-kien-kinh-doanh-dich-vu-kiem-dinh-xe-co-gioi-to-chuc-hoat-dong-cua-co-so-dang-kiem-nien-han-su-dung-cua-xe-co-gioi-383321-d1.html",
    "05/2024/TT-BGTVT": "https://luatvietnam.vn/giao-thong/thong-tu-05-2024-tt-bgtvt-sua-doi-cac-thong-tu-lien-quan-den-linh-vuc-van-tai-duong-bo-309166-d1.html",
    "16/2024/TT-BGTVT": "https://luatvietnam.vn/dau-tu/thong-tu-16-2024-tt-bgtvt-cua-bo-giao-thong-van-tai-quy-dinh-mot-so-noi-dung-ve-lua-chon-nha-dau-tu-thuc-hien-du-an-dau-tu-kinh-doanh-cong-trinh-tram-dung-nghi-347765-d1.html",
    "18/2024/TT-BGTVT": "https://luatvietnam.vn/giao-thong/thong-tu-18-2024-tt-bgtvt-sua-doi-tt-12-2020-tt-bgtvt-quy-dinh-quan-ly-hoat-dong-van-tai-bang-xe-oto-346016-d1.html",
    "24/2023/TT-BCA": "https://luatvietnam.vn/giao-thong/thong-tu-24-2023-tt-bca-cap-thu-hoi-dang-ky-bien-so-xe-co-gioi-259077-d1.html",
    "39/2024/TT-BGTVT": "https://luatvietnam.vn/giao-thong/thong-tu-39-2024-tt-bgtvt-tai-trong-kho-gioi-han-cua-duong-bo-luu-hanh-xe-qua-kho-gioi-han-377464-d1.html",
    "51/2024/TT-BGTVT": "https://luatvietnam.vn/giao-thong/thong-tu-51-2024-tt-bgtvt-quy-chuan-ky-thuat-quoc-gia-ve-bao-hieu-duong-bo-376855-d1.html",
    "79/2024/TT-BCA": "https://luatvietnam.vn/giao-thong/thong-tu-79-2024-tt-bca-cap-thu-hoi-chung-nhan-dang-ky-xe-bien-so-xe-co-gioi-xe-may-chuyen-dung-377888-d1.html",
    "35/2024/QH15": "https://luatvietnam.vn/giao-thong/luat-duong-bo-2024-so-35-2024-qh15-360336-d1.html",
    "36/2024/QH15": "https://luatvietnam.vn/an-ninh-trat-tu/luat-trat-tu-an-toan-giao-thong-duong-bo-2024-so-36-2024-qh15-360844-d1.html",
    "151/2024/NĐ-CP": "https://luatvietnam.vn/an-ninh-trat-tu/nghi-dinh-151-2024-nd-cp-cua-chinh-phu-quy-dinh-chi-tiet-mot-so-dieu-va-bien-phap-thi-hanh-luat-trat-tu-an-toan-giao-thong-duong-bo-378814-d1.html",
    "38/2024/TT-BGTVT": "https://luatvietnam.vn/giao-thong/thong-tu-38-2024-tt-bgtvt-toc-do-khoang-cach-an-toan-cua-xe-may-chuyen-dung-tham-gia-giao-thong-375831-d1.html",
    "36/2024/TT-BGTVT": "https://luatvietnam.vn/giao-thong/thong-tu-36-2024-tt-bgtvt-quan-ly-hoat-dong-van-tai-bang-xe-o-to-va-hoat-dong-cua-ben-xe-bai-do-xe-377349-d1.html",
    "47/2024/TT-BGTVT": "https://luatvietnam.vn/xuat-nhap-khau/thong-tu-47-2024-tt-bgtvt-trinh-tu-thu-tuc-kiem-dinh-khi-thai-xe-mo-to-xe-gan-may-379962-d1.html",
    "35/2024/TT-BGTVT": "https://luatvietnam.vn/giao-thong/thong-tu-35-2024-tt-bgtvt-dao-tao-cap-giay-phep-lai-xe-giay-phep-lai-xe-quoc-te-chung-chi-giao-thong-duong-bo-378513-d1.html",
    "13/2025/TT-BCA": "https://luatvietnam.vn/an-ninh-trat-tu/thong-tu-13-2025-tt-bca-sua-doi-bo-sung-cac-thong-tu-quy-dinh-ve-trat-tu-an-toan-giao-thong-duong-bo-duong-sat-va-duong-thuy-noi-dia-392093-d1.html",
    "73/2024/TT-BCA": "https://luatvietnam.vn/an-ninh-trat-tu/thong-tu-73-2024-tt-bca-quy-dinh-cong-tac-tuan-tra-xu-ly-vi-pham-ve-trat-tu-atgt-duong-bo-cua-csgt-376504-d1.html",
    "71/2024/TT-BCA": "https://luatvietnam.vn/giao-thong/thong-tu-71-2024-tt-bca-he-thong-quan-ly-du-lieu-thiet-bi-giam-sat-hanh-trinh-ghi-nhan-hinh-anh-nguoi-lai-xe-373603-d1.html",
    "72/2024/TT-BCA": "https://luatvietnam.vn/giao-thong/thong-tu-72-2024-tt-bca-quy-trinh-dieu-tra-giai-quyet-tai-nan-giao-thong-duong-bo-cua-csgt-376047-d1.html",
    "83/2024/TT-BCA": "https://luatvietnam.vn/giao-thong/thong-tu-83-2024-tt-bca-quy-dinh-quan-ly-van-hanh-su-dung-he-thong-giam-sat-bao-dam-an-toan-giao-thong-duong-bo-374791-d1.html",
    "336/2025/NĐ-CP": "https://luatvietnam.vn/vi-pham-hanh-chinh/nghi-dinh-336-2025-nd-cp-xu-phat-vi-pham-hanh-chinh-trong-hoat-dong-duong-bo-422205-d1.html",
    "118/2025/QH15": "https://luatvietnam.vn/an-ninh-trat-tu/luat-so-118-2025-qh15-sua-doi-bo-sung-10-luat-ve-an-ninh-trat-tu-2025-422147-d1.html",
}


def canonical(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).upper()
    return "".join(ch for ch in s if ch.isalnum())


def contains_number(text: str, number: str) -> bool:
    return canonical(number) in canonical(text)


def normalize(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_session() -> requests.Session:
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    s = requests.Session()
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.5",
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
    })
    return s


def get(session: requests.Session, url: str) -> requests.Response:
    r = session.get(url, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT), allow_redirects=True)
    r.raise_for_status()
    return r


def article_count(text: str) -> int:
    """
    Count legal articles in either raw extracted text or rendered Markdown.

    Examples accepted:
      Điều 1. Phạm vi điều chỉnh
      ### Điều 1. Phạm vi điều chỉnh
    """
    return len(
        re.findall(
            r"(?im)^\s*(?:#{1,6}\s*)?Điều\s+\d+[A-Za-z]?(?:\.|\s)",
            text,
        )
    )


def validate_legal_text(text: str, number: str) -> tuple[bool, str]:
    if len(text) < MIN_TEXT_CHARS:
        return False, f"too short ({len(text):,} chars)"
    if not contains_number(text, number):
        return False, "document number not found"
    n_articles = article_count(text)
    if n_articles < MIN_ARTICLE_COUNT:
        return False, f"too few legal articles ({n_articles})"
    return True, f"{len(text):,} chars, {n_articles} articles"


def clean_node(node) -> str:
    clone = BeautifulSoup(str(node), "html.parser")
    for tag in clone(["script", "style", "nav", "header", "footer", "aside",
                      "form", "iframe", "button", "noscript", "svg"]):
        tag.decompose()
    return normalize(clone.get_text("\n", strip=True))


def extract_best_legal_node(page_html: str, number: str) -> str:
    soup = BeautifulSoup(page_html, "html.parser")

    # Site-specific selectors first, generic legal/article containers second.
    selectors = [
        "#divcontent",
        "#content",
        ".content1",
        ".content",
        ".detail-content",
        ".article-content",
        ".news-content",
        ".entry-content",
        ".fulltext",
        "article",
        "main",
    ]

    candidates: list[tuple[int, str]] = []
    seen_text = set()

    for selector in selectors:
        for node in soup.select(selector):
            text = clean_node(node)
            if not text or text in seen_text:
                continue
            seen_text.add(text)
            ok, _ = validate_legal_text(text, number)
            if ok:
                # Prefer a compact container containing the legal document,
                # rather than the entire page with navigation noise.
                score = article_count(text) * 100000 - len(text)
                candidates.append((score, text))

    # Fallback: inspect div/article/main nodes that contain the document number.
    if not candidates:
        for node in soup.find_all(["div", "article", "main", "section"]):
            raw = node.get_text(" ", strip=True)
            if not contains_number(raw, number):
                continue
            text = clean_node(node)
            ok, _ = validate_legal_text(text, number)
            if ok:
                score = article_count(text) * 100000 - len(text)
                candidates.append((score, text))

    if not candidates:
        # Last HTML-only attempt, still no OCR/PDF.
        body = soup.body
        if body:
            text = clean_node(body)
            ok, _ = validate_legal_text(text, number)
            if ok:
                candidates.append((article_count(text) * 100000 - len(text), text))

    if not candidates:
        return ""

    return max(candidates, key=lambda x: x[0])[1]


def is_official_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host.endswith("chinhphu.vn")


def fetch_html_text(session: requests.Session, url: str, number: str):
    r = get(session, url)
    text = extract_best_legal_node(r.text, number)
    ok, reason = validate_legal_text(text, number) if text else (False, "no legal node")
    if not ok:
        raise RuntimeError(f"{r.url}: {reason}")
    return text, r



def _extract_search_links(page_html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(page_html, "html.parser")
    out: list[str] = []
    seen: set[str] = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"].strip())
        if "luatvietnam.vn/" not in href.lower():
            continue
        if not href.lower().endswith(".html"):
            continue
        if "-d1.html" not in href.lower():
            continue
        if href not in seen:
            seen.add(href)
            out.append(href)
    return out


def discover_luatvietnam_candidates(session: requests.Session, number: str) -> list[str]:
    """
    Search fallback only. Direct verified URLs in LUATVIETNAM_DIRECT are preferred.

    DuckDuckGo HTML and Bing HTML are attempted because they do not require an API key.
    Search-engine failure is non-fatal.
    """
    from urllib.parse import quote_plus

    query = f'site:luatvietnam.vn "{number}"'
    endpoints = [
        "https://html.duckduckgo.com/html/?q=" + quote_plus(query),
        "https://www.bing.com/search?q=" + quote_plus(query),
    ]

    found: list[str] = []
    seen: set[str] = set()

    for endpoint in endpoints:
        try:
            r = get(session, endpoint)
        except Exception:
            continue

        for href in _extract_search_links(r.text, r.url):
            if href not in seen:
                seen.add(href)
                found.append(href)

        if found:
            break

    return found[:10]


def fetch_luatvietnam_fulltext(session: requests.Session, number: str):
    errors = []
    candidates: list[str] = []

    direct = LUATVIETNAM_DIRECT.get(number)
    if direct:
        print(f"      direct LuatVietnam candidate: {direct}")
        candidates.append(direct)

    for url in discover_luatvietnam_candidates(session, number):
        if url not in candidates:
            candidates.append(url)

    if not candidates:
        raise RuntimeError(
            f"no LuatVietnam candidate URL found for {number}; "
            "add its verified -d1.html URL to LUATVIETNAM_DIRECT"
        )

    best = None

    for url in candidates:
        try:
            r = get(session, url)
            text = extract_best_legal_node(r.text, number)

            if not text:
                errors.append(f"{url}: no verified legal node")
                continue

            ok, reason = validate_legal_text(text, number)
            if not ok:
                errors.append(f"{url}: {reason}")
                continue

            # Remove UI residue that LuatVietnam inserts between legal paragraphs.
            text = re.sub(r"(?m)^\s*(Đang theo dõi|Phân tích|Bổ sung)\s*$", "", text)
            text = normalize(text)

            score = article_count(text) * 100000 + len(text)
            if best is None or score > best[0]:
                best = (score, text, r)
        except Exception as exc:
            errors.append(f"{url}: {exc}")

    if best is None:
        raise RuntimeError(" ; ".join(errors[-8:]))

    _, text, r = best
    return text, r

def fetch_document(session: requests.Session, doc: LegalDoc):
    errors = []

    # 1. Explicit official full-text article.
    if doc.official_fulltext_url:
        try:
            text, r = fetch_html_text(session, doc.official_fulltext_url, doc.number)
            return text, {
                "content_url": r.url,
                "content_source_type": "official_html",
                "official_evidence_url": doc.official_url,
                "sha256": hashlib.sha256(r.content).hexdigest(),
            }
        except Exception as exc:
            errors.append(f"official fulltext: {exc}")

    # 2. Official metadata/source page itself may contain full legal text.
    try:
        text, r = fetch_html_text(session, doc.official_url, doc.number)
        return text, {
            "content_url": r.url,
            "content_source_type": "official_html",
            "official_evidence_url": doc.official_url,
            "sha256": hashlib.sha256(r.content).hexdigest(),
        }
    except Exception as exc:
        errors.append(f"official page: {exc}")

    # 3. Verified LuatVietnam HTML transcription. Official URL remains evidence.
    try:
        text, r = fetch_luatvietnam_fulltext(session, doc.number)
        return text, {
            "content_url": r.url,
            "content_source_type": "secondary_html_transcription",
            "official_evidence_url": doc.official_url,
            "sha256": hashlib.sha256(r.content).hexdigest(),
        }
    except Exception as exc:
        errors.append(f"LuatVietnam HTML fallback: {exc}")

    raise RuntimeError(" | ".join(errors))


def add_markdown_headings(text: str) -> str:
    text = normalize(text)
    text = re.sub(r"(?m)^(Chương\s+[IVXLCDM\d]+.*)$", r"## \1", text, flags=re.I)
    text = re.sub(r"(?m)^(Mục\s+\d+.*)$", r"### \1", text, flags=re.I)
    text = re.sub(r"(?m)^(Điều\s+\d+[A-Za-z]?\.\s*.*)$", r"### \1", text)
    text = re.sub(r"(?m)^(PHỤ LỤC(?:\s+[IVXLCDM\d]+)?.*)$", r"## \1", text, flags=re.I)
    return text


def yq(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def render(doc: LegalDoc, text: str, provenance: dict) -> str:
    source_quality = (
        "A_official_html"
        if provenance["content_source_type"] == "official_html"
        else "B_secondary_html_verified_against_official_metadata"
    )

    return (
        "---\n"
        f"document_number: {yq(doc.number)}\n"
        f"dataset_tier: {yq(doc.tier)}\n"
        f"legal_status_hint: {yq(doc.status)}\n"
        f"content_source_type: {yq(provenance['content_source_type'])}\n"
        f"source_quality: {yq(source_quality)}\n"
        f"content_url: {yq(provenance['content_url'])}\n"
        f"official_evidence_url: {yq(provenance['official_evidence_url'])}\n"
        f"source_sha256: {yq(provenance['sha256'])}\n"
        "verification: \"exact_document_number_and_legal_article_structure_found_in_html\"\n"
        "ingest_status: \"OK\"\n"
        "exclude_from_rag: false\n"
        + (f"note: {yq(doc.note)}\n" if doc.note else "")
        + "---\n\n"
        f"# {doc.number}\n\n"
        + add_markdown_headings(text)
        + "\n"
    )


def failure_stub(doc: LegalDoc, error: str) -> str:
    return (
        "---\n"
        f"document_number: {yq(doc.number)}\n"
        f"official_evidence_url: {yq(doc.official_url)}\n"
        "ingest_status: \"FAILED\"\n"
        "exclude_from_rag: true\n"
        f"error: {yq(normalize(error)[:1800])}\n"
        "---\n\n"
        f"# INGEST FAILED: {doc.number}\n"
    )


def failed_stub(s: str) -> bool:
    return "exclude_from_rag: true" in s or 'ingest_status: "FAILED"' in s


def valid_existing(s: str, doc: LegalDoc) -> bool:
    ok, _ = validate_legal_text(s, doc.number)
    return bool(s.strip()) and not failed_stub(s) and ok


def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def selected_docs(args) -> list[LegalDoc]:
    docs = list(BASE_DOCS)
    if args.include_recommended:
        docs += RECOMMENDED_DOCS
    if args.include_current_2026:
        docs += CURRENT_2026_DOCS

    if args.only:
        wanted = set(args.only)
        known = {d.filename for d in docs}
        unknown = wanted - known
        if unknown:
            raise SystemExit("Unknown --only files: " + ", ".join(sorted(unknown)))
        docs = [d for d in docs if d.filename in wanted]

    return docs


def audit(root: Path, docs: list[LegalDoc]) -> int:
    errors = 0
    print("\nAudit:")
    for doc in docs:
        p = root / doc.filename
        if not p.exists():
            print(f"  MISSING  {doc.filename}")
            errors += 1
            continue

        s = p.read_text(encoding="utf-8", errors="replace")
        if failed_stub(s):
            print(f"  FAILED   {doc.filename}")
            errors += 1
            continue

        if not valid_existing(s, doc):
            ok, reason = validate_legal_text(s, doc.number)
            print(
                f"  INVALID  {doc.filename} ({p.stat().st_size:,} bytes) | "
                f"{reason} | article_count={article_count(s)} | "
                f"number_present={contains_number(s, doc.number)}"
            )
            errors += 1
            continue

        quality = "secondary"
        if 'source_quality: "A_official_html"' in s:
            quality = "official"
        print(f"  OK       {doc.filename} ({p.stat().st_size:,} bytes, {quality})")
    return errors



def validator_self_test() -> None:
    raw = """100/2019/NĐ-CP
Điều 1. Phạm vi điều chỉnh
Nội dung.
Điều 2. Đối tượng áp dụng
Nội dung.
"""
    rendered = """---
document_number: "100/2019/NĐ-CP"
exclude_from_rag: false
---

# 100/2019/NĐ-CP

### Điều 1. Phạm vi điều chỉnh
Nội dung.

### Điều 2. Đối tượng áp dụng
Nội dung.
"""
    assert article_count(raw) == 2, article_count(raw)
    assert article_count(rendered) == 2, article_count(rendered)
    assert contains_number(rendered, "100/2019/NĐ-CP")



def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/corpus/mds")
    ap.add_argument("--include-recommended", action="store_true")
    ap.add_argument(
        "--include-current-2026",
        action="store_true",
        help="Add current 2026 replacements/amendments required for a current-law corpus.",
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--audit-only", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--sleep", type=float, default=0.7)
    ap.add_argument(
        "--keep-failure-stubs",
        action="store_true",
        help="Write exclude_from_rag stubs. Otherwise a new failed target remains empty.",
    )
    return ap.parse_args()


def main() -> int:
    validator_self_test()
    args = parse_args()
    root = Path(args.dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    docs = selected_docs(args)

    print(f"Target: {root}")
    print(f"Documents: {len(docs)}")
    print("Strategy: official HTML -> LuatVietnam HTML -> search-discovered LuatVietnam HTML; OCR disabled")

    if args.audit_only:
        return 1 if audit(root, docs) else 0

    session = make_session()
    failures = []

    for idx, doc in enumerate(docs, 1):
        path = root / doc.filename

        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
            print(f"[{idx}/{len(docs)}] CREATE {doc.filename}")

        old = path.read_text(encoding="utf-8", errors="replace")
        old_valid = valid_existing(old, doc)

        if old_valid and not args.force:
            print(f"[{idx}/{len(docs)}] SKIP {doc.filename}: valid existing")
            continue

        print(f"[{idx}/{len(docs)}] HTML FETCH {doc.number} -> {doc.filename}")

        try:
            text, provenance = fetch_document(session, doc)
            ok, reason = validate_legal_text(text, doc.number)
            if not ok:
                raise RuntimeError(reason)
            output = render(doc, text, provenance)
            try:
                from clean_traffic_corpus import clean_markdown
                output, _ = clean_markdown(output)
            except (ImportError, ValueError) as exc:
                raise RuntimeError(f"deterministic cleanup failed: {exc}") from exc
            atomic_write(path, output)

            print(
                f"    OK {len(text):,} chars, {article_count(text)} articles | "
                f"{provenance['content_source_type']} | {provenance['content_url']}"
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            failures.append((doc.filename, error))

            if old_valid:
                print(f"    FAIL, kept previous valid file: {error}", file=sys.stderr)
            elif args.keep_failure_stubs:
                atomic_write(path, failure_stub(doc, error))
                print(f"    FAIL, wrote excluded stub: {error}", file=sys.stderr)
            else:
                path.write_text("", encoding="utf-8")
                print(f"    FAIL, left empty: {error}", file=sys.stderr)

        if idx < len(docs):
            time.sleep(max(0.0, args.sleep))

    local_errors = audit(root, docs)

    if failures:
        print("\nFailures:", file=sys.stderr)
        for name, err in failures:
            print(f"  - {name}: {err}", file=sys.stderr)

    if failures or local_errors:
        return 1

    print("\nAll requested files passed HTML verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
