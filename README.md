# ESP32-C3 DHT22 Monitoring System
#### By Topi Heikkilä

## Purpose

A temperature and humidity monitoring system using an ESP32-C3 and three DHT22 sensors. The system collects measurements and sends them to a computer for local storage and visualization. The project is made for customer of mine to collect temperature and humidity data of client's three beehives.

## Components

- ESP32-C3 Super Mini
- 3 × DHT22 / AM2302 sensors
- 4.7 kΩ pull-up resistors
- cables for power, gnd and data

## Wirign
<img width="1742" height="1082" alt="wiring" src="https://github.com/user-attachments/assets/37cfd00b-a598-48c6-ba0f-a7e5db858530" />


## Implementation

The ESP32-C3 creates its own Wi-Fi access point and runs a simple HTTP server. The three sensors are connected to GPIO 3, 7 and 10.

A Python desktop application retrieves the measurements using HTTP/JSON and stores them in a local SQLite database. The application also provides historical graphs for temperature and humidity.

<img width="3508" height="1741" alt="system" src="https://github.com/user-attachments/assets/a5304d27-8f08-40c9-ad6d-b81870fb5f59" />


## Methods

- Arduino/C++ firmware
- DHT22 sensor readings
- Wi-Fi and HTTP communication
- JSON data transfer
- Python and Tkinter
- SQLite database
- Matplotlib visualization

## Result

The result is a simple local monitoring system capable of collecting, storing and visualizing temperature and humidity data from three different locations.

<img width="977" height="402" alt="monitor" src="https://github.com/user-attachments/assets/46a45f87-4faa-4bee-bfae-b4e0308b82f8" />
