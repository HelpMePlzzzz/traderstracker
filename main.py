import requests
import json
import os
from datetime import datetime
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
import google.generativeai as genai

# 1. 환경 설정 및 API 세팅
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash") # 최신 모델명 확인

# 2. 유틸리티 함수들 (항상 상단에 위치해야 합니다)
def send_telegram(text):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

def get_naver_lowest(query):
    if not query or len(query) < 2:
        return None
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

def get_danawa_link(product_name):
    clean_name = product_name.replace(" ", "+").replace("(", "").replace(")", "")
    return f"https://prod.danawa.com/list/?go=productSearch&searchKeyword={clean_name}"

def get_all_flyer_images():
    """트레이더스 전단지 페이지에서 모든 이미지 URL을 추출하고 PIL 객체로 변환합니다."""
    flyer_url = "https://eapp.emart.com/tradersclub/flyerImgView.do"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    
    try:
        response = requests.get(flyer_url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 실제 전단 이미지가 들어있는 img 태그들을 모두 찾습니다.
        all_imgs = soup.find_all('img')
        image_objects = []
        seen_urls = set()

        print("🔎 전단지 이미지 추출 중...")
        for img in all_imgs:
            src = img.get('src') or img.get('data-src')
            # 'upload' 혹은 'flyer'가 포함된 것이 실제 상품 이미지일 확률이 높음
            if src and ('upload' in src.lower() or 'flyer' in src.lower()):
                if not src.startswith('http'):
                    src = "https://eapp.emart.com" + src
                
                if src not in seen_urls:
                    seen_urls.add(src)
                    try:
                        img_res = requests.get(src, timeout=10)
                        image_objects.append(Image.open(BytesIO(img_res.content)))
                        print(f"✅ 이미지 로드 성공: {src}")
                    except:
                        continue
        return image_objects
    except Exception as e:
        print(f"이미지 추출 중 오류 발생: {e}")
        return []

# ================== 메인 실행부 ==================
def main():
    print("🚀 트레이더스 전단 분석 시작...")
    send_telegram("📸 트레이더스 오늘 전단 분석 시작합니다!\n5면 전체를 분석해서 10% 이상 저렴한 상품을 찾아드려요.")

    # 1. 전단지 이미지 가져오기
    flyer_images = get_all_flyer_images()

    if not flyer_images:
        print("❌ 이미지를 찾을 수 없습니다.")
        send_telegram("⚠️ 전단지 이미지를 불러오지 못했습니다. 사이트 구조가 변경되었을 수 있습니다.")
        return

    print(f"📸 총 {len(flyer_images)}장의 전단지를 분석합니다.")

    # 2. Gemini를 이용한 상품 정보 추출 (이미지 전체 전달)
    prompt = """
    당신은 이마트 트레이더스 전단 전문 분석가입니다.
    첨부된 모든 이미지(전단지 전체 면)를 분석하여 할인 상품들을 추출해주세요.

    각 상품마다 아래 JSON 형식으로만 출력하세요. 다른 설명은 절대 하지 마세요:
    [
      {
        "name": "상품의 정확한 이름",
        "original_price": 정상가_숫자,
        "discount": 할인금액_숫자,
        "sale_price": 실제판매가_숫자
      }
    ]
    """

    try:
        response = model.generate_content([*flyer_images, prompt])
        raw_text = response.text.strip()
        
        # Markdown 코드 블록 제거
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].strip()
            
        products = json.loads(raw_text)
        print(f"✅ 총 {len(products)}개 상품 추출 성공!")
    except Exception as e:
        print(f"Gemini 분석 또는 JSON 파싱 실패: {e}")
        send_telegram("❌ 상품 정보를 분석하는 중 오류가 발생했습니다.")
        return

    # 3. 결과 정리 및 네이버 가격 비교
    message = f"🔥 <b>트레이더스 {datetime.now().strftime('%m월 %d일')} 작은 상품 승리 목록</b>\n\n"
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

        if sale_price <= 1000: continue

        naver_price = get_naver_lowest(name)
        danawa_link = get_danawa_link(name)

        # 네이버 최저가보다 10% 이상 저렴한 경우만 포함
        if naver_price and sale_price < naver_price * 0.90:
            diff = naver_price - sale_price
            percent = round((diff / naver_price) * 100)

            message += f"🏆 <b>{name}</b>\n"
            message += f"트레이더스: <b>{sale_price:,}원</b>\n"
            message += f"네이버 최저: {naver_price:,}원 (▼{percent}% 저렴)\n"
            message += f"📊 <a href='{danawa_link}'>다나와 가격추이</a>\n\n"
            good_count += 1

    if good_count == 0:
        message += "이번 주는 10% 이상 저렴한 상품이 없네요."
    else:
        message += f"🎉 총 {good_count}개 핫딜 발견!"

    send_telegram(message)
    print(f"✅ 분석 완료! {good_count}개 상품 전송.")

if __name__ == "__main__":
    main()
