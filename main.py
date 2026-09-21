# ============================================================
# 가스 누출 조기 경보 시스템
# Raspberry Pi Pico 2 W + MQ-2 + WS2813
#
# MQ-2  : GP26 (ADC0)
# WS2813 : GP16
# LED 수 : 10개
#
# wifi_config.py
# ----------------
# WIFI_SSID = "WiFi이름"
# WIFI_PASSWORD = "WiFi비밀번호"
# ----------------
# ============================================================

import network
import socket
import time
import json
from machine import Pin, ADC
from neopixel import NeoPixel

from wifi_config import WIFI_SSID, WIFI_PASSWORD


# ============================================================
# 1. 기본 설정
# ============================================================

# MQ-2 센서
MQ2_PIN = 26
mq2 = ADC(Pin(MQ2_PIN))

# WS2813
LED_PIN = 16
LED_COUNT = 10

# WS2813에서 필요한 타이밍
TIMING = (280, 515, 515, 745)

led = NeoPixel(
    Pin(LED_PIN),
    LED_COUNT,
    timing=TIMING
)

# 측정 주기
SENSOR_INTERVAL = 0.5

# 위험 단계 기준
# 실제 가스 농도(ppm)가 아니라 MQ-2 ADC 상대값 기준입니다.
WARNING_LEVEL = 35
DANGER_LEVEL = 65


# ============================================================
# 2. Wi-Fi 연결
# ============================================================

print()
print("======================================")
print("   GAS LEAK EARLY WARNING SYSTEM")
print("======================================")
print("Wi-Fi 연결 중...")

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

if not wlan.isconnected():

    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    timeout = 20
    start_time = time.time()

    while not wlan.isconnected():

        if time.time() - start_time > timeout:
            print("Wi-Fi 연결 시간 초과")
            break

        print(".", end="")
        time.sleep(1)

print()

if wlan.isconnected():

    ip_address = wlan.ifconfig()[0]

    print("Wi-Fi 연결 성공!")
    print("IP 주소:", ip_address)
    print()
    print("휴대폰 또는 PC에서 아래 주소로 접속하세요.")
    print("http://" + ip_address)

else:

    print("Wi-Fi 연결 실패")


# ============================================================
# 3. 센서 데이터 변수
# ============================================================

sensor_value = 0
voltage = 0.0
percentage = 0.0

status = "정상"
status_code = "good"

previous_value = 0

# 위험 상태에서 LED 점멸용
danger_blink = False
last_blink_time = time.ticks_ms()

# 센서값을 조금 안정적으로 만들기 위한 이동 평균
sensor_history = []

MAX_HISTORY = 10


# ============================================================
# 4. 센서값 읽기
# ============================================================

def read_sensor():

    global sensor_history

    raw = mq2.read_u16()

    # 최근 측정값 저장
    sensor_history.append(raw)

    if len(sensor_history) > MAX_HISTORY:
        sensor_history.pop(0)

    # 이동 평균
    average = sum(sensor_history) / len(sensor_history)

    # ADC 16비트 값을 0~100%로 변환
    percent = (average / 65535) * 100

    # 0~3.3V 기준 전압 계산
    volts = (average / 65535) * 3.3

    return int(average), volts, percent


# ============================================================
# 5. 위험 단계 판단
# ============================================================

def check_status(percent):

    if percent < WARNING_LEVEL:

        return "정상", "good"

    elif percent < DANGER_LEVEL:

        return "주의", "warning"

    else:

        return "위험", "danger"


# ============================================================
# 6. LED 전체 끄기
# ============================================================

def clear_led():

    for i in range(LED_COUNT):

        led[i] = (0, 0, 0)

    led.write()


# ============================================================
# 7. LED 상태 표시
# ============================================================

def update_leds(current_status):

    global danger_blink
    global last_blink_time

    # -----------------------------
    # 정상
    # -----------------------------

    if current_status == "good":

        danger_blink = False

        for i in range(LED_COUNT):
            led[i] = (0, 60, 0)

        led.write()


    # -----------------------------
    # 주의
    # -----------------------------

    elif current_status == "warning":

        danger_blink = False

        # LED 5개 정도 노란색
        for i in range(LED_COUNT):

            if i < 5:
                led[i] = (60, 45, 0)

            else:
                led[i] = (0, 0, 0)

        led.write()


    # -----------------------------
    # 위험
    # -----------------------------

    elif current_status == "danger":

        now = time.ticks_ms()

        # 0.5초마다 ON/OFF
        if time.ticks_diff(now, last_blink_time) >= 500:

            danger_blink = not danger_blink
            last_blink_time = now

        if danger_blink:

            for i in range(LED_COUNT):
                led[i] = (70, 0, 0)

        else:

            for i in range(LED_COUNT):
                led[i] = (0, 0, 0)

        led.write()


