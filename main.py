import sys
import requests
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel, QStatusBar, QButtonGroup,
    QLineEdit, QListWidget, QListWidgetItem, QTextEdit, QProgressBar, QDialog
)
from PyQt6.QtCore import Qt, QObject, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QImage, QIcon
from scraper import AniLifeScraper
from VideoPlayer import VideoPlayer

# --- Workers for Threading ---
class SearchWorker(QObject):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword
        self.scraper = AniLifeScraper()
    def run(self):
        try:
            self.finished.emit(self.scraper.search(self.keyword))
        except Exception as e:
            self.error.emit(str(e))

class DetailWorker(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    def __init__(self, anime_id):
        super().__init__()
        self.anime_id = anime_id
        self.scraper = AniLifeScraper()
    def run(self):
        try:
            self.finished.emit(self.scraper.get_anime_details(self.anime_id))
        except Exception as e:
            self.error.emit(str(e))

class ThumbnailDownloader(QObject):
    finished = pyqtSignal(QListWidgetItem, QPixmap)
    def __init__(self, item, url):
        super().__init__()
        self.item = item
        self.url = url
    def run(self):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
                'Referer': 'https://anilife.live/'
            }
            response = requests.get(self.url, headers=headers, timeout=15)
            response.raise_for_status()
            image = QImage()
            image.loadFromData(response.content)
            self.finished.emit(self.item, QPixmap.fromImage(image))
        except Exception as e:
            print(f"Thumbnail download failed for {self.url}: {e}")
            self.finished.emit(self.item, QPixmap())

class PosterDownloader(QObject):
    finished = pyqtSignal(QPixmap)
    def __init__(self, url):
        super().__init__()
        self.url = url
    def run(self):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
                'Referer': 'https://anilife.live/'
            }
            response = requests.get(self.url, headers=headers, timeout=15)
            response.raise_for_status()
            image = QImage()
            image.loadFromData(response.content)
            self.finished.emit(QPixmap.fromImage(image))
        except Exception as e:
            print(f"Poster download failed for {self.url}: {e}")
            self.finished.emit(QPixmap())

class VideoWorker(QObject):
    progress_update = pyqtSignal(int, int, str)
    sub_progress_update = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, provider_id, anime_id):
        super().__init__()
        self.provider_id = provider_id
        self.anime_id = anime_id
        # Scraper는 run 메소드 안에서, 해당 스레드에서 생성되어야 함
        self.scraper = None

    def run(self):
        print("[DEBUG] VideoWorker.run() 시작")
        self.scraper = AniLifeScraper()

        # Scraper의 시그널을 Worker의 시그널로 다시 전달(re-emit)
        self.scraper.progress_update.connect(self.progress_update)
        self.scraper.sub_progress_update.connect(self.sub_progress_update)
        self.scraper.finished.connect(self.finished)
        self.scraper.error.connect(self.error)

        # Scraper가 자체적으로 finished/error 시그널을 보내므로,
        # Worker는 그냥 실행만 시키면 됨.
        self.scraper.get_video_info(self.provider_id, self.anime_id)
        print("[DEBUG] VideoWorker.run() 종료")

# --- Custom Widgets ---
class ProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("다운로드 진행률")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        self.main_progress_label = QLabel("전체 진행률: 대기 중...")
        self.main_progress_bar = QProgressBar()
        self.sub_progress_label = QLabel("세부 진행률:")
        self.sub_progress_bar = QProgressBar()
        
        layout.addWidget(self.main_progress_label)
        layout.addWidget(self.main_progress_bar)
        layout.addWidget(self.sub_progress_label)
        layout.addWidget(self.sub_progress_bar)

        # 사용자가 창을 닫지 못하도록 설정 (선택 사항)
        self.setModal(True)

    def update_main_progress(self, current, total, message):
        self.main_progress_bar.setRange(0, total)
        self.main_progress_bar.setValue(current)
        self.main_progress_label.setText(f"전체 진행률: {message} ({current}/{total})")

    def update_sub_progress(self, current, total, label):
        self.sub_progress_bar.setRange(0, total)
        self.sub_progress_bar.setValue(current)
        self.sub_progress_label.setText(f"{label}: {current} / {total}")

    def set_finished_status(self, message, success):
        self.main_progress_label.setText(message)
        self.sub_progress_label.setText("완료" if success else "실패")
        self.main_progress_bar.setValue(self.main_progress_bar.maximum())
        self.sub_progress_bar.setValue(self.sub_progress_bar.maximum())
        # 완료 후 자동으로 닫히게 하려면 self.accept() 호출
        # self.accept()

