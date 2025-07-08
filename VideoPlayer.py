import sys
import os
import ctypes

# --- VLC 내장을 위한 경로 설정 (최종 해결책) ---
# 스크립트가 실행되는 위치를 기준으로 VLC 라이브러리를 찾도록 설정
try:
    if sys.platform.startswith('win'):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        vlc_dll_path = os.path.join(script_dir, 'libvlc.dll')
        
        # 1. DLL 검색 경로에 스크립트 디렉토리 추가
        os.add_dll_directory(script_dir)
        
        # 2. ctypes를 이용해 DLL을 직접 로드 (가장 확실한 방법)
        if os.path.exists(vlc_dll_path):
            ctypes.CDLL(vlc_dll_path)
        else:
             raise FileNotFoundError(f"'{vlc_dll_path}'를 찾을 수 없습니다.")

        # 3. 플러그인 경로 설정
        plugin_path = os.path.join(script_dir, 'plugins')
        if os.path.isdir(plugin_path):
            os.environ['VLC_PLUGIN_PATH'] = plugin_path
except Exception as e:
    print(f"VLC 경로 설정 중 오류 발생: {e}")
    print("프로젝트 폴더에 libvlc.dll, libvlccore.dll, plugins 폴더가 있는지, 64비트 파일이 맞는지 확인해주세요.")

import vlc
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QFrame, QApplication, QLabel
)
from PyQt6.QtCore import Qt

class VideoPlayer(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Helena's Video Player")
        self.setModal(False)
        self.resize(800, 600)
        self.setStyleSheet("""
            QDialog { background-color: #1e2228; }
            QPushButton { 
                background-color: #61afef; color: #1e2228; 
                border: none; padding: 8px; border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #82c0ff; }
            QSlider::groove:horizontal {
                border: 1px solid #3b4048;
                height: 8px;
                background: #3b4048;
                margin: 2px 0;
            }
            QSlider::handle:horizontal {
                background: #61afef;
                border: 1px solid #61afef;
                width: 18px;
                margin: -2px 0;
                border-radius: 3px;
            }
        """)

        # VLC 인스턴스 및 플레이어 생성
        try:
            self.instance = vlc.Instance()
            self.player = self.instance.media_player_new()
        except Exception as e:
            print(f"VLC 플레이어 생성 실패: {e}")
            self.player = None
            # UI에 오류 메시지 표시
            error_label = QLabel(f"VLC 플레이어 생성 실패:\n{e}\n\n프로젝트 폴더의 VLC 파일들을 확인해주세요.")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setStyleSheet("color: #abb2bf;")
            layout = QVBoxLayout(self)
            layout.addWidget(error_label)
            return

        # UI 구성
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: black;")
        
        self.play_pause_button = QPushButton("재생")
        self.stop_button = QPushButton("정지")
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMaximum(100)
        
        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self.play_pause_button)
        controls_layout.addWidget(self.stop_button)
        controls_layout.addWidget(self.volume_slider)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.video_frame)
        main_layout.addLayout(controls_layout)

        if self.player:
            self.volume_slider.setValue(self.player.audio_get_volume())
            self.play_pause_button.clicked.connect(self.toggle_play_pause)
            self.stop_button.clicked.connect(self.stop_video)
            self.volume_slider.valueChanged.connect(self.set_volume)

            if sys.platform.startswith('linux'):
                self.player.set_xwindow(self.video_frame.winId())
            elif sys.platform == "win32":
                self.player.set_hwnd(self.video_frame.winId())
            elif sys.platform == "darwin":
                self.player.set_nsobject(int(self.video_frame.winId()))

    def play_video(self, path): # url 대신 path를 받음
        if not self.player: return
        
        # 로컬 파일을 재생할 때는 특별한 옵션이 필요 없음
        print(f"[DEBUG] Playing local playlist: {path}")
        media = self.instance.media_new(path)
        self.player.set_media(media)
        self.player.play()
        self.play_pause_button.setText("일시정지")

    def toggle_play_pause(self):
        if not self.player: return
        if self.player.is_playing():
            self.player.pause()
            self.play_pause_button.setText("재생")
        else:
            self.player.play()
            self.play_pause_button.setText("일시정지")

    def stop_video(self):
        if not self.player: return
        self.player.stop()
        self.play_pause_button.setText("재생")

    def set_volume(self, volume):
        if not self.player: return
        self.player.audio_set_volume(volume)

    def closeEvent(self, event):
        if self.player:
            self.stop_video()
            self.player.release()
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    player_dialog = VideoPlayer()
    if player_dialog.player:
        test_url = "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"
        player_dialog.play_video(test_url)
        player_dialog.show()
    else:
        # 오류가 발생했을 때, 생성자에서 이미 오류 UI를 표시하도록 변경됨
        player_dialog.show()
    
    sys.exit(app.exec())