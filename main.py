import requests
import json
import os
from datetime import datetime
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def send_telegram(text):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def get_naver_lowest(query):
    if not query or len(query) < 3:
        return None
    
    # 상품명 정리 - 최대한 일반적으로 (특정 상품 하드코딩 완전 제거)
    clean_query = query.replace("트레이더스", "").replace("(각)", "").replace("세트", "").strip()
    clean_query = clean_query[:60]   # 검색어 길이 제한
    
    # 과도한 보정 없이 그대로 검색 (다음 주 전단에 맞게 유연하게)
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

def get_danawa_link(product_name):
    """다나와 가격 추이 링크 생성"""
    clean_name = product_name.replace(" ", "+").replace("(", "").replace(")", "")
    return f"https://prod.danawa.com/list/?go=productSearch&searchKeyword={clean_name}"

# ================== 메인 실행 ==================
print("🚀 트레이더스 전단 분석 시작...")

send_telegram("📸 트레이더스 오늘 전단 분석 시작합니다!\n10% 이상 저렴한 작은 상품 + 다나와 링크 함께 보내드려요.")

# 전단 페이지 가져오기
flyer_url = "https://eapp.emart.com/tradersclub/flyerImgView.do"
page_response = requests.get(flyer_url, headers={"User-Agent": "Mozilla/5.0"})

# 매주 바뀌는 전단에 강건한 프롬프트
prompt = """
이 페이지는 이마트 트레이더스 이번 주 전단 페이지입니다.
페이지 전체를 분석해서 할인 상품들, 특히 아래쪽 작은 상품(생활용품, 세제, 가전, 의류, 침구 등)을 중점으로 추출해주세요.
상품 이미지에서 상품 상단에 적힌 검정숫자가 원래가격이고 빨간 숫자가 할인해주는 금액입니다.

각 상품마다 아래 JSON 형식으로만 정확히 출력해. 다른 설명은 절대 넣지 마세요:

[
  {
    "name": "상품의 정확하고 자연스러운 전체 이름",
    "original_price": 정상가_숫자,
    "discount": 할인금액_숫자,
    "sale_price": 실제판매가_숫자
  }
]

실제 판매가는 original_price - discount로 계산해서 넣어주세요.
가능한 한 많은 상품을 추출해주세요.
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
        danawa_link = get_danawa_link(name)

        if naver_price and sale_price < naver_price * 0.90:
            diff = naver_price - sale_price
            percent = round((diff / naver_price) * 100)

            message += f"🏆 <b>{name}</b>\n"
            message += f"트레이더스: <b>{sale_price:,}원</b> (원가 {original:,}원 - {discount:,}원 할인)\n"
            message += f"네이버 현재 최저: {naver_price:,}원 (▼{diff:,}원, {percent}% 저렴)\n"
            message += f"📊 다나와 가격 추이 보기 → {danawa_link}\n\n"
            good_count += 1

    if good_count == 0:
        message += "이번 주는 10% 이상 저렴한 작은 상품이 없네요.\n전단 직접 확인 추천드려요!"
    else:
        message += f"🎉 총 {good_count}개 상품에서 트레이더스가 10% 이상 승리했습니다!"

    send_telegram(message)
    print(f"✅ 분석 완료! {good_count}개 승리 상품을 보냈습니다.")
