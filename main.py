"""
QuakeWatch - ES-Net Serial Data Parser
地震 ESP32 資料解析器 - 即時監測與視覺化
"""

import serial
import serial.tools.list_ports
import struct
import sys
import time
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from collections import deque

# 串列埠設定
BAUD_RATE = 115200

# 資料緩衝區設定
MAX_SAMPLES = 500
x_data = deque(maxlen=MAX_SAMPLES)
y_data = deque(maxlen=MAX_SAMPLES)
z_data = deque(maxlen=MAX_SAMPLES)
time_data = deque(maxlen=MAX_SAMPLES)
timestamp_data = deque(maxlen=MAX_SAMPLES)  # NTP 時間戳記

intensity_history = deque(maxlen=100)
a_history = deque(maxlen=100)
intensity_time = deque(maxlen=100)
intensity_timestamp = deque(maxlen=100)  # NTP 時間戳記

packet_count = {'sensor': 0, 'intensity': 0, 'error': 0}
start_time = time.time()
first_timestamp = None  # 第一個收到的時間戳記


def parse_serial_data(ser):
    """解析串列埠資料"""
    try:
        header = ser.read(1)
        if len(header) != 1:
            return None

        header_byte = header[0]

        if header_byte == 0x53:  # 'S' for Sensor
            # 讀取 20 bytes (1 個 uint64 + 3 個 float)
            data = ser.read(20)
            if len(data) == 20:
                timestamp, x, y, z = struct.unpack('<Qfff', data)
                packet_count['sensor'] += 1
                return ('sensor', timestamp, x, y, z)

        elif header_byte == 0x49:  # 'I' for Intensity
            # 讀取 16 bytes (1 個 uint64 + 2 個 float)
            data = ser.read(16)
            if len(data) == 16:
                timestamp, intensity, a = struct.unpack('<Qff', data)
                packet_count['intensity'] += 1
                return ('intensity', timestamp, intensity, a)
        else:
            # 靜默跳過未知的 header（可能是文字格式或其他資料）
            packet_count['error'] += 1
            return None

    except Exception as e:
        packet_count['error'] += 1
        # 只在錯誤嚴重時才輸出
        if packet_count['error'] % 100 == 0:
            print(f"Error: {e} (總共 {packet_count['error']} 個錯誤)")
        return None


def list_serial_ports():
    """列出所有可用的串列埠"""
    ports = serial.tools.list_ports.comports()
    available_ports = []

    print("\n可用的串列埠:")
    print("="*60)

    if not ports:
        print("未找到任何串列埠!")
        return None

    for i, port in enumerate(ports):
        available_ports.append(port.device)
        print(f"[{i}] {port.device}")
        print(f"    描述: {port.description}")
        if port.manufacturer:
            print(f"    製造商: {port.manufacturer}")
        print()

    return available_ports


def select_serial_port():
    """互動式選擇串列埠"""
    available_ports = list_serial_ports()

    if not available_ports:
        return None

    if len(available_ports) == 1:
        print(f"自動選擇: {available_ports[0]}")
        return available_ports[0]

    while True:
        try:
            choice = input(
                f"請選擇 [0-{len(available_ports)-1}] 或 q 退出: ").strip()
            if choice.lower() == 'q':
                return None
            index = int(choice)
            if 0 <= index < len(available_ports):
                return available_ports[index]
            print(f"請輸入 0-{len(available_ports)-1}")
        except ValueError:
            print("請輸入數字")
        except KeyboardInterrupt:
            return None


def update_plot(frame, ser, lines):
    """更新圖表"""
    global start_time, first_timestamp
    from datetime import datetime

    current_time = time.time() - start_time  # 在迴圈外定義

    for _ in range(10):
        result = parse_serial_data(ser)
        if result is None:
            continue

        current_time = time.time() - start_time  # 更新時間

        if result[0] == 'sensor':
            _, timestamp, x, y, z = result

            # 儲存第一個時間戳記作為參考
            if first_timestamp is None and timestamp > 0:
                first_timestamp = timestamp

            x_data.append(x)
            y_data.append(y)
            z_data.append(z)
            time_data.append(current_time)
            timestamp_data.append(timestamp)

        elif result[0] == 'intensity':
            _, timestamp, intensity, a = result

            # 儲存第一個時間戳記作為參考
            if first_timestamp is None and timestamp > 0:
                first_timestamp = timestamp

            intensity_history.append(intensity)
            a_history.append(a)
            intensity_time.append(current_time)
            intensity_timestamp.append(timestamp)

            # 轉換時間戳記為可讀格式
            if timestamp > 0:
                dt = datetime.fromtimestamp(timestamp / 1000.0)
                time_str = dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
            else:
                time_str = f"{int(current_time):04d}s (No NTP)"

            print(f"[{time_str}] I: {intensity:.2f}, a: {a:.2f} Gal")

    if len(time_data) > 0:
        lines[0].set_data(list(time_data), list(x_data))
        lines[1].set_data(list(time_data), list(y_data))
        lines[2].set_data(list(time_data), list(z_data))

    if len(intensity_time) > 0:
        lines[3].set_data(list(intensity_time), list(intensity_history))
        lines[4].set_data(list(intensity_time), list(a_history))

    # 自動調整 X 軸範圍
    for ax in [ax1, ax2]:
        if len(time_data) > 0:
            ax.set_xlim(max(0, current_time - 10), current_time + 1)

    return lines


