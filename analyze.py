"""수집한 로또 당첨번호(data/lotto.csv)로 번호별 출현 빈도와 홀짝 비율을 분석한다.

분석 결과는 콘솔에 출력하고, 차트는 output/ 폴더에 PNG로 저장한다.
먼저 collect.py로 데이터를 모아야 한다.
"""
from collections import Counter
from itertools import combinations
from math import comb
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "lotto.csv"
OUT_DIR = BASE_DIR / "output"
NUM_COLS = ["n1", "n2", "n3", "n4", "n5", "n6"]
NUMBERS = range(1, 46)

# 번호가 완전히 무작위라면 카이제곱 값이 이보다 클 확률은 5%뿐이다. (자유도 44)
CHI2_CRITICAL = 60.48

# 차트 색상
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
ORANGE = "#eb6834"

plt.rcParams.update({
    "font.family": "Malgun Gothic",  # 윈도우 기본 한글 폰트
    "axes.unicode_minus": False,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": BASELINE,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 1,
    "axes.titlecolor": INK,
    "axes.titlesize": 14,
    "axes.titleweight": "bold",
    "axes.labelcolor": INK_SECONDARY,
    "xtick.color": INK_MUTED,
    "ytick.color": INK_MUTED,
    "ytick.left": False,
})


# ---------------------------------------------------------------- 분석

def number_frequency(df):
    """1~45 각 번호가 당첨번호(보너스 제외)로 나온 횟수."""
    return df[NUM_COLS].stack().value_counts().reindex(NUMBERS, fill_value=0)


def chi_square(freq):
    """모든 번호가 똑같이 나온다고 가정했을 때와의 차이(카이제곱 통계량)."""
    expected = freq.sum() / len(freq)
    return ((freq - expected) ** 2 / expected).sum()


def odd_even_ratio(df):
    """회차별 홀수 개수(0~6개)의 실제 비율과 이론 확률."""
    odd_count = (df[NUM_COLS] % 2 == 1).sum(axis=1)
    actual = odd_count.value_counts(normalize=True).reindex(range(7), fill_value=0)
    # 1~45에는 홀수 23개, 짝수 22개 → 6개를 뽑을 때 홀수가 k개일 확률(초기하분포)
    theory = pd.Series([comb(23, k) * comb(22, 6 - k) / comb(45, 6) for k in range(7)])
    return actual, theory


# 번호 6개 합계(21~255) 구간: 60 이하, 61~80, 81~100, ..., 201~220, 221 이상 (양 끝은 거의 안 나와서 묶음)
SUM_BIN_COUNT = 10
RANGES = [(1, 10), (11, 20), (21, 30), (31, 40), (41, 45)]


