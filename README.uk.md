*[English version](README.md)*

# rotary-pico

## 1. Опис

Керуючий модуль для саморобного поворотного стола (turntable) під 3D-сканер типу Creality Raptor, на базі плати **BTT SKR Pico** (RP2040, MicroPython).

- **Вісь X** — обертає стіл (безкінечне обертання, керування швидкістю).
- **Вісь Y** — переміщує каретку зі сканером над столом (циклічний рух між нижньою та верхньою межею).
- **Сервопривід ST3215** — нахиляє голову сканера (циклічний рух між мінімальним і максимальним кутом).

Усі три вузли працюють одночасно та незалежно один від одного (кооперативна багатозадачність на `uasyncio`), керування — консольними командами у стилі G-code.

Проєкт надихнений відео [Creality Raptor Turntable](https://www.youtube.com/watch?v=kjL7HI78B2U&t=881s) — у `table_models/` додані моделі поворотного стола цього ж автора.

### Файли проєкту

| Файл / папка | Призначення |
|---|---|
| `tmc2209.py` | Драйвер TMC2209 через UART (спільна шина, адресація по MS1/MS2) |
| `st3215.py` | Драйвер сервоприводу ST3215 (протокол Feetech SMS/STS) |
| `scanner_rig.py` | Оркестратор: асинхронні задачі X/Y/сервo + консольний парсер команд |
| `main.py` | Простий стендовий тест одного мотора (bring-up/діагностика) |
| `freecad/` | Власні моделі FreeCAD (кроковий двигун, кріплення сервоприводу) |
| `table_models/` | Моделі поворотного стола (STEP) автора надихаючого відео |

## 2. Система команд

Команди подаються по одній на рядок у консолі (REPL):

| Команда | Опис |
|---|---|
| `X SPEED <steps_per_sec>` | Швидкість обертання столу (знак визначає напрямок, 0 = стоп) |
| `X START` | Почати обертання столу |
| `X STOP` | Зупинити обертання столу |
| `Y MIN <steps>` | Нижня межа руху каретки (в мікрокроках) |
| `Y MAX <steps>` | Верхня межа руху каретки (в мікрокроках) |
| `Y SPEED <steps_per_sec>` | Швидкість руху каретки |
| `Y START` | Почати циклічний рух каретки між `MIN` і `MAX` |
| `Y STOP` | Зупинити каретку |
| `S MIN <deg>` | Мінімальний кут нахилу сканера (градуси) |
| `S MAX <deg>` | Максимальний кут нахилу сканера (градуси) |
| `S SPEED <raw_units>` | Швидкість сервоприводу (внутрішні одиниці регістра, підбирається емпірично) |
| `S START` | Почати циклічний нахил між `MIN` і `MAX` |
| `S STOP` | Зупинити сервопривід |
| `STATUS` | Поточний стан усіх трьох осей |
| `HELP` | Довідка по командах |

Приклад сеансу:

```
X SPEED 200
X START
Y MIN 0
Y MAX 3200
Y SPEED 400
Y START
S MIN 30
S MAX 150
S SPEED 300
S START
STATUS
```

## 3. Перелік компонентів

| Компонент | Фото | Опис | Документація |
|---|---|---|---|
| **BTT SKR Pico V1.0** | <img src="https://cdn.shopify.com/s/files/1/1619/4791/files/PICO_fa4f69b4-1193-4923-99ba-fb467d87f334.jpg?v=1695350854" width="200"> | Керуюча плата на RP2040, 2MB flash, 4 вбудовані драйвери TMC2209 (UART, спільна шина з адресацією MS1/MS2), USB-C | [GitHub: bigtreetech/SKR-Pico](https://github.com/bigtreetech/SKR-Pico) |
| **ST3215** | <img src="https://www.waveshare.com/media/catalog/product/cache/1/image/800x800/9df78eab33525d08d6e5fb8d27136e95/s/t/st3215-servo-1_5.jpg" width="200"> | Serial bus servo (Feetech SMS/STS), 360° магнітний енкодер, керування по UART (single-wire), momento до 30 кг·см | [Waveshare Wiki: ST3215 Servo](https://www.waveshare.com/wiki/ST3215_Servo) |
| **NEMA17 34mm** | <img src="https://upload.wikimedia.org/wikipedia/commons/8/83/Nema_17_Stepper_Motor.jpg" width="200"> | Кроковий двигун, коротка (34мм) версія — знижений момент, менша вага/габарит, під драйвери TMC2209 | — |
| **Waveshare Bus Servo Adapter (A)** | <img src="https://www.waveshare.com/media/catalog/product/cache/1/image/800x800/9df78eab33525d08d6e5fb8d27136e95/b/u/bus-servo-adapter-a-1_2.jpg" width="200"> | Перехідник UART (TX/RX) → однопровідна напівдуплексна шина сервоприводів Feetech/Waveshare, живлення сервоприводу | [Waveshare Wiki: Bus Servo Adapter (A)](https://www.waveshare.com/wiki/Bus_Servo_Adapter_(A)) |
