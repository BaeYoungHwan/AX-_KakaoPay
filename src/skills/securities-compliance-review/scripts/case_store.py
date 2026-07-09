"""과거 심의 이력을 JSON 파일에 저장·조회하는 가벼운 사례 저장소.

ChromaDB/임베딩 모델 대신 단어 겹침 기반 유사도(Jaccard)를 사용한다.
평가자 환경에 별도 벡터DB나 임베딩 모델 설치 없이 바로 실행되도록
표준 라이브러리만 사용한다.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone

_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cases.json")

# 거절/수정 건에서 의미 없는 피드백으로 간주하는 기본값 (심의_기준.md 6절)
_MEANINGLESS_FEEDBACK = {"거절", "수정 승인", "rejected", "modified", ""}


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[가-힣A-Za-z0-9]+", text))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def load_cases() -> list[dict]:
    if not os.path.isfile(_DATA_PATH):
        return []
    with open(_DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_all(cases: list[dict]) -> None:
    os.makedirs(os.path.dirname(_DATA_PATH), exist_ok=True)
    with open(_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)


def query_similar_cases(content: str, content_type: str | None = None, n: int = 3) -> list[dict]:
    """content_type이 일치하는 과거 사례 중 단어 겹침 유사도 상위 n건을 반환한다."""
    cases = load_cases()
    if content_type:
        cases = [c for c in cases if c.get("content_type") == content_type]

    query_tokens = _tokenize(content)
    scored = []
    for c in cases:
        sim = _jaccard(query_tokens, _tokenize(c.get("content", "")))
        scored.append((sim, c))
    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        {**c, "similarity": round(sim, 3)}
        for sim, c in scored[:n]
    ]


def _is_low_quality(result: str, feedback: str, violated_laws: list[str]) -> bool:
    """승인이 아닌 케이스에서 피드백 품질이 부족한지 판단한다 (심의_기준.md 6절).

    - 피드백 텍스트가 기본값이거나 5자 미만이면 저품질
    - 거절 시 위반 법령이 명시되지 않으면 저품질
    """
    if result == "approved":
        return False
    stripped = feedback.strip()
    if stripped in _MEANINGLESS_FEEDBACK or len(stripped) < 5:
        return True
    if result == "rejected" and not violated_laws:
        return True
    return False


def save_case(
    content: str,
    result: str,
    content_type: str,
    department: str,
    violated_laws: list[str],
    feedback: str,
) -> str | None:
    """심의 결과를 저장한다. 저품질 피드백은 저장하지 않고 None을 반환한다."""
    if _is_low_quality(result, feedback, violated_laws):
        return None

    cases = load_cases()
    case_id = str(uuid.uuid4())
    cases.append(
        {
            "id": case_id,
            "content": content,
            "content_type": content_type,
            "department": department,
            "result": result,
            "violated_laws": violated_laws,
            "feedback": feedback,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save_all(cases)
    return case_id


def main() -> int:
    parser = argparse.ArgumentParser(description="증권업 준법 심의 이력 저장소")
    sub = parser.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("query", help="유사 과거 사례 조회")
    q.add_argument("content")
    q.add_argument("--type", dest="content_type", default=None)
    q.add_argument("--n", type=int, default=3)

    s = sub.add_parser("save", help="심의 결과 저장")
    s.add_argument("--content", required=True)
    s.add_argument("--result", required=True, choices=["approved", "rejected", "modified"])
    s.add_argument("--type", dest="content_type", required=True)
    s.add_argument("--department", default="")
    s.add_argument("--violated-laws", default="", help="쉼표로 구분")
    s.add_argument("--feedback", default="")

    args = parser.parse_args()

    if args.cmd == "query":
        result = query_similar_cases(args.content, args.content_type, args.n)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "save":
        violated = [v.strip() for v in args.violated_laws.split(",") if v.strip()]
        case_id = save_case(
            content=args.content,
            result=args.result,
            content_type=args.content_type,
            department=args.department,
            violated_laws=violated,
            feedback=args.feedback,
        )
        if case_id is None:
            print(json.dumps({"saved": False, "reason": "저품질 피드백 — 저장 거부"}, ensure_ascii=False))
        else:
            print(json.dumps({"saved": True, "case_id": case_id}, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