def sum_bin(total):
    """번호 합계가 속한 구간 번호(0~9)."""
    return min(max((total - 41) // 20, 0), SUM_BIN_COUNT - 1)


def sum_distribution(df):
    """회차별 번호 6개 합계가 각 구간에 들어간 비율."""
    bins = df[NUM_COLS].sum(axis=1).map(sum_bin)
    return bins.value_counts(normalize=True).reindex(range(SUM_BIN_COUNT), fill_value=0)


def sum_theory():
    """1~45에서 6개를 뽑을 때 합계 구간별 이론 확률. 모든 조합(8,145,060개)의 합을 세어 계산한다."""
    # ways[k][s]: 지금까지 본 번호 중 k개를 골라 합이 s가 되는 경우의 수
    ways = [[0] * 256 for _ in range(7)]
    ways[0][0] = 1
    for n in NUMBERS:
        for k in range(6, 0, -1):
            for s in range(255, n - 1, -1):
                ways[k][s] += ways[k - 1][s - n]
    shares = [0.0] * SUM_BIN_COUNT
    for s in range(21, 256):
        shares[sum_bin(s)] += ways[6][s] / comb(45, 6)
    return pd.Series(shares)


def range_share(df):
    """당첨번호(보너스 제외)가 1~10, 11~20, 21~30, 31~40, 41~45 구간에 속한 비율과 이론 비율."""
    nums = df[NUM_COLS].to_numpy().ravel()
    actual = pd.Series([((nums >= lo) & (nums <= hi)).mean() for lo, hi in RANGES])
    theory = pd.Series([(hi - lo + 1) / 45 for lo, hi in RANGES])
    return actual, theory


def pair_counts(df):
    """두 번호가 같은 회차 당첨번호(보너스 제외)에 함께 나온 횟수.
    (1,2), (1,3), ..., (1,45), (2,3), ..., (44,45) 순서로 990개를 돌려준다."""
    counts = Counter()
    for row in df[NUM_COLS].itertuples(index=False):
        counts.update(combinations(sorted(row), 2))
    return [counts[pair] for pair in combinations(NUMBERS, 2)]


# ---------------------------------------------------------------- 번호 패턴 (실제 비율 vs 이론 확률)
# 각 함수는 {"actual": 구간별 실제 비율, "theory": 구간별 이론 확률, "total": 비율의 분모} 를 돌려준다.

def fold(values, last):
    """0, 1, ..., last-1, last 이상으로 묶는다. (값이 last 이상인 칸을 하나로 합침)"""
    return values[:last] + [sum(values[last:])]


def consecutive_pairs(df):
    """회차별 연속 번호 쌍(예: 23·24)의 개수: 없음, 1쌍, 2쌍, 3쌍 이상.
    23·24·25처럼 세 개가 이어지면 2쌍으로 센다."""
    pairs = df[NUM_COLS].diff(axis=1).eq(1).sum(axis=1).clip(upper=3)
    actual = pairs.value_counts(normalize=True).reindex(range(4), fill_value=0)
    # 1~45에서 6개를 고를 때 연속 쌍이 정확히 s개인 조합 수 = C(5, s) × C(40, 6 − s)
    theory = [comb(5, s) * comb(40, 6 - s) / comb(45, 6) for s in range(6)]
    return {"actual": actual.tolist(), "theory": fold(theory, 3), "total": len(df)}


def low_high(df):
    """회차별 낮은 번호(1~22) 개수 0~6개의 비율. 높은 번호(23~45)는 6 − 낮은 번호 개수다."""
    low = (df[NUM_COLS] <= 22).sum(axis=1)
    actual = low.value_counts(normalize=True).reindex(range(7), fill_value=0)
    # 낮은 번호 22개, 높은 번호 23개 중 6개를 뽑을 때 낮은 번호가 k개일 확률 (초기하분포)
    theory = [comb(22, k) * comb(23, 6 - k) / comb(45, 6) for k in range(7)]
    return {"actual": actual.tolist(), "theory": theory, "total": len(df)}


# 끝자리(일의 자리)별 번호 개수: 끝자리 0은 4개(10·20·30·40), 1~5는 5개, 6~9는 4개
ENDING_COUNTS = [sum(1 for n in NUMBERS if n % 10 == d) for d in range(10)]


def ending_share(df):
    """당첨번호(보너스 제외)의 끝자리 0~9 비율과 이론 비율(끝자리별 번호 개수 ÷ 45)."""
    endings = df[NUM_COLS].to_numpy().ravel() % 10
    actual = [float((endings == d).mean()) for d in range(10)]
    return {"actual": actual, "theory": [c / 45 for c in ENDING_COUNTS], "total": int(endings.size)}


def ending_kinds(df):
    """회차별 번호 6개의 끝자리 종류 수: 3가지 이하, 4가지, 5가지, 6가지(모두 다름)."""
    kinds = (df[NUM_COLS] % 10).nunique(axis=1).clip(lower=3)
    actual = kinds.value_counts(normalize=True).reindex(range(3, 7), fill_value=0)
    # 끝자리 묶음마다 몇 개를 고를지 정해 가며 (고른 개수, 쓴 끝자리 종류 수)별 조합 수를 센다
    ways = {(0, 0): 1}
    for size in ENDING_COUNTS:
        nxt = Counter()
        for (picked, used), w in ways.items():
            for take in range(min(size, 6 - picked) + 1):
                nxt[(picked + take, used + (take > 0))] += w * comb(size, take)
        ways = nxt
    theory = [ways[(6, k)] / comb(45, 6) for k in range(1, 7)]  # 종류 수 1~6가지
    return {"actual": actual.tolist(), "theory": [sum(theory[:3])] + theory[3:], "total": len(df)}


def carryover_neighbors(df):
    """직전 회차와 비교한 이월수(직전 당첨번호가 다시 나온 개수)와 이웃수(직전 번호의 ±1이 나온 개수).
    각각 0개, 1개, 2개, 3개 이상. 직전 번호와 같은 번호는 이월수로만 센다. 첫 회차는 직전 회차가 없어 뺀다."""
    rows = df.sort_values("draw_no")[NUM_COLS].to_numpy().tolist()
    carry, near = Counter(), Counter()
    near_theory = [0.0] * 7
    for prev, cur in zip(rows, rows[1:]):
        prev, cur = set(prev), set(cur)
        neighbors = {n + d for n in prev for d in (-1, 1) if 1 <= n + d <= 45} - prev
        carry[min(len(cur & prev), 3)] += 1
        near[min(len(cur & neighbors), 3)] += 1
        # 이웃 번호 개수(m)가 회차마다 달라서, 회차마다 초기하분포를 구해 평균 낸다
        m = len(neighbors)
        for k in range(7):
            near_theory[k] += comb(m, k) * comb(45 - m, 6 - k) / comb(45, 6)
    n = len(rows) - 1
    # 직전 당첨번호 6개와 나머지 39개 중 6개를 뽑을 때 직전 번호가 k개 들어갈 확률 (초기하분포)
    carry_theory = [comb(6, k) * comb(39, 6 - k) / comb(45, 6) for k in range(7)]
    return (
        {"actual": [carry[k] / n for k in range(4)], "theory": fold(carry_theory, 3), "total": n},
        {"actual": [near[k] / n for k in range(4)], "theory": fold([t / n for t in near_theory], 3), "total": n},
    )


def draws_since_last_seen(df):
    """번호별로 마지막으로 나온 뒤 몇 회차째 안 나오고 있는지."""
    long = df.melt(id_vars="draw_no", value_vars=NUM_COLS, value_name="number")
    last_seen = long.groupby("number")["draw_no"].max().reindex(NUMBERS)
    return df["draw_no"].max() - last_seen


def yearly_trend(df):
    """연도별 회당 평균 1등 당첨자 수, 1등 1인당 평균 당첨금, 회당 평균 판매액."""
    df = df.assign(year=df["draw_date"].str[:4].astype(int))
    rows = []
    for year, g in df.groupby("year"):
        won = g[g["first_winners"] > 0]  # 1등이 없어 이월된 회차는 당첨금 평균에서 뺀다
        rows.append({
            "year": int(year),
            "draws": len(g),
            "winners": round(float(g["first_winners"].mean()), 2),
            "prize": int(won["first_prize"].mean()) if len(won) else 0,
            "sales": int(g["total_sales"].mean()),
        })
    return rows


def cumulative(df):
    """1회부터 더한 값: 총 판매액, 1등 당첨자 수, 1등 당첨금 총액(회차별 당첨자 수 × 1인당 당첨금)."""
    return {
        "sales": int(df["total_sales"].sum()),
        "winners": int(df["first_winners"].sum()),
        "payout": int((df["first_winners"] * df["first_prize"]).sum()),
    }


def records(df):
    """역대 기록: 1등 당첨금·당첨자 수·판매액의 최고/최저, 이월 횟수, 번호별 최장 미출현 구간."""
    won = df[df["first_winners"] > 0]
    no_winner = df[df["first_winners"] == 0]

    def draw(row):
        return {"no": int(row.draw_no), "date": row.draw_date, "winners": int(row.first_winners),
                "prize": int(row.first_prize), "sales": int(row.total_sales)}

    # 번호마다 나온 회차 사이의 간격을 보고, 연속으로 안 나온 가장 긴 구간을 찾는다
    last_no = int(df["draw_no"].max())
    long = df.melt(id_vars="draw_no", value_vars=NUM_COLS, value_name="number")
    drought = {"number": 0, "length": 0, "from": 0, "to": 0}
    for number, g in long.groupby("number"):
        seen = [0] + sorted(g["draw_no"].tolist()) + [last_no + 1]
        for a, b in zip(seen, seen[1:]):
            if b - a - 1 > drought["length"]:
                drought = {"number": int(number), "length": b - a - 1, "from": a + 1, "to": b - 1}

    return {
        "topPrize": draw(won.loc[won["first_prize"].idxmax()]),
        "lowPrize": draw(won.loc[won["first_prize"].idxmin()]),
        "mostWinners": draw(df.loc[df["first_winners"].idxmax()]),
        "topSales": draw(df.loc[df["total_sales"].idxmax()]),
        "noWinner": {"count": len(no_winner), "last": draw(no_winner.iloc[-1]) if len(no_winner) else None},
        "drought": drought,
    }


# ---------------------------------------------------------------- 차트

def plot_frequency(freq, draw_range, path):
    expected = freq.sum() / len(freq)
    fig, ax = plt.subplots(figsize=(12, 5), dpi=150)

    ax.bar(freq.index, freq.values, width=0.6, color=BLUE)
    ax.axhline(expected, color=INK_SECONDARY, linewidth=1)
    ax.text(45.6, expected, f"기대값\n{expected:.1f}회", va="center", fontsize=9, color=INK_SECONDARY)

    # 가장 많이/적게 나온 번호에만 값 표시
    for number in [freq.idxmax(), freq.idxmin()]:
        ax.text(number, freq[number] + 2, f"{freq[number]}", ha="center", va="bottom",
                fontsize=9, fontweight="bold", color=INK)

    ax.set_title(f"번호별 당첨 횟수 ({draw_range}, 보너스 제외)", loc="left", pad=12)
    ax.set_xticks(list(NUMBERS))
    ax.tick_params(axis="x", labelsize=8, length=0)
    ax.set_xlim(0.3, 45.7)
    ax.set_ylabel("당첨 횟수")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def plot_odd_even(actual, theory, draw_range, path):
    x = list(range(7))
    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)

    bars = ax.bar(x, actual * 100, width=0.6, color=BLUE)
    dots, = ax.plot(x, theory * 100, "o", markersize=9, color=ORANGE,
                    markeredgecolor=SURFACE, markeredgewidth=2)

    for k in x:
        top = max(actual[k], theory[k]) * 100
        ax.text(k, top + 1.2, f"{actual[k] * 100:.1f}%", ha="center", va="bottom",
                fontsize=9, color=INK)

    ax.set_title(f"회차별 홀짝 조합 비율 ({draw_range})", loc="left", pad=12)
    ax.set_xticks(x, [f"{k}:{6 - k}" for k in x])
    ax.tick_params(axis="x", labelsize=10, length=0, labelcolor=INK_SECONDARY)
    ax.set_xlabel("홀수 : 짝수")
    ax.set_ylabel("비율 (%)")
    ax.legend([bars, dots], ["실제 비율", "이론 확률"], frameon=False, loc="upper right",
              labelcolor=INK_SECONDARY)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------- 실행

def main():
    if not DATA_FILE.exists():
        raise SystemExit("data/lotto.csv가 없습니다. 먼저 collect.py를 실행해 주세요.")

    df = pd.read_csv(DATA_FILE).sort_values("draw_no")
    OUT_DIR.mkdir(exist_ok=True)
    first, last = df.iloc[0], df.iloc[-1]
    draw_range = f"{first.draw_no}~{last.draw_no}회"

    print(f"=== 로또 6/45 분석: {first.draw_no}회({first.draw_date}) ~ "
          f"{last.draw_no}회({last.draw_date}), 총 {len(df)}회 ===\n")

    # 1. 번호별 출현 빈도
    freq = number_frequency(df)
    expected = freq.sum() / len(freq)
    most = freq.sort_values(ascending=False).head(6)
    least = freq.sort_values().head(6)
    chi2 = chi_square(freq)

    print("[1] 번호별 출현 빈도 (보너스 제외)")
    print(f"  기대값: 6개 × {len(df)}회 ÷ 45 = {expected:.1f}회")
    print("  많이 나온 번호: " + ", ".join(f"{n}({c}회)" for n, c in most.items()))
    print("  적게 나온 번호: " + ", ".join(f"{n}({c}회)" for n, c in least.items()))
    verdict = "우연으로 설명되는 수준" if chi2 < CHI2_CRITICAL else "우연이라 보기엔 큰 차이"
    print(f"  카이제곱 {chi2:.1f} (기준 {CHI2_CRITICAL}) → 번호별 차이는 {verdict}\n")

    # 2. 홀짝 비율
    actual, theory = odd_even_ratio(df)
    print("[2] 회차별 홀짝 조합")
    print("  홀:짝    실제    이론")
    for k in range(7):
        print(f"  {k}:{6 - k}   {actual[k] * 100:5.1f}%  {theory[k] * 100:5.1f}%")
    total_odd = (df[NUM_COLS] % 2 == 1).to_numpy().sum()
    print(f"  전체 당첨번호 중 홀수 비율: {total_odd / df[NUM_COLS].size * 100:.1f}% "
          f"(이론 {23 / 45 * 100:.1f}%)\n")

    # 3. 오래 안 나온 번호
    gap = draws_since_last_seen(df).sort_values(ascending=False).head(5)
    print("[3] 오래 안 나온 번호")
    print("  " + ", ".join(f"{n}({g}회째)" for n, g in gap.items()) + "\n")

    plot_frequency(freq, draw_range, OUT_DIR / "number_frequency.png")
    plot_odd_even(actual, theory, draw_range, OUT_DIR / "odd_even.png")
    print(f"차트 저장: {OUT_DIR / 'number_frequency.png'}")
    print(f"           {OUT_DIR / 'odd_even.png'}")


if __name__ == "__main__":
    main()
