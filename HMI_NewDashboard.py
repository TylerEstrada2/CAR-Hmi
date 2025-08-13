import sys
import time
import logging
import traceback
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, 
    QStackedWidget, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, 
    QSpacerItem, QSizePolicy, QDialog, QScrollArea
)
from PySide6.QtGui import QFont, QPainter, QPen, QColor, QPixmap, QAction
from PySide6.QtCore import Qt, QRect, QMetaObject, Slot, Q_ARG, QTimer
import can
from cantools.database.can.signal import NamedSignalValue
import cantools
import threading
import os

# Set up logging with file and console handlers
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

# AIN states for button color and label
AIN_STATES = {
    0: ("Off", "gray"),
    1: ("Standby", "white"),
    2: ("Active", "green")
}

# Verify DBC file
DBC_PATH = "/home/user/Code/Y3CompV1_2.dbc"
if not os.path.exists(DBC_PATH):
    logger.error(f"DBC file not found at {DBC_PATH}")
    sys.exit(1)
db = cantools.database.load_file(DBC_PATH)

PCM_SIGNALS = [
    'FEM_Power', 'REM_Power', 'RESS_SOC', 'RESS_Temp',
    'F_MotTmp', 'R_MotTmp', 'F_InvTmp', 'R_InvTmp', 'Master_Warning',
    'Dyno_mode_req_team', 'CACC_light', 'CACC_mileage', 'Headway_time',
    'Target_distance', 'USP_data_rx', 'Vehicle_ahead', 'ActETRS', 'BrakePdlPos', 'AccelPdlPos',
    'UDP_data_received', 'Sim_state', 'Dyno_mode_request',
    'LnDtWrnCntrlFtrSt', 'V2X_CurrentPhase',
    'AIN_engaged', 'DMS_engage', 'AINSystemStatus',
    'Warning_First', 'Warning_Second',
    'EDU001', 'EDU002', 'EDU003', 'EDU004'
]

TX_SIGNALS = ['Dyno_mode_req_team', 'AIN_engaged', 'DMS_engage']

MAIN_DASHBOARD_SIGNALS = [
    'Front Motor Power (kW)', 'Rear Motor Power (kW)', 'Battery Temperature (C)',
    'Accelerator Pedal Position (%)', 'Brake Pedal Position (%)', 'Drive Mode'
]

PCM_SIGNALS_PCM = [
    'Front Motor Power (kW)', 'Rear Motor Power (kW)', 'Battery SOC (%)', 'Battery Temperature (C)',
    'Front Motor Temperature (C)', 'Rear Motor Temperature (C)', 'Front Inverter Temperature (C)', 
    'Rear Inverter Temperature (C)', 'Master_Warning', 'Drive Mode'
]

SIGNAL_NAME_MAPPING = {
    'Front Motor Power (kW)': 'FEM_Power', 'Rear Motor Power (kW)': 'REM_Power',
    'Battery SOC (%)': 'RESS_SOC', 'Battery Temperature (C)': 'RESS_Temp',
    'Front Motor Temperature (C)': 'F_MotTmp', 'Rear Motor Temperature (C)': 'R_MotTmp',
    'Front Inverter Temperature (C)': 'F_InvTmp', 'Rear Inverter Temperature (C)': 'R_InvTmp',
    'Master_Warning': 'Master_Warning', 'Accelerator Pedal Position (%)': 'AccelPdlPos',
    'Brake Pedal Position (%)': 'BrakePdlPos', 'Drive Mode': 'ActETRS',
    'Headway': 'Headway_time', 'Distance': 'Target_distance'
}

CACC_STATES = {
    1: ("Hold", "white"), 2: ("Active", "green"), 3: ("Acceleration Override, standby", "blue"),
    4: ("Brake Override, Cancel", "white"), 5: ("Off", "gray"), 6: ("Fault", "red")
}

LCC_STATES = {
    0: ("Off", "gray"),
    1: ("Standby","white"),
    2: ("Active", "green"),
    3: ("Disabled", "white"),
}

DRIVE_MODE_MAPPING = {0: "Unknown", 1: "Park", 2: "Reverse", 3: "Neutral", 4: "Drive"}

DTC_SIGNALS = ['EDU001', 'EDU002', 'EDU003', 'EDU004']

DTC_DESCRIPTIONS = {
    'EDU001': "\nEDU001 Front EDU Torque Derating",
    'EDU002': "\nEDU002 Rear EDU Torque Derating",
    'EDU003': "\nEDU003 Front EDU Overtemperature Condition",
    'EDU004': "\nEDU004 Rear EDU Overtemperature Condition"
}

class WarningPopup(QDialog):
    def __init__(self, parent=None, warning_message=""):
        super().__init__(parent)
        self.setWindowTitle("Driver Warning")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        
        # Set to full screen
        if parent:
            self.setFixedSize(parent.size())
        else:
            self.showFullScreen()

        # Center the popup
        if parent:
            self.move(0, 0)  # Cover parent's entire area

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        self.warning_label = QLabel(warning_message)
        self.warning_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.warning_label.setAlignment(Qt.AlignCenter)
        self.warning_label.setStyleSheet("color: white;")

        layout.addWidget(self.warning_label, alignment=Qt.AlignCenter)
        # Solid red background, no transparency
        self.setStyleSheet("background-color: rgb(255, 0, 0);")

def init_can_bus():
    retries = 3
    for attempt in range(retries):
        try:
            bus = can.interface.Bus(channel='can0', interface='socketcan', bitrate=500000)
            logger.info(f"CAN bus initialized successfully on attempt {attempt + 1}")
            return bus
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}/{retries} - Error initializing CAN bus: {e}")
            if attempt < retries - 1:
                time.sleep(1)
    logger.error("Failed to initialize CAN bus after all retries")
    return None

def decode_message(message):
    try:
        return db.decode_message(message.arbitration_id, message.data)
    except Exception as e:
        logger.error(f"Error decoding message: {e}")
        return {}

class VehicleAheadIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.state = 0
        self.initUI()

    def initUI(self):
        try:
            layout = QHBoxLayout()
            self.setLayout(layout)
            self.icon_label = QLabel()
            icon_path = "/home/user/Code/VehicleAheadIndicator.png"
            if not os.path.exists(icon_path):
                logger.error(f"Pixmap not found: {icon_path}")
                self.icon_label.setText("VAI Missing")
                layout.addWidget(self.icon_label)
                return
            icon_pixmap = QPixmap(icon_path)
            if icon_pixmap.isNull():
                logger.error(f"Failed to load pixmap: {icon_path}")
                self.icon_label.setText("VAI Error")
                layout.addWidget(self.icon_label)
                return
            icon_width = 150  # Standardized size for CAVS icons
            icon_height = 150
            logger.info(f"VehicleAheadIndicator size: {icon_width}x{icon_height}")
            icon_pixmap = icon_pixmap.scaled(icon_width, icon_height, Qt.KeepAspectRatio)
            self.icon_label.setPixmap(icon_pixmap)
            self.icon_label.setFixedSize(icon_width, icon_height)
            self.update_color()
            layout.addWidget(self.icon_label)
        except Exception as e:
            logger.error(f"Error initializing VehicleAheadIndicator: {e}\n{traceback.format_exc()}")

    def update_color(self):
        color = "green" if self.state == 1 else "gray"
        self.icon_label.setStyleSheet(f"background-color: {color}; border-radius: 5px;")

    @Slot(int)
    def set_state(self, state):
        self.state = state
        self.update_color()

class CACCIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.state = 0
        self.initUI()

    def initUI(self):
        try:
            layout = QVBoxLayout()
            self.setLayout(layout)
            self.icon_label = QLabel()
            icon_path = "/home/user/Code/CACCIndicator_transparent.png"
            if not os.path.exists(icon_path):
                logger.error(f"Pixmap not found: {icon_path}")
                self.icon_label.setText("CACC Missing")
                layout.addWidget(self.icon_label)
                return
            self.icon_pixmap = QPixmap(icon_path)
            if self.icon_pixmap.isNull():
                logger.error(f"Failed to load pixmap: {icon_path}")
                self.icon_label.setText("CACC Error")
                layout.addWidget(self.icon_label)
                return
            icon_width = 150  # Standardized size for CAVS icons
            icon_height = 150
            logger.info(f"CACCIndicator size: {icon_width}x{icon_height}")
            self.icon_pixmap = self.icon_pixmap.scaled(icon_width, icon_height, Qt.KeepAspectRatio)
            self.icon_label.setPixmap(self.icon_pixmap)
            self.icon_label.setAlignment(Qt.AlignCenter)
            self.icon_label.setFixedSize(icon_width, icon_height)
            self.update_color()
            layout.addWidget(self.icon_label)
        except Exception as e:
            logger.error(f"Error initializing CACCIndicator: {e}\n{traceback.format_exc()}")

    def update_color(self):
        _, color = CACC_STATES.get(self.state, ("Unknown", "gray"))
        self.icon_label.setStyleSheet(f"background-color: {color}; border-radius: 5px;")

    @Slot(int)
    def set_state(self, state):
        self.state = state
        self.update_color()

class LCCIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.state = 0
        self.initUI()

    def initUI(self):
        try:
            layout = QVBoxLayout()
            self.setLayout(layout)
            self.icon_label = QLabel()
            icon_path = "/home/user/Code/LCC_Icon.png"
            if not os.path.exists(icon_path):
                logger.error(f"Pixmap not found: {icon_path}")
                self.icon_label.setText("LCC Missing")
                layout.addWidget(self.icon_label)
                return
            self.icon_pixmap = QPixmap(icon_path)
            if self.icon_pixmap.isNull():
                logger.error(f"Failed to load pixmap: {icon_path}")
                self.icon_label.setText("LCC Error")
                layout.addWidget(self.icon_label)
                return
            icon_width = 150  # Standardized size for CAVS icons
            icon_height = 150
            logger.info(f"LCCIndicator size: {icon_width}x{icon_height}")
            self.icon_pixmap = self.icon_pixmap.scaled(icon_width, icon_height, Qt.KeepAspectRatio)
            self.icon_label.setPixmap(self.icon_pixmap)
            self.icon_label.setAlignment(Qt.AlignCenter)
            self.icon_label.setFixedSize(icon_width, icon_height)
            self.update_color()
            layout.addWidget(self.icon_label)
        except Exception as e:
            logger.error(f"Error initializing LCCIndicator: {e}\n{traceback.format_exc()}")

    def update_color(self):
        _, color = LCC_STATES.get(self.state, ("Unknown", "gray"))
        self.icon_label.setStyleSheet(f"background-color: {color}; border-radius: 5px;")

    @Slot(int)
    def set_state(self, state):
        self.state = state
        self.update_color()

class TrafficLightIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.state = 0
        self.initUI()

    def initUI(self):
        try:
            layout = QHBoxLayout()
            self.setLayout(layout)
            self.icon_label = QLabel()
            self.icon_label.setAlignment(Qt.AlignCenter)
            self.icon_label.setFixedSize(150, 150)
            layout.addWidget(self.icon_label)
            self.update_color()
        except Exception as e:
            logger.error(f"Error initializing TrafficLightIndicator: {e}\n{traceback.format_exc()}")

    def update_color(self):
        icon_paths = {
            0: "TrafficLightNone.png",
            3: "TrafficLightRed.png",
            6: "TrafficLightGreen.png",
            8: "TrafficLightYellow.png"
        }
        icon_file = icon_paths.get(self.state, "TrafficLightNone.png")
        icon_path = os.path.join("/home/user/Code/", icon_file)

        if not os.path.exists(icon_path):
            logger.error(f"Traffic light icon not found: {icon_path}")
            self.icon_label.setText("Missing")
            return

        pixmap = QPixmap(icon_path)
        if pixmap.isNull():
            logger.error(f"Failed to load traffic light pixmap: {icon_path}")
            self.icon_label.setText("Error")
            return

        self.icon_label.setPixmap(pixmap.scaled(150, 150, Qt.KeepAspectRatio))
        self.icon_label.setStyleSheet("")  # Clear any previous style

    @Slot(int)
    def set_state(self, state):
        logger.info(f"Setting TrafficLightIndicator state: {state}")
        self.state = state if state in [0, 3, 6, 8] else 0
        self.update_color()

