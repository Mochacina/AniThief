import requests
from bs4 import BeautifulSoup
import json
import re
import base64
import subprocess
import os
from tqdm import tqdm
from urllib.parse import urljoin

from PyQt6.QtCore import QObject, pyqtSignal

from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import webbrowser

class AniLifeScraper(QObject):
    # 시그널 정의
    # progress_update: (현재 단계, 전체 단계, 메시지)
    progress_update = pyqtSignal(int, int, str)
    # sub_progress_update: (현재 값, 전체 값, 레이블) - 다운로드, FFMPEG 등 세부 진행률
    sub_progress_update = pyqtSignal(int, int, str)
    # finished: (결과 딕셔너리)
    finished = pyqtSignal(dict)
    # error: (에러 메시지)
    error = pyqtSignal(str)

    BASE_URL = "https://anilife.live"

    def __init__(self):
        super().__init__()
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
        """[FINAL ORDER] 최종 명령"""
        print(f"--- [DEBUG] get_video_info 시작 (Provider ID: {provider_id}, Anime ID: {anime_id}) ---")
        self.progress_update.emit(0, 15, f"작업 시작 (Provider: {provider_id})")
        driver = None
        try:
            # 1단계: Selenium WebDriver 초기화
            print("[DEBUG] 1단계: Selenium WebDriver 초기화...")
            self.progress_update.emit(1, 15, "Selenium WebDriver 초기화...")
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

            # --- [전략 회귀] JS를 처음부터 비활성화 ---
            driver.execute_cdp_cmd("Emulation.setScriptExecutionDisabled", {"value": True})
            
            # 1-1단계: 상세 페이지 방문
            details_url = f"{self.BASE_URL}/detail/id/{anime_id}"
            print(f"[DEBUG] 1단계: 상세 페이지 방문 시도 -> {details_url}")
            self.progress_update.emit(2, 15, "상세 페이지 방문 및 쿠키 획득...")
            driver.get(details_url)
            print("[DEBUG] 1단계: 상세 페이지 방문 성공 (쿠키 획득 추정)")

            # 2단계: 리다이렉트된 페이지에서 실제 에피소드 링크 클릭
            print(f"[DEBUG] 2단계: Provider ID '{provider_id}'를 포함하는 링크 탐색 및 클릭 시도...")
            self.progress_update.emit(3, 15, f"에피소드 링크 탐색...")
            wait = WebDriverWait(driver, 10)
            episode_link_xpath = f"//a[contains(@href, '{provider_id}')]"
            episode_link = wait.until(EC.element_to_be_clickable((By.XPATH, episode_link_xpath)))
            print(f"[DEBUG] 2단계: 링크 발견 및 클릭 -> {episode_link.get_attribute('href')}")
            episode_link.click()

            # 2-1단계: Provider 페이지로 이동했는지 확인
            wait.until(EC.url_contains(f"/ani/provider/{provider_id}"))
            print("[DEBUG] 2-1단계: Provider 페이지로 성공적으로 이동함")
            self.progress_update.emit(4, 15, "Provider 페이지로 이동...")

            # 3단계: Provider 페이지에서 JS를 실행하는 대신, URL을 추출
            print("[DEBUG] 3단계: Provider 페이지 소스에서 최종 URL 추출 시도...")
            self.progress_update.emit(5, 15, "최종 재생 페이지 URL 추출...")
            provider_page_source = driver.page_source
            match = re.search(r"location\.href = \"(.*?/h/live\?p=.*?)\"", provider_page_source)
            if not match:
                raise Exception("Provider 페이지에서 location.href 패턴을 찾을 수 없음")
            live_page_url = match.group(1)
            print(f"[DEBUG] 3단계: 최종 재생 페이지 URL 추출 성공 -> {live_page_url}")

            # 4단계: 최종 페이지로 이동 (JS 비활성화 상태)
            print(f"[DEBUG] 4단계: 최종 페이지 요청 (JS 비활성화) -> {live_page_url}")
            self.progress_update.emit(6, 15, "최종 재생 페이지로 이동...")
            driver.get(live_page_url)

            # 5단계: 최종 페이지에서 데이터 추출
            print("[DEBUG] 5단계: 최종 페이지에서 데이터 추출 시도...")
            self.progress_update.emit(7, 15, "비디오 데이터 추출...")
            final_page_source = driver.page_source
            aldata_match = re.search(r"var\s+_aldata\s*=\s*'([^']*)'", final_page_source)
            if not aldata_match:
                raise Exception("_aldata를 찾을 수 없음")
            
            encoded_aldata = aldata_match.group(1)
            print("[DEBUG] 5단계: _aldata 추출 성공")

            # 6단계: 데이터 해독
            print("[DEBUG] 6단계: Base64 디코딩 시도...")
            self.progress_update.emit(8, 15, "비디오 데이터 디코딩...")
            # JS에서 넘어온 불필요한 백슬래시 제거
            processed_aldata = encoded_aldata.replace('\\', '')
            
            # 패딩 처리
            missing_padding = len(processed_aldata) % 4
            if missing_padding:
                processed_aldata += '=' * (4 - missing_padding)
                print(f"[DEBUG] 6단계: 패딩 {4 - missing_padding}개 추가됨.")

            # 서버가 비표준 인코딩(euc-kr)을 사용하므로, 해당 인코딩으로 디코딩
            aldata_decoded = base64.b64decode(processed_aldata).decode('euc-kr')
            video_data = json.loads(aldata_decoded)
            encoded_video_path = video_data.get('vid_url_1080') or video_data.get('vid_url_720')
            if not encoded_video_path or encoded_video_path == "none":
                raise Exception("JSON 데이터에서 비디오 URL을 찾을 수 없음")
            
            # 최종 경로는 Base64 인코딩이 아니라, 슬래시가 이스케이프 처리된 문자열임
            cleaned_video_path = encoded_video_path.replace('\\/', '/')
            m3u8_url = "https://" + cleaned_video_path
            print(f"[DEBUG] M3U8 URL 획득: {m3u8_url}")
            self.progress_update.emit(9, 15, "M3U8 URL 획득...")

            # --- [NEW] FFMPEG를 위한 완전한 위장 정보 생성 ---
            print("[DEBUG] 7단계: FFMPEG용 위조 여권(쿠키) 생성...")
            self.progress_update.emit(10, 15, "FFMPEG용 인증 정보 생성...")
            cookies = driver.get_cookies()
            cookie_str = '; '.join([f"{c['name']}={c['value']}" for c in cookies])
            
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'

            # FFMPEG에 전달할 모든 헤더를 하나의 문자열로 결합
            headers = (
                f"User-Agent: {user_agent}\r\n"
                f"Referer: {live_page_url}\r\n"
                f"Cookie: {cookie_str}\r\n"
            )
            
            # 1차 응답(JSON)은 requests로 가져오기
            s = requests.Session()
            s.headers.update({'User-Agent': user_agent, 'Referer': live_page_url})
            for cookie in cookies:
                s.cookies.set(cookie['name'], cookie['value'])
            
            json_response = s.get(m3u8_url)
            json_response.raise_for_status()
            master_m3u8_url = json_response.json()[0]['url']
            print(f"[DEBUG] 7-1단계: 최종 Master M3U8 URL 획득 -> {master_m3u8_url}")
            self.progress_update.emit(11, 15, "Master M3U8 URL 획득...")

            # --- [NEW] requests로 m3u8 내용 직접 가져오기 ---
            print("[DEBUG] 8단계: requests로 M3U8 내용 직접 강탈 시도...")
            self.progress_update.emit(12, 15, "M3U8 플레이리스트 다운로드...")
            m3u8_content_response = s.get(master_m3u8_url)
            m3u8_content_response.raise_for_status()
            m3u8_content = m3u8_content_response.text

            # m3u8 파일 내의 상대 경로를 절대 경로로 수정
            base_url = '/'.join(master_m3u8_url.split('/')[:-1])
            m3u8_content_fixed = re.sub(r'^(?!#)(?!https?://)(.*)', fr'{base_url}/\1', m3u8_content, flags=re.MULTILINE)

            playlist_path = "temp_playlist.m3u8"
            with open(playlist_path, 'w', encoding='utf-8') as f:
                f.write(m3u8_content_fixed)
            print(f"[DEBUG] 8-1단계: M3U8 플레이리스트를 '{playlist_path}'에 저장 성공")

            # --- [FINAL STRATEGY] 모든 부품을 로컬로 다운로드 후 확장자 변경 및 조립 ---
            temp_dir = "temp_download"
            # 작전 시작 전, 이전의 모든 임시 파일/폴더를 깨끗하게 청소한다.
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)

            # 1. 모든 비디오 조각(.aaa) 다운로드
            ts_urls = [line.strip() for line in m3u8_content_fixed.split('\n') if line.strip() and not line.startswith('#')]
            print(f"[DEBUG] 9단계: 총 {len(ts_urls)}개의 비디오 조각 다운로드 시작...")
            self.progress_update.emit(13, 15, f"비디오 조각 다운로드 중...")
            for i, ts_url in enumerate(ts_urls):
                ts_response = s.get(ts_url, headers={'Referer': live_page_url})
                ts_response.raise_for_status()
                local_ts_path = os.path.join(temp_dir, f"segment_{i:04d}.aaa")
                with open(local_ts_path, 'wb') as f:
                    f.write(ts_response.content)
                self.sub_progress_update.emit(i + 1, len(ts_urls), "다운로드")
            print(f"[DEBUG] 10단계: 모든 세그먼트 다운로드 완료.")

            # 2. 다운로드된 .aaa 파일들의 확장자를 .ts로 변경
            print(f"[DEBUG] 11단계: .aaa -> .ts 확장자 변경 작업 시작...")
            for i in range(len(ts_urls)):
                segment_filename = f"segment_{i:04d}.aaa"
                ts_filename = f"segment_{i:04d}.ts"
                old_path = os.path.join(temp_dir, segment_filename)
                new_path = os.path.join(temp_dir, ts_filename)
                if os.path.exists(old_path):
                    os.rename(old_path, new_path)
            print(f"[DEBUG] 12단계: 확장자 변경 완료.")

            # 3. 로컬 파일만 참조하는 최종 플레이리스트 생성
            final_playlist_path = os.path.join(temp_dir, "playlist_final.m3u8")
            # 원본 m3u8에서 EXTINF 시간 정보 추출
            extinf_lines = [line for line in m3u8_content.splitlines() if line.startswith('#EXTINF')]
            
            with open(final_playlist_path, 'w', encoding='utf-8') as f:
                f.write("#EXTM3U\n")
                f.write("#EXT-X-VERSION:3\n")
                # 원본 m3u8에서 TARGETDURATION 값을 가져오거나 기본값 사용
                target_duration_match = re.search(r'#EXT-X-TARGETDURATION:(\d+)', m3u8_content)
                if target_duration_match:
                    f.write(f"#EXT-X-TARGETDURATION:{target_duration_match.group(1)}\n")
                else:
                    f.write("#EXT-X-TARGETDURATION:10\n") # 기본값
                f.write("#EXT-X-MEDIA-SEQUENCE:0\n")

                for i in range(len(ts_urls)):
                    # 원본에 EXTINF 정보가 있다면 사용, 없다면 기본값 사용
                    if i < len(extinf_lines):
                        f.write(extinf_lines[i] + "\n")
                    else:
                        f.write("#EXTINF:4.000000,\n") # 기본값
                    f.write(f"segment_{i:04d}.ts\n")
                
                f.write("#EXT-X-ENDLIST\n")
            print(f"[DEBUG] 13단계: 최종 로컬 플레이리스트 '{final_playlist_path}' 생성 완료.")
            self.progress_update.emit(14, 15, "로컬 플레이리스트 생성...")

            # 4. 파일 경로 및 이름 규칙 설정
            # video_data는 176번째 줄에서 이미 파싱되었으므로 재사용한다.
            anime_title = video_data.get('ani_name', 'Unknown_Title')
            anime_episode = video_data.get('ani_story', 'Unknown_Episode')

            # 폴더명으로 사용할 수 없는 문자 제거 및 공백을 '_'로 변경
            sanitized_title = re.sub(r'[\\/*?:"<>|]', '', anime_title).replace(' ', '_')

            # 최종 저장 경로 생성
            base_download_dir = "downloaded"
            anime_dir = os.path.join(base_download_dir, f"{anime_id}_{sanitized_title}")
            os.makedirs(anime_dir, exist_ok=True)
            
            output_filepath = os.path.join(anime_dir, f"{anime_episode}.mp4")
            
            print(f"[DEBUG] 14단계: 최종 저장 경로 설정 -> {output_filepath}")

            # 5. FFmpeg로 비디오 병합
            print("[DEBUG] 15단계: FFMPEG로 최종 조립 시작...")
            self.progress_update.emit(15, 15, "영상 합치는 중 (FFMPEG)...")
            
            ffmpeg_path = "ffmpeg.exe"
            command = [
                ffmpeg_path,
                '-protocol_whitelist', 'file,pipe', # 로컬 파일만 허용하도록 명시
                '-i', "playlist_final.m3u8",
                '-c', 'copy',
                # cwd가 temp_dir이므로, 절대 경로로 지정해줘야 함
                os.path.abspath(output_filepath)
            ]
            # FFMPEG 진행률 표시는 일단 제거하고, 안정적인 버전으로 되돌림
            process = subprocess.Popen(command, cwd=temp_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
            
            # FFMPEG 진행률을 0%에서 100%로 서서히 올리는 것처럼 보이게 처리 (임시)
            self.sub_progress_update.emit(0, 100, "영상 합치는 중...")
            
            for line in process.stdout:
                print(f"[FFMPEG] {line.strip()}")

            process.wait()
            self.sub_progress_update.emit(100, 100, "영상 합치기 완료")

            if process.returncode == 0:
                print(f"[DEBUG] 최종 성공: 영상이 '{output_filepath}'으로 저장되었습니다.")
                # 임시 파일 정리
                import shutil
                shutil.rmtree(temp_dir)
                self.finished.emit({'download_path': os.path.abspath(output_filepath)})
                return {'download_path': os.path.abspath(output_filepath)}
            else:
                # stderr_output 변수가 없으므로 제거
                raise Exception(f"FFMPEG 조립 실패 (종료 코드: {process.returncode})")

        except Exception as e:
            error_message = f"처리 중 오류 발생: {e}"
            print(f"[DEBUG] {error_message}")
            self.error.emit(error_message)
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