class SearchPageWidget(QWidget):
    anime_selected = pyqtSignal(str)
    def __init__(self, status_bar_callback):
        super().__init__()
        self.status_bar_callback = status_bar_callback
        layout = QVBoxLayout(self)
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("애니메이션 제목을 입력하세요...")
        self.search_input.returnPressed.connect(self.start_search)
        search_layout.addWidget(self.search_input)
        self.search_button = QPushButton("검색")
        self.search_button.clicked.connect(self.start_search)
        search_layout.addWidget(self.search_button)
        layout.addLayout(search_layout)
        self.results_list = QListWidget()
        self.results_list.setIconSize(QSize(80, 120))
        self.results_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.results_list)

    def on_item_double_clicked(self, item):
        anime_data = item.data(Qt.ItemDataRole.UserRole)
        if anime_data and 'id' in anime_data:
            self.anime_selected.emit(anime_data['id'])

    def start_search(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            self.status_bar_callback("검색어를 입력해주세요.")
            return
        self.status_bar_callback(f"'{keyword}' 검색 중...")
        self.search_button.setEnabled(False)
        self.results_list.clear()
        self.thread = QThread()
        self.worker = SearchWorker(keyword)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.update_results)
        self.worker.error.connect(self.search_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def update_results(self, results):
        self.results_list.clear()
        if not results:
            self.status_bar_callback("검색 결과가 없습니다.")
        else:
            for data in results:
                list_item = QListWidgetItem(f"  {data['title']}")
                list_item.setData(Qt.ItemDataRole.UserRole, data)

                # 썸네일 공간을 미리 확보하기 위해 투명한 아이콘 설정
                placeholder_pixmap = QPixmap(self.results_list.iconSize())
                placeholder_pixmap.fill(Qt.GlobalColor.transparent)
                list_item.setIcon(QIcon(placeholder_pixmap))

                self.results_list.addItem(list_item)
                thumbnail_url = data.get('thumbnail_url')
                if thumbnail_url:
                    self.download_thumbnail(list_item, thumbnail_url)
            self.status_bar_callback(f"{len(results)}개의 결과를 찾았습니다.")
        self.search_button.setEnabled(True)

    def download_thumbnail(self, item, url):
        thread = QThread()
        downloader = ThumbnailDownloader(item, url)
        downloader.moveToThread(thread)
        item.thread = thread
        item.downloader = downloader
        thread.started.connect(downloader.run)
        downloader.finished.connect(self.set_thumbnail)
        downloader.finished.connect(thread.quit)
        downloader.finished.connect(downloader.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def set_thumbnail(self, item, pixmap):
        if not pixmap.isNull():
            item.setIcon(QIcon(pixmap))

    def search_error(self, error_message):
        self.status_bar_callback(f"오류 발생: {error_message}")
        self.search_button.setEnabled(True)

class AnimeDetailWidget(QWidget):
    back_requested = pyqtSignal()
    episode_selected = pyqtSignal(str, str)
    def __init__(self):
        super().__init__()
        self.current_anime_id = None
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        self.poster_label = QLabel("포스터 로딩 중...")
        self.poster_label.setFixedSize(250, 350)
        self.poster_label.setScaledContents(True)
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setStyleSheet("background-color: #1e2228; border-radius: 5px;")
        main_layout.addWidget(self.poster_label)
        details_layout = QVBoxLayout()
        details_layout.setSpacing(10)
        top_layout = QHBoxLayout()
        back_button = QPushButton("◀ 뒤로가기")
        back_button.clicked.connect(self.back_requested.emit)
        back_button.setFixedWidth(100)
        self.title_label = QLabel("제목")
        self.title_label.setStyleSheet("font-size: 22px; font-weight: bold;")
        self.title_label.setWordWrap(True)
        top_layout.addWidget(self.title_label, 1)
        top_layout.addWidget(back_button)
        details_layout.addLayout(top_layout)
        details_layout.addWidget(QLabel("상세 정보"))
        self.info_text = QTextEdit()
        self.info_text.setReadOnly(True)
        self.info_text.setStyleSheet("background-color: #1e2228; border: none; padding: 5px;")
        details_layout.addWidget(self.info_text, 1)
        details_layout.addWidget(QLabel("줄거리"))
        self.summary_label = QTextEdit()
        self.summary_label.setReadOnly(True)
        self.summary_label.setStyleSheet("background-color: #1e2228; border: none; padding: 5px;")
        details_layout.addWidget(self.summary_label, 1)
        details_layout.addWidget(QLabel("에피소드"))
        self.episodes_list = QListWidget()
        self.episodes_list.itemDoubleClicked.connect(self.on_episode_double_clicked)
        details_layout.addWidget(self.episodes_list, 2)
        main_layout.addLayout(details_layout, 1)

    def on_episode_double_clicked(self, item):
        print(f"[DEBUG] 에피소드 아이템 더블클릭: {item.text()}")
        provider_id = item.data(Qt.ItemDataRole.UserRole)
        if provider_id and self.current_anime_id:
            # 다운로드 시작 시, 리스트를 비활성화 하도록 MainWindow에 요청
            self.episodes_list.setEnabled(False)
            print(f"[DEBUG] Provider ID '{provider_id}'와 Anime ID '{self.current_anime_id}'로 episode_selected 시그널 발생")
            self.episode_selected.emit(provider_id, self.current_anime_id)
        else:
            print(f"[DEBUG] Provider ID({provider_id}) 또는 Anime ID({self.current_anime_id})를 찾을 수 없음")

    def update_details(self, data, anime_id=None):
        self.current_anime_id = anime_id
        self.title_label.setText(data.get('title', 'Loading...'))
        self.summary_label.setText(data.get('summary', ''))
        extra_info = data.get('extra_info', {})
        info_html = ""
        for key, value in extra_info.items():
            info_html += f"<b>{key}:</b> {value}<br>"
        self.info_text.setHtml(info_html)
        self.episodes_list.clear()
        for episode in data.get('episodes', []):
            item_text = f"{episode.get('num', '')}화 - {episode.get('title', '제목 없음')}"
            item = QListWidgetItem(item_text.strip())
            item.setData(Qt.ItemDataRole.UserRole, episode['provider_id'])
            self.episodes_list.addItem(item)
        poster_url = data.get('poster_url')
        if poster_url:
            self.download_poster(poster_url)
        else:
            self.poster_label.setText("이미지 없음")

    def download_poster(self, url):
        self.poster_thread = QThread()
        self.poster_downloader = PosterDownloader(url)
        self.poster_downloader.moveToThread(self.poster_thread)
        self.poster_thread.started.connect(self.poster_downloader.run)
        self.poster_downloader.finished.connect(self.set_poster)
        self.poster_downloader.finished.connect(self.poster_thread.quit)
        self.poster_downloader.finished.connect(self.poster_downloader.deleteLater)
        self.poster_thread.finished.connect(self.poster_thread.deleteLater)
        self.poster_thread.start()

    def set_poster(self, pixmap):
        if not pixmap.isNull():
            self.poster_label.setPixmap(pixmap)
        else:
            self.poster_label.setText("이미지 로드 실패")

# --- Stylesheet ---
DARK_THEME_QSS = """
QWidget {
    background-color: #282c34; color: #abb2bf;
    font-family: "Segoe UI", "Inter", sans-serif; font-size: 14px;
}
QMainWindow { background-color: #282c34; }
#LeftNavBar { background-color: #1e2228; }
#LeftNavBar QPushButton {
    background-color: transparent; border: none; color: #abb2bf;
    padding: 15px; text-align: left; font-size: 15px; border-radius: 0px;
}
#LeftNavBar QPushButton:hover { background-color: #3b4048; }
#LeftNavBar QPushButton:checked {
    background-color: #282c34; border-left: 3px solid #61afef; font-weight: bold;
}
#ContentArea { background-color: #282c34; }
QStatusBar { color: #abb2bf; }
QListWidget {
    background-color: #1e2228; border: 1px solid #3b4048;
    border-radius: 5px; padding: 5px;
}
QListWidget::item { padding: 8px; }
QListWidget::item:hover { background-color: #3b4048; }
QListWidget::item:selected { background-color: #61afef; color: #1e2228; }
QLineEdit {
    background-color: #1e2228; border: 1px solid #3b4048;
    border-radius: 5px; padding: 8px;
}
QPushButton {
    background-color: #61afef; color: #1e2228; border: none;
    padding: 8px 16px; border-radius: 5px; font-weight: bold;
}
QPushButton:hover { background-color: #82c0ff; }
QPushButton:disabled { background-color: #4a5058; color: #888; }
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AniLife Player by Brie/Helena")
        self.setGeometry(100, 100, 1200, 800)
        self.initUI()

    def initUI(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.left_nav_bar = self.create_left_nav_bar()
        main_layout.addWidget(self.left_nav_bar)
        self.content_area = QStackedWidget()
        self.content_area.setObjectName("ContentArea")
        main_layout.addWidget(self.content_area, 1)
        self.search_page = SearchPageWidget(self.set_status_message)
        self.search_page.anime_selected.connect(self.show_anime_details)
        self.detail_page = AnimeDetailWidget()
        self.detail_page.back_requested.connect(self.show_search_page)
        self.detail_page.episode_selected.connect(self.play_video)
        self.video_player = None
        self.pages = {
            "search": self.search_page,
            "daily": self.create_placeholder_page("요일별 애니"),
            "quarter": self.create_placeholder_page("분기별 애니"),
            "top20": self.create_placeholder_page("TOP 20"),
            "genre": self.create_placeholder_page("장르별"),
        }
        self.content_area.addWidget(self.search_page)
        self.content_area.addWidget(self.detail_page)
        for name in ["daily", "quarter", "top20", "genre"]:
             self.content_area.addWidget(self.pages[name])
        self.nav_button_group.buttonClicked.connect(self.switch_page)
        self.setCentralWidget(main_widget)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.set_status_message("준비 완료. 헬레나님, 출격 준비 완료!")
        self.nav_buttons["search"].setChecked(True)
        self.content_area.setCurrentWidget(self.search_page)

    def create_placeholder_page(self, text):
        page = QLabel(f"{text}\n(구현 예정)")
        page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page.setStyleSheet("font-size: 24px; font-weight: bold;")
        return page

    def create_left_nav_bar(self):
        nav_bar = QWidget()
        nav_bar.setObjectName("LeftNavBar")
        nav_layout = QVBoxLayout(nav_bar)
        nav_layout.setContentsMargins(0, 10, 0, 10)
        nav_layout.setSpacing(5)
        self.nav_buttons = {
            "search": QPushButton("🔍 검색"), "daily": QPushButton("📅 요일별"),
            "quarter": QPushButton("🌸 분기별"), "top20": QPushButton("🏆 TOP 20"),
            "genre": QPushButton("🎭 장르"),
        }
        self.nav_button_group = QButtonGroup(self)
        self.nav_button_group.setExclusive(True)
        for name, button in self.nav_buttons.items():
            button.setCheckable(True)
            button.setObjectName(name)
            nav_layout.addWidget(button)
            self.nav_button_group.addButton(button)
        nav_layout.addStretch()
        nav_bar.setFixedWidth(160)
        return nav_bar

    def switch_page(self, button):
        page_name = button.objectName()
        if page_name in self.pages:
            self.content_area.setCurrentWidget(self.pages[page_name])
            self.set_status_message(f"{button.text().strip()} 페이지로 이동했습니다.")

    def show_anime_details(self, anime_id):
        self.set_status_message(f"애니메이션 정보 로딩 중...")
        self.detail_page.update_details({}, anime_id) 
        self.content_area.setCurrentWidget(self.detail_page)
        self.detail_thread = QThread()
        self.detail_worker = DetailWorker(anime_id)
        self.detail_worker.moveToThread(self.detail_thread)
        self.detail_thread.started.connect(self.detail_worker.run)
        self.detail_worker.finished.connect(self.on_details_loaded)
        self.detail_worker.error.connect(self.on_details_error)
        self.detail_worker.finished.connect(self.detail_thread.quit)
        self.detail_worker.finished.connect(self.detail_worker.deleteLater)
        self.detail_thread.finished.connect(self.detail_thread.deleteLater)
        self.detail_thread.start()

    def on_details_loaded(self, data):
        if not data:
            self.set_status_message("상세 정보를 불러오는 데 실패했습니다.")
            self.show_search_page()
        else:
            self.detail_page.update_details(data, self.detail_page.current_anime_id)
            self.set_status_message(f"'{data.get('title', '')}' 정보 로드 완료.")

    def on_details_error(self, error_message):
        self.set_status_message(f"오류 발생: {error_message}")
        self.show_search_page()

    def show_search_page(self):
        self.content_area.setCurrentWidget(self.search_page)
        self.set_status_message("검색 페이지로 돌아왔습니다.")

    def play_video(self, provider_id, anime_id):
        print(f"[DEBUG] play_video 슬롯 실행됨. Provider ID: {provider_id}, Anime ID: {anime_id}")
        
        self.progress_dialog = ProgressDialog(self)
        
        self.video_thread = QThread()
        self.video_worker = VideoWorker(provider_id, anime_id)
        self.video_worker.moveToThread(self.video_thread)

        # Worker의 시그널을 ProgressDialog의 슬롯에 연결
        self.video_worker.progress_update.connect(self.progress_dialog.update_main_progress)
        self.video_worker.sub_progress_update.connect(self.progress_dialog.update_sub_progress)
        self.video_worker.finished.connect(self.on_download_finished)
        self.video_worker.error.connect(self.on_download_error)
        
        # 스레드 및 워커 정리
        self.video_worker.finished.connect(self.video_thread.quit)
        self.video_worker.error.connect(self.video_thread.quit)
        self.video_worker.finished.connect(self.video_worker.deleteLater)
        self.video_thread.finished.connect(self.video_thread.deleteLater)

        self.video_thread.started.connect(self.video_worker.run)
        self.video_thread.start()
        
        self.progress_dialog.show()

    def on_download_finished(self, result):
        download_path = result.get('download_path')
        message = f"다운로드 완료! '{download_path}'" if download_path else "다운로드 실패."
        self.set_status_message(message)
        self.progress_dialog.set_finished_status(message, success=bool(download_path))
        self.detail_page.episodes_list.setEnabled(True)
        # self.progress_dialog.accept() # 완료 후 자동으로 닫기

    def on_download_error(self, error_message):
        message = f"오류 발생: {error_message}"
        self.set_status_message(message)
        self.progress_dialog.set_finished_status(message, success=False)
        self.detail_page.episodes_list.setEnabled(True)
        # self.progress_dialog.accept() # 완료 후 자동으로 닫기

    def set_status_message(self, message):
        self.status_bar.showMessage(message)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME_QSS)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())