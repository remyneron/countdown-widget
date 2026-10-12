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

from PySide6.QtCore import Qt, QTimer, QPoint, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QPen, QBrush, QAction, QCursor, QPolygonF, QActionGroup
)
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
        self.total_seconds = float(self.config.get("duration_seconds", 1500.0))
        self.remaining_seconds = self.total_seconds
        
        self.paused = True
        self.alarm_active = False
        self.alarm_flash_state = False
        self.start_timestamp = 0.0
        self.double_clicked = False
        
        # Active skin: 'evangelion' or 'classic'
        self.skin = self.config.get("skin", "evangelion")
        
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
        
        # Size & position based on active skin
        screen = QApplication.primaryScreen().geometry()
        
        if self.skin == "evangelion":
            w = self.config.get("eva_width", 380)
            h = self.config.get("eva_height", 240)
            self.setFixedSize(w, h)
            default_x = screen.width() - w - 40
            default_y = 60
        else:
            size = self.config.get("size", 150)
            self.setFixedSize(size, size)
            default_x = screen.width() - size - 50
            default_y = 100
        
        x = self.config.get("x", default_x)
        y = self.config.get("y", default_y)
        
        # Validate coordinates (e.g. if they are completely off-screen, reset to defaults)
        cur_w = self.width()
        cur_h = self.height()
        if x < -cur_w or x > screen.width() or y < -cur_h or y > screen.height():
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
                background-color: #0c1017;
                color: #e2e8f0;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                padding: 6px 22px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #0284c7;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #1e293b;
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
            "size": 150,
            "eva_width": 380,
            "eva_height": 240,
            "skin": "evangelion"
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
            self.config["skin"] = self.skin
            if self.skin == "evangelion":
                self.config["eva_width"] = self.width()
                self.config["eva_height"] = self.height()
            else:
                self.config["size"] = self.width()
            with open(self.config_path, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception:
            pass

    def set_skin(self, new_skin):
        if self.skin == new_skin:
            return
        self.skin = new_skin
        if self.skin == "evangelion":
            w = self.config.get("eva_width", 380)
            h = self.config.get("eva_height", 240)
            self.setFixedSize(w, h)
        else:
            size = self.config.get("size", 150)
            self.setFixedSize(size, size)
            
        self.save_config()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()
        
        if self.skin == "evangelion":
            panel_x = w - max(124, int(w * 0.34))
            iw = int(panel_x - 30)
            ih = int(h * 0.38)
            ix = 16
            iy = int(h * 0.19)
            self.input_field.setGeometry(ix, iy, iw, ih)
            self.input_field.setStyleSheet(f"""
                QLineEdit {{
                    background-color: rgba(12, 16, 24, 245);
                    color: #ff3b30;
                    border: 2px solid #ff3b30;
                    border-radius: 4px;
                    font-size: {max(14, int(h * 0.22))}px;
                    font-weight: bold;
                    padding: 2px;
                }}
            """)
        else:
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
            
            if self.skin == "evangelion":
                new_w = int(self.width() * scale)
                new_h = int(self.height() * scale)
                if 220 <= new_w <= 700 and 140 <= new_h <= 450:
                    self.setFixedSize(new_w, new_h)
                    self.update()
                    self.save_config()
            else:
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
            # 33ms interval for Eva skin for fluid centiseconds, 100ms for classic skin
            tick_interval = 33 if self.skin == "evangelion" else 100
            self.timer.start(tick_interval)
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

    # 7-Segment digit drawing
    def draw_7segment_digit(self, painter, x, y, w, h, digit, lit_color, unlit_color, slant_deg=5):
        segments_map = {
            '0': (1, 1, 1, 1, 1, 1, 0),
            '1': (0, 1, 1, 0, 0, 0, 0),
            '2': (1, 1, 0, 1, 1, 0, 1),
            '3': (1, 1, 1, 1, 0, 0, 1),
            '4': (0, 1, 1, 0, 0, 1, 1),
            '5': (1, 0, 1, 1, 0, 1, 1),
            '6': (1, 0, 1, 1, 1, 1, 1),
            '7': (1, 1, 1, 0, 0, 0, 0),
            '8': (1, 1, 1, 1, 1, 1, 1),
            '9': (1, 1, 1, 1, 0, 1, 1),
            ' ': (0, 0, 0, 0, 0, 0, 0),
            '-': (0, 0, 0, 0, 0, 0, 1)
        }
        
        seg_states = segments_map.get(str(digit), (0, 0, 0, 0, 0, 0, 0))
        
        painter.save()
        painter.translate(x, y)
        
        # Shear for italic slant
        shear_val = math.tan(math.radians(-slant_deg))
        painter.shear(shear_val, 0)
        
        t = w * 0.235 # thickness
        gap = w * 0.04 # gap
        half_h = h / 2.0
        
        # Horizontals
        def horiz_poly(py):
            poly = QPolygonF()
            poly.append(QPointF(gap + t * 0.5, py))
            poly.append(QPointF(w - gap - t * 0.5, py))
            poly.append(QPointF(w - gap - t, py + t * 0.5))
            poly.append(QPointF(w - gap - t * 0.5, py + t))
            poly.append(QPointF(gap + t * 0.5, py + t))
            poly.append(QPointF(gap + t, py + t * 0.5))
            return poly

        def mid_horiz_poly(py):
            poly = QPolygonF()
            poly.append(QPointF(gap + t * 0.6, py))
            poly.append(QPointF(w - gap - t * 0.6, py))
            poly.append(QPointF(w - gap - t * 0.1, py + t * 0.5))
            poly.append(QPointF(w - gap - t * 0.6, py + t))
            poly.append(QPointF(gap + t * 0.6, py + t))
            poly.append(QPointF(gap + t * 0.1, py + t * 0.5))
            return poly

        def vert_poly(px, py_top, py_bot):
            poly = QPolygonF()
            poly.append(QPointF(px, py_top + t * 0.5))
            poly.append(QPointF(px + t * 0.5, py_top))
            poly.append(QPointF(px + t, py_top + t * 0.5))
            poly.append(QPointF(px + t, py_bot - t * 0.5))
            poly.append(QPointF(px + t * 0.5, py_bot))
            poly.append(QPointF(px, py_bot - t * 0.5))
            return poly

        poly_a = horiz_poly(0)
        poly_b = vert_poly(w - t, gap, half_h - gap * 0.5)
        poly_c = vert_poly(w - t, half_h + gap * 0.5, h - gap)
        poly_d = horiz_poly(h - t)
        poly_e = vert_poly(0, half_h + gap * 0.5, h - gap)
        poly_f = vert_poly(0, gap, half_h - gap * 0.5)
        poly_g = mid_horiz_poly(half_h - t * 0.5)
        
        polys = [poly_a, poly_b, poly_c, poly_d, poly_e, poly_f, poly_g]
        
        painter.setPen(Qt.PenStyle.NoPen)
        for state, poly in zip(seg_states, polys):
            painter.setBrush(QBrush(lit_color if state else unlit_color))
            painter.drawPolygon(poly)
            
        painter.restore()

    # Paint event router
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self.skin == "evangelion":
            self.paint_evangelion_skin(painter)
        else:
            self.paint_classic_skin(painter)

    # 1. EVANGELION SKIN
    def paint_evangelion_skin(self, painter):
        w = self.width()
        h = self.height()
        
        is_running = (not self.paused and not self.alarm_active)
        
        # Background & border colors
        if self.alarm_active:
            if self.alarm_flash_state:
                bg_col = QColor(60, 15, 15, 245)
                outer_border_col = QColor(255, 30, 30)
                hud_line_col = QColor(255, 50, 50)
            else:
                bg_col = QColor(25, 8, 8, 240)
                outer_border_col = QColor(160, 20, 20)
                hud_line_col = QColor(180, 30, 30)
        else:
            bg_col = QColor(10, 13, 20, 246)
            outer_border_col = QColor(38, 75, 108)
            hud_line_col = QColor(36, 75, 110)
            
        bg_rect = QRectF(0, 0, w, h)
        painter.setBrush(QBrush(bg_col))
        painter.setPen(QPen(outer_border_col, 1.5))
        painter.drawRect(bg_rect.adjusted(2, 2, -2, -2))
        
        # Inner framing line
        painter.setPen(QPen(QColor(outer_border_col.red()//2, outer_border_col.green()//2, outer_border_col.blue()//2), 1.0))
        painter.drawRect(bg_rect.adjusted(5, 5, -5, -5))
        
        # Ruler tick marks along top
        ruler_y = max(6, int(h * 0.04))
        tick_step = max(8, int(w * 0.026))
        for tx in range(14, w - 14, tick_step):
            painter.setPen(QPen(hud_line_col, 1))
            painter.drawLine(tx, ruler_y, tx, ruler_y + (4 if tx % (tick_step * 3) == 0 else 2))
            
        # Right panel divider: 34% width for the right column
        panel_x = w - max(124, int(w * 0.34))
        painter.setPen(QPen(hud_line_col, 1.5))
        painter.drawLine(panel_x, 10, panel_x, h - 10)
        
        # Right column box metrics (INTERNAL, MAIN ENERGY, EXTERNAL)
        rx = panel_x + 6
        rw = w - rx - 10
        box1_y = 10
        box1_h = int((h - 32) * 0.38)
        box2_y = box1_y + box1_h + 6
        box2_h = int((h - 32) * 0.24)
        box3_y = box2_y + box2_h + 6
        box3_h = h - 10 - box3_y
        
        # Top Header
        font_size_jp = max(8, int(h * 0.044))
        font_jp = QFont("Noto Serif CJK JP", font_size_jp, QFont.Weight.Bold)
        fm_jp = QFontMetrics(font_jp)
        jp_text = "活動限界まで"
        jp_w = fm_jp.horizontalAdvance(jp_text)
        
        header_y = max(18, int(h * 0.11))
        
        if self.alarm_active:
            painter.setFont(font_jp)
            painter.setPen(QColor(255, 40, 40))
            painter.drawText(14, header_y, "非常事態 EMERGENCY ALERT")
        else:
            painter.setFont(font_jp)
            painter.setPen(QColor(255, 60, 60) if is_running else QColor(230, 145, 45))
            painter.drawText(14, header_y, jp_text)
            
            # English "ACTIVE TIME REMAINING": placed strictly after Japanese text with clear gap
            gap = 8
            text_x = 14 + jp_w + gap
            avail_en_w = panel_x - text_x - 8
            
            font_size_en = max(6, int(h * 0.038))
            font_en = QFont("sans-serif", font_size_en, QFont.Weight.Bold)
            while QFontMetrics(font_en).horizontalAdvance("ACTIVE TIME REMAINING") > avail_en_w and font_en.pointSize() > 5:
                font_en.setPointSize(font_en.pointSize() - 1)
                
            painter.setFont(font_en)
            painter.setPen(QColor(225, 230, 240))
            painter.drawText(text_x, header_y, "ACTIVE TIME REMAINING")
            
            painter.setFont(QFont("Noto Serif CJK JP", max(6, int(h * 0.032))))
            painter.setPen(QColor(160, 175, 195))
            painter.drawText(14, header_y + int(h * 0.055), "あと")

        # Main Timer Display
        if not self.input_field.isVisible():
            total_s = max(0.0, self.remaining_seconds)
            mins = int(total_s // 60)
            secs = int(total_s % 60)
            if self.paused or self.alarm_active:
                centis = 0
            else:
                centis = int((total_s - int(total_s)) * 100)
                
            m_str = f"{mins}"
            s_str = f"{secs:02d}"
            c_str = f"{centis:02d}"
            
            if self.alarm_active:
                timer_lit = QColor(255, 30, 30) if self.alarm_flash_state else QColor(100, 20, 20)
                timer_unlit = QColor(40, 10, 10)
            else:
                timer_lit = QColor(255, 40, 40)
                timer_unlit = QColor(36, 10, 10)
                
            # Dynamic sizing for digits
            num_chars = len(m_str) + len(s_str) + len(c_str)
            colon_count = 2
            avail_w = panel_x - 24
            
            digit_w = int(avail_w / (num_chars + colon_count * 0.4 + 1.2))
            digit_h = int(h * 0.35)
            digit_gap = max(2, int(digit_w * 0.12))
            colon_w = max(6, int(digit_w * 0.38))
            
            digit_y = int(h * 0.19)
            cur_x = 14
            
            # Minutes
            for ch in m_str:
                self.draw_7segment_digit(painter, cur_x, digit_y, digit_w, digit_h, ch, timer_lit, timer_unlit)
                cur_x += digit_w + digit_gap
                
            # Colon 1
            painter.setBrush(QBrush(timer_lit))
            painter.setPen(Qt.PenStyle.NoPen)
            dot_s = max(3, int(digit_w * 0.22))
            dot_x = cur_x + (colon_w - dot_s) * 0.5
            painter.drawRect(QRectF(dot_x, digit_y + digit_h * 0.3 - dot_s * 0.5, dot_s, dot_s))
            painter.drawRect(QRectF(dot_x, digit_y + digit_h * 0.68 - dot_s * 0.5, dot_s, dot_s))
            cur_x += colon_w + digit_gap
            
            # Seconds
            for ch in s_str:
                self.draw_7segment_digit(painter, cur_x, digit_y, digit_w, digit_h, ch, timer_lit, timer_unlit)
                cur_x += digit_w + digit_gap
                
            # Colon 2
            dot_x2 = cur_x + (colon_w - dot_s) * 0.5
            painter.drawRect(QRectF(dot_x2, digit_y + digit_h * 0.3 - dot_s * 0.5, dot_s, dot_s))
            painter.drawRect(QRectF(dot_x2, digit_y + digit_h * 0.68 - dot_s * 0.5, dot_s, dot_s))
            cur_x += colon_w + digit_gap
            
            # Centiseconds
            for ch in c_str:
                self.draw_7segment_digit(painter, cur_x, digit_y, digit_w, digit_h, ch, timer_lit, timer_unlit)
                cur_x += digit_w + digit_gap

        # Bottom status indicators row: [STOP] [SLOW] [NORMAL] [RACING]
        # Aligned with External block grid (starts at box3_y) and occupying ~half of its vertical height
        modes = [("STOP", "やめる"), ("SLOW", "スロー"), ("NORMAL", "正常"), ("RACING", "レース")]
        btn_y = box3_y
        gap_under_btn = 5
        btn_h = int((box3_h - gap_under_btn) * 0.46)
        btn_gap = max(3, int(w * 0.012))
        btn_w = (panel_x - 26 - (len(modes) - 1) * btn_gap) / len(modes)
        bx = 14
        active_mode = "RACING" if is_running else "STOP"
        
        sample_longest = "NORMAL"
        f_btn_en = QFont("sans-serif", 8, QFont.Weight.Bold)
        while QFontMetrics(f_btn_en).horizontalAdvance(sample_longest) > btn_w - 6 and f_btn_en.pointSize() > 5:
            f_btn_en.setPointSize(f_btn_en.pointSize() - 1)
            
        f_btn_jp = QFont("Noto Serif CJK JP", max(5, int(f_btn_en.pointSize() * 0.8)))
        
        for en_text, jp_text in modes:
            is_act = (en_text == active_mode)
            box_rect = QRectF(bx, btn_y, btn_w, btn_h)
            if is_act:
                if en_text in ("STOP", "RACING"):
                    box_bg = QColor(48, 16, 16, 235)
                    box_border = QColor(245, 50, 50)
                    text_col = QColor(255, 75, 75)
                else:
                    box_bg = QColor(16, 42, 58, 235)
                    box_border = QColor(0, 220, 255)
                    text_col = QColor(0, 240, 255)
            else:
                box_bg = QColor(12, 16, 24, 180)
                box_border = QColor(28, 50, 72)
                text_col = QColor(75, 100, 125)
                
            painter.setBrush(QBrush(box_bg))
            painter.setPen(QPen(box_border, 1.2 if is_act else 1.0))
            painter.drawRect(box_rect)
            
            # English text
            painter.setFont(f_btn_en)
            painter.setPen(text_col)
            painter.drawText(QRectF(bx, btn_y + 2, btn_w, btn_h * 0.46), Qt.AlignmentFlag.AlignCenter, en_text)
            
            # Japanese subtext
            painter.setFont(f_btn_jp)
            painter.setPen(text_col if is_act else QColor(65, 85, 110))
            painter.drawText(QRectF(bx, btn_y + btn_h * 0.48, btn_w, btn_h * 0.44), Qt.AlignmentFlag.AlignCenter, jp_text)
            
            # Underline bar for active indicator
            if is_act:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(text_col))
                painter.drawRect(QRectF(bx + 4, btn_y + btn_h - 3, btn_w - 8, 2))
                
            bx += btn_w + btn_gap

        # EVA GRAPHIC PANEL: AUXILIARY TELEMETRY & POWER GAUGE
        # Strictly constrained to end at (box3_y + box3_h = h - 10), matching External block bottom
        gfx_y = btn_y + btn_h + gap_under_btn
        gfx_h = (box3_y + box3_h) - gfx_y
        if gfx_h > 12:
            gfx_rect = QRectF(14, gfx_y, panel_x - 26, gfx_h)
            if is_running:
                gfx_bg = QColor(22, 12, 14, 220)
                gfx_border = QColor(150, 40, 40)
                accent_col = QColor(255, 60, 60)
                sub_text_col = QColor(225, 95, 95)
                seg_lit_col = QColor(255, 50, 50)
                seg_unlit_col = QColor(48, 16, 16)
            else:
                gfx_bg = QColor(10, 16, 25, 205)
                gfx_border = QColor(32, 60, 90)
                accent_col = QColor(0, 220, 250)
                sub_text_col = QColor(110, 150, 185)
                seg_lit_col = QColor(0, 225, 250)
                seg_unlit_col = QColor(16, 28, 42)
                
            painter.setBrush(QBrush(gfx_bg))
            painter.setPen(QPen(gfx_border, 1.2))
            painter.drawRect(gfx_rect)
            
            # Corner accents
            c_len = min(6, int(gfx_h * 0.22))
            painter.setPen(QPen(accent_col, 1.5))
            painter.drawLine(int(gfx_rect.left()), int(gfx_rect.top()), int(gfx_rect.left() + c_len), int(gfx_rect.top()))
            painter.drawLine(int(gfx_rect.left()), int(gfx_rect.top()), int(gfx_rect.left()), int(gfx_rect.top() + c_len))
            painter.drawLine(int(gfx_rect.right()), int(gfx_rect.bottom()), int(gfx_rect.right() - c_len), int(gfx_rect.bottom()))
            painter.drawLine(int(gfx_rect.right()), int(gfx_rect.bottom()), int(gfx_rect.right()), int(gfx_rect.bottom() - c_len))
            
            # Top subline: [STATUS // CH-01] on left, [PERCENT] on right
            inner_x = 20
            inner_w = int(panel_x - 38)
            
            pct_val = max(0.0, min(1.0, self.remaining_seconds / self.total_seconds if self.total_seconds > 0 else 0))
            pct_int = int(pct_val * 100)
            
            f_tech = QFont("sans-serif", max(5, int(gfx_h * 0.20)), QFont.Weight.Bold)
            painter.setFont(f_tech)
            painter.setPen(sub_text_col)
            label_text = "NERV CH-01 // BATTERY DISCHARGE" if is_running else "NERV CH-01 // EXTERNAL POWER LINK"
            painter.drawText(QRectF(inner_x, gfx_y + 2, inner_w * 0.72, gfx_h * 0.38), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label_text)
            
            painter.setPen(accent_col)
            painter.drawText(QRectF(inner_x + inner_w * 0.72, gfx_y + 2, inner_w * 0.28, gfx_h * 0.38), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{pct_int}%")
            
            # Middle: Segmented Power / Discharge Bar
            bar_y = gfx_y + int(gfx_h * 0.44)
            bar_h = max(3, int(gfx_h * 0.22))
            num_segs = 24
            seg_gap = 2
            seg_w = (inner_w - (num_segs - 1) * seg_gap) / num_segs
            lit_segs = int(round(pct_val * num_segs))
            
            painter.setPen(Qt.PenStyle.NoPen)
            for si in range(num_segs):
                sx = inner_x + si * (seg_w + seg_gap)
                painter.setBrush(QBrush(seg_lit_col if si < lit_segs else seg_unlit_col))
                painter.drawRect(QRectF(sx, bar_y, seg_w, bar_h))
                
            # Bottom subline: Japanese telemetry
            f_sub_jp = QFont("Noto Serif CJK JP", max(4, int(gfx_h * 0.16)))
            painter.setFont(f_sub_jp)
            painter.setPen(QColor(140, 165, 190) if not is_running else QColor(200, 100, 100))
            sub_jp_text = "主電源断線 // 内部電池駆動中" if is_running else "外部電源接続 // 待機電力維持"
            painter.drawText(QRectF(inner_x, gfx_y + int(gfx_h * 0.70), inner_w, gfx_h * 0.28), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sub_jp_text)

        # RIGHT COLUMN: INTERNAL, MAIN ENERGY, EXTERNAL
        
        # Hazard stripes area: 30% of rw, placed at the far right
        hazard_w = max(24, int(rw * 0.30))
        hazard_x = rx + rw - hazard_w - 4
        # Text area: strictly between rx + 6 and hazard_x - 4
        text_w = hazard_x - (rx + 6) - 4
        
        # 1. TOP BOX: INTERNAL (Active when running)
        int_active = is_running
        if int_active:
            int_bg = QColor(48, 14, 14, 240)
            int_border = QColor(255, 45, 45)
            int_text_col = QColor(255, 55, 55)
            stripe_col = QColor(255, 45, 45)
        else:
            int_bg = QColor(14, 16, 24, 180)
            int_border = QColor(36, 55, 78)
            int_text_col = QColor(65, 85, 110)
            stripe_col = QColor(36, 55, 78)
            
        painter.setBrush(QBrush(int_bg))
        painter.setPen(QPen(int_border, 1.5))
        int_rect = QRectF(rx, box1_y, rw, box1_h)
        painter.drawRect(int_rect)
        
        # Kanji 内部
        painter.setFont(QFont("Noto Serif CJK JP", max(9, int(box1_h * 0.34)), QFont.Weight.Bold))
        painter.setPen(int_text_col)
        painter.drawText(QRectF(rx + 6, box1_y + 4, text_w, int(box1_h * 0.5)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "内部")
        
        # English INTERNAL: auto-fitted so it never touches stripes
        f_int = QFont("sans-serif", max(6, int(box1_h * 0.17)), QFont.Weight.Bold)
        while QFontMetrics(f_int).horizontalAdvance("INTERNAL") > text_w and f_int.pointSize() > 5:
            f_int.setPointSize(f_int.pointSize() - 1)
        painter.setFont(f_int)
        painter.drawText(QRectF(rx + 6, box1_y + int(box1_h * 0.5), text_w, int(box1_h * 0.45)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "INTERNAL")
        
        # Hazard stripes on the right of INTERNAL box
        painter.setClipRect(QRectF(hazard_x, box1_y + 3, hazard_w, box1_h - 6))
        painter.setPen(QPen(stripe_col, max(2.5, box1_h * 0.05)))
        s_step = max(6, int(box1_h * 0.14))
        for sx in range(int(hazard_x - box1_h), int(hazard_x + hazard_w + box1_h), s_step):
            painter.drawLine(sx, box1_y + box1_h, sx + int(box1_h * 0.4), box1_y)
        painter.setClipping(False)
        
        # 2. MIDDLE BOX: MAIN ENERGY SUPPLY SYSTEM (Highlighted in red when running on internal)
        if int_active:
            box2_bg = QColor(48, 14, 14, 240)
            box2_border = QColor(255, 45, 45)
            box2_text_jp = QColor(255, 65, 65)
            box2_text_en = QColor(255, 95, 95)
        else:
            box2_bg = QColor(14, 20, 30, 210)
            box2_border = QColor(36, 70, 102)
            box2_text_jp = QColor(175, 200, 225)
            box2_text_en = QColor(135, 170, 205)

        painter.setBrush(QBrush(box2_bg))
        painter.setPen(QPen(box2_border, 1.5 if int_active else 1.2))
        box2_rect = QRectF(rx, box2_y, rw, box2_h)
        painter.drawRect(box2_rect)
        
        f_mid_jp = QFont("Noto Serif CJK JP", max(6, int(box2_h * 0.2)), QFont.Weight.Bold)
        while QFontMetrics(f_mid_jp).horizontalAdvance("主電源供給システム") > rw - 8 and f_mid_jp.pointSize() > 5:
            f_mid_jp.setPointSize(f_mid_jp.pointSize() - 1)
        painter.setFont(f_mid_jp)
        painter.setPen(box2_text_jp)
        painter.drawText(QRectF(rx + 4, box2_y + 2, rw - 8, int(box2_h * 0.4)), Qt.AlignmentFlag.AlignCenter, "主電源供給システム")
        
        f_mid_en = QFont("sans-serif", max(5, int(box2_h * 0.16)), QFont.Weight.Bold)
        painter.setFont(f_mid_en)
        painter.setPen(box2_text_en)
        painter.drawText(QRectF(rx + 4, box2_y + int(box2_h * 0.4), rw - 8, int(box2_h * 0.28)), Qt.AlignmentFlag.AlignCenter, "MAIN ENERGY")
        painter.drawText(QRectF(rx + 4, box2_y + int(box2_h * 0.68), rw - 8, int(box2_h * 0.28)), Qt.AlignmentFlag.AlignCenter, "SUPPLY SYSTEM")
        
        # 3. BOTTOM BOX: EXTERNAL (Active when paused/stopped)
        ext_active = not is_running
        if ext_active:
            ext_bg = QColor(14, 38, 54, 240)
            ext_border = QColor(0, 230, 255)
            ext_text_col = QColor(0, 235, 255)
            stripe_col2 = QColor(0, 230, 255)
        else:
            ext_bg = QColor(14, 16, 24, 180)
            ext_border = QColor(36, 55, 78)
            ext_text_col = QColor(65, 85, 110)
            stripe_col2 = QColor(36, 55, 78)
            
        painter.setBrush(QBrush(ext_bg))
        painter.setPen(QPen(ext_border, 1.5))
        ext_rect = QRectF(rx, box3_y, rw, box3_h)
        painter.drawRect(ext_rect)
        
        # Kanji 外部
        painter.setFont(QFont("Noto Serif CJK JP", max(9, int(box3_h * 0.34)), QFont.Weight.Bold))
        painter.setPen(ext_text_col)
        painter.drawText(QRectF(rx + 6, box3_y + 4, text_w, int(box3_h * 0.5)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "外部")
        
        # English EXTERNAL: auto-fitted so it never touches stripes
        f_ext = QFont("sans-serif", max(6, int(box3_h * 0.17)), QFont.Weight.Bold)
        while QFontMetrics(f_ext).horizontalAdvance("EXTERNAL") > text_w and f_ext.pointSize() > 5:
            f_ext.setPointSize(f_ext.pointSize() - 1)
        painter.setFont(f_ext)
        painter.drawText(QRectF(rx + 6, box3_y + int(box3_h * 0.5), text_w, int(box3_h * 0.45)), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "EXTERNAL")
        
        # Hazard stripes on right of EXTERNAL box
        painter.setClipRect(QRectF(hazard_x, box3_y + 3, hazard_w, box3_h - 6))
        painter.setPen(QPen(stripe_col2, max(2.5, box3_h * 0.05)))
        for sx in range(int(hazard_x - box3_h), int(hazard_x + hazard_w + box3_h), s_step):
            painter.drawLine(sx, box3_y + box3_h, sx + int(box3_h * 0.4), box3_y)
        painter.setClipping(False)

    # 2. CLASSIC MINIMALIST CIRCLE SKIN
    def paint_classic_skin(self, painter):
        w = self.width()
        h = self.height()
        center = QPoint(w // 2, h // 2)
        radius = min(w, h) // 2 - 4
        
        # Background
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
        
        # Progress rings
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
            
        # Time Text
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
        
        # Skin switcher menu
        skins_menu = menu.addMenu("Скин оформления")
        skin_group = QActionGroup(self)
        
        eva_action = skins_menu.addAction("Евангелион (NERV HUD)")
        eva_action.setCheckable(True)
        eva_action.setChecked(self.skin == "evangelion")
        eva_action.triggered.connect(lambda: self.set_skin("evangelion"))
        skin_group.addAction(eva_action)
        
        classic_action = skins_menu.addAction("Минималистичный (круг)")
        classic_action.setCheckable(True)
        classic_action.setChecked(self.skin == "classic")
        classic_action.triggered.connect(lambda: self.set_skin("classic"))
        skin_group.addAction(classic_action)
        
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
