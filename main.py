import requests
import json
import os
from datetime import datetime
import google.generativeai as genai
import re
import time

# API 설정
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash") # 최신 모델 권장

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
                time.sleep(0.6)

def send_telegram_photo(photo_url, caption=""):
    """이미지를 텔레그램으로 전송하는 함수"""
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        requests.post(url, data={"chat_id": chat_id, "photo": photo_url, "caption": caption})
    except Exception as e:
        print(f"❌ 이미지 전송 실패: {e}")

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

flyer_url = "https://eapp.emart.com/tradersclub/flyerImgView.do"
try:
    page_response = requests.get(flyer_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    html_text = page_response.text

    # 1. 이미지 URL 추출 (트레이더스 전단 이미지 패턴 추출)
    # 보통 전단지 이미지는 src=".../flyer/..." 형태이거나 특정 경로에 몰려있습니다.
    image_candidates = re.findall(r'https?://[^\s<>"]+?\.(?:jpg|jpeg|png)', html_text)
    
    # 트레이더스 서버의 이미지 경로 필터링 (불필요한 아이콘 제외)
    flyer_images = [img for img in image_candidates if 'flyer' in img.lower() or 'upload' in img.lower()]
    
    if flyer_images:
        print(f"🖼 {len(flyer_images)}개의 이미지를 발견했습니다. 첫 장을 전송합니다.")
        send_telegram_photo(flyer_images[0], f"📸 {datetime.now().strftime('%m/%d')} 트레이더스 전단입니다.")
    else:
        send_telegram("📸 전단 이미지를 자동으로 찾지 못했습니다. 분석만 진행합니다.")

except Exception as e:
    print(f"페이지 로드 실패: {e}")
    send_telegram("❌ 전단 페이지에 접속할 수 없습니다.")
    exit()

# 2. Gemini 분석 요청
prompt = """
너는 JSON만 출력하는 기계이다. 절대 설명, 코드, 주석, 마크다운을 넣지 말고 오직 JSON 배열만 출력해라.
이 페이지에서 실제 상품 정보(이름, 가격, 할인)만 분석해서 추출해라.

아래 형식으로만 정확히 출력:
[
  {
    "name": "상품의 정확하고 자연스러운 전체 이름",
    "original_price": 정상가_숫자,
    "discount": 할인금액_숫자,
    "sale_price": 실제판매가_숫자
  }
]
실제 판매가는 original_price - discount로 계산해서 넣어라.
"""

response = model.generate_content([html_text, prompt])
raw_text = response.text.strip()

# JSON 파싱 안전 처리
try:
    raw_text = re.sub(r'```json|```', '', raw_text).strip()
    start = raw_text.find("[")
    end = raw_text.rfind("]")
    if start != -1 and end != -1:
        raw_text = raw_text[start:end+1]
    
    products = json.loads(raw_text)
    print(f"✅ 총 {len(products)}개 상품 추출 성공!")
except Exception as e:
    print("JSON 파싱 실패:", e)
    send_telegram("❌ 상품 데이터를 해석하는 데 실패했습니다.")
    products = []

# 3. 네이버 비교 및 결과 정리
if products:
    message_header = f"🔥 <b>트레이더스 {datetime.now().strftime('%m월 %d일')} 최강 가성비 목록</b>\n\n"
    good_count = 0
    seen = set()
    temp_message = ""

    for p in products:
        name = str(p.get("name", "")).strip()
        if not name or name in seen or len(name) < 2:
            continue
        seen.add(name)

        try:
            original = int(p.get("original_price") or 0)
            discount = int(p.get("discount") or 0)
            sale_price = int(p.get("sale_price") or (original - discount))
        except:
            continue

        if sale_price <= 2000: # 너무 싼 소모품 제외
            continue

        naver_price = get_naver_lowest(name, original)

        # 네이버보다 10% 이상 저렴한 경우만 선정
        if naver_price and sale_price < naver_price * 0.90:
            diff = naver_price - sale_price
            percent = round((diff / naver_price) * 100)

            item_text = f"🏆 <b>{name}</b>\n"
            item_text += f"🛒 트레이더스: <b>{sale_price:,}원</b> (-{discount:,}원)\n"
            item_text += f"🔍 네이버 최저: {naver_price:,}원 (▼{percent}% 저렴)\n\n"

            if len(temp_message) + len(item_text) > 3500:
                send_telegram(message_header + temp_message)
                temp_message = item_text
            else:
                temp_message += item_text
            good_count += 1

    if temp_message:
        send_telegram(message_header + temp_message)

    if good_count == 0:
        send_telegram("이번 주는 온라인보다 압도적으로 저렴한 상품이 보이지 않네요. 🧐")
    else:
        print(f"✅ 분석 완료! {good_count}개 상품 추천 완료.")
