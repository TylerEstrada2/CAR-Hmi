import sys
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget, QMessageBox
from PySide6.QtGui import QFont, QPainter, QPen, QColor, QPixmap
from PySide6.QtCore import Qt, QRect
import can
import cantools
import threading

# Load DBC file
db = cantools.database.load_file(r"C:\SchoolBooks\Code\CAN_14 1.dbc")

# Define the signals to display on the PCM tab
PCM_SIGNALS = [
    'F_Mot_Power', 'R_Mot_Power', 'RESS_SOC', 'RESS_Temp',
    'F_MotTmp', 'R_MotTmp', 'F_InvTmp', 'R_InvTmp', 'Master_Warning',
    'Vehicle_ahead', 'CACC_light', 'CACC_mileage', 'Dyno_mode_req_sim',
    'Headway_time', 'Sim_active', 'Target_dist', 'UDP_data_rx'
]

# Define CACC states and their corresponding colors
CACC_STATES = {
    1: ("Off", "gray"),  # SHOULD BE BOTH 1 and 5
    2: ("Active", "green"),
    3: ("Acceleration Override, standby", "blue"),
    4: ("Brake Override, Cancel", "white"),
    5: ("Off", "gray"),
    7: ("Fault", "red"),  # Doesn't have a signal yet
}

def init_can_bus():
    try:
        # Use 'virtual' interface for testing
        bus = can.interface.Bus(channel='virtual_channel', interface='virtual', bitrate=500000)
        return bus
    except Exception as e:
        print(f"CAN Initialization Error: {e}")
        return None

def decode_message(message):
    try:
        return db.decode_message(message.arbitration_id, message.data)
    except Exception as e:
        print(f"Error decoding message: {e}")
        return {}

class SignalWidgetManager(QWidget):
    def __init__(self, signals):
        super().__init__()
        self.widgets = {}
        self.initUI(signals)

    def initUI(self, signals):
        layout = QVBoxLayout()
        self.setLayout(layout)
        for signal in signals:
            # Initialize labels with 0 instead of N/A
            label = QLabel(f"{signal}: 0")
            label.setFont(QFont("Arial", 14, QFont.Bold))
            layout.addWidget(label)
            self.widgets[signal] = label

    def update_signal(self, signal_name, value):
        if signal_name in self.widgets:
            self.widgets[signal_name].setText(f"{signal_name}: {value}")

    def clear_signals(self):
        for label in self.widgets.values():
            label.setText("0")  # Reset to 0 instead of N/A

class VehicleAheadIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        layout = QHBoxLayout()
        self.setLayout(layout)

        # Placeholder for the vehicle ahead icon
        self.icon_label = QLabel()
        icon_pixmap = QPixmap(r"C:\Users\Tyler\Pictures\Screenshots\VehicleAheadIndicator.png")  # Replace with your icon path
        icon_pixmap = icon_pixmap.scaled(100, 100)
        self.icon_label.setPixmap(icon_pixmap)
        
        # Set a fixed size for the icon label to ensure it doesn't stretch
        self.icon_label.setFixedSize(100, 100)
        layout.addWidget(self.icon_label)

        # Label to display the distance to the vehicle ahead (left)
        self.distance_label = QLabel("Distance: N/A")
        self.distance_label.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(self.distance_label, alignment=Qt.AlignCenter)

        # Label to display the headway in seconds (right)
        self.headway_label = QLabel("Headway: N/A")
        self.headway_label.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(self.headway_label, alignment=Qt.AlignLeft)

    def update_distance(self, distance):
        if distance is not None:
            self.distance_label.setText(f"Distance: {distance} m")
        else:
            self.distance_label.setText("Distance: N/A")

    def update_headway(self, headway):
        if headway is not None:
            self.headway_label.setText(f"Headway: {headway} s")
            self.icon_label.setStyleSheet("background-color: green;")
        else:
            self.headway_label.setText("Headway: N/A")
            self.icon_label.setStyleSheet("background-color: gray;")

class CACCIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.state = 0  # Initial state is Off
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Load the image for the CACC indicator
        self.icon_label = QLabel()
        self.icon_pixmap = QPixmap(r"C:\Users\Tyler\Pictures\CACCIndicator_transparent.png")  # Replace with your image path
        self.icon_pixmap = self.icon_pixmap.scaled(100, 100, Qt.KeepAspectRatio)  # Resize the image
        self.icon_label.setPixmap(self.icon_pixmap)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedSize(100, 100)  # Set a fixed size for the icon label
        self.update_color()
        layout.addWidget(self.icon_label)

    def update_color(self):
        _, color = CACC_STATES.get(self.state, ("Unknown", "gray"))
        self.icon_label.setStyleSheet(f"background-color: {color}; border-radius: 10px;")

    def set_state(self, state):
        self.state = state
        self.update_color()

class BatteryWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.charge = 0  # Battery charge percentage
        self.setFixedSize(300, 50)  # Fixed size for the battery widget

    def set_charge(self, charge):
        self.charge = min(charge, 100)  # Ensure charge doesn't exceed 100%
        self.update()  # Trigger a repaint

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

        # Extract signal names and units from the DBC file
        self.signals = []
        self.signal_units = {}
        for message in db.messages:
            for signal in message.signals:
                self.signals.append(signal.name)
                self.signal_units[signal.name] = signal.unit or ""  # Use empty string if no unit is defined

        self.signal_values = {signal: "-" for signal in self.signals}

        self.bus = self.init_can_bus()
        
        self.initUI()
        threading.Thread(target=self.listen_can_messages, daemon=True).start()
    
    def init_can_bus(self):
        try:
            # Use 'virtual' interface for testing
            bus = can.interface.Bus(channel='virtual_channel', interface='virtual', bitrate=500000)
            return bus
        except Exception as e:
            self.showErrorDialog(f"CAN Initialization Error: {e}")
            sys.exit(1)

    def listen_can_messages(self):
        """Listen for CAN messages and update the UI accordingly."""
        while True:
            try:
                msg = self.bus.recv(timeout=0.1)  # Wait for CAN messages
                if msg:
                    decoded = db.decode_message(msg.arbitration_id, msg.data)
                    for signal in self.signals:
                        if signal in decoded:
                            self.signal_values[signal] = decoded[signal]
                            if signal == 'RESS_SOC':
                                self.update_battery_display(decoded[signal])
                            elif signal == 'Sim_UDP_Received':
                                self.update_sim_udp_label(decoded[signal])
                            elif signal == 'Dyno_Mode_Request':
                                self.update_dyno_request_label(decoded[signal])
                            elif signal == 'Sim_Active':
                                self.update_sim_active_label(decoded[signal])
                            elif signal == 'Vehicle_Ahead_Distance':
                                self.update_Target_dist(decoded[signal])
                            elif signal == 'Vehicle_Ahead_Headway':
                                self.update_vehicle_ahead_headway(decoded[signal])
                            elif signal == 'CACC_State':
                                self.update_cacc_indicator(decoded[signal])
                            elif signal == 'Vehicle_ahead':
                                self.update_vehicle_ahead_indicator(decoded[signal])
                            elif signal == 'CACC_light':
                                self.update_cacc_light(decoded[signal])
                            elif signal == 'CACC_mileage':
                                self.update_cacc_mileage(decoded[signal])
                            elif signal == 'Headway_time':
                                self.update_headway_time(decoded[signal])
                            elif signal == 'Sim_active':
                                self.update_sim_active(decoded[signal])
                            elif signal == 'Target_dist':
                                self.update_target_dist(decoded[signal])
                            elif signal == 'UDP_data_rx':
                                self.update_udp_data_rx(decoded[signal])
            except Exception as e:
                print(f"Error processing CAN message: {e}")

    def send_can_message(self, signal_name, value):
        """Send a CAN message with the specified signal and value."""
        try:
            # Find the message that contains the signal
            message = None
            for msg in db.messages:
                if signal_name in msg.signal_tree:
                    message = msg
                    break

            if not message:
                print(f"Signal '{signal_name}' not found in any message in the DBC file.")
                return

            # Encode the signal value into the message data
            data = message.encode({signal_name: value})

            # Create a CAN message
            msg = can.Message(
                arbitration_id=message.frame_id,
                data=data,
                is_extended_id=False
            )

            # Send the message on the CAN bus
            self.bus.send(msg)
            print(f"Sent CAN message: {signal_name} = {value}")
        except Exception as e:
            print(f"Error sending CAN message: {e}")

    def toggle_dyno_icon(self):
        button = self.sender()
        if button.isChecked():
            button.setStyleSheet("background-color: green; color: white;")
            self.send_can_message('Dyno_mode_req_team', 1)  # Send 1 when activated
        else:
            button.setStyleSheet("background-color: gray; color: black;")
            self.send_can_message('Dyno_mode_req_team', 0)  # Send 0 when deactivated

    def update_battery_display(self, soc):
        self.battery_label.setText(f"Battery: {soc}%")
        self.battery_widget.set_charge(soc)
    
    def update_sim_udp_label(self, value):
        if value:  # If the signal is received
            self.sim_udp_label.setText("Sim UDP received and byte count: ✅")
            self.sim_udp_label.setStyleSheet("color: green;")
        else:  # If the signal changes back
            self.sim_udp_label.setText("Sim UDP received and byte count: ❌")
            self.sim_udp_label.setStyleSheet("color: red;")

    def update_dyno_request_label(self, value):
        if value:  # If the signal is received
            self.dyno_request_label.setText("Request for Dyno Mode: ✅")
            self.dyno_request_label.setStyleSheet("color: green;")
        else:  # If the signal changes back
            self.dyno_request_label.setText("Request for Dyno Mode: ❌")
            self.dyno_request_label.setStyleSheet("color: red;")

    def update_sim_active_label(self, value):
        if value:  # If the signal is received
            self.sim_active_label.setText("Sim Active: ✅")
            self.sim_active_label.setStyleSheet("color: green;")
        else:  # If the signal changes back
            self.sim_active_label.setText("Sim Active: ❌")
            self.sim_active_label.setStyleSheet("color: red;")

    def update_vehicle_ahead_indicator(self, distance):
        self.vehicle_ahead_indicator.update_distance(distance)
    
    def update_vehicle_ahead_headway(self, headway):
        self.vehicle_ahead_indicator.update_headway(headway)
    
    def update_cacc_indicator(self, state):
        self.cacc_indicator.set_state(state)
    
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
        self.pcm = self.create_pcm_screen()
        self.errors = self.create_errors_screen()
        self.auto_park = self.create_auto_park_screen()
        self.cav_data = self.create_cav_data_screen()

        # Add tab screens to the stacked widget
        self.stacked_widget.addWidget(self.dyno_mode)
        self.stacked_widget.addWidget(self.pcm)
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
        error_dialog.exec()

    def initMainScreen(self):
        main_layout = QVBoxLayout(self.main_screen)

        # Create a container widget for the battery label and widget
        battery_container = QWidget()
        battery_container_layout = QVBoxLayout(battery_container)
        battery_container_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        battery_container_layout.setSpacing(5)  # Small spacing between label and widget

        # Battery Label
        self.battery_label = QLabel("Battery: 0%")
        self.battery_label.setFont(QFont("Arial", 24))
        self.battery_label.setAlignment(Qt.AlignLeft)  # Align text to the right

        # Battery Widget
        self.battery_widget = BatteryWidget()

        # Add the label and widget to the container layout
        battery_container_layout.addWidget(self.battery_label, alignment=Qt.AlignLeft)
        battery_container_layout.addWidget(self.battery_widget, alignment=Qt.AlignLeft)

        # Add the battery container to the main layout, aligned to the top-right
        main_layout.addWidget(battery_container, alignment=Qt.AlignTop | Qt.AlignLeft)

        # Add the CACC indicator
        self.cacc_indicator = CACCIndicator()
        main_layout.addWidget(self.cacc_indicator, alignment=Qt.AlignTop | Qt.AlignLeft)

        # Add the vehicle ahead indicator
        self.vehicle_ahead_indicator = VehicleAheadIndicator()
        main_layout.addWidget(self.vehicle_ahead_indicator, alignment=Qt.AlignBottom)

    def create_dyno_screen(self):
        dyno_screen = QWidget()
    
        # Create a vertical layout for the entire screen
        screen_layout = QVBoxLayout(dyno_screen)

        # Add a horizontal layout for "Activate Dyno Mode" and its button
        dyno_layout = QHBoxLayout()
        dyno_label = QLabel("Activate Dyno Mode:")
        dyno_label.setFont(QFont("Arial", 14))
        dyno_layout.addWidget(dyno_label)

        # Add the small Dyno Mode toggle button
        self.dyno_button = QPushButton()
        self.dyno_button.setFixedSize(50, 30)  # Smaller button size
        self.dyno_button.setCheckable(True)
        self.dyno_button.setStyleSheet("background-color: gray; color: black;")  # Start gray
        self.dyno_button.clicked.connect(self.toggle_dyno_icon)
        dyno_layout.addWidget(self.dyno_button)

        screen_layout.addLayout(dyno_layout)

        # Add a label for "Sim UDP received and byte count"
        self.sim_udp_label = QLabel("Sim UDP received and byte count: ❌")
        self.sim_udp_label.setFont(QFont("Arial", 14))
        self.sim_udp_label.setStyleSheet("color: red;")  # Start with red color
        screen_layout.addWidget(self.sim_udp_label, alignment=Qt.AlignLeft)

        # Add a label for "Request for Dyno Mode"
        self.dyno_request_label = QLabel("Request for Dyno Mode: ❌")
        self.dyno_request_label.setFont(QFont("Arial", 14))
        self.dyno_request_label.setStyleSheet("color: red;")  # Start with red color
        screen_layout.addWidget(self.dyno_request_label, alignment=Qt.AlignLeft)

        # Add a label for "Sim Active"
        self.sim_active_label = QLabel("Sim Active: ❌")
        self.sim_active_label.setFont(QFont("Arial", 14))
        self.sim_active_label.setStyleSheet("color: red;")  # Start with red color
        screen_layout.addWidget(self.sim_active_label, alignment=Qt.AlignLeft)

        # Add the back button at the bottom
        back_button = QPushButton("Back to Main Dashboard")
        back_button.clicked.connect(lambda: self.switch_screen(0))
        screen_layout.addWidget(back_button, alignment=Qt.AlignBottom)

        dyno_screen.setLayout(screen_layout)
        return dyno_screen
    
    def create_pcm_screen(self):
        pcm_screen = QWidget()
        pcm_layout = QVBoxLayout(pcm_screen)
        
        # Add a label to indicate the PCM screen
        label = QLabel("PCM Screen")
        label.setFont(QFont("Arial", 24))
        pcm_layout.addWidget(label, alignment=Qt.AlignCenter)

        # Add the SignalWidgetManager for PCM signals
        self.pcm_manager = SignalWidgetManager(PCM_SIGNALS)
        pcm_layout.addWidget(self.pcm_manager)

        return pcm_screen
    
    def create_errors_screen(self):
        errors_screen = QWidget()
        errors_layout = QVBoxLayout(errors_screen)
        
        errors_label = QLabel("Errors Content")
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
        cav_data_label.setAlignment(Qt.AlignCenter)
        cav_data_layout.addWidget(cav_data_label)
        
        back_button = QPushButton("Back to Main Dashboard")
        back_button.clicked.connect(lambda: self.switch_screen(0))
        cav_data_layout.addWidget(back_button, alignment=Qt.AlignBottom)
        
        return cav_data_screen
    
    def switch_screen(self, index):
        """Switch between screens in the stacked widget."""
        self.stacked_widget.setCurrentIndex(index)
    
if __name__ == "__main__":
    app = QApplication(sys.argv) 

    globalFont = QFont("Arial", 16)
    app.setFont(globalFont)

    window = Dashboard() 
    window.show() 
    sys.exit(app.exec())
       