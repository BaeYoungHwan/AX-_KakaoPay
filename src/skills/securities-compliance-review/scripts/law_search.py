import argparse
import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("LAW_API_KEY")
BASE_URL = os.getenv("LAW_API_BASE_URL", "http://www.law.go.kr/DRF")


@dataclass
class LawItem:
    name: str
    mst: str
    department: str
    promulgation_date: str
    link: str


@dataclass
class LawArticle:
    law_name: str
    article_no: str
    article_title: str
    content: str


def search_laws(query: str, display: int = 5, page: int = 1) -> list[LawItem]:
    params = {
        "OC": API_KEY,
        "target": "law",
        "type": "XML",
        "query": query,
        "display": display,
        "page": page,
    }
    resp = requests.get(f"{BASE_URL}/lawSearch.do", params=params, timeout=10)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    results = []
    for law in root.findall(".//law"):
        results.append(
            LawItem(
                name=_text(law, "법령명한글"),
                mst=_text(law, "법령일련번호"),
                department=_text(law, "소관부처명"),
                promulgation_date=_text(law, "공포일자"),
                link=_text(law, "법령상세링크"),
            )
        )
    return results


def get_law_articles(mst: str) -> list[LawArticle]:
    url = (
        f"{BASE_URL}/lawService.do"
        f"?OC={API_KEY}&target=law&MST={mst}&type=XML"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read()

    root = ET.fromstring(data)
    law_name = _text(root, ".//법령명_한글")
    results = []
    for jo in root.findall(".//조문단위"):
        if _text(jo, "조문여부") != "조문":
            continue
        content = _text(jo, "조문내용")
        if not content:
            continue
        results.append(
            LawArticle(
                law_name=law_name,
                article_no=_text(jo, "조문번호"),
                article_title=_text(jo, "조문제목"),
                content=content,
            )
        )
    return results


def search_relevant_articles(keywords: list[str], max_laws: int = 3) -> list[LawArticle]:
    import time
    articles = []
    seen_mst = set()
    for kw in keywords:
        laws = []
        for attempt in range(3):
            try:
                laws = search_laws(kw, display=max_laws)
                break
            except Exception:
                if attempt < 2:
                    time.sleep(1)
        for law in laws:
            if law.mst in seen_mst:
                continue
            seen_mst.add(law.mst)
            for attempt in range(3):
                try:
                    articles.extend(get_law_articles(law.mst))
                    break
                except Exception:
                    if attempt < 2:
                        time.sleep(1)
    return articles


def _text(element: ET.Element, path: str) -> str:
    node = element.find(path)
    return (node.text or "").strip() if node is not None else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="법제처 Open API 조문 검색")
    parser.add_argument(
        "keywords",
        nargs="+",
        help="검색 키워드 (예: 자본시장법 금융소비자보호법). content_classifier.py의 law_keywords 출력을 그대로 넣으면 된다.",
    )
    parser.add_argument("--max-laws", type=int, default=2, help="키워드당 조회할 법령 수")
    args = parser.parse_args()

    if not API_KEY:
        print(
            json.dumps(
                {"error": "LAW_API_KEY 환경변수가 설정되지 않았습니다. .env.example을 참고해 .env를 만드세요."},
                ensure_ascii=False,
            )
        )
        return 1

    articles = search_relevant_articles(args.keywords, max_laws=args.max_laws)
    print(json.dumps([asdict(a) for a in articles], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