def print_statistics():
    """顯示統計"""
    from datetime import datetime

    elapsed = time.time() - start_time
    print("\n" + "="*60)
    print(f"執行時間: {elapsed:.1f} 秒")

    if elapsed > 0:
        print(
            f"感測器封包: {packet_count['sensor']} ({packet_count['sensor']/elapsed:.1f} Hz)")
        print(
            f"強度封包: {packet_count['intensity']} ({packet_count['intensity']/elapsed:.1f} Hz)")
        print(f"錯誤封包: {packet_count['error']}")

    # 顯示時間戳記資訊
    if first_timestamp is not None and first_timestamp > 0:
        dt = datetime.fromtimestamp(first_timestamp / 1000.0)
        print(f"\n首次時間戳記: {dt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

        if len(timestamp_data) > 0:
            latest = timestamp_data[-1]
            if latest > 0:
                dt_latest = datetime.fromtimestamp(latest / 1000.0)
                print(
                    f"最新時間戳記: {dt_latest.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")

                # 計算時間跨度
                duration_ms = latest - first_timestamp
                print(f"資料時間跨度: {duration_ms / 1000.0:.2f} 秒")
    else:
        print("\n⚠ 未接收到有效的 NTP 時間戳記")

    print("="*60)


def main():
    """主程式"""
    global ax1, ax2

    print("QuakeWatch - ES-Net Serial Data Parser")
    print("="*60)

    selected_port = select_serial_port()
    if not selected_port:
        print("未選擇串列埠")
        sys.exit(0)

    try:
        ser = serial.Serial(selected_port, BAUD_RATE, timeout=1)
        print(f"\n✓ 已連接: {selected_port} @ {BAUD_RATE} baud")
    except serial.SerialException as e:
        print(f"\n✗ 錯誤: {e}")
        sys.exit(1)

    # 設定圖表
    try:
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS',
                                           'Heiti TC', 'SimHei']
        plt.rcParams['axes.unicode_minus'] = False
    except:
        pass

    plt.style.use('dark_background')
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

    ax1.set_title('三軸加速度 (Gal)', fontsize=14, fontweight='bold')
    ax1.set_ylabel('加速度 (Gal)')
    ax1.grid(True, alpha=0.3)
    line_x, = ax1.plot([], [], 'r-', label='X 軸', linewidth=1)
    line_y, = ax1.plot([], [], 'g-', label='Y 軸', linewidth=1)
    line_z, = ax1.plot([], [], 'b-', label='Z 軸', linewidth=1)
    ax1.legend(loc='upper right')
    ax1.set_ylim(-100, 100)

    ax2.set_title('JMA 強度', fontsize=14, fontweight='bold')
    ax2.set_xlabel('時間 (秒)')
    ax2.set_ylabel('強度 / PGA (Gal)')
    ax2.grid(True, alpha=0.3)
    line_i, = ax2.plot([], [], 'y-', label='強度',
                       linewidth=2, marker='o', markersize=4)
    line_a, = ax2.plot([], [], 'c-', label='a (Gal)', linewidth=1.5)
    ax2.legend(loc='upper right')
    ax2.set_ylim(-1, 7)

    lines = [line_x, line_y, line_z, line_i, line_a]
    plt.tight_layout()

    print("\n開始接收資料...\n")

    ani = FuncAnimation(fig, update_plot, fargs=(ser, lines),
                        interval=50, blit=True, cache_frame_data=False)

    try:
        plt.show()
    except KeyboardInterrupt:
        print("\n程式終止")
    finally:
        print_statistics()
        ser.close()
        print("串列埠已關閉")


if __name__ == '__main__':
    main()
