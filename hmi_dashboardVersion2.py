import sys
import random
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget, QMessageBox
from PySide6.QtGui import QFont, QPixmap, QPainter, QPen, QColor, QIcon
from PySide6.QtCore import Qt, QTimer, QRect, QPoint, QSize
import math

class SpeedometerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.speed = 0  # Current speed
        self.max_speed = 160  # Maximum speed
        self.setFixedSize(300, 300)  # Increased size for the speedometer

    def set_speed(self, speed):
        self.speed = min(speed, self.max_speed)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            rect = self.rect()
            center = rect.center()
            radius = min(rect.width(), rect.height()) // 2 - 10

            # Fill the inside of the speedometer with black
            painter.setBrush(Qt.black)
            painter.setPen(Qt.black)
            painter.drawEllipse(center, radius, radius)

            # Draw ticks and labels
            for i in range(0, self.max_speed + 1, 5):
                angle = 225 - (270 * i / self.max_speed)
                radian = math.radians(angle)
                x1 = center.x() + (radius - 10) * math.cos(radian)
                y1 = center.y() - (radius - 10) * math.sin(radian)
                x2 = center.x() + radius * math.cos(radian)
                y2 = center.y() - radius * math.sin(radian)
                if i % 10 == 0:  # Bold every 2 ticks (every 10 units)
                    painter.setPen(QPen(Qt.white, 4))
                else:
                    painter.setPen(QPen(Qt.white, 2))
                painter.drawLine(int(x1), int(y1), int(x2), int(y2))
                if i % 20 == 0 or i == 0:  # Add MPH labels inside the speedometer, including 0 MPH
                    label_x = center.x() + (radius - 30) * math.cos(radian)
                    label_y = center.y() - (radius - 30) * math.sin(radian)
                    painter.setPen(Qt.white)
                    painter.setFont(QFont("Arial", 12))
                    painter.drawText(int(label_x) - 10, int(label_y) + 5, f"{i}")

            # Draw needle
            angle = 225 - (270 * self.speed / self.max_speed)
            radian = math.radians(angle)
            needle_length = radius - 20
            needle_x = center.x() + needle_length * math.cos(radian)
            needle_y = center.y() - needle_length * math.sin(radian)
            painter.setPen(QPen(Qt.red, 3))
            painter.drawLine(center, QPoint(int(needle_x), int(needle_y)))
        finally:
            painter.end()

class BatteryWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.charge = 0  # Battery charge percentage
        self.setFixedSize(300, 50)  # Fixed size for the battery widget

    def set_charge(self, charge):
        self.charge = min(charge, 100)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        
        # Draw the outer border of the battery
        painter.setPen(QPen(Qt.black, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))  # Draw the rectangle inside the border
        
        # Draw the battery bars
        bar_width = (rect.width() - 10) // 4  # Width of each bar
        bar_height = rect.height() - 10  # Height of each bar
        gap = 2  # Gap between bars
        
        for i in range(4):
            x = rect.left() + 5 + i * (bar_width + gap)
            y = rect.top() + 5
            if self.charge > i * 25:
                painter.setBrush(QColor(0, 255, 0))  # Green bars
            else:
                painter.setBrush(Qt.gray)  # Gray bars
            painter.drawRect(QRect(x, y, bar_width, bar_height))

