"""분석 결과를 GitHub Pages용 웹페이지로 만든다.

data/lotto.csv를 기간별(전체, 최근 100회, 최근 52회)로 집계해서
site_template.html의 __DATA__ 자리에 JSON으로 넣고, GitHub Pages가 보여주는 docs/index.html로 저장한다.
원본 당첨번호 전체는 넣지 않고 집계 결과만 넣는다.
"""
import json
from html import escape
from pathlib import Path

import pandas as pd

from analyze import (CHI2_CRITICAL, DATA_FILE, NUM_COLS, bonus_frequency, carryover_neighbors,
                     chi_square, combo_counts, consecutive_pairs, cumulative, draws_since_last_seen, ending_kinds,
                     ending_share, low_high, number_frequency, odd_even_ratio, pair_counts,
                     range_share, records, sum_distribution, sum_theory, yearly_trend)

BASE_DIR = Path(__file__).parent
TEMPLATE_FILE = BASE_DIR / "site_template.html"
OUT_FILE = BASE_DIR / "docs" / "index.html"
WINDOWS = {"all": None, "100": 100, "52": 52}  # 최근 N회 (None은 전체, 52회는 약 1년)


def summarize(df):
    """한 기간의 번호별 빈도(당첨번호, 보너스), 홀짝 비율, 카이제곱 값."""
    freq = number_frequency(df)
    actual, _ = odd_even_ratio(df)
    ranges, _ = range_share(df)
    return {
        "draws": len(df),
        "freq": freq.tolist(),
        "bonusFreq": bonus_frequency(df).tolist(),  # 보너스 번호로 나온 횟수 (번호 1~45)
        "oddEven": [round(x, 6) for x in actual],
        "chi2": round(float(chi_square(freq)), 1),
        "sumDist": [round(x, 6) for x in sum_distribution(df)],
        "sumMean": round(float(df[NUM_COLS].sum(axis=1).mean()), 1),
        "rangeShare": [round(x, 6) for x in ranges],
    }


def pattern(result):
    """번호 패턴 결과의 비율을 소수 6자리로 줄인다."""
    return {
        "actual": [round(x, 6) for x in result["actual"]],
        "theory": [round(x, 6) for x in result["theory"]],
        "total": result["total"],
    }


def combos(df, k):
    """3개·4개 동반 출현 결과의 기대값을 줄인다."""
    result = combo_counts(df, k)
    return {**result, "expected": round(result["expected"], 4),
            "theory": [round(x, 3) for x in result["theory"]]}


def main():
    if not DATA_FILE.exists():
        raise SystemExit("data/lotto.csv가 없습니다. 먼저 collect.py를 실행해 주세요.")

    df = pd.read_csv(DATA_FILE).sort_values("draw_no")
    first, last = df.iloc[0], df.iloc[-1]
    _, theory = odd_even_ratio(df)
    _, range_theory = range_share(df)

    # 같은 데이터면 항상 같은 페이지가 나오도록 생성 날짜 같은 값은 넣지 않는다.
    # (자동 갱신 때 새 회차가 없으면 바뀐 게 없어 커밋하지 않게 하려는 것)
    data = {
        "first": {"no": int(first.draw_no), "date": first.draw_date},
        "last": {
            "no": int(last.draw_no),
            "date": last.draw_date,
            "numbers": [int(last[col]) for col in NUM_COLS],
            "bonus": int(last.bonus),
            "firstWinners": int(last.first_winners),  # 1등 당첨자 수
            "firstPrize": int(last.first_prize),      # 1등 1인당 당첨금(원)
        },
        "chi2Critical": CHI2_CRITICAL,
        "oddEvenTheory": [round(x, 6) for x in theory],
        "sumTheory": [round(x, 6) for x in sum_theory()],
        "rangeTheory": [round(x, 6) for x in range_theory],
        "gap": draws_since_last_seen(df).astype(int).tolist(),
        "windows": {key: summarize(df if n is None else df.tail(n)) for key, n in WINDOWS.items()},
        "yearly": yearly_trend(df),
        "cumulative": cumulative(df),
        "records": records(df),
        "pairs": pair_counts(df),  # (1,2), (1,3), ..., (44,45) 순서
        "combos": {str(k): combos(df, k) for k in (3, 4)},  # 3개·4개가 함께 나온 횟수
        # 번호 패턴: 카드마다 차트 순서대로 [{actual, theory, total}, ...]
        "patterns": {
            "consecutive": [pattern(consecutive_pairs(df))],
            "lowHigh": [pattern(low_high(df))],
            "ending": [pattern(ending_share(df)), pattern(ending_kinds(df))],
            "carry": [pattern(p) for p in carryover_neighbors(df)],
        },
    }

    # 검색 결과와 공유 미리보기 카드에 보일 설명 (최신 회차가 바뀌면 함께 바뀐다)
    numbers = ", ".join(str(n) for n in data["last"]["numbers"])
    description = (f"최신 {data['last']['no']}회 당첨번호 {numbers} + 보너스 {data['last']['bonus']}. "
                   f"1회부터 {data['last']['no']}회까지 번호별 출현 빈도와 홀짝 조합을 분석했습니다.")

    html = TEMPLATE_FILE.read_text(encoding="utf-8")
    html = html.replace("__DESCRIPTION__", escape(description))
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"웹페이지 생성: {OUT_FILE} ({last.draw_no}회 기준)")


if __name__ == "__main__":
    main()
