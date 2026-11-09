"""동행복권 로또 6/45 당첨번호 수집기.

동행복권 '당첨결과' 페이지(https://www.dhlottery.co.kr/lt645/result)는
화면을 그릴 때 아래 API_URL에서 JSON으로 당첨 정보를 받아온다.
이 주소를 직접 호출해 1회차부터 최신 회차까지 모아 data/lotto.csv에 저장한다.

- 이미 저장된 회차는 건너뛰고 새 회차만 이어서 받는다. (매주 다시 실행하면 됨)
- 한 번 요청에 10개 회차씩 오며, 요청 사이에 DELAY_SEC만큼 쉰다.
- 마지막 추첨일로부터 7일이 안 지났으면(다음 회차가 아직 없으면) 아무 요청도 하지 않고 끝낸다.

안전장치 (하나라도 걸리면 데이터는 요청하지 않고 멈춘다):
1. 수집 전에 robots.txt를 읽어 데이터 주소가 금지돼 있으면 멈춘다. 읽지 못해도 멈춘다.
2. robots.txt가 마지막으로 사람이 확인한 내용(robots_snapshot.txt)과 다르면 멈춘다.
   확인 후 문제가 없으면 `python collect.py --accept-robots`로 저장본을 갱신한다.
3. 수집 후 최신 회차가 STALE_DAYS일 넘게 그대로면 실패로 알린다. (매주 토요일 추첨)
"""
import csv
import difflib
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.robotparser import RobotFileParser

import requests

API_URL = "https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do"
ROBOTS_URL = "https://www.dhlottery.co.kr/robots.txt"
BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "lotto.csv"
ROBOTS_SNAPSHOT = BASE_DIR / "robots_snapshot.txt"  # 마지막으로 사람이 확인한 robots.txt
DELAY_SEC = 1.0  # 서버에 부담을 주지 않도록 요청 사이 대기 시간(초)
STALE_DAYS = 8   # 최신 추첨일로부터 이만큼 지나도 새 회차가 없으면 이상한 것
DRAW_INTERVAL_DAYS = 7  # 매주 토요일 추첨. 마지막 추첨일로부터 이만큼 지나야 다음 회차가 나온다
KST = timezone(timedelta(hours=9))

COLUMNS = [
    "draw_no",        # 회차
    "draw_date",      # 추첨일
    "n1", "n2", "n3", "n4", "n5", "n6",  # 당첨번호 6개 (오름차순)
    "bonus",          # 보너스 번호
    "first_winners",  # 1등 당첨자 수
    "first_prize",    # 1등 1인당 당첨금(원)
    "total_sales",    # 총 판매금액(원)
]


# ---------------------------------------------------------------- 안전장치