class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Autonomous Vehicle HMI")
        self.setGeometry(100, 100, 800, 480)
        self.setFixedSize(800, 480)  # Fixed size to prevent elongation
        self.setStyleSheet("background-color: #555F61; color: white;")
        
        self.initUI()
        self.initTimer()
    
    def initUI(self):
        self.main_layout = QVBoxLayout()
        
        # Top bar with navigation buttons
        self.top_bar = QHBoxLayout()
        self.buttons = []
        screen_names = ["Dyno Mode", "PCM", "Errors", "🅿 Auto Park", "ACC"]
        for i, name in enumerate(screen_names):
            btn = QPushButton(name)
            btn.clicked.connect(lambda checked, index=i: self.switch_screen(index + 1))
            self.buttons.append(btn)
            self.top_bar.addWidget(btn)
        
        self.main_layout.addLayout(self.top_bar)
        
        # Create stacked widget for screens
        self.stacked_widget = QStackedWidget()
        
        # Main dashboard screen
        self.main_screen = QWidget()
        self.initMainScreen()
        self.stacked_widget.addWidget(self.main_screen)
        
        # Define each tab screen with unique content
        self.dyno_mode = self.create_dyno_screen()
        self.performance = self.create_performance_screen()
        self.errors = self.create_errors_screen()
        self.auto_park = self.create_auto_park_screen()
        self.cav_data = self.create_cav_data_screen()

        # Add tab screens to the stacked widget
        self.stacked_widget.addWidget(self.dyno_mode)
        self.stacked_widget.addWidget(self.performance)
        self.stacked_widget.addWidget(self.errors)
        self.stacked_widget.addWidget(self.auto_park)
        self.stacked_widget.addWidget(self.cav_data)

        self.main_layout.addWidget(self.stacked_widget)
        self.setLayout(self.main_layout)

    def showErrorDialog(self, error_message):
        error_dialog = QMessageBox(self)
        error_dialog.setWindowTitle("Error")
        error_dialog.setText(f"{error_message} error occurred. Consult manual to fix.")
        error_dialog.setStandardButtons(QMessageBox.Ok)
        error_dialog.exec_()

    def toggle_button_color(self):
        button = self.sender()
        if button.isChecked():
            button.setStyleSheet("background-color: green; color: white;")
        else:
            button.setStyleSheet("")

    def initMainScreen(self):
        main_layout = QVBoxLayout(self.main_screen)
        
        # Speed Labels
        self.labels_layout = QHBoxLayout()
        self.speed_label = QLabel("Speed: 0 mph")
        self.speed_label.setFont(QFont("Arial", 24))
        self.speed_label.setAlignment(Qt.AlignCenter)
        
        self.labels_layout.addStretch()
        self.labels_layout.addWidget(self.speed_label)
        self.labels_layout.addStretch()

        # Battery Label
        self.battery_layout = QHBoxLayout()
        self.battery_label = QLabel("Battery: 0%")
        self.battery_label.setFont(QFont("Arial", 24))
        self.battery_label.setAlignment(Qt.AlignRight)

        self.battery_layout.addStretch()
        self.battery_layout.addWidget(self.speed_label)
        
        self.labels_layout.addSpacing(300)  # Increased spacing between the labels
        self.labels_layout.addWidget(self.battery_label)
        self.labels_layout.addStretch()
        
        # Speedometer, buttons, and Battery Widget
        self.speedometer = SpeedometerWidget()
        self.battery_widget = BatteryWidget()

        self.controls_layout = QVBoxLayout()

        self.acc_button = QPushButton()
        self.acc_button.setIcon(QIcon(r"C:\Users\Tyler\Pictures\acc_icon.png")) 
        self.acc_button.setIconSize(QSize(100, 100))
        self.acc_button.setFixedSize(100, 100)
        self.acc_button.setCheckable(True)
        self.acc_button.clicked.connect(self.toggle_button_color)

        self.lane_assist_button = QPushButton()
        self.lane_assist_button.setIcon(QIcon(r"C:\Users\Tyler\Pictures\LKA_icon.png"))
        self.lane_assist_button.setIconSize(QSize(100,100))
        self.lane_assist_button.setFixedSize(100, 100)
        self.lane_assist_button.setCheckable(True)
        self.lane_assist_button.clicked.connect(self.toggle_button_color)

        self.placeholder_button_1 = QPushButton("Placeholder 1")
        self.placeholder_button_1.setFixedSize(100, 100)
        self.placeholder_button_1.setCheckable(True)
        self.placeholder_button_1.clicked.connect(self.toggle_button_color)

        self.placeholder_button_2 = QPushButton("Placeholder 2")
        self.placeholder_button_2.setFixedSize(100, 100)
        self.placeholder_button_2.setCheckable(True)
        self.placeholder_button_2.clicked.connect(self.toggle_button_color)

        self.controls_layout.addWidget(self.acc_button)
        self.controls_layout.addWidget(self.lane_assist_button)
        self.controls_layout.addWidget(self.placeholder_button_1)
        self.controls_layout.addWidget(self.placeholder_button_2)
        self.controls_layout.addStretch()
        
        self.gauges_layout = QHBoxLayout()
        self.gauges_layout.addStretch()
        self.gauges_layout.addWidget(self.speedometer, alignment=Qt.AlignCenter)
        self.gauges_layout.addLayout(self.controls_layout)
        self.gauges_layout.addWidget(self.battery_widget, alignment=Qt.AlignCenter)
        self.gauges_layout.addStretch()
        
        main_layout.addLayout(self.labels_layout)
        main_layout.addLayout(self.gauges_layout)

    def create_dyno_screen(self):
        dyno_screen = QWidget()
    
        # Create a horizontal layout for the label and button
        dyno_layout = QHBoxLayout()
        dyno_layout.addStretch()  # Pushes everything to the left
        dyno_label = QLabel("Activate Dyno Mode:")

        dyno_button = QPushButton()

        #dyno_label.setFont(QFont("Arial", 24))
        dyno_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)  # Vertically center, align left
        dyno_label.setAlignment(Qt.AlignVCenter)
        dyno_layout.addWidget(dyno_label, alignment=Qt.AlignVCenter)

        dyno_button.setIcon(QIcon(r"C:\Users\Tyler\Pictures\Off_icon.png"))
        dyno_button.setIconSize(QSize(200, 250))
        dyno_button.setFixedSize(200, 100)
        dyno_button.setCheckable(True)
        dyno_button.clicked.connect(self.toggle_dyno_icon)
        dyno_layout.addWidget(dyno_button, alignment=Qt.AlignLeft)

        # Create a vertical layout for the entire screen
        screen_layout = QVBoxLayout(dyno_screen)
        screen_layout.addLayout(dyno_layout)
    
        # Add the back button at the bottom
        back_button = QPushButton("Back to Main Dashboard")
        back_button.clicked.connect(lambda: self.switch_screen(0))
        screen_layout.addWidget(back_button, alignment=Qt.AlignBottom)
    
        dyno_screen.setLayout(screen_layout)
        return dyno_screen
    
    def toggle_dyno_icon(self): 
        button = self.sender() 
        if button.isChecked(): 
            button.setIcon(QIcon(r"C:\Users\Tyler\Pictures\On_icon.png")) 
            #CAN SIGNAL TO BE SENT
        else: 
            button.setIcon(QIcon(r"C:\Users\Tyler\Pictures\Off_Icon.png"))
            #CAN SIGNAL TO BE SENT
    
    def create_performance_screen(self):
        performance_screen = QWidget()
        performance_layout = QVBoxLayout(performance_screen)
        
        performance_label = QLabel("Performance Content")
        #performance_label.setFont(QFont("Arial", 24))
        performance_label.setAlignment(Qt.AlignCenter)
        performance_layout.addWidget(performance_label)
        
        back_button = QPushButton("Back to Main Dashboard")
        back_button.clicked.connect(lambda: self.switch_screen(0))
        performance_layout.addWidget(back_button, alignment=Qt.AlignBottom)
        
        return performance_screen
    
    def create_errors_screen(self):
        errors_screen = QWidget()
        errors_layout = QVBoxLayout(errors_screen)
        
        errors_label = QLabel("Errors Content")
        #errors_label.setFont(QFont("Arial", 24))
        errors_label.setAlignment(Qt.AlignCenter)
        errors_layout.addWidget(errors_label)
        
        back_button = QPushButton("Back to Main Dashboard")
        back_button.clicked.connect(lambda: self.switch_screen(0))
        errors_layout.addWidget(back_button, alignment=Qt.AlignBottom)
        
        return errors_screen
    
    def create_auto_park_screen(self):
        auto_park_screen = QWidget()
        auto_park_layout = QVBoxLayout(auto_park_screen)
        
        auto_park_label = QLabel("Auto Park Content")
        #auto_park_label.setFont(QFont("Arial", 24))
        auto_park_label.setAlignment(Qt.AlignCenter)
        auto_park_layout.addWidget(auto_park_label)
        
        back_button = QPushButton("Back to Main Dashboard")
        back_button.clicked.connect(lambda: self.switch_screen(0))
        auto_park_layout.addWidget(back_button, alignment=Qt.AlignBottom)
        
        return auto_park_screen
    
    def create_cav_data_screen(self):
        cav_data_screen = QWidget()
        cav_data_layout = QVBoxLayout(cav_data_screen)
        
        cav_data_label = QLabel("CAV Data Content")
        #cav_data_label.setFont(QFont("Arial", 24))
        cav_data_label.setAlignment(Qt.AlignCenter)
        cav_data_layout.addWidget(cav_data_label)
        
        back_button = QPushButton("Back to Main Dashboard")
        back_button.clicked.connect(lambda: self.switch_screen(0))
        cav_data_layout.addWidget(back_button, alignment=Qt.AlignBottom)
        
        return cav_data_screen
    
    def switch_screen(self, index):
        self.stacked_widget.setCurrentIndex(index)
    
    def initTimer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateData)
        self.timer.start(1000)  # Updates every second
    
    def updateData(self):
        # Simulate Speed
        speed = random.randint(0, 120) 
        self.speed_label.setText(f"Speed: {speed} mph") 
        self.speedometer.set_speed(speed) # Simulate Battery Gauge 
        battery = random.randint(0, 100) 
        self.battery_label.setText(f"Battery: {battery}%") 
        self.battery_widget.set_charge(battery) 
        # if random.choice([True, False]): # Randomly trigger error for demonstration 
        # # error_message = "Some" 
        # # self.showErrorDialog(error_message) 

if __name__ == "__main__": 
    app = QApplication(sys.argv) 

    globalFont = QFont("Arial",16)
    app.setFont(globalFont)

    window = Dashboard() 
    window.show() 
    sys.exit(app.exec())
