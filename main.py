import requests
import json
import os
from datetime import datetime
import google.generativeai as genai
import re

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.5-flash")

def send_telegram(text):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    MAX_LENGTH = 3800
    if len(text) <= MAX_LENGTH:
        requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    else:
        parts = []
        current = ""
        lines = text.split('\n')
        for line in lines:
            if len(current) + len(line) + 1 > MAX_LENGTH and current:
                parts.append(current.strip())
                current = line + '\n'
            else:
                current += line + '\n'
        if current.strip():
            parts.append(current.strip())
        
        for i, part in enumerate(parts, 1):
            prefix = f"📋 {i}/{len(parts)}\n\n" if len(parts) > 1 else ""
            requests.post(url, data={"chat_id": chat_id, "text": prefix + part, "parse_mode": "HTML"})
            if i < len(parts):
                import time
                time.sleep(0.6)

def get_naver_lowest(query, original_price=0):
    if not query or len(query) < 3:
        return None

    clean_query = re.sub(r'[A-Za-z0-9]{6,}', '', query)
    clean_query = clean_query.replace("트레이더스", "").replace("(각)", "").replace("세트", "").strip()
    clean_query = re.sub(r'\s+', ' ', clean_query).strip()[:55]

    search_query = clean_query + " 최저가"

    url = "https://openapi.naver.com/v1/search/shop.json"
    params = {"query": search_query, "display": 3, "sort": "sim"}
    headers = {
        "X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
        "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"]
    }

    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        items = res.json().get("items", [])
        if not items:
            return None

        prices = [int(item["lprice"]) for item in items[:3] if int(item["lprice"]) > 1000]

        if not prices:
            return None

        avg_price = int(sum(prices) / len(prices))

        if avg_price < 8000 or (original_price > 0 and avg_price < original_price * 0.25):
            short_query = " ".join(clean_query.split()[:4]) + " 최저가"
            res2 = requests.get(url, params={"query": short_query, "display": 3, "sort": "sim"}, headers=headers, timeout=10)
            items2 = res2.json().get("items", [])
            if items2:
                prices2 = [int(item["lprice"]) for item in items2[:3] if int(item["lprice"]) > 1000]
                if prices2:
                    avg_price = int(sum(prices2) / len(prices2))

        print(f"검색어: {search_query} → 평균 최저가: {avg_price:,}원")
        return avg_price

    except Exception as e:
        print(f"네이버 검색 실패 ({search_query}): {e}")
        return None

# ================== 메인 실행 ==================
print("🚀 트레이더스 전단 분석 시작...")

send_telegram("📸 트레이더스 오늘 전단 분석 시작합니다!")

flyer_url = "https://eapp.emart.com/tradersclub/flyerImgView.do"
page_response = requests.get(flyer_url, headers={"User-Agent": "Mozilla/5.0"})

prompt = """
이 페이지는 이마트 트레이더스 이번 주 전단 페이지입니다.
전체 내용을 분석해서 할인 상품들을 추출해주세요.

각 상품마다 아래 JSON 형식으로만 출력해. 다른 설명은 절대 넣지 마세요.
할인율(%)이 아닌 숫자 할인 금액을 discount에 넣어주세요.

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

# JSON 파싱 안전 처리
try:
    if "```json" in raw_text:
        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        raw_text = raw_text.split("```")[1].strip()
    
    raw_text = raw_text.strip()

    if not raw_text.startswith("["):
        start = raw_text.find("[")
        if start != -1:
            raw_text = raw_text[start:]
    if not raw_text.endswith("]"):
        end = raw_text.rfind("]")
        if end != -1:
            raw_text = raw_text[:end+1]

    products = json.loads(raw_text)
    print(f"✅ 총 {len(products)}개 상품 추출 성공!")
except Exception as e:
    print("JSON 파싱 실패:", e)
    print("Gemini 원본 응답 미리보기:", raw_text[:500])
    send_telegram("❌ 상품을 제대로 읽지 못했습니다.\n다음에 다시 시도할게요.")
    products = []

# ================== 결과 정리 ==================
if not products:
    send_telegram("상품 추출 실패")
else:
    message = f"🔥 <b>트레이더스 {datetime.now().strftime('%m월 %d일')} 작은 상품 승리 목록 (10% 이상 저렴)</b>\n\n"
    
    good_count = 0
    seen = set()
    temp_message = ""

    for p in products:
        name = str(p.get("name", "")).strip()
        if not name or name in seen:
            continue
        seen.add(name)

        # 안전한 숫자 변환
        original = 0
        discount = 0
        sale_price = 0

        try:
            original = int(p.get("original_price") or 0)
            discount = int(p.get("discount") or 0)
            sale_price = int(p.get("sale_price") or (original - discount))
        except:
            continue

        if sale_price <= 1000:
            continue

        naver_price = get_naver_lowest(name, original)

        if naver_price and sale_price < naver_price * 0.90:
            diff = naver_price - sale_price
            percent = round((diff / naver_price) * 100)

            item_text = f"🏆 <b>{name}</b>\n"
            item_text += f"트레이더스: <b>{sale_price:,}원</b> (원가 {original:,}원 - {discount:,}원 할인)\n"
            item_text += f"네이버 현재 최저: {naver_price:,}원 (▼{diff:,}원, {percent}% 저렴)\n\n"

            if len(temp_message) + len(item_text) > 3800 and temp_message:
                send_telegram(message + temp_message)
                temp_message = item_text
            else:
                temp_message += item_text
            good_count += 1

    if temp_message:
        send_telegram(message + temp_message)

    if good_count == 0:
        send_telegram("이번 주는 10% 이상 저렴한 작은 상품이 없네요.\n전단 직접 확인 추천드려요!")
    else:
        print(f"✅ 분석 완료! {good_count}개 승리 상품을 보냈습니다.")
