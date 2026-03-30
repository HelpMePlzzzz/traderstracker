import requests
import json
import os
from datetime import datetime
import google.generativeai as genai
import re
import statistics   # 평균 계산용

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.5-flash")

def send_telegram(text):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def get_naver_lowest(query, original_price=0):
    if not query or len(query) < 3:
        return None

    # 모델명 제거 + 정리
    clean_query = re.sub(r'[A-Za-z0-9]{6,}', '', query)
    clean_query = clean_query.replace("트레이더스", "").replace("(각)", "").replace("세트", "").strip()
    clean_query = re.sub(r'\s+', ' ', clean_query).strip()[:55]

    search_query = clean_query + " 최저가"

    url = "https://openapi.naver.com/v1/search/shop.json"
    params = {"query": search_query, "display": 3, "sort": "sim"}   # sim = 랭킹순 (관련도 순)
    headers = {
        "X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
        "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"]
    }

    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        items = res.json().get("items", [])

        if not items:
            return None

        prices = []
        for item in items[:3]:   # 상위 3개만 사용
            try:
                price = int(item["lprice"])
                if price > 1000:   # 너무 낮은 가격은 제외
                    prices.append(price)
            except:
                continue

        if not prices:
            return None

        # 상위 3개 가격의 평균 계산
        avg_price = int(statistics.mean(prices))
        
        print(f"검색어: {search_query} → 상위 3개 평균: {avg_price:,}원 (개별: {[f'{p:,}' for p in prices]})")

        # 원가 대비 이상치 체크
        if original_price > 0 and avg_price < original_price * 0.25:
            print(f"⚠️ 원가 대비 가격 이상치 감지 → 재검색 시도")
            # 재검색 (더 짧은 검색어)
            short_query = " ".join(clean_query.split()[:4]) + " 최저가"
            res2 = requests.get(url, params={"query": short_query, "display": 3, "sort": "sim"}, headers=headers, timeout=10)
            items2 = res2.json().get("items", [])
            if items2:
                prices2 = [int(item["lprice"]) for item in items2[:3] if int(item["lprice"]) > 1000]
                if prices2:
                    avg_price = int(statistics.mean(prices2))
                    print(f"재검색 평균: {avg_price:,}원")

        return avg_price

    except Exception as e:
        print(f"네이버 검색 실패 ({search_query}): {e}")
        return None

# ================== 메인 실행 ==================
print("🚀 트레이더스 전단 분석 시작...")

send_telegram("📸 트레이더스 오늘 전단 분석 시작합니다!\n네이버 상위 3개 평균 가격으로 계산합니다.")

flyer_url = "https://eapp.emart.com/tradersclub/flyerImgView.do"
page_response = requests.get(flyer_url, headers={"User-Agent": "Mozilla/5.0"})

prompt = """
이 페이지는 이마트 트레이더스 이번 주 전단 페이지입니다.
전체 내용을 분석해서 할인 상품들을 추출해주세요.

각 상품마다 아래 JSON 형식으로만 출력해. 다른 설명은 절대 넣지 마세요:

[
  {
    "name": "상품의 정확하고 자연스러운 전체 이름",
    "original_price": 정상가_숫자,
    "discount": 할인금액_숫자,
    "sale_price": 실제판매가_숫자
  }
]

실제 판매가는 original_price - discount로 계산해서 넣어주세요.
"""

response = model.generate_content([page_response.text, prompt])

raw_text = response.text.strip()

try:
    if "```json" in raw_text:
        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        raw_text = raw_text.split("```")[1].strip()
    
    products = json.loads(raw_text)
    print(f"✅ 총 {len(products)}개 상품 추출 성공!")
except Exception as e:
    print("JSON 파싱 실패:", e)
    products = []

# ================== 결과 정리 ==================
if not products:
    send_telegram("상품 추출 실패")
else:
    message = f"🔥 <b>트레이더스 {datetime.now().strftime('%m월 %d일')} 작은 상품 승리 목록 (10% 이상 저렴)</b>\n\n"
    
    good_count = 0
    seen = set()

    for p in products:
        name = str(p.get("name", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)

        original = int(p.get("original_price") or 0)
        discount = int(p.get("discount") or 0)
        sale_price = int(p.get("sale_price") or (original - discount))

        if sale_price <= 1000:
            continue

        naver_price = get_naver_lowest(name, original)

        if naver_price and sale_price < naver_price * 0.90:
            diff = naver_price - sale_price
            percent = round((diff / naver_price) * 100)

            message += f"🏆 <b>{name}</b>\n"
            message += f"트레이더스: <b>{sale_price:,}원</b> (원가 {original:,}원 - {discount:,}원 할인)\n"
            message += f"네이버 상위 3개 평균 최저: {naver_price:,}원 (▼{diff:,}원, {percent}% 저렴)\n\n"
            good_count += 1

    if good_count == 0:
        message += "이번 주는 10% 이상 저렴한 작은 상품이 없네요.\n전단 직접 확인 추천드려요!"
    else:
        message += f"🎉 총 {good_count}개 상품에서 트레이더스가 10% 이상 승리했습니다!"

    send_telegram(message)
    print(f"✅ 분석 완료! {good_count}개 승리 상품을 보냈습니다.")