# ============================================================
# 8. HTML 웹페이지
# ============================================================

HTML = """<!DOCTYPE html>
<html lang="ko">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width,
      initial-scale=1.0">

<title>가스 누출 조기 경보 시스템</title>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    font-family:
        Arial,
        "Noto Sans KR",
        sans-serif;

    background:
        linear-gradient(
            135deg,
            #111827,
            #1f2937
        );

    color: white;

    min-height: 100vh;

    padding: 20px;
}

.container {

    max-width: 1000px;

    margin: auto;
}

header {

    text-align: center;

    margin-bottom: 25px;
}

header h1 {

    margin-bottom: 8px;

    font-size: 30px;
}

header p {

    color: #cbd5e1;

    margin: 0;
}

.cards {

    display: grid;

    grid-template-columns:
        repeat(
            auto-fit,
            minmax(180px, 1fr)
        );

    gap: 15px;

    margin-bottom: 20px;
}

.card {

    background:
        rgba(
            255,
            255,
            255,
            0.08
        );

    border:
        1px solid
        rgba(
            255,
            255,
            255,
            0.12
        );

    border-radius: 18px;

    padding: 22px;

    text-align: center;

    backdrop-filter:
        blur(10px);
}

.card-title {

    color: #cbd5e1;

    font-size: 14px;

    margin-bottom: 10px;
}

.card-value {

    font-size: 30px;

    font-weight: bold;
}

.status {

    border-radius: 18px;

    padding: 25px;

    text-align: center;

    margin-bottom: 20px;

    background:
        rgba(
            255,
            255,
            255,
            0.08
        );
}

.status-title {

    color: #cbd5e1;

    font-size: 15px;

    margin-bottom: 8px;
}

.status-value {

    font-size: 42px;

    font-weight: bold;
}

.good {
    color: #22c55e;
}

.warning {
    color: #facc15;
}

.danger {
    color: #ef4444;
}

.chart-box {

    background:
        rgba(
            255,
            255,
            255,
            0.08
        );

    border-radius: 18px;

    padding: 20px;

    margin-bottom: 20px;
}

.chart-box h2 {

    font-size: 18px;

    margin-top: 0;
}

.info {

    background:
        rgba(
            255,
            255,
            255,
            0.05
        );

    border-radius: 15px;

    padding: 18px;

    color: #cbd5e1;

    font-size: 14px;

    line-height: 1.7;
}

@media (max-width: 600px) {

    body {
        padding: 12px;
    }

    header h1 {
        font-size: 23px;
    }

    .card-value {
        font-size: 25px;
    }

    .status-value {
        font-size: 35px;
    }
}

</style>

</head>


<body>

<div class="container">

<header>

<h1>🚨 가스 누출 조기 경보 시스템</h1>

<p>
Raspberry Pi Pico 2 W + MQ-2 + WS2813
</p>

</header>


<div class="status">

<div class="status-title">
현재 상태
</div>

<div
    id="status"
    class="status-value good"
>
정상
</div>

</div>


<div class="cards">

<div class="card">

<div class="card-title">
MQ-2 센서값
</div>

<div
    id="sensor"
    class="card-value"
>
0
</div>

</div>


<div class="card">

<div class="card-title">
전압
</div>

<div
    id="voltage"
    class="card-value"
>
0.00 V
</div>

</div>


<div class="card">

<div class="card-title">
상대 위험도
</div>

<div
    id="percentage"
    class="card-value"
>
0.0 %
</div>

</div>

</div>


<div class="chart-box">

<h2>📊 실시간 센서 변화</h2>

<canvas id="chart"></canvas>

</div>


<div class="info">

<strong>위험 단계 기준</strong>

<br>

🟢 정상 :
센서 상대값 35% 미만

<br>

🟡 주의 :
센서 상대값 35% 이상 65% 미만

<br>

🔴 위험 :
센서 상대값 65% 이상

<br><br>

※ MQ-2 값은 환경과 센서 상태에 따라 달라집니다.
이 시스템의 수치는 실제 가스 농도(ppm)가 아닌
센서의 상대적인 ADC 측정값을 이용한 교육용 경보 기준입니다.

</div>

</div>


<script>

const ctx =
document
.getElementById("chart")
.getContext("2d");


const chart =
new Chart(
    ctx,
    {

        type: "line",

        data: {

            labels: [],

            datasets: [

                {

                    label:
                    "MQ-2 센서값",

                    data: [],

                    borderWidth: 2,

                    pointRadius: 0,

                    tension: 0.25

                }

            ]

        },

        options: {

            responsive: true,

            animation: false,

            scales: {

                y: {

                    beginAtZero: true,

                    max: 65535

                }

            }

        }

    }
);


async function updateData() {

    try {

        const response =
            await fetch(
                "/data"
            );

        const data =
            await response.json();


        document
            .getElementById("sensor")
            .textContent =
            data.sensor;


        document
            .getElementById("voltage")
            .textContent =
            data.voltage.toFixed(2)
            + " V";


        document
            .getElementById("percentage")
            .textContent =
            data.percentage.toFixed(1)
            + " %";


        const statusElement =
            document
            .getElementById("status");


        statusElement.textContent =
            data.status;


        statusElement.className =
            "status-value "
            + data.status_code;


        const now =
            new Date()
            .toLocaleTimeString();


        chart.data.labels.push(now);

        chart.data.datasets[0]
            .data.push(data.sensor);


        if (
            chart.data.labels.length
            > 60
        ) {

            chart.data.labels.shift();

            chart.data.datasets[0]
                .data.shift();

        }


        chart.update();

    }

    catch(error) {

        console.log(
            "데이터 수신 오류:",
            error
        );

    }

}


updateData();

setInterval(
    updateData,
    500
);

</script>

</body>

</html>
"""


