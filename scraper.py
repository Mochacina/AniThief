import requests
from bs4 import BeautifulSoup
import json
import re
import base64

class AniLifeScraper:
    BASE_URL = "https://anilife.live"

    def _make_request(self, url, params=None):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
                'Referer': 'https://anilife.live/'
            }
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            print(f"Error during request to {url}: {e}")
            return None

    def search(self, keyword):
        search_url = f"{self.BASE_URL}/search"
        response = self._make_request(search_url, params={'keyword': keyword})
        if not response:
            return []
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
                    results.append({
                        'id': anime_id,
                        'title': title,
                        'thumbnail_url': thumbnail_url
                    })
        return results

    def get_anime_details(self, anime_id):
        details_url = f"{self.BASE_URL}/detail/id/{anime_id}"
        response = self._make_request(details_url)
        if not response:
            return {}
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
        return {
            'title': title, 'summary': summary, 'poster_url': poster_url,
            'episodes': episodes, 'extra_info': extra_info
        }

    def get_video_info(self, provider_id):
        """[FINAL] 실제 비디오 스트리밍 URL(.m3u8)을 3단계에 걸쳐 가져옵니다."""
        # 1단계: Provider 페이지에서 최종 재생 페이지 URL 가져오기
        provider_url = f"{self.BASE_URL}/ani/provider/{provider_id}"
        provider_response = self._make_request(provider_url)
        if not provider_response:
            return {}

        match = re.search(r"location\.href = \"(.*?/h/live\?p=.*?)\"", provider_response.text)
        if not match:
            return {}
        
        live_page_url = match.group(1)

        # 2단계: 최종 재생 페이지에서 _aldata 추출
        live_page_response = self._make_request(live_page_url)
        if not live_page_response:
            return {}

        aldata_match = re.search(r"var _aldata = '(.*?)'", live_page_response.text)
        if not aldata_match:
            return {}
        
        encoded_aldata = aldata_match.group(1)

        # 3단계: _aldata 디코딩 및 최종 URL 추출
        try:
            decoded_json_str = base64.b64decode(encoded_aldata).decode('utf-8')
            video_data = json.loads(decoded_json_str)
            
            encoded_video_path = video_data.get('vid_url_1080') or video_data.get('vid_url_720')
            if not encoded_video_path or encoded_video_path == "none":
                return {}
            
            decoded_video_path = base64.b64decode(encoded_video_path).decode('utf-8')
            
            final_video_url = "https://" + decoded_video_path
            return {'video_url': final_video_url}
        except Exception as e:
            print(f"최종 URL 디코딩/파싱 중 오류 발생: {e}")
            return {}

# For testing purposes
if __name__ == '__main__':
    scraper = AniLifeScraper()
    test_provider_id = "30df7673-b666-4b2a-b1db-de749788202d" 
    print(f"--- 비디오 정보 테스트 (Provider ID: {test_provider_id}) ---")
    video_info = scraper.get_video_info(test_provider_id)
    if video_info and video_info.get('video_url'):
        print(f"최종 비디오 URL: {video_info['video_url']}")
    else:
        print("최종 비디오 URL을 찾지 못했습니다.")