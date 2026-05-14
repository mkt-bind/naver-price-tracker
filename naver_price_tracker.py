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

gc = gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"]))
ws = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)


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
        valid = [it for it in items if it.get("lprice") and it["lprice"] != "0"]

        if not valid:
            price_str, mall_str = "결과없음", "-"
        else:
            min_item = min(valid, key=lambda x: int(x["lprice"]))
            price_str = f"{int(min_item['lprice']):,}"
            mall_str = min_item.get("mallName", "-")

        updates.append({
            "range": f"Q{row_num}:S{row_num}",
            "values": [[price_str, mall_str, now]],
        })
        print(f"  → {price_str}원 ({mall_str})")

    if updates:
        ws.batch_update(updates)
        print(f"\n완료: {len(updates)}개 상품 업데이트 ({now})")
    else:
        print("업데이트할 항목 없음 — P열(검색어) 확인 필요")


if __name__ == "__main__":
    main()
