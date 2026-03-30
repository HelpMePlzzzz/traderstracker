import requests
import json
import os
import re
from datetime import datetime
from PIL import Image
from io import BytesIO
from google import genai  # 최신 라이브러리 방식

# 1. 환경 설정
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def send_telegram(text):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
    except: pass

def get_naver_lowest(query):
    if not query or len(query) < 2: return None
    clean_query = query.replace("트레이더스", "").replace("(각)", "").replace("세트", "").strip()[:60]
    headers = {
        "X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
        "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"]
    }
    try:
        res = requests.get("https://openapi.naver.com/v1/search/shop.json", 
                           params={"query": clean_query, "display": 1, "sort": "asc"}, 
                           headers=headers, timeout=10)
        items = res.json().get("items", [])
        return int(items[0]["lprice"]) if items else None
    except: return None

def get_flyer_images():
    """트레이더스 서버에서 실제 전단 이미지 리스트를 가져오는 핵심 로직"""
    print("🔎 전단지 이미지 추출 중...")
    
    # 1단계: 메인 페이지 접속해서 현재 전단지 ID(flyerId) 혹은 이미지 경로 찾기
    main_url = "https://eapp.emart.com/tradersclub/flyerImgView.do"
    headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"}
    
    try:
        res = requests.get(main_url, headers=headers, timeout=15)
        html = res.text
        
        # 2단계: HTML 소스 내부에 자바스크립트 배열 형태로 숨겨진 이미지 URL들 추출
        # 보통 ['/upload/flyer/123_1.jpg', '/upload/flyer/123_2.jpg' ...] 형태를 찾습니다.
        img_paths = re.findall(r'[\'"](/upload/flyer/[^\'"]+?\.jpg)[\'"]', html)
        
        if not img_paths:
            # 다른 경로 패턴 시도 (trd 접두어 등)
            img_paths = re.findall(r'[\'"](/upload/[^\'"]+?\.jpg)[\'"]', html)

        image_objects = []
        base_url = "https://eapp.emart.com"
        
        # 중복 제거 후 5~6개 페이지만 처리
        final_urls = list(dict.fromkeys([base_url + p for p in img_paths]))
        
        for url in final_urls[:6]:
            try:
                img_res = requests.get(url, timeout=10)
                if img_res.status_code == 200:
                    image_objects.append(Image.open(BytesIO(img_res.content)))
                    print(f"✅ 로드 성공: {url}")
            except: continue
            
        return image_objects
    except Exception as e:
        print(f"❌ 오류: {e}")
        return []

def main():
    print("🚀 트레이더스 전단 분석 시작...")
    send_telegram(f"📸 {datetime.now().strftime('%m/%d')} 트레이더스 5면 분석을 시작합니다.")

    images = get_flyer_images()
    if not images:
        print("❌ 이미지를 찾을 수 없습니다.")
        send_telegram("⚠️ 이미지를 찾지 못했습니다. 사이트 구조를 확인해주세요.")
        return

    print(f"✅ 총 {len(images)}장의 전단지 확보. Gemini 분석 중...")

    # 3단계: Gemini 1.5 Flash 멀티모달 분석
    prompt = """트레이더스 전단지 이미지들입니다. 모든 이미지의 할인 상품 정보를 추출하세요. 
    반드시 [ {"name": "이름", "original_price": 0, "discount": 0, "sale_price": 0} ] 형식의 JSON만 출력하세요."""

    try:
        # 최신 SDK 방식 (이미지와 텍스트 동시 전달)
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[*images, prompt]
        )
        
        raw_text = response.text.strip()
        # JSON 정제 (마크다운 제거)
        json_str = re.sub(r'```json|```', '', raw_text).strip()
        products = json.loads(json_str)
    except Exception as e:
        print(f"분석 에러: {e}")
        return

    # 4단계: 네이버 비교 및 결과 전송
    message = f"🔥 <b>트레이더스 금주 핫딜 (10% 이상 저렴)</b>\n\n"
    count = 0
    for p in products:
        name = p.get("name", "")
        sale_price = p.get("sale_price", 0)
        if not name or sale_price < 1000: continue
        
        naver_price = get_naver_lowest(name)
        if naver_price and sale_price < naver_price * 0.90:
            diff = naver_price - sale_price
            message += f"🏆 <b>{name}</b>\n💰 <b>{sale_price:,}원</b> (네이버 {naver_price:,}원 대비 ▼{diff:,}원)\n\n"
            count += 1
            if count >= 15: break # 텔레그램 길이 제한 방지

    if count == 0: message += "이번 주는 대박 상품이 없네요."
    send_telegram(message)
    print(f"✅ 전송 완료 ({count}개 상품)")

if __name__ == "__main__":
    main()
