import requests
from bs4 import BeautifulSoup
import json
import re
import base64
from tqdm import tqdm
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import webbrowser

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
        """[ULTIMATE FINAL Mk.XIX] 순수 Python & Selenium을 이용한 최종 다운로드 작전"""
        print(f"--- [DEBUG] get_video_info 시작 (Provider ID: {provider_id}, Anime ID: {anime_id}) ---")
        driver = None
        try:
            # 1단계: Selenium WebDriver 초기화
            print("[DEBUG] 1단계: Selenium WebDriver 초기화...")
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--log-level=3")
            options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36')
            
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)

            # --- 봇 탐지 우회 (CDP) ---
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
            
            # 1-1단계: 상세 페이지 방문
            details_url = f"{self.BASE_URL}/detail/id/{anime_id}"
            print(f"[DEBUG] 1단계: 상세 페이지 방문 시도 -> {details_url}")
            driver.get(details_url)
            print("[DEBUG] 1단계: 상세 페이지 방문 성공 (쿠키 획득 추정)")

            # 2단계: 리다이렉트된 페이지에서 실제 에피소드 링크 클릭
            print(f"[DEBUG] 2단계: Provider ID '{provider_id}'를 포함하는 링크 탐색 및 클릭 시도...")
            wait = WebDriverWait(driver, 10)
            episode_link_xpath = f"//a[contains(@href, '{provider_id}')]"
            episode_link = wait.until(EC.element_to_be_clickable((By.XPATH, episode_link_xpath)))
            print(f"[DEBUG] 2단계: 링크 발견 및 클릭 -> {episode_link.get_attribute('href')}")
            episode_link.click()

            # 2-1단계: Provider 페이지로 이동했는지 확인
            wait.until(EC.url_contains(f"/ani/provider/{provider_id}"))
            print("[DEBUG] 2-1단계: Provider 페이지로 성공적으로 이동함")

            # 3단계: Provider 페이지에서 JS를 실행하는 대신, URL을 추출
            print("[DEBUG] 3단계: Provider 페이지 소스에서 최종 URL 추출 시도...")
            provider_page_source = driver.page_source
            match = re.search(r"location\.href = \"(.*?/h/live\?p=.*?)\"", provider_page_source)
            if not match:
                raise Exception("Provider 페이지에서 location.href 패턴을 찾을 수 없음")
            live_page_url = match.group(1)
            print(f"[DEBUG] 3단계: 최종 재생 페이지 URL 추출 성공 -> {live_page_url}")

            # 4단계: JS를 비활성화하고 최종 페이지로 이동
            print("[DEBUG] 4단계: JavaScript 비활성화...")
            driver.execute_cdp_cmd("Emulation.setScriptExecutionDisabled", {"value": True})
            
            print(f"[DEBUG] 4단계: JS 비활성화 상태로 최종 페이지 요청 -> {live_page_url}")
            
            # [임시 디버깅] OS 기본 브라우저로 URL 열기
            print(f"[DEBUG] 임시: OS 기본 브라우저로 URL 열기 -> {live_page_url}")
            webbrowser.open(live_page_url)

            driver.get(live_page_url)

            # 5단계: 최종 페이지에서 데이터 추출
            print("[DEBUG] 5단계: 최종 페이지에서 데이터 추출 시도...")
            final_page_source = driver.page_source
            # _aldata 변수 값을 더 안전하게 추출
            # 공백 변화에 대응하기 위해 정규표현식 강화
            aldata_match = re.search(r"var\s+_aldata\s*=\s*'([^']*)'", final_page_source)
            if not aldata_match:
                raise Exception("_aldata를 찾을 수 없음 (JS 비활성화 후)")
            
            encoded_aldata = aldata_match.group(1)
            print("[DEBUG] 5단계: _aldata 추출 성공")

            # 6단계: 데이터 해독
            print("[DEBUG] 6단계: Base64 디코딩 시도...")
            # JS에서 넘어온 불필요한 백슬래시 제거
            processed_aldata = encoded_aldata.replace('\\', '')
            
            # 패딩 처리
            missing_padding = len(processed_aldata) % 4
            if missing_padding:
                processed_aldata += '=' * (4 - missing_padding)
                print(f"[DEBUG] 6단계: 패딩 {4 - missing_padding}개 추가됨.")

            # 서버가 비표준 인코딩(euc-kr)을 사용하므로, 해당 인코딩으로 디코딩
            decoded_json_str = base64.b64decode(processed_aldata).decode('euc-kr')
            video_data = json.loads(decoded_json_str)
            encoded_video_path = video_data.get('vid_url_1080') or video_data.get('vid_url_720')
            if not encoded_video_path or encoded_video_path == "none":
                raise Exception("JSON 데이터에서 비디오 URL을 찾을 수 없음")
            
            # 최종 경로는 Base64 인코딩이 아니라, 슬래시가 이스케이프 처리된 문자열임
            cleaned_video_path = encoded_video_path.replace('\\/', '/')
            m3u8_url = "https://" + cleaned_video_path
            print(f"[DEBUG] M3U8 URL 획득: {m3u8_url}")

            # --- [NEW] M3U8 파일 직접 다운로드 ---
            # 셀레니움이 가진 쿠키와 세션을 그대로 사용하여 m3u8 파일에 접근
            print("[DEBUG] 7단계: 획득한 세션으로 M3U8 파일 다운로드 시도...")
            cookies = driver.get_cookies()
            s = requests.Session()
            for cookie in cookies:
                s.cookies.set(cookie['name'], cookie['value'])
            
            headers = {
                'Referer': live_page_url,
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
            }
            
            m3u8_response = s.get(m3u8_url, headers=headers)
            m3u8_response.raise_for_status()
            
            # 1차 응답은 JSON이므로, 여기서 진짜 m3u8 URL을 파싱
            print("[DEBUG] 7-1단계: JSON 응답 파싱 시도...")
            json_data = m3u8_response.json()
            master_m3u8_url = json_data[0]['url']
            print(f"[DEBUG] 7-2단계: 최종 Master M3U8 URL 획득 -> {master_m3u8_url}")

            # --- [NEW] FFMPEG로 다운로드 ---
            print("[DEBUG] 8단계: FFMPEG를 사용하여 다운로드 시작...")
            output_filename = f"{anime_id}_episode.mp4"
            
            # FFMPEG 명령어 생성
            # Referer와 User-Agent를 헤더로 전달하여 403 오류 회피
            ffmpeg_headers = f"Referer: {live_page_url}\r\nUser-Agent: {headers['User-Agent']}\r\n"
            command = [
                'ffmpeg',
                '-headers', ffmpeg_headers,
                '-i', master_m3u8_url,
                '-c', 'copy',
                '-bsf:a', 'aac_adtstoasc',
                output_filename
            ]
            
            print(f"[DEBUG] FFMPEG Command: {' '.join(command)}")

            # FFMPEG 실행
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8')
            
            # 실시간 출력 (디버깅용)
            for line in process.stdout:
                print(f"[FFMPEG] {line.strip()}")

            process.wait()

            if process.returncode == 0:
                print(f"[DEBUG] 최종 성공: 영상이 '{output_filename}'으로 저장되었습니다.")
                return {'download_path': output_filename}
            else:
                raise Exception(f"FFMPEG 다운로드 실패 (종료 코드: {process.returncode})")

        except Exception as e:
            print(f"[DEBUG] 처리 중 오류 발생: {e}")
            if driver:
                print("--- 현재 페이지 소스 ---")
                print(driver.page_source)
                print("--- HTML 끝 ---")
            return {}
        finally:
            if driver:
                print("[DEBUG] WebDriver 종료")
                driver.quit()
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