# ============================================================
# 9. JSON 데이터 생성
# ============================================================

def get_json_data():

    global sensor_value
    global voltage
    global percentage
    global status
    global status_code

    data = {
        "sensor": sensor_value,
        "voltage": voltage,
        "percentage": percentage,
        "status": status,
        "status_code": status_code
    }

    return json.dumps(data)


# ============================================================
# 10. HTTP 응답 전송
# ============================================================

def send_response(client, content, content_type="text/html"):

    response = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: "
        + content_type
        + "\r\n"
        "Connection: close\r\n"
        "\r\n"
        + content
    )

    try:

        client.send(response)

    except:

        pass


# ============================================================
# 11. 웹 서버 시작
# ============================================================

addr = socket.getaddrinfo(
    "0.0.0.0",
    80
)[0][-1]

server = socket.socket()

server.setsockopt(
    socket.SOL_SOCKET,
    socket.SO_REUSEADDR,
    1
)

server.bind(addr)

server.listen(1)

server.settimeout(0.05)

print()
print("웹 서버 시작!")
print("http://" + wlan.ifconfig()[0])
print()


# ============================================================
# 12. 메인 루프
# ============================================================

last_sensor_time = time.ticks_ms()

while True:

    # --------------------------------------------------------
    # 센서 측정
    # --------------------------------------------------------

    now = time.ticks_ms()

    if time.ticks_diff(
        now,
        last_sensor_time
    ) >= int(SENSOR_INTERVAL * 1000):

        last_sensor_time = now

        sensor_value, voltage, percentage = read_sensor()

        status, status_code = check_status(
            percentage
        )

        update_leds(status_code)

        print(
            "MQ-2:",
            sensor_value,
            "| 전압:",
            round(voltage, 2),
            "V",
            "| 위험도:",
            round(percentage, 1),
            "%",
            "| 상태:",
            status
        )


    # --------------------------------------------------------
    # 웹 요청 처리
    # --------------------------------------------------------

    try:

        client, remote_addr = server.accept()

        request = client.recv(1024)

        request_text = request.decode(
            "utf-8",
            "ignore"
        )

        # /data 요청
        if "GET /data" in request_text:

            data = get_json_data()

            send_response(
                client,
                data,
                "application/json"
            )

        # 그 외 요청
        else:

            send_response(
                client,
                HTML,
                "text/html; charset=UTF-8"
            )

        client.close()

    except OSError:

        # 현재 접속 요청이 없으면
        # 계속 센서 측정
        pass

    except Exception as e:

        print(
            "서버 오류:",
            e
        )

        try:
            client.close()
        except:
            pass
