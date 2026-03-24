import requests
import json
import os
from datetime import datetime
from google import genai

# Gemini 설정
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def send_telegram(text):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def get_naver_lowest(query):
    if not query or len(query) < 3:
        return None
    
    clean_query = query.replace("트레이더스", "").replace("(각)", "").replace("세트", "").strip()[:40]
    
    if "비바로" in clean_query and "큐브" in clean_query:
        clean_query = "비바로 큐브 실내자전거"
    elif "글라스락" in clean_query:
        clean_query = "글라스락 더클린 밀폐용기"

    url = "https://openapi.naver.com/v1/search/shop.json"
    params = {"query": clean_query, "display": 1, "sort": "asc"}
    headers = {
        "X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
        "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"]
    }
    
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        items = res.json().get("items", [])
        if items:
            price = int(items[0]["lprice"])
            print(f"검색어: {clean_query} → 네이버 최저가: {price:,}원")
            return price
    except Exception as e:
        print(f"네이버 검색 실패 ({clean_query}): {e}")
    
    return None

# ================== 메인 실행 ==================
print("🚀 트레이더스 전단 분석을 시작합니다...")

send_telegram("📸 트레이더스 오늘 전단 분석 시작합니다!\n10% 이상 저렴한 작은 상품만 보내드려요.")

flyer_url = "https://eapp.emart.com/tradersclub/flyerImgView.do"
headers = {"User-Agent": "Mozilla/5.0"}

page_response = requests.get(flyer_url, headers=headers)

prompt = """
이 페이지는 이마트 트레이더스 이번 주 전단 페이지입니다.
아래쪽 회색 배경 작은 상품들을 중점으로 분석해서 정확한 JSON으로만 출력해.

[
  {
    "name": "상품의 정확하고 완전한 이름",
    "original_price": 정상가_숫자,
    "discount": 할인액_숫자,
    "sale_price": 실제판매가_숫자
  }
]

실제판매가는 original_price - discount 계산해서 넣어주세요.
"""

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[page_response.text, prompt]
)

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

# ================== 비교 로직 ==================
if not products:
    send_telegram("상품 추출 실패")
else:
    message = f"🔥 <b>트레이더스 {datetime.now().strftime('%m월 %d일')} 작은 상품 승리 목록 (10% 이상 저렴)</b>\n"
    message += "트레이더스 실제 판매가가 네이버보다 10% 이상 저렴한 상품들만 모았습니다!\n\n"
    
    good_count = 0
    seen = set()
    results = []

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

        naver_price = get_naver_lowest(name)

        if naver_price and sale_price < naver_price * 0.90:
            diff = naver_price - sale_price
            percent = round((diff / naver_price) * 100)
            results.append((name, sale_price, naver_price, diff, percent, original, discount))
            good_count += 1

    results.sort(key=lambda x: x[3], reverse=True)

    for name, sale_p, naver_p, diff, percent, orig, disc in results:
        message += f"🏆 <b>{name}</b>\n"
        message += f"트레이더스: <b>{sale_p:,}원</b> (원가 {orig:,}원 - {disc:,}원 할인)\n"
        message += f"네이버: {naver_p:,}원 (▼{diff:,}원, {percent}% 저렴)\n\n"

    if good_count == 0:
        message += "이번 주는 10% 이상 저렴한 작은 상품이 없네요."
    else:
        message += f"🎉 총 {good_count}개 상품에서 트레이더스가 10% 이상 승리했습니다!"

    send_telegram(message)
    print(f"\n✅ 분석 완료! {good_count}개 승리 상품을 보냈습니다.")
