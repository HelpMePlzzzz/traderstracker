import requests
import json
import os
from datetime import datetime
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.5-flash")

def send_telegram(text):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def get_naver_lowest(query):
    if not query or len(query) < 3:
        return None
    
    # 상품명 정리 (일반적으로)
    clean_query = query.replace("트레이더스", "").replace("(각)", "").replace("세트", "").strip()
    clean_query = clean_query[:60]
    
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
print("🚀 트레이더스 전단 분석 시작...")

send_telegram("📸 트레이더스 오늘 전단 분석 시작합니다!\n전체 페이지를 분석해서 10% 이상 저렴한 작은 상품을 찾아드려요.")

# 전단 페이지 가져오기
flyer_url = "https://eapp.emart.com/tradersclub/flyerImgView.do"
page_response = requests.get(flyer_url, headers={"User-Agent": "Mozilla/5.0"})

# 전체 페이지 분석을 강조한 프롬프트
prompt = """
이 페이지는 이마트 트레이더스 이번 주 전단 페이지입니다.
사용자가 오른쪽/왼쪽으로 넘겨가며 보는 여러 페이지로 구성된 전단입니다.

전체 페이지 내용을 모두 분석해서 할인 상품들, 특히 작은 상품(생활용품, 세제, 가전, 의류, 침구, 식품 등)을 최대한 많이 정확하게 추출해주세요.

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
가능한 한 많은 상품을 전체 페이지에서 추출해주세요.
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

        naver_price = get_naver_lowest(name)

        if naver_price and sale_price < naver_price * 0.90:
            diff = naver_price - sale_price
            percent = round((diff / naver_price) * 100)

            message += f"🏆 <b>{name}</b>\n"
            message += f"트레이더스: <b>{sale_price:,}원</b> (원가 {original:,}원 - {discount:,}원 할인)\n"
            message += f"네이버 현재 최저: {naver_price:,}원 (▼{diff:,}원, {percent}% 저렴)\n\n"
            good_count += 1

    if good_count == 0:
        message += "이번 주는 10% 이상 저렴한 작은 상품이 없네요.\n전단 직접 확인 추천드려요!"
    else:
        message += f"🎉 총 {good_count}개 상품에서 트레이더스가 10% 이상 승리했습니다!"

    send_telegram(message)
    print(f"✅ 분석 완료! {good_count}개 승리 상품을 보냈습니다.")