class BatteryWidget(QWidget):
    def __init__(self):
        super().__init__()
        try:
            widget_width = 300  # Fixed size as requested
            widget_height = 70
            logger.info(f"BatteryWidget size: {widget_width}x{widget_height}")
            self.setFixedSize(widget_width, widget_height)
            self.charge = 0
        except Exception as e:
            logger.error(f"Error initializing BatteryWidget: {e}\n{traceback.format_exc()}")

    @Slot(int)
    def set_charge(self, charge):
        self.charge = min(charge, 100)
        self.update()

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            rect = self.rect()
            painter.setPen(QPen(Qt.black, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            bar_width = (rect.width() - 16) // 4
            bar_height = rect.height() - 16
            gap = 2
            for i in range(4):
                x = rect.left() + 8 + i * (bar_width + gap)
                y = rect.top() + 8
                if self.charge > i * 25:
                    painter.setBrush(QColor(0, 255, 0))
                else:
                    painter.setBrush(Qt.gray)
                painter.drawRect(QRect(x, y, bar_width, bar_height))
        except Exception as e:
            logger.error(f"Error painting BatteryWidget: {e}\n{traceback.format_exc()}")

class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        logger.info("Initializing Dashboard")

        try:
            # === Setup UI styling and screen ===
            self.setWindowTitle("Autonomous Vehicle HMI")
            self.setStyleSheet("background-color: #555F61; color: white;")
            screen = QApplication.primaryScreen().geometry()
            self.screen_width = screen.width()
            self.screen_height = screen.height()
            logger.info(f"Screen resolution: {self.screen_width}x{self.screen_height}")
            if self.screen_width <= 0 or self.screen_height <= 0:
                raise ValueError("Invalid screen resolution detected")
            self.showFullScreen()

            # === Setup buttons' locks and flags ===
            self.dyno_mode_lock = threading.Lock()
            self.dms_mode_lock = threading.Lock()
            self.ain_mode_lock = threading.Lock()
            self.dyno_mode_active = False
            self.dms_active = False
            self.ain_mode_active = False
            self.ain_system_status = 0  # Initialize AINSystemStatus
            self.warning_popup = None
            self.warning_first_active = False
            self.warning_second_active = False

            # === Setup Escape key to exit fullscreen ===
            self.exit_fullscreen_action = QAction("Exit Fullscreen", self)
            self.exit_fullscreen_action.setShortcut("Esc")
            self.exit_fullscreen_action.triggered.connect(self.toggle_fullscreen)
            self.addAction(self.exit_fullscreen_action)

            # === Setup signal lists and lookup tables ===
            self.signals = PCM_SIGNALS
            self.txsignals = TX_SIGNALS
            self.signal_units = {}
            for message in db.messages:
                for signal in message.signals:
                    if signal.name in self.signals:
                        self.signal_units[signal.name] = signal.unit or ""

            # === Initialize signal values ===
            self.signal_values = {signal: "-" for signal in self.signals}

            # === Initialize CAN bus ===
            self.bus = init_can_bus()
            if self.bus is None:
                logger.error("CAN bus initialization failed")
                self.showErrorDialog("Failed to initialize CAN bus. Exiting...")
                sys.exit(1)

            # === Set up other state tracking ===
            self.battery_widgets = []
            self.battery_labels = []
            self.dtc_labels = []
            self.mil_indicator = None
            self.dtc_states = {signal: 0 for signal in DTC_SIGNALS}

            self.tx_messages = {
                'Dyno_mode_req_team': 0x519,
                'AIN_engaged': 0x519,
                'DMS_engage': 0x519
            }
            self.validate_tx_messages()

            # === Initialize UI ===
            self.initUI()

            # === Start TX thread (after initUI) ===
            self.tx_thread_running = True
            self.tx_send_thread = threading.Thread(target=self.send_tx_messages, daemon=True)
            self.tx_send_thread.start()

            # === Start CAN listener thread ===
            self.can_listener_thread = threading.Thread(target=self.listen_can_messages, daemon=True)
            self.can_listener_thread.start()

            logger.info(f"Main window size: {self.size().width()}x{self.size().height()}")

        except Exception as e:
            logger.error(f"Error initializing Dashboard: {e}\n{traceback.format_exc()}")
            self.showErrorDialog("Failed to initialize UI. Check logs.")
            sys.exit(1)

    def validate_tx_messages(self):
        for signal_name, message_id in self.tx_messages.items():
            try:
                message = db.get_message_by_frame_id(message_id)
                if signal_name not in [signal.name for signal in message.signals]:
                    logger.error(f"Signal '{signal_name}' not found in message ID {hex(message_id)}")
                else:
                    logger.info(f"Validated signal '{signal_name}' in message ID {hex(message_id)}")
            except Exception as e:
                logger.error(f"Message ID {hex(message_id)} not found in DBC: {e}")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _send_message(self, message_id, signal_name, value, message_type):
        retries = 3
        for attempt in range(retries):
            try:
                message = db.get_message_by_frame_id(message_id)
                if signal_name not in [signal.name for signal in message.signals]:
                    logger.error(f"Signal '{signal_name}' not found in message ID {hex(message_id)}")
                    return

                signal = next(s for s in message.signals if s.name == signal_name)
                if not (signal.minimum <= value <= signal.maximum):
                    logger.error(f"Value {value} for signal '{signal_name}' is out of range [{signal.minimum}, {signal.maximum}]")
                    return

                data = db.encode_message(message_id, {signal_name: value}, strict=False)
                if len(data) < 8:
                    data = data.ljust(8, b'\x00')

                can_msg = can.Message(arbitration_id=message_id, data=data, is_extended_id=False)
                self.bus.send(can_msg, timeout=0.4)
                logger.info(f"Sent {message_type} message: ID={hex(message_id)}, Signal={signal_name}, Value={value}, Data={data.hex()}")
                return
            except can.CanError as e:
                logger.error(f"Attempt {attempt + 1}/{retries} - CAN Error sending {message_type}: {e}")
                if attempt < retries - 1:
                    time.sleep(0.2)
                else:
                    logger.error(f"Failed to send {message_type} CAN message after {retries} attempts.")
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}/{retries} - Other Error sending {message_type}: {e}")
                return
    
    def send_tx_messages(self):
        while self.tx_thread_running:
            start_time = time.time()
            
            # Compute values for all signals
            with self.dyno_mode_lock:
                dyno_value = 1 if self.dyno_mode_active else 0
            with self.ain_mode_lock:
                ain_value = 1 if self.ain_mode_active else 0
                logger.info(f"AIN_engaged value: {ain_value}, ain_mode_active={self.ain_mode_active}")
            with self.dms_mode_lock:
                dms_value = 1 if self.dms_active else 0
                logger.info(f"DMS state: self.dms_active={self.dms_active}, button_checked={self.dms_button.isChecked()}")
            
            # Send combined 0x519 message (Dyno_mode_req_team and AIN_engaged)
            try:
                message_id = 0x519
                data = db.encode_message(
                    message_id,
                    {
                        "Dyno_mode_req_team": dyno_value,
                        "AIN_engaged": ain_value,
                        "DMS_engage": dms_value
                    },
                    strict=False
                )
                if len(data) < 8:
                    data = data.ljust(8, b'\x00')
                can_msg = can.Message(arbitration_id=message_id, data=data, is_extended_id=False)
                self.bus.send(can_msg, timeout=0.2)
                logger.info(f"Sent 0x519: Dyno_mode_req_team={dyno_value}, AIN_engaged={ain_value},DMS_engage={dms_value}, Data={data.hex()}")
            except can.CanError as e:
                logger.error(f"CAN Error sending 0x519 message: {e}")
            except Exception as e:
                logger.error(f"Error sending 0x519 message: {e}")
            
            # # Send HMI2DMS (0x524)
            # try:
            #     message_id = 0x524
            #     data = db.encode_message(
            #         message_id,
            #         {
            #             "HMI2DMS": dms_value
            #         },
            #         strict=False
            #     )
            #     if len(data) < 8:
            #         data = data.ljust(8, b'\x00')
            #     can_msg = can.Message(arbitration_id=message_id, data=data, is_extended_id=False)
            #     self.bus.send(can_msg, timeout=0.5)
            #     logger.info(f"Sent 0x524: HMI2DMS={dms_value}, Data={data.hex()}")
            # except can.CanError as e:
            #     logger.error(f"CAN Error sending 0x524 message: {e}")
            # except Exception as e:
            #     logger.error(f"Error sending 0x524 message: {e}")
            
            # Sleep to maintain 100ms cycle
            elapsed = time.time() - start_time
            time.sleep(max(0.5 - elapsed, 0))

    def listen_can_messages(self):
        while True:
            try:
                msg = self.bus.recv(timeout=0.1)
                if msg:
                    decoded = decode_message(msg)
                    for signal in self.signals:
                        if signal in decoded:
                            value = decoded[signal]
                            if isinstance(value, NamedSignalValue):
                                value = value.value
                            elif isinstance(value, bool):
                                value = 1 if value else 0
                            if signal in ['Headway_time', 'Target_distance']:
                                try:
                                    value = float(value)  # Ensure float for consistent handling
                                    logger.info(f"Received {signal}: value={value}, type={type(value)}")
                                except (ValueError, TypeError) as e:
                                    logger.error(f"Failed to convert {signal} to float: value={value}, type={type(value)}, error={e}")
                                    value = None  # Use None to indicate invalid value
                            self.signal_values[signal] = value
                            if signal == 'V2X_CurrentPhase':
                                logger.info(f"Received V2X_CurrentPhase: {value}")
                            if signal == 'Warning_First' and int(value) == 1:
                                QMetaObject.invokeMethod(self, "show_warning_popup", Qt.QueuedConnection, Q_ARG(int, 1))
                            elif signal == 'Warning_Second' and int(value) == 1:
                                QMetaObject.invokeMethod(self, "show_warning_popup", Qt.QueuedConnection, Q_ARG(int, 2))
                            elif signal == 'Warning_First' and int(value) == 0:
                                QMetaObject.invokeMethod(self, "clear_warning", Qt.QueuedConnection, Q_ARG(int, 1))
                            elif signal == 'Warning_Second' and int(value) == 0:
                                QMetaObject.invokeMethod(self, "clear_warning", Qt.QueuedConnection, Q_ARG(int, 2))
                            elif signal == 'ActETRS':
                                drive_mode = DRIVE_MODE_MAPPING.get(int(value), "Unknown")
                                QMetaObject.invokeMethod(self, "update_drive_mode_display", Qt.QueuedConnection, Q_ARG(str, signal), Q_ARG(str, drive_mode))
                            else:
                                if isinstance(value, int):
                                    QMetaObject.invokeMethod(self, "update_signal_display_int", Qt.QueuedConnection, Q_ARG(str, signal), Q_ARG(int, value))
                                elif isinstance(value, float):
                                    QMetaObject.invokeMethod(self, "update_signal_display_float", Qt.QueuedConnection, Q_ARG(str, signal), Q_ARG(float, value))
                                elif isinstance(value, str):
                                    QMetaObject.invokeMethod(self, "update_signal_display_str", Qt.QueuedConnection, Q_ARG(str, signal), Q_ARG(str, value))
                                elif value is None:
                                    QMetaObject.invokeMethod(self, "update_signal_display_str", Qt.QueuedConnection, Q_ARG(str, signal), Q_ARG(str, "N/A"))
            except Exception as e:
                logger.error(f"Error processing CAN message: {e}")
                time.sleep(0.1)

    @Slot(int)
    def show_warning_popup(self, warning_type):
        # Determine the message and check if the warning is already active
        if warning_type == 1:
            if self.warning_first_active:
                return  # Popup already shown for Warning_First
            self.warning_first_active = True
            message = "Driver: Pay Attention to the Road!"
        elif warning_type == 2:
            if self.warning_second_active:
                return  # Popup already shown for Warning_Second
            self.warning_second_active = True
            message = ("Driver: Pay Attention to the Road!\n"
                      "ACC and LCC systems will be disabled for 30 seconds after attention is regained.")
        else:
            return

        # Close existing popup if it exists and is visible
        if self.warning_popup is not None and self.warning_popup.isVisible():
            try:
                self.warning_popup.close()
                self.warning_popup.deleteLater()
            except Exception as e:
                logger.warning(f"Warning popup close/delete failed: {e}")

        # Create and show new popup
        self.warning_popup = WarningPopup(self, warning_message=message)
        self.warning_popup.setWindowModality(Qt.ApplicationModal)
        self.warning_popup.show()
        self.warning_popup.raise_()
        self.warning_popup.activateWindow()

        logger.info(f"DMS Warning popup shown: Type {warning_type}")

    @Slot(int)
    def clear_warning(self, warning_type):
        if warning_type == 1:
            self.warning_first_active = False
        elif warning_type == 2:
            self.warning_second_active = False

        # Close popup only if no warnings are active
        if not self.warning_first_active and not self.warning_second_active:
            if self.warning_popup and self.warning_popup.isVisible():
                try:
                    self.warning_popup.close()
                    self.warning_popup.deleteLater()
                    self.warning_popup = None
                except Exception as e:
                    logger.warning(f"Warning popup close/delete failed: {e}")
                logger.info("DMS Warning popup closed: No active warnings")

    @Slot(str, str)
    def update_drive_mode_display(self, signal_name, value):
        try:
            if signal_name == 'ActETRS':
                drive_mode = value
                row = MAIN_DASHBOARD_SIGNALS.index('Drive Mode')
                self.pcm_table_main.setItem(row, 1, QTableWidgetItem(drive_mode))
                if hasattr(self, 'pcm_table'):
                    row = PCM_SIGNALS_PCM.index('Drive Mode')
                    self.pcm_table.setItem(row, 1, QTableWidgetItem(drive_mode))
        except Exception as e:
            logger.error(f"Error updating drive mode display: {e}\n{traceback.format_exc()}")

    def update_ain_button_color(self):
        try:
            if not hasattr(self, 'ain_button') or self.ain_button is None:
                logger.error("AIN button not initialized")
                return
            state, color = AIN_STATES.get(self.ain_system_status, ("Unknown", "gray"))
            text_color = "white" if color in ["green", "gray"] else "black"
            self.ain_button.setStyleSheet(f"background-color: {color}; color: {text_color};")
            logger.info(f"AIN button color updated: AINSystemStatus={self.ain_system_status}, State={state}, Color={color}")
        except Exception as e:
            logger.error(f"Error updating AIN button color: {e}\n{traceback.format_exc()}")

    @Slot(str, object)
    def update_signal_display(self, signal_name, value):
        logger.info(f"Processing signal: {signal_name}, value={value}, type={type(value)}")
        if hasattr(value, 'name'):
            value = value.name

        if signal_name == 'ActETRS':
            return

        if signal_name == 'Headway_time':
            if value is None or isinstance(value, str) or value == 0.0:
                self.VAI_Headway_Label.setText("Headway: N/A")
                logger.warning(f"Invalid Headway_time value: {value}")
            else:
                try:
                    formatted_value = f"{float(value):.1f}"
                    self.VAI_Headway_Label.setText(f"Headway: {formatted_value} s")
                    logger.info(f"Updated Headway_time: {formatted_value} s")
                except (ValueError, TypeError) as e:
                    self.VAI_Headway_Label.setText("Headway: N/A")
                    logger.error(f"Error formatting Headway_time: value={value}, error={e}")

        elif signal_name == 'Target_distance':
            if value is None or isinstance(value, str) or value == 0.0:
                self.VAI_Distance_Label.setText("Distance: N/A")
                logger.warning(f"Invalid Target_distance value: {value}")
            else:
                try:
                    formatted_value = f"{float(value):.1f}"
                    self.VAI_Distance_Label.setText(f"Distance: {formatted_value} m")
                    logger.info(f"Updated Target_distance: {formatted_value} m")
                except (ValueError, TypeError) as e:
                    self.VAI_Distance_Label.setText("Distance: N/A")
                    logger.error(f"Error formatting Target_distance: value={value}, error={e}")

        elif signal_name == 'CACC_light':
            self.cacc_indicator.set_state(int(value))

        elif signal_name == 'Vehicle_ahead':
            self.VAI_Indicator.set_state(int(value))

        elif signal_name == 'Sim_state':
            self.sim_active_label.setStyleSheet(f"color: {'green' if value == 1 else 'white'};")

        elif signal_name == 'Dyno_mode_request':
            self.dyno_request_label.setStyleSheet(f"color: {'green' if value == 1 else 'white'};")

        elif signal_name == 'UDP_data_received':
            self.sim_udp_label.setStyleSheet(f"color: {'green' if value == 1 else 'white'};")

        elif signal_name in DTC_SIGNALS:
            self.dtc_states[signal_name] = int(value)
            active_dtcs = [DTC_DESCRIPTIONS[sig] for sig, state in self.dtc_states.items() if state == 1]
            dtc_text = "DTCs: None" if not active_dtcs else f"DTCs: {', '.join(active_dtcs)}"
            self.dtc_status_label.setText(dtc_text)
            any_dtc_active = any(state == 1 for state in self.dtc_states.values())
            self.mil_indicator.setVisible(any_dtc_active)
            for label in self.dtc_labels:
                label.setText("DTC: Active" if any_dtc_active else "DTC: No Issues")

        elif signal_name == 'LnDtWrnCntrlFtrSt':
            self.lcc_indicator.set_state(int(value))

        elif signal_name == 'V2X_CurrentPhase':
            self.traffic_light_indicator.set_state(int(value))

        elif signal_name == 'AINSystemStatus':
            try:
                self.ain_system_status = int(value)
                self.update_ain_button_color()
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid AINSystemStatus value: {value}, Error: {e}")
                self.ain_system_status = 0
                self.update_ain_button_color()

        else:
            rounded_value = round(value, 1) if isinstance(value, float) else value
            if signal_name == 'RESS_SOC':
                soc_rounded = round(value, 1)
                for label, widget in zip(self.battery_labels, self.battery_widgets):
                    label.setText(f"Battery: {soc_rounded}%")
                    widget.set_charge(soc_rounded)
                mapped_name = SIGNAL_NAME_MAPPING.get('Battery SOC (%)')
                if mapped_name and mapped_name in PCM_SIGNALS_PCM:
                    row = PCM_SIGNALS_PCM.index(mapped_name)
                    self.pcm_table.setItem(row, 1, QTableWidgetItem(str(soc_rounded)))

            mapped_name = next((new_name for new_name, orig_name in SIGNAL_NAME_MAPPING.items() if orig_name == signal_name), None)
            if mapped_name:
                if mapped_name in PCM_SIGNALS_PCM:
                    row = PCM_SIGNALS_PCM.index(mapped_name)
                    if mapped_name in ['Front Motor Power (kW)', 'Rear Motor Power (kW)']:
                        self.pcm_table.setItem(row, 1, QTableWidgetItem(str(round(rounded_value/1000, 3))))
                    else:
                        self.pcm_table.setItem(row, 1, QTableWidgetItem(str(rounded_value)))
                if mapped_name in MAIN_DASHBOARD_SIGNALS:
                    row = MAIN_DASHBOARD_SIGNALS.index(mapped_name)
                    if mapped_name in ['Front Motor Power (kW)', 'Rear Motor Power (kW)']:
                        self.pcm_table_main.setItem(row, 1, QTableWidgetItem(str(round(rounded_value/1000, 3))))
                    else:
                        self.pcm_table_main.setItem(row, 1, QTableWidgetItem(str(rounded_value)))

            elif signal_name == 'AccelPdlPos':
                row = MAIN_DASHBOARD_SIGNALS.index('Accelerator Pedal Position (%)')
                self.pcm_table_main.setItem(row, 1, QTableWidgetItem(f"{rounded_value}%"))
            elif signal_name == 'BrakePdlPos':
                row = MAIN_DASHBOARD_SIGNALS.index('Brake Pedal Position (%)')
                self.pcm_table_main.setItem(row, 1, QTableWidgetItem(f"{rounded_value}%"))
            elif signal_name == 'CACC_mileage':
                self.cacc_mileage_label.setText(f"Current CACC Mileage: {round(rounded_value*0.621371,1)} mi")

    def toggle_dyno_icon(self):
        try:
            button = self.sender()
            button_width = 200
            button_height = 100
            logger.info(f"Dyno button size: {button_width}x{button_height}")
            button.setFixedSize(button_width, button_height)
            with self.dyno_mode_lock:
                self.dyno_mode_active = button.isChecked()
                button.setStyleSheet(f"background-color: {'green' if self.dyno_mode_active else 'gray'}; color: {'white' if self.dyno_mode_active else 'black'};")
                logger.info(f"Dyno mode toggled: dyno_mode_active={self.dyno_mode_active}")
        except Exception as e:
            logger.error(f"Error toggling dyno icon: {e}\n{traceback.format_exc()}")

    def toggle_ain_button(self):
        try:
            button = self.sender()
            button_width = 200
            button_height = 100
            logger.info(f"AIN button size: {button_width}x{button_height}")
            button.setFixedSize(button_width, button_height)
            with self.ain_mode_lock:
                self.ain_mode_active = button.isChecked()
                self.update_ain_button_color()
                logger.info(f"AIN button toggled: ain_mode_active={self.ain_mode_active}, AIN_engaged={'1' if self.ain_mode_active else '0'}")
        except Exception as e:
            logger.error(f"Error toggling AIN button: {e}\n{traceback.format_exc()}")

    def toggle_dms_icon(self):
        try:
            button = self.sender()
            button_width = 200
            button_height = 100
            logger.info(f"DMS button size: {button_width}x{button_height}")
            button.setFixedSize(button_width, button_height)
            with self.dms_mode_lock:
                self.dms_active = button.isChecked()
                button.setStyleSheet(f"background-color: {'green' if self.dms_active else 'gray'}; color: {'white' if self.dms_active else 'black'};")
                logger.info(f"DMS toggled: dms_active={self.dms_active}, DMS_engage={'1' if self.dms_active else '0'}")
        except Exception as e:
            logger.error(f"Error toggling DMS icon: {e}\n{traceback.format_exc()}")

    @Slot(str, int)
    def update_signal_display_int(self, signal_name, value):
        self.update_signal_display(signal_name, value)

    @Slot(str, float)
    def update_signal_display_float(self, signal_name, value):
        self.update_signal_display(signal_name, value)

    @Slot(str, str)
    def update_signal_display_str(self, signal_name, value):
        self.update_signal_display(signal_name, value)

    def initUI(self):
        logger.info("Starting initUI")
        try:
            self.main_layout = QVBoxLayout()
            self.main_layout.setContentsMargins(10, 10, 10, 10)

            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setStyleSheet("background-color: #555F61;")
            content_widget = QWidget()
            content_layout = QVBoxLayout(content_widget)

            self.header_layout = QHBoxLayout()
            self.header_layout.setSpacing(11)
            header_widget = QWidget()
            logger.info("Header layout spacing set to 11px")
            header_widget.setStyleSheet("background-color: #555F61;")
            header_widget.setLayout(self.header_layout)

            battery_container = QWidget()
            battery_layout = QHBoxLayout(battery_container)
            self.battery_widget = BatteryWidget()
            self.battery_label = QLabel("Battery: N/A%")
            self.battery_label.setFont(QFont("Arial", 16))
            battery_layout.addWidget(self.battery_widget)
            battery_layout.addWidget(self.battery_label)
            battery_layout.setSpacing(10)
            self.battery_labels = [self.battery_label]
            self.header_layout.addWidget(battery_container)

            self.header_layout.addSpacerItem(QSpacerItem(50, 0, QSizePolicy.Fixed, QSizePolicy.Minimum))

            self.dtc_label = QLabel("DTC: No Issues")
            self.dtc_label.setFont(QFont("Arial", 18))

            self.mil_indicator = QLabel()
            mil_path = "/home/user/Code/MIL.png"
            if not os.path.exists(mil_path):
                logger.error(f"Pixmap not found: {mil_path}")
                self.mil_indicator.setText("MIL Missing")
            else:
                mil_pixmap = QPixmap(mil_path)
                if mil_pixmap.isNull():
                    logger.error(f"Failed to load pixmap: {mil_path}")
                    self.mil_indicator.setText("MIL Error")
                else:
                    mil_width = 100
                    mil_height = 80
                    logger.info(f"MIL Indicator size: {mil_width}x{mil_height}")
                    mil_pixmap = mil_pixmap.scaled(mil_width, mil_height, Qt.KeepAspectRatio)
                    self.mil_indicator.setPixmap(mil_pixmap)
            self.mil_indicator.setVisible(False)
            logger.info("MIL indicator initialized, geometry: %s", self.mil_indicator.geometry())
            self.header_layout.addWidget(self.mil_indicator)
            self.header_layout.addSpacerItem(QSpacerItem(50, 0, QSizePolicy.Fixed, QSizePolicy.Fixed))

            self.ain_button = QPushButton("AIN ACTIVATE")
            self.ain_button.setMinimumSize(200, 100)
            self.ain_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.ain_button.setFont(QFont("Arial", 18))
            self.ain_button.setStyleSheet("padding: 5px; background-color: gray; color: white;")
            self.ain_button.setCheckable(True)
            self.ain_button.clicked.connect(self.toggle_ain_button)
            logger.info("AIN button initialized, geometry: %s", self.ain_button.geometry())
            self.header_layout.addWidget(self.ain_button)
            self.header_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

            self.header_layout.addStretch()
            content_layout.addWidget(header_widget)

            self.battery_widgets = [self.battery_widget]
            self.dtc_labels = [self.dtc_label]

            # Adjust tab buttons size and layout
            self.top_bar = QHBoxLayout()
            self.top_bar.setSpacing(1)
            screen_names = ["Dyno Mode", "PCM", "CAVs", "DTC"]
            for i, name in enumerate(screen_names):
                btn = QPushButton(name)
                btn.clicked.connect(lambda checked, index=i: self.switch_screen(index + 1))
                btn.setMinimumSize(250, 60)  # Reduced height, increased width
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                btn.setFont(QFont("Arial", 18))
                btn.setStyleSheet("padding: 5px; background-color: #333; color: white; border-radius: 5px;")
                self.top_bar.addWidget(btn)
            content_layout.addLayout(self.top_bar)

            self.stacked_widget = QStackedWidget()
            self.main_screen = QWidget()
            self.initMainScreen()
            self.stacked_widget.addWidget(self.main_screen)

            self.dyno_mode = self.create_dyno_screen()
            self.pcm = self.create_pcm_screen()
            self.acc = self.create_acc_screen()
            self.dtc = self.create_dtc_screen()

            self.stacked_widget.addWidget(self.dyno_mode)
            self.stacked_widget.addWidget(self.pcm)
            self.stacked_widget.addWidget(self.acc)
            self.stacked_widget.addWidget(self.dtc)

            content_layout.addWidget(self.stacked_widget)
            scroll_area.setWidget(content_widget)
            self.main_layout.addWidget(scroll_area)

            self.setLayout(self.main_layout)
            logger.info("initUI completed")
        except Exception as e:
            logger.error(f"Error in initUI: {e}\n{traceback.format_exc()}")
            raise

    def showErrorDialog(self, error_message):
        try:
            logger.error(f"Showing error dialog: {error_message}")
            error_dialog = QMessageBox(self)
            error_dialog.setWindowTitle("Error")
            error_dialog.setText(f"{error_message} error occurred. Consult manual to fix.")
            error_dialog.setStandardButtons(QMessageBox.Ok)
            error_dialog.exec()
        except Exception as e:
            logger.error(f"Error showing error dialog: {e}\n{traceback.format_exc()}")

    def initMainScreen(self):
        try:
            main_layout = QVBoxLayout(self.main_screen)
            content_layout = QHBoxLayout()

            dms_container = QHBoxLayout()
            dms_label = QLabel("Activate DMS System:")
            dms_label.setFont(QFont("Arial", 18))
            dms_container.addWidget(dms_label)
            self.dms_button = QPushButton("DMS")
            self.dms_button.setMinimumSize(200, 100)
            self.dms_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.dms_button.setFont(QFont("Arial", 18))
            self.dms_button.setStyleSheet("padding: 5px; background-color: gray; color: black; border-radius: 5px;")
            self.dms_button.setCheckable(True)
            self.dms_button.clicked.connect(self.toggle_dms_icon)
            dms_container.addWidget(self.dms_button)
            content_layout.addLayout(dms_container)

            self.pcm_table_main = QTableWidget()
            self.pcm_table_main.setRowCount(len(MAIN_DASHBOARD_SIGNALS))
            self.pcm_table_main.setColumnCount(2)
            self.pcm_table_main.setHorizontalHeaderLabels(["Signal", "Value"])
            self.pcm_table_main.verticalHeader().setVisible(False)
            table_width = 700
            table_height = 290
            logger.info(f"pcm_table_main size: width={table_width}, height={table_height}")
            self.pcm_table_main.setFixedSize(table_width, table_height)
            self.pcm_table_main.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            
            table_font = QFont("Arial", 18)
            self.pcm_table_main.setFont(table_font)
            
            for row in range(self.pcm_table_main.rowCount()):
                self.pcm_table_main.setRowHeight(row, 40)
            for row, signal in enumerate(MAIN_DASHBOARD_SIGNALS):
                signal_item = QTableWidgetItem(signal)
                value_item = QTableWidgetItem("0" if signal != 'Drive Mode' else "Unknown")
                signal_item.setFont(table_font)
                value_item.setFont(table_font)
                self.pcm_table_main.setItem(row, 0, signal_item)
                self.pcm_table_main.setItem(row, 1, value_item)
            self.pcm_table_main.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            content_layout.addWidget(self.pcm_table_main)

            main_layout.addLayout(content_layout)
            main_layout.addStretch()
        except Exception as e:
            logger.error(f"Error initializing main screen: {e}\n{traceback.format_exc()}")

    def create_dyno_screen(self):
        try:
            dyno_screen = QWidget()
            screen_layout = QVBoxLayout(dyno_screen)

            dyno_layout = QHBoxLayout()
            dyno_label = QLabel("Activate Dyno Mode:")
            dyno_label.setFont(QFont("Arial", 18))
            dyno_layout.addWidget(dyno_label)
            self.dyno_button = QPushButton("Dyno Mode")
            self.dyno_button.setMinimumSize(200, 100)
            self.dyno_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.dyno_button.setFont(QFont("Arial", 18))
            self.dyno_button.setStyleSheet("padding: 5px; background-color: gray; color: black; border-radius: 5px;")
            self.dyno_button.setCheckable(True)
            self.dyno_button.clicked.connect(self.toggle_dyno_icon)
            dyno_layout.addWidget(self.dyno_button)
            screen_layout.addLayout(dyno_layout)

            self.sim_udp_label = QLabel("Sim UDP received and byte count")
            self.sim_udp_label.setFont(QFont("Arial", 18))
            self.sim_udp_label.setStyleSheet("color: white;")
            screen_layout.addWidget(self.sim_udp_label, alignment=Qt.AlignLeft)
            self.dyno_request_label = QLabel("Request for Dyno Mode")
            self.dyno_request_label.setFont(QFont("Arial", 18))
            self.dyno_request_label.setStyleSheet("color: white;")
            screen_layout.addWidget(self.dyno_request_label, alignment=Qt.AlignLeft)
            self.sim_active_label = QLabel("Sim Active")
            self.sim_active_label.setFont(QFont("Arial", 18))
            self.sim_active_label.setStyleSheet("color: white;")
            screen_layout.addWidget(self.sim_active_label, alignment=Qt.AlignLeft)

            back_button = QPushButton("Back to Main Dashboard")
            back_button.setMinimumSize(1000, 70)
            back_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            back_button.setFont(QFont("Arial", 18))
            back_button.setStyleSheet("padding: 5px; background-color: #333; color: white; border-radius: 5px;")
            back_button.clicked.connect(lambda: self.switch_screen(0))
            screen_layout.addWidget(back_button, alignment=Qt.AlignBottom | Qt.AlignCenter)
            return dyno_screen
        except Exception as e:
            logger.error(f"Error creating dyno screen: {e}\n{traceback.format_exc()}")
            return QWidget()

    def create_pcm_screen(self):
        try:
            pcm_screen = QWidget()
            pcm_layout = QVBoxLayout(pcm_screen)

            self.pcm_table = QTableWidget()
            self.pcm_table.setRowCount(len(PCM_SIGNALS_PCM))
            self.pcm_table.setColumnCount(2)
            self.pcm_table.setHorizontalHeaderLabels(["Signal", "Value"])
            self.pcm_table.verticalHeader().setVisible(False)
            self.pcm_table.setMinimumWidth(700)
            self.pcm_table.setMinimumHeight(400)
            self.pcm_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.pcm_table.setFont(QFont("Arial", 18))
            self.pcm_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self.pcm_table.verticalHeader().setSectionResizeMode(QHeaderView.Stretch)
            for row in range(self.pcm_table.rowCount()):
                self.pcm_table.setRowHeight(row, 40)
            for row, signal in enumerate(PCM_SIGNALS_PCM):
                signal_item = QTableWidgetItem(signal)
                value_item = QTableWidgetItem("0")
                signal_item.setFont(QFont("Arial", 18))
                value_item.setFont(QFont("Arial", 18))
                self.pcm_table.setItem(row, 0, signal_item)
                self.pcm_table.setItem(row, 1, value_item)
            pcm_layout.addWidget(self.pcm_table)

            back_button = QPushButton("Back to Main Dashboard")
            back_button.setMinimumSize(1000, 70)
            back_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            back_button.setFont(QFont("Arial", 18))
            back_button.setStyleSheet("padding: 5px; background-color: #333; color: white; border-radius: 5px;")
            back_button.clicked.connect(lambda: self.switch_screen(0))
            pcm_layout.addWidget(back_button, alignment=Qt.AlignBottom | Qt.AlignCenter)
            return pcm_screen
        except Exception as e:
            logger.error(f"Error creating PCM screen: {e}\n{traceback.format_exc()}")
            return QWidget()

    def create_acc_screen(self):
        try:
            acc_screen = QWidget()
            acc_layout = QVBoxLayout(acc_screen)

            row1 = QHBoxLayout()
            row1.setSpacing(30)

            cacc_layout = QHBoxLayout()
            self.cacc_indicator = CACCIndicator()
            cacc_layout.addWidget(self.cacc_indicator)
            self.cacc_mileage_label = QLabel("Current CACC Mileage: N/A")
            self.cacc_mileage_label.setFont(QFont("Arial", 18))
            cacc_layout.addWidget(self.cacc_mileage_label)
            cacc_layout.addStretch()
            row1.addLayout(cacc_layout)

            traffic_layout = QHBoxLayout()
            traffic_container = QWidget()
            traffic_container.setLayout(traffic_layout)

            self.traffic_light_indicator = TrafficLightIndicator()
            traffic_label = QLabel("Traffic Light Phase")
            traffic_label.setFont(QFont("Arial", 18))
            traffic_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            traffic_layout.addWidget(self.traffic_light_indicator)
            traffic_layout.addWidget(traffic_label)
            traffic_container.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)

            row1.addWidget(traffic_container)
            acc_layout.addLayout(row1)

            row2 = QHBoxLayout()
            row2.setSpacing(30)

            vai_layout = QHBoxLayout()
            self.VAI_Indicator = VehicleAheadIndicator()
            vai_layout.addWidget(self.VAI_Indicator)
            self.VAI_Headway_Label = QLabel("Headway: N/A")
            self.VAI_Headway_Label.setFont(QFont("Arial", 18))
            vai_layout.addWidget(self.VAI_Headway_Label)
            self.VAI_Distance_Label = QLabel("Distance: N/A")
            self.VAI_Distance_Label.setFont(QFont("Arial", 18))
            vai_layout.addWidget(self.VAI_Distance_Label)
            vai_layout.addStretch()
            row2.addLayout(vai_layout)

            lcc_layout = QHBoxLayout()
            lcc_container = QWidget()
            lcc_container.setLayout(lcc_layout)

            self.lcc_indicator = LCCIndicator()
            lcc_label = QLabel("            LCC Status")
            lcc_label.setFont(QFont("Arial", 18))
            lcc_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            lcc_layout.addWidget(self.lcc_indicator)
            lcc_layout.addWidget(lcc_label)
            lcc_container.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)

            row2.addWidget(lcc_container)
            acc_layout.addLayout(row2)

            acc_layout.addStretch()

            back_button = QPushButton("Back to Main Dashboard")
            back_button.setMinimumSize(1000, 70)
            back_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            back_button.setFont(QFont("Arial", 18))
            back_button.setStyleSheet("padding: 5px; background-color: #333; color: white; border-radius: 5px;")
            back_button.clicked.connect(lambda: self.switch_screen(0))
            acc_layout.addWidget(back_button, alignment=Qt.AlignBottom | Qt.AlignCenter)

            return acc_screen
        except Exception as e:
            logger.error(f"Error creating ACC screen: {e}\n{traceback.format_exc()}")
            return QWidget()

    def create_dtc_screen(self):
        try:
            dtc_screen = QWidget()
            dtc_layout = QVBoxLayout(dtc_screen)

            self.dtc_status_label = QLabel("DTCs: None")
            self.dtc_status_label.setFont(QFont("Arial", 20))
            self.dtc_status_label.setAlignment(Qt.AlignCenter)
            dtc_layout.addWidget(self.dtc_status_label)

            dtc_layout.addStretch()

            back_button = QPushButton("Back to Main Dashboard")
            back_button.setMinimumSize(1000, 70)
            back_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            back_button.setFont(QFont("Arial", 18))
            back_button.setStyleSheet("padding: 5px; background-color: #333; color: white; border-radius: 5px;")
            back_button.clicked.connect(lambda: self.switch_screen(0))
            dtc_layout.addWidget(back_button, alignment=Qt.AlignBottom | Qt.AlignCenter)
            return dtc_screen
        except Exception as e:
            logger.error(f"Error creating DTC screen: {e}\n{traceback.format_exc()}")
            return QWidget()

    def switch_screen(self, index):
        try:
            self.stacked_widget.setCurrentIndex(index)
        except Exception as e:
            logger.error(f"Error switching screen: {e}\n{traceback.format_exc()}")

    def closeEvent(self, event):
        try:
            self.tx_thread_running = False
            if self.bus:
                self.bus.shutdown()
            event.accept()
        except Exception as e:
            logger.error(f"Error in closeEvent: {e}\n{traceback.format_exc()}")

if __name__ == "__main__":
    try:
        logger.info("Starting application")
        QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QApplication(sys.argv)
        globalFont = QFont("Arial", 18)
        app.setFont(globalFont)
        window = Dashboard()
        window.showFullScreen()
        logger.info("Application started, entering event loop")
        sys.exit(app.exec())
    except Exception as e:
        logger.error(f"Application failed to start: {e}\n{traceback.format_exc()}")
        sys.exit(1)