def fetch_robots():
    """동행복권 robots.txt 내용. 읽지 못하면 수집을 멈춘다."""
    try:
        res = requests.get(ROBOTS_URL, timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        sys.exit(f"[중단] robots.txt를 읽지 못해 수집하지 않습니다: {e}")
    return res.text.replace("\r\n", "\n").strip()


def is_allowed(robots_text):
    """robots.txt 규칙상 우리 데이터 주소를 수집해도 되는지."""
    parser = RobotFileParser()
    parser.parse(robots_text.splitlines())
    return parser.can_fetch(requests.utils.default_user_agent(), API_URL)


def check_robots():
    """수집 전 robots.txt 확인. 금지됐거나, 확인해 둔 내용과 달라졌으면 멈춘다."""
    current = fetch_robots()
    if not is_allowed(current):
        sys.exit(f"[중단] robots.txt에서 데이터 주소({API_URL}) 수집을 금지하고 있어 수집하지 않습니다.")

    saved = ROBOTS_SNAPSHOT.read_text(encoding="utf-8").strip() if ROBOTS_SNAPSHOT.exists() else ""
    if current != saved:
        diff = "\n".join(difflib.unified_diff(saved.splitlines(), current.splitlines(),
                                              "확인해 둔 robots.txt", "지금 robots.txt", lineterm=""))
        sys.exit("[중단] robots.txt 내용이 마지막으로 확인한 것과 달라 수집하지 않습니다.\n"
                 f"{diff}\n"
                 "내용을 확인하고 문제가 없으면 `python collect.py --accept-robots`로 저장본을 갱신하세요.")
    print("robots.txt 확인: 변경 없음, 데이터 주소 수집 허용")


def accept_robots():
    """지금 robots.txt를 확인했다고 기록한다. (데이터는 수집하지 않는다)"""
    current = fetch_robots()
    ROBOTS_SNAPSHOT.write_text(current + "\n", encoding="utf-8")
    print(current)
    print(f"\n위 내용을 {ROBOTS_SNAPSHOT.name}에 저장했습니다.")
    print("데이터 주소 수집: " + ("허용" if is_allowed(current) else "금지 → 수집하지 않습니다"))


def days_since(draw_date):
    """추첨일(YYYY-MM-DD)로부터 오늘(한국 시간)까지 지난 날 수."""
    return (datetime.now(KST).date() - date.fromisoformat(draw_date)).days


def check_fresh(last_date):
    """최신 추첨일이 STALE_DAYS일 넘게 지났으면 실패로 알린다. (조용히 멈춰 있는 것을 잡기 위해)"""
    days = days_since(last_date)
    if days >= STALE_DAYS:
        sys.exit(f"[확인 필요] 최신 회차 추첨일({last_date})로부터 {days}일이 지났는데 새 회차가 없습니다. "
                 "사이트 응답이 바뀌었을 수 있습니다.")


# ---------------------------------------------------------------- 수집

def to_row(item):
    """API 응답의 한 회차 데이터를 CSV 한 줄(dict)로 바꾼다."""
    ymd = item["ltRflYmd"]  # 예: "20240127"
    return {
        "draw_no": item["ltEpsd"],
        "draw_date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
        **{f"n{i}": item[f"tm{i}WnNo"] for i in range(1, 7)},
        "bonus": item["bnsWnNo"],
        "first_winners": item["rnk1WnNope"],
        "first_prize": item["rnk1WnAmt"],
        "total_sales": item["wholEpsdSumNtslAmt"],
    }


def fetch_after(last_no):
    """last_no 회차 다음부터 최대 10개 회차를 회차 오름차순으로 가져온다."""
    if last_no == 0:
        params = {"srchDir": "center", "srchLtEpsd": 1}  # 1~10회
    else:
        params = {"srchDir": "latest", "srchCursorLtEpsd": last_no}

    res = requests.get(API_URL, params=params, timeout=10)
    res.raise_for_status()
    try:
        items = res.json()["data"]["list"]
    except (ValueError, KeyError, TypeError):
        # 추첨 시간대나 점검 중에는 JSON 대신 안내 페이지가 올 수 있다.
        sys.exit("응답이 예상한 형식이 아닙니다. 사이트 점검 중일 수 있으니 잠시 후 다시 실행해 주세요.")

    rows = [to_row(item) for item in items if item["ltEpsd"] > last_no]
    return sorted(rows, key=lambda row: row["draw_no"])


def load_last():
    """이미 저장된 마지막 회차의 (번호, 추첨일). 저장된 게 없으면 (0, None)."""
    if not DATA_FILE.exists():
        return 0, None
    with DATA_FILE.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return 0, None
    last = max(rows, key=lambda row: int(row["draw_no"]))
    return int(last["draw_no"]), last["draw_date"]


def main():
    if "--accept-robots" in sys.argv:
        accept_robots()
        return

    last_no, last_date = load_last()
    # 마지막 추첨일로부터 7일이 안 지났으면 다음 회차가 아직 없으므로 동행복권에 아무 요청도 하지 않는다.
    # (예: 아침 자동 갱신이 이미 반영한 주의 저녁 예비 실행)
    if last_date and days_since(last_date) < DRAW_INTERVAL_DAYS:
        print(f"저장된 마지막 회차: {last_no}회 ({last_date}) · 다음 추첨 전이라 수집하지 않습니다.")
        return

    check_robots()
    print(f"저장된 마지막 회차: {last_no}회" if last_no else "저장된 데이터 없음 → 1회차부터 수집")

    DATA_FILE.parent.mkdir(exist_ok=True)
    write_header = not DATA_FILE.exists()
    added = 0

    with DATA_FILE.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            writer.writeheader()

        while rows := fetch_after(last_no):
            writer.writerows(rows)
            f.flush()  # 중간에 멈춰도 여기까지는 저장되도록
            last_no, last_date = rows[-1]["draw_no"], rows[-1]["draw_date"]
            added += len(rows)
            print(f"  {rows[0]['draw_no']:>4}~{last_no}회 저장")
            time.sleep(DELAY_SEC)

    print(f"완료: {added}개 회차 추가 (최신 {last_no}회) → {DATA_FILE}")
    if last_date:
        check_fresh(last_date)


if __name__ == "__main__":
    main()
