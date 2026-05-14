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
COL_SEARCH = 16  # P열 (1-indexed)

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

        print(f"[{row_num}행] {search_term}")
        items = search_naver(search_term)

        # 유효 가격 + 허용 채널 필터링 후 가격 오름차순 상위 3개
        valid = [
            it for it in items
            if it.get("lprice") and it["lprice"] != "0"
            and is_allowed_mall(it.get("mallName", ""))
        ]
        valid.sort(key=lambda x: int(x["lprice"]))
        top3 = valid[:3]

        # 3순위까지 (가격, 판매처, 링크) 구성 → Q~Z열 (10개)
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
        result.append(now)  # Z열 수집일시

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
