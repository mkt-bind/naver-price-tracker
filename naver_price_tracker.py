import os
import json
import time
import requests
import gspread
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

NAVER_CLIENT_ID = os.environ["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
SHEET_NAME = os.environ["SHEET_NAME"]
NAVER_API_URL = "https://openapi.naver.com/v1/search/shop.json"

START_ROW = 5
COL_SEARCH = 16   # P열: SKU + 컬러코드 (1차 검색어)
COL_FALLBACK = 7  # G열: SKU 품번만 (2차 검색어)

ALLOWED_MALLS = {
    "머스트잇", "트렌비", "발란", "젠테스토어", "렉스몬드",
    "무신사", "29CM", "4910", "하이버", "댄블", "필웨이", "퀸잇", "구하다"
}

gc = gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]))
ws = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)


def is_allowed_mall(mall_name: str) -> bool:
    mall_lower = mall_name.lower()
    for allowed in ALLOWED_MALLS:
        if allowed.lower() in mall_lower:
            return True
    return False


def search_naver(query: str) -> list:
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    items = []
    for start in [1, 101]:
        try:
            resp = requests.get(
                NAVER_API_URL,
                headers=headers,
                params={"query": query, "display": 100, "start": start, "sort": "asc"},
                timeout=10,
            )
            if resp.status_code == 200:
                items.extend(resp.json().get("items", []))
            else:
                print(f"  API 오류 {resp.status_code}: {resp.text[:100]}")
        except requests.RequestException as e:
            print(f"  요청 실패: {e}")
        time.sleep(0.3)
    return items


def filter_allowed(items: list) -> list:
    return [
        it for it in items
        if it.get("lprice") and it["lprice"] != "0"
        and is_allowed_mall(it.get("mallName", ""))
    ]


def merge_and_rank(list1: list, list2: list) -> list:
    """두 결과를 합쳐 판매처별 최저가 기준으로 상위 3개 반환"""
    by_mall = {}
    for item in list1 + list2:
        mall = item.get("mallName", "")
        price = int(item.get("lprice", 0))
        if mall not in by_mall or price < int(by_mall[mall]["lprice"]):
            by_mall[mall] = item
    return sorted(by_mall.values(), key=lambda x: int(x["lprice"]))


def main():
    all_values = ws.get_all_values()
    data_rows = all_values[START_ROW - 1:]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    updates = []

    for i, row in enumerate(data_rows):
        row_num = START_ROW + i
        search_term = row[COL_SEARCH - 1].strip() if len(row) >= COL_SEARCH else ""
        if not search_term:
            continue

        # 1차 검색: P열 (SKU + 컬러코드)
        print(f"[{row_num}행] 1차: {search_term}")
        valid1 = filter_allowed(search_naver(search_term))

        # 2차 검색: 3개 미만이면 G열 (SKU 품번만) 으로 보완
        valid2 = []
        if len(valid1) < 3:
            fallback_term = row[COL_FALLBACK - 1].strip() if len(row) >= COL_FALLBACK else ""
            if fallback_term and fallback_term != search_term:
                print(f"  → {len(valid1)}개 결과, 2차: {fallback_term}")
                valid2 = filter_allowed(search_naver(fallback_term))

        # 두 결과 합산 → 판매처별 최저가 기준 상위 3개
        top3 = merge_and_rank(valid1, valid2)[:3]

        # Q~Z열 구성 (가격, 판매처, 링크) × 3 + 수집일시
        result = []
        for j in range(3):
            if j < len(top3):
                item = top3[j]
                result.extend([
                    f"{int(item['lprice']):,}",
                    item.get("mallName", "-"),
                    item.get("link", "-"),
                ])
            else:
                result.extend(["결과없음", "-", "-"])
        result.append(now)

        updates.append({
            "range": f"Q{row_num}:Z{row_num}",
            "values": [result],
        })

        if top3:
            print(f"  1위: {result[0]}원 ({result[1]})")
            if len(top3) > 1:
                print(f"  2위: {result[3]}원 ({result[4]})")
            if len(top3) > 2:
                print(f"  3위: {result[6]}원 ({result[7]})")
        else:
            print("  → 허용 채널 결과없음")

    if updates:
        ws.batch_update(updates)
        print(f"\n완료: {len(updates)}개 상품 업데이트 ({now})")
    else:
        print("업데이트할 항목 없음 — P열(검색어) 확인 필요")


if __name__ == "__main__":
    main()
