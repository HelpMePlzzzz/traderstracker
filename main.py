import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

# ... [기존 설정 및 네이버 함수 동일] ...

def get_all_flyer_images():
    flyer_url = "https://eapp.emart.com/tradersclub/flyerImgView.do"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    
    response = requests.get(flyer_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 1. 전단지 이미지 URL 모두 찾기 
    # 보통 class="swiper-slide" 내부의 img 태그들이나 특정 패턴의 src를 찾습니다.
    all_imgs = soup.find_all('img')
    image_objects = []
    seen_urls = set()

    print("🔎 전단지 이미지 추출 중...")
    for img in all_imgs:
        src = img.get('src') or img.get('data-src')
        # 전단 이미지임을 식별하는 키워드 (사이트 구조에 따라 'flyer' 등으로 필터링)
        if src and ('flyer' in src.lower() or 'upload' in src.lower()):
            if not src.startswith('http'):
                src = "https://eapp.emart.com" + src
            
            if src not in seen_urls:
                seen_urls.add(src)
                try:
                    # 이미지를 메모리로 바로 다운로드해서 PIL 객체로 변환
                    img_res = requests.get(src, timeout=10)
                    image_objects.append(Image.open(BytesIO(img_res.content)))
                    print(f"✅ 이미지 로드 완료: {src}")
                except:
                    continue

    return image_objects

# ================== 메인 실행부 수정 ==================

# 1. 5면 전체 이미지 가져오기
flyer_images = get_all_flyer_images()

if not flyer_images:
    print("❌ 이미지를 찾을 수 없습니다.")
    send_telegram("전단지 이미지를 불러오지 못했습니다.")
else:
    print(f"📸 총 {len(flyer_images)}장의 전단지를 분석합니다.")
    
    # 2. 제미나이에게 이미지 리스트 전달 (멀티모달 분석)
    # 이미지 객체 리스트 뒤에 마지막으로 프롬프트를 붙여줍니다.
    prompt = """
    당신은 이마트 트레이더스 전단 전문 분석가입니다.
    첨부된 **모든 이미지(총 5면)**를 꼼꼼히 확인하고 분석해주세요.
    
    각 면에 있는 할인 상품(생활용품, 식품, 가전 등)을 최대한 많이 추출하세요.
    중복된 상품은 하나만 기록하세요.

    출력 형식은 반드시 아래 JSON 배열 포맷으로만 작성하세요:
    [
      {
        "name": "상품명",
        "original_price": 숫자,
        "discount": 숫자,
        "sale_price": 숫자
      }
    ]
    """
    
    # 이미지 리스트와 프롬프트를 합쳐서 전송
    response = model.generate_content([*flyer_images, prompt])
    
    # ... [이후 JSON 파싱 및 텔레그램 발송 로직 동일] ...
