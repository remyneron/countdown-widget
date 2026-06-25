#!/usr/bin/env python3
import sys
import os
import time
import math
import struct
import wave
import json
import subprocess
import shutil

from PySide6.QtCore import Qt, QTimer, QPoint, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QConicalGradient, QAction, QCursor
from PySide6.QtWidgets import QApplication, QWidget, QLineEdit, QMenu

# Audio Generation
def generate_chime(filename):
    sample_rate = 44100
    duration = 1.2
    num_samples = int(sample_rate * duration)
    data = bytearray()
    
    for i in range(num_samples):
        t = i / sample_rate
        val = 0.0
        
        # Beep 1
        if 0.0 <= t < 0.25:
            dt = t - 0.0
            amplitude = math.exp(-15 * dt)
            val = math.sin(2 * math.pi * 880 * dt) * amplitude
        # Beep 2
        elif 0.3 <= t < 0.55:
            dt = t - 0.3
            amplitude = math.exp(-15 * dt)
            val = math.sin(2 * math.pi * 880 * dt) * amplitude
        # Beep 3
        elif 0.6 <= t < 1.1:
            dt = t - 0.6
            amplitude = math.exp(-5 * dt)
            val = math.sin(2 * math.pi * 1320 * dt) * amplitude
            
        sample = int(val * 32767)
        data.extend(struct.pack('<h', sample))
        
    try:
        with wave.open(filename, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(data)
    except Exception as e:
        print(f"Error generating chime sound: {e}")

# Play audio
def play_sound(wav_path):
    for player in ['pw-play', 'paplay', 'aplay']:
        if shutil.which(player):
            try:
                subprocess.Popen([player, wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                continue
    return False

# Desktop Notification
def send_notification(title, message):
    if shutil.which("notify-send"):
        try:
            subprocess.Popen(["notify-send", title, message, "-t", "5000", "-i", "alarm-clock"])
        except Exception:
            pass

class CustomLineEdit(QLineEdit):
    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if hasattr(self.parent(), 'cancel_inline_edit'):
            self.parent().cancel_inline_edit()

class CountdownWidget(QWidget):
    def __init__(self):
        super().__init__()
        
        # Load config first to set initial values
        self.config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
        self.load_config()
        
        # Timer values
        self.total_seconds = self.config.get("duration_seconds", 1500.0)
        self.remaining_seconds = self.total_seconds
        
        self.paused = True
        self.alarm_active = False
        self.alarm_flash_state = False
        self.start_timestamp = 0.0
        self.double_clicked = False
        
        # Sound file
        self.chime_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chime.wav")
        if not os.path.exists(self.chime_path):
            generate_chime(self.chime_path)
            
        self.init_ui()
        
        # Set up timers
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.timer_tick)
        
        self.alarm_timer = QTimer(self)
        self.alarm_timer.timeout.connect(self.alarm_flash_tick)
        
    def init_ui(self):
        # Frameless, Window, Always on Top, Tool window
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window | Qt.WindowType.Tool
        if self.config.get("always_on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        
        # Translucent background
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Size & position
        size = self.config.get("size", 150)
        self.setFixedSize(size, size)
        
        # Determine screen boundaries to prevent off-screen spawning
        screen = QApplication.primaryScreen().geometry()
        default_x = screen.width() - size - 50
        default_y = 100
        
        x = self.config.get("x", default_x)
        y = self.config.get("y", default_y)
        
        # Validate coordinates (e.g. if they are completely off-screen, reset to defaults)
        if x < -size or x > screen.width() or y < -size or y > screen.height():
            x = default_x
            y = default_y
            
        self.move(x, y)
        
        # Inline text editor for changing duration
        self.input_field = CustomLineEdit(self)
        self.input_field.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.input_field.hide()
        self.input_field.returnPressed.connect(self.apply_custom_time)
        
        # Context menu styling
        self.setStyleSheet("""
            QMenu {
                background-color: #1a1a1f;
                color: #e2e2e7;
                border: 1px solid #2c2c35;
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #00bcd4;
                color: #0f0f12;
            }
            QMenu::separator {
                height: 1px;
                background-color: #2c2c35;
                margin: 5px 8px;
            }
        """)
        
        self.setWindowTitle("countdown")
        
    def load_config(self):
        default_config = {
            "duration_seconds": 1500.0,
            "always_on_top": True,
            "x": 100,
            "y": 100,
            "size": 150
        }
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    self.config = json.load(f)
                    for k, v in default_config.items():
                        self.config.setdefault(k, v)
            except Exception:
                self.config = default_config
        else:
            self.config = default_config

    def save_config(self):
        try:
            self.config["duration_seconds"] = self.total_seconds
            self.config["always_on_top"] = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
            self.config["x"] = self.x()
            self.config["y"] = self.y()
            self.config["size"] = self.width()
            with open(self.config_path, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()
        iw = int(w * 0.55)
        ih = int(h * 0.22)
        self.input_field.setGeometry((w - iw) // 2, (h - ih) // 2, iw, ih)
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba(20, 20, 25, 240);
                color: #ffffff;
                border: 1.5px solid rgba(0, 240, 255, 180);
                border-radius: {max(3, int(w*0.03))}px;
                font-size: {max(10, int(w*0.12))}px;
                font-weight: bold;
                padding: 1px;
            }}
        """)

    # Dragging & click handling
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.drag_start_pos = event.globalPosition().toPoint()
            self.dragged = False
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            delta = event.globalPosition().toPoint() - self.drag_start_pos
            if delta.manhattanLength() > 5:
                self.dragged = True
                self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.double_clicked:
                self.double_clicked = False
                event.accept()
                return
                
            if not self.dragged:
                self.toggle_timer()
            else:
                self.save_config()
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked = True
            self.start_inline_edit()
            event.accept()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Scale widget size
            angle = event.angleDelta().y()
            scale = 1.1 if angle > 0 else 0.9
            new_size = int(self.width() * scale)
            if 80 <= new_size <= 400:
                self.setFixedSize(new_size, new_size)
                self.update()
                self.save_config()
            event.accept()
        else:
            # Adjust timer when paused
            if self.paused and not self.alarm_active and not self.input_field.isVisible():
                angle = event.angleDelta().y()
                delta = 60 if angle > 0 else -60
                new_time = max(60.0, self.total_seconds + delta)
                self.set_duration(new_time)
                event.accept()

    def toggle_timer(self):
        if self.input_field.isVisible():
            self.cancel_inline_edit()
            return
            
        if self.alarm_active:
            self.stop_alarm()
            self.reset_timer()
            return
            
        self.paused = not self.paused
        if not self.paused:
            self.start_timestamp = time.time() - (self.total_seconds - self.remaining_seconds)
            self.timer.start(100)
        else:
            self.timer.stop()
        self.update()
        self.save_config()

    def reset_timer(self):
        self.paused = True
        self.timer.stop()
        self.stop_alarm()
        self.remaining_seconds = self.total_seconds
        self.update()
        self.save_config()

    def set_duration(self, seconds):
        self.total_seconds = float(seconds)
        self.remaining_seconds = self.total_seconds
        if not self.paused:
            self.start_timestamp = time.time()
        self.update()
        self.save_config()

    def start_inline_edit(self):
        if not self.paused:
            self.toggle_timer()
            
        mins = self.total_seconds / 60
        if mins.is_integer():
            self.input_field.setText(str(int(mins)))
        else:
            self.input_field.setText(f"{mins:.1f}")
            
        self.input_field.show()
        self.input_field.setFocus()
        self.input_field.selectAll()

    def apply_custom_time(self):
        text = self.input_field.text().strip()
        try:
            text = text.replace(',', '.')
            minutes = float(text)
            if minutes <= 0:
                raise ValueError
            self.set_duration(minutes * 60)
        except ValueError:
            pass
        self.input_field.hide()
        self.update()

    def cancel_inline_edit(self):
        self.input_field.hide()
        self.update()

    def toggle_always_on_top(self):
        flags = self.windowFlags()
        if flags & Qt.WindowType.WindowStaysOnTopHint:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        else:
            flags |= Qt.WindowType.WindowStaysOnTopHint
            
        self.setWindowFlags(flags)
        self.show()
        self.save_config()

    # Time ticks
    def timer_tick(self):
        if self.paused or self.alarm_active:
            return
            
        elapsed = time.time() - self.start_timestamp
        rem = self.total_seconds - elapsed
        
        if rem <= 0:
            self.remaining_seconds = 0
            self.trigger_alarm()
        else:
            self.remaining_seconds = rem
            self.update()

    def trigger_alarm(self):
        self.timer.stop()
        self.alarm_active = True
        self.alarm_flash_state = True
        self.alarm_timer.start(500)
        
        play_sound(self.chime_path)
        send_notification("Таймер завершен!", f"Истекло время: {int(self.total_seconds // 60)} мин.")
        
        self.update()

    def alarm_flash_tick(self):
        self.alarm_flash_state = not self.alarm_flash_state
        self.update()

    def stop_alarm(self):
        self.alarm_timer.stop()
        self.alarm_active = False
        self.alarm_flash_state = False
        self.update()

    # Paint event
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w = self.width()
        h = self.height()
        center = QPoint(w // 2, h // 2)
        radius = min(w, h) // 2 - 4
        
        # 1. Background
        if self.alarm_active:
            if self.alarm_flash_state:
                bg_color = QColor(60, 20, 20, 225)
            else:
                bg_color = QColor(30, 10, 10, 210)
        else:
            bg_color = QColor(18, 18, 22, 205)
            
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1))
        painter.drawEllipse(center, radius, radius)
        
        # 2. Progress rings
        ring_width = max(3, int(w * 0.05))
        ring_radius = radius - ring_width
        
        # Track
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 12), ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawEllipse(center, ring_radius, ring_radius)
        
        # Active arc
        if self.total_seconds > 0:
            pct = self.remaining_seconds / self.total_seconds
        else:
            pct = 0.0
            
        if pct > 0:
            rect = QRectF(center.x() - ring_radius, center.y() - ring_radius, ring_radius * 2, ring_radius * 2)
            
            if self.alarm_active:
                pen_color = QColor(255, 45, 45)
            else:
                if self.paused:
                    pen_color = QColor(0, 160, 190, 130)
                else:
                    pen_color = QColor(0, 230, 255)
                    
            pen = QPen(pen_color, ring_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            
            start_angle = 90 * 16
            span_angle = int(-pct * 360 * 16)
            painter.drawArc(rect, start_angle, span_angle)
            
        # 3. Time Text
        if not self.input_field.isVisible():
            total_s = int(math.ceil(self.remaining_seconds))
            mins = total_s // 60
            secs = total_s % 60
            time_str = f"{mins:02d}:{secs:02d}"
            
            font_size = max(10, int(w * 0.18))
            font = QFont("sans-serif", font_size, QFont.Weight.Bold)
            painter.setFont(font)
            
            if self.alarm_active:
                text_color = QColor(255, 60, 60)
            elif self.paused:
                text_color = QColor(255, 255, 255, 130)
            else:
                text_color = QColor(255, 255, 255, 235)
                
            painter.setPen(text_color)
            text_rect = QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, time_str)

    # Context menu
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        play_pause_text = "Пауза" if not self.paused else "Старт"
        if self.alarm_active:
            play_pause_text = "Остановить сигнал"
            
        play_pause_action = menu.addAction(play_pause_text)
        play_pause_action.triggered.connect(self.toggle_timer)
        
        reset_action = menu.addAction("Сброс")
        reset_action.triggered.connect(self.reset_timer)
        
        menu.addSeparator()
        
        presets_menu = menu.addMenu("Предустановки")
        presets = [1, 3, 5, 10, 15, 25, 45, 60]
        for p in presets:
            action = presets_menu.addAction(f"{p} мин")
            action.triggered.connect(lambda checked=False, val=p: self.set_duration(val * 60))
            
        custom_action = menu.addAction("Ввести время...")
        custom_action.triggered.connect(self.start_inline_edit)
        
        menu.addSeparator()
        
        always_top_action = menu.addAction("Всегда поверх окон")
        always_top_action.setCheckable(True)
        is_always = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        always_top_action.setChecked(is_always)
        always_top_action.triggered.connect(self.toggle_always_on_top)
        
        menu.addSeparator()
        
        exit_action = menu.addAction("Выход")
        exit_action.triggered.connect(QApplication.instance().quit)
        
        # Use robust cursor position for menu display
        menu.exec(QCursor.pos())

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("countdown")
    app.setApplicationDisplayName("countdown")
    widget = CountdownWidget()
    widget.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
