import requests
import json
import os
import time
from datetime import datetime
from bs4 import BeautifulSoup
from io import BytesIO
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import google.generativeai as genai

# ... [기존 텔레그램/네이버 함수 동일] ...

print("🚀 트레이더스 5면 전단 분석 시작...")
send_telegram("📸 트레이더스 오늘 전단 분석 시작합니다!\n5면 전체를 분석해서 10% 이상 저렴한 작은 상품을 찾아드려요.")

# 1. Selenium으로 동적 페이지 로드
options = Options()
options.add_argument("--headless") # 브라우저 창 띄우지 않음
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")

driver = webdriver.Chrome(options=options)
flyer_url = "https://eapp.emart.com/tradersclub/flyerImgView.do"
driver.get(flyer_url)

# 자바스크립트 및 이미지가 로딩될 시간을 충분히 줍니다.
time.sleep(3) 

# 2. 렌더링된 HTML에서 전체 전단지 이미지 URL 추출
soup = BeautifulSoup(driver.page_source, 'html.parser')
driver.quit()

# 웹페이지 구조에 따라 img 태그를 찾는 로직이 필요합니다.
# 보통 슬라이더 안의 이미지를 찾습니다. (예: 클래스명이나 속성으로 필터링)
img_tags = soup.find_all('img')
image_urls = []

for img in img_tags:
    # 지연 로딩(lazy loading)을 고려해 data-src가 있는지 먼저 확인
    src = img.get('data-src') or img.get('src') 
    
    # 전단지 이미지의 특징(예: url에 flyer, trd 등이 포함됨)을 찾아 필터링 
    # (실제 사이트의 이미지 url 구조를 확인 후 수정하세요)
    if src and ('flyer' in src.lower() or 'upload' in src.lower()):
        if not src.startswith('http'):
            src = "https://eapp.emart.com" + src
        if src not in image_urls:
            image_urls.append(src)

print(f"총 {len(image_urls)}개의 전단지 이미지 URL을 찾았습니다.")

# 3. 이미지 다운로드 및 PIL Image 객체로 변환
gemini_inputs = []
for url in image_urls[:5]: # 최대 5면까지만 (혹시 모를 에러 방지)
    try:
        res = requests.get(url)
        img_obj = Image.open(BytesIO(res.content))
        gemini_inputs.append(img_obj)
    except Exception as e:
        print(f"이미지 로드 실패: {url} - {e}")

# 4. 제미나이에게 '이미지 리스트 + 프롬프트'를 한 번에 전달
prompt = """
당신은 이마트 트레이더스 전단 전문 분석가입니다.
첨부된 이미지들은 이번 주 트레이더스 전단지 전체 면입니다.

전체 내용을 모두 분석해서 할인 상품들, 특히 작은 상품(생활용품, 세제, 가전, 의류, 침구, 식품 등)을 최대한 많이 정확하게 추출해주세요.

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

# 이미지 배열과 프롬프트를 리스트로 묶어서 전달
gemini_inputs.append(prompt)
response = model.generate_content(gemini_inputs)

# ... [이하 기존 JSON 파싱 및 결과 정리 코드 동일] ...
