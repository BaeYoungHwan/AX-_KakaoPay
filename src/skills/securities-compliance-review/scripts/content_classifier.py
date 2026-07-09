"""증권업 투자권유·광고 콘텐츠 분류 + 규칙 기반 위험도 사전 판정.

법제처 API 같은 외부 호출이 필요 없는 순수 규칙 조회이므로, Codex가
`python content_classifier.py <콘텐츠 타입> "<본문>"` 형태로 직접 실행해
법령 검색 키워드와 사전 위험도를 결정론적으로 얻는다. 판정 기준의
출처는 skills/securities-compliance-review/references/심의_기준.md.
"""
from __future__ import annotations
import argparse
import json
import sys

# 콘텐츠 타입별 우선 검색 법령 (references/심의_기준.md 1~2절)
CONTENT_TYPE_LAWS: dict[str, list[str]] = {
    "투자권유문자":            ["자본시장법", "금융소비자보호법"],
    "상품소개서":              ["자본시장법", "금융투자업규정"],
    "SNS광고":                ["자본시장법", "금융투자업규정"],
    "리서치·투자자문 코멘트":    ["자본시장법", "금융소비자보호법"],
    "신규상품 안내 이메일":      ["자본시장법", "금융소비자보호법"],
}

# 콘텐츠 내 키워드가 감지되면 해당 법령을 우선 적용 (심의_기준.md 3절)
_KEYWORD_BOOST: dict[str, list[str]] = {
    "수익":     ["금융소비자보호법"],
    "보장":     ["금융소비자보호법"],
    "확정":     ["금융소비자보호법"],
    "원금":     ["금융소비자보호법"],
    "손실":     ["금융소비자보호법"],
    "투자":     ["자본시장법", "금융소비자보호법"],
    "펀드":     ["자본시장법"],
    "손실 없이": ["자본시장법", "금융소비자보호법"],
    "무조건":    ["자본시장법", "금융투자업규정"],
    "확실히":    ["자본시장법", "금융투자업규정"],
    "원금 보장": ["자본시장법", "금융소비자보호법"],
    "확정 수익": ["자본시장법", "금융소비자보호법"],
    "확정 금리": ["자본시장법", "금융소비자보호법"],
    "국내 유일": ["금융투자업규정"],
    "업계 최초": ["금융투자업규정"],
    "타사 대비": ["금융투자업규정"],
    "과거 수익률": ["자본시장법", "금융투자업규정"],
    "지금 아니면": ["금융투자업규정"],
    "한정":      ["금융투자업규정"],
    "선착순":     ["금융투자업규정"],
}

# 규칙 기반 위험도 선판정 (심의_기준.md 4절)
# Codex가 최종 판단하기 전에 명백한 위반 표현에 기본 위험도를 부여해,
# 위반을 과소평가하지 않도록 하는 안전장치. 최종 판단·조문 인용은
# SKILL.md 지침에 따라 Codex가 검색된 조문 근거로 다시 확인한다.
_RISK_RULES: list[tuple[str, list[str], str]] = [
    (
        "High",
        ["원금 보장", "확정 수익", "확정 금리", "원금보장", "확정수익", "확정금리"],
        "투자상품을 예금처럼 오인하게 하는 표현은 자본시장법상 부당권유 소지가 매우 큼",
    ),
    (
        "Medium",
        ["손실 없이", "무조건", "국내 유일", "업계 최초", "타사 대비"],
        "단정·과장 표현으로 과장 광고 소지",
    ),
    (
        "Medium",
        ["과거 수익률", "과거수익률"],
        "과거 실적을 미래 수익 보장으로 오인시킬 소지",
    ),
    (
        "Low",
        ["지금 아니면", "한정", "선착순"],
        "긴급성 표현으로 합리적 판단을 저해할 소지 (단독 위반은 아님)",
    ),
]

_RISK_ORDER = {"없음": 0, "Low": 1, "Medium": 2, "High": 3}


def get_law_keywords(content_type: str, content: str = "") -> list[str]:
    """콘텐츠 타입 + 본문 키워드 분석으로 적용 법령 목록을 반환한다."""
    base = list(CONTENT_TYPE_LAWS.get(content_type, []))
    for keyword, laws in _KEYWORD_BOOST.items():
        if keyword in content:
            for law in laws:
                if law not in base:
                    base.append(law)
    return base


def get_preliminary_risk(content: str) -> dict | None:
    """규칙 기반 사전 위험도 판정. 매칭되는 규칙이 없으면 None.

    가장 높은 위험도의 규칙 하나를 {"risk": ..., "reason": ...} 형태로 반환한다.
    """
    best: dict | None = None
    for risk, keywords, reason in _RISK_RULES:
        if any(kw in content for kw in keywords):
            if best is None or _RISK_ORDER[risk] > _RISK_ORDER[best["risk"]]:
                best = {"risk": risk, "reason": reason}
    return best


def get_all_types() -> list[str]:
    return list(CONTENT_TYPE_LAWS.keys())


def classify(content_type: str, content: str) -> dict:
    return {
        "content_type": content_type,
        "law_keywords": get_law_keywords(content_type, content),
        "preliminary_risk": get_preliminary_risk(content),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="증권업 콘텐츠 타입/키워드/사전위험도 분류")
    parser.add_argument("content_type", help=f"콘텐츠 타입 (예: {', '.join(get_all_types())})")
    parser.add_argument("content", help="심의 대상 본문")
    args = parser.parse_args()

    result = classify(args.content_type, args.content)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
