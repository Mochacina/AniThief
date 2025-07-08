import requests
from bs4 import BeautifulSoup
import json
import re
import base64
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class AniLifeScraper:
    BASE_URL = "https://anilife.live"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        })

    def _make_request(self, url, params=None, headers=None):
        request_headers = self.session.headers.copy()
        if headers:
            request_headers.update(headers)
        try:
            response = self.session.get(url, params=params, headers=request_headers, timeout=10)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            print(f"Error during request to {url}: {e}")
            return None

    def search(self, keyword):
        search_url = f"{self.BASE_URL}/search"
        response = self._make_request(search_url, params={'keyword': keyword})
        if not response: return []
        soup = BeautifulSoup(response.text, 'html.parser')
        search_items = soup.select('.listupd .bs')
        results = []
        for item in search_items:
            a_tag = item.select_one('.bsx > a')
            img_tag = item.select_one('.bsx > a img')
            title_tag = item.select_one('.bsx > a .tt')
            if a_tag and img_tag and title_tag:
                href = a_tag.get('href', '')
                if '/detail/id/' in href:
                    anime_id = href.split('/detail/id/')[-1]
                    title = title_tag.find('h2').get_text(strip=True) if title_tag.find('h2') else title_tag.get_text(strip=True)
                    thumbnail_url = img_tag.get('src', '')
                    results.append({'id': anime_id, 'title': title, 'thumbnail_url': thumbnail_url})
        return results

    def get_anime_details(self, anime_id):
        details_url = f"{self.BASE_URL}/detail/id/{anime_id}"
        response = self._make_request(details_url)
        if not response: return {}
        soup = BeautifulSoup(response.text, 'html.parser')
        title_tag = soup.select_one('.infox .entry-title')
        title = title_tag.get_text(strip=True) if title_tag else 'N/A'
        summary_tag = soup.select_one('.synp .entry-content p')
        summary = summary_tag.get_text(strip=True) if summary_tag else '줄거리 정보 없음'
        poster_tag = soup.select_one('.thumbook .thumb img')
        poster_url = poster_tag['src'] if poster_tag else ''
        episodes = []
        episode_items = soup.select('.eplister ul li')
        for item in episode_items:
            a_tag = item.select_one('a')
            if a_tag:
                href = a_tag.get('href', '')
                if '/ani/provider/' in href:
                    provider_id = href.split('/ani/provider/')[-1]
                    ep_num_tag = a_tag.select_one('.epl-num')
                    ep_num = ep_num_tag.get_text(strip=True) if ep_num_tag else ''
                    ep_title_tag = a_tag.select_one('.epl-title')
                    ep_title = ep_title_tag.get_text(strip=True) if ep_title_tag else '제목 없음'
                    episodes.append({'num': ep_num, 'title': ep_title, 'provider_id': provider_id})
        extra_info = {}
        info_spans = soup.select('.infox .info-content .spe span')
        for span in info_spans:
            key_tag = span.find('b')
            if key_tag:
                key = key_tag.get_text(strip=True).replace(':', '')
                value = ' '.join(t.strip() for t in span.find_all(string=True, recursive=False) if t.strip())
                if not value:
                    value_tags = span.find_all('a')
                    value = ', '.join(a.get_text(strip=True) for a in value_tags if a.get_text(strip=True))
                extra_info[key] = value if value else "정보 없음"
        genres = [a.get_text(strip=True) for a in soup.select('.genxed a')]
        extra_info['장르'] = ', '.join(genres) if genres else "정보 없음"
        return {'title': title, 'summary': summary, 'poster_url': poster_url, 'episodes': episodes, 'extra_info': extra_info}

    def get_video_info(self, provider_id, anime_id):
        """[ULTIMATE FINAL Mk.II] Selenium으로 상세페이지부터 방문하여 쿠키를 획득하고 비디오 URL을 가져옵니다."""
        print(f"--- [DEBUG] get_video_info 시작 (Provider ID: {provider_id}, Anime ID: {anime_id}) ---")
        live_page_url = None
        driver = None
        try:
            # 1단계: Selenium으로 상세 페이지에 먼저 방문하여 쿠키 획득
            print("[DEBUG] 1단계: Selenium WebDriver 초기화...")
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--log-level=3")
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            
            details_url = f"{self.BASE_URL}/detail/id/{anime_id}"
            print(f"[DEBUG] 1단계: 상세 페이지 방문 시도 -> {details_url}")
            driver.get(details_url)
            print("[DEBUG] 1단계: 상세 페이지 방문 성공 (쿠키 획득 추정)")

            # 2단계: 리다이렉트된 페이지에서 실제 에피소드 링크 클릭
            print(f"[DEBUG] 2단계: Provider ID '{provider_id}'를 포함하는 링크 탐색 및 클릭 시도...")
            try:
                wait = WebDriverWait(driver, 10)
                # provider_id를 포함하는 <a> 태그를 찾아서 클릭
                episode_link_xpath = f"//a[contains(@href, '{provider_id}')]"
                episode_link = wait.until(EC.element_to_be_clickable((By.XPATH, episode_link_xpath)))
                
                print(f"[DEBUG] 2단계: 링크 발견 및 클릭 -> {episode_link.get_attribute('href')}")
                episode_link.click()

                # 페이지가 provider 페이지로 완전히 넘어갈 때까지 대기
                wait.until(EC.url_contains(f"/ani/provider/{provider_id}"))
                print("[DEBUG] 2단계: Provider 페이지로 성공적으로 이동함")
                
                page_source = driver.page_source
            except Exception as e:
                print(f"[DEBUG] 2단계 실패: 에피소드 링크를 찾거나 클릭하는 중 오류 발생: {e}")
                print("--- 현재 페이지 소스 ---")
                print(driver.page_source)
                print("--- HTML 끝 ---")
                return {}

            if "영상 제공 회사" not in page_source:
                print("[DEBUG] 2단계 실패: 서버가 진짜 Provider 페이지를 주지 않았음 (클릭 후)")
                print("--- 받은 HTML ---")
                print(page_source)
                print("--- HTML 끝 ---")
                return {}
            print("[DEBUG] 2단계 성공: 진짜 Provider 페이지 확인")

            # 3단계: Provider 페이지에서 최종 재생 페이지 URL 추출
            match = re.search(r"location\.href = \"(.*?/h/live\?p=.*?)\"", page_source)
            if not match:
                print("[DEBUG] 3단계 실패: location.href 패턴을 찾을 수 없음")
                return {}
            live_page_url = match.group(1)
            print(f"[DEBUG] 3단계 성공: 최종 재생 페이지 URL 추출 -> {live_page_url}")

        except Exception as e:
            print(f"[DEBUG] Selenium 실행 중 오류 발생: {e}")
            return {}
        finally:
            if driver:
                print("[DEBUG] WebDriver 종료")
                driver.quit()

        if not live_page_url:
            return {}

        # 4단계: 최종 페이지에서 암호화된 데이터 추출 및 해독
        print(f"[DEBUG] 4단계: 최종 재생 페이지 요청 -> {live_page_url}")
        live_page_response = self._make_request(live_page_url)
        if not live_page_response: return {}
        aldata_match = re.search(r"var _aldata = '(.*?)'", live_page_response.text)
        if not aldata_match: return {}
        encoded_aldata = aldata_match.group(1)
        print("[DEBUG] 4단계: _aldata 추출 성공")

        try:
            decoded_json_str = base64.b64decode(encoded_aldata).decode('utf-8')
            video_data = json.loads(decoded_json_str)
            encoded_video_path = video_data.get('vid_url_1080') or video_data.get('vid_url_720')
            if not encoded_video_path or encoded_video_path == "none": return {}
            decoded_video_path = base64.b64decode(encoded_video_path).decode('utf-8')
            final_video_url = "https://" + decoded_video_path
            print(f"[DEBUG] 최종 성공: 비디오 URL 생성 -> {final_video_url}")
            return {'video_url': final_video_url}
        except Exception as e:
            print(f"최종 URL 디코딩/파싱 중 오류 발생: {e}")
            return {}

# For testing purposes
if __name__ == '__main__':
    scraper = AniLifeScraper()
    test_provider_id = "30df7673-b666-4b2a-b1db-de749788202d" 
    test_anime_id = "6739"
    print(f"--- 비디오 정보 테스트 (Provider ID: {test_provider_id}, Anime ID: {test_anime_id}) ---")
    video_info = scraper.get_video_info(test_provider_id, test_anime_id)
    if video_info and video_info.get('video_url'):
        print(f"최종 비디오 URL: {video_info['video_url']}")
    else:
        print("최종 비디오 URL을 찾지 못했습니다.")