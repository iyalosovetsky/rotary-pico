import time
from machine import UART, Pin


# --- НАЛАШТУВАННЯ UART (змініть піни під вашу плату) ---
# Для Raspberry Pi Pico: TX=Pin(4), RX=Pin(5), UART ID = 1
uart = UART(1, baudrate=9600,  tx=Pin(8), rx=Pin(9), timeout=10)

step_pin = Pin(6, Pin.OUT)
dir_pin = Pin(5, Pin.OUT)
en_pin = Pin(7, Pin.OUT, value=1)
en_pin.value(0 )

SLAVE_ADDR = 0x02 

def calc_crc(packet):
    crc = 0
    for byte in packet:
        for i in range(8):
            if (crc ^ byte) & 0x01:
                crc = (crc >> 1) ^ 0x8C
            else:
                crc >>= 1
            byte >>= 1
    return crc

# --- ФУНКЦІЯ ЗАПИСУ ---
def tmc_write(reg_addr, data_32bit):
    d3 = (data_32bit >> 24) & 0xFF
    d2 = (data_32bit >> 16) & 0xFF
    d1 = (data_32bit >> 8) & 0xFF
    d0 = data_32bit & 0xFF
    
    packet = bytearray([0x05, SLAVE_ADDR, reg_addr | 0x80, d3, d2, d1, d0])
    packet.append(calc_crc(packet))
    uart.write(packet)
    time.sleep_ms(2)

# --- ФУНКЦІЯ ЧИТАННЯ ---
def tmc_read(reg_addr):
    # 1. Повністю очищаємо буфер перед відправкою
    while uart.any():
        uart.read()
        
    # 2. Формуємо та відправляємо запит (4 байти)
    packet = bytearray([0x05, SLAVE_ADDR, reg_addr & 0x7F])
    packet.append(calc_crc(packet))
    uart.write(packet)
    
    # 3. Чекаємо, поки пакет запиту повністю вийде в лінію
    time.sleep_ms(2) 
    
    # 4. ВАЖЛИВО: Видаляємо з буфера прийому наше власне ЕХО (ті самі 4 байти, що ми відправили)
    if uart.any() >= 4:
        uart.read(4) # Просто "викидаємо" ці байти
        
    # 5. Тепер чекаємо на чисту відповідь від драйвера (має прийти 8 байт)
    time.sleep_ms(5)
    if uart.any() >= 8:
        reply = uart.read(8)
        if calc_crc(reply[:7]) == reply:
            val = (reply[3] << 24) | (reply[4] << 16) | (reply[5] << 8) | reply[6]
            return val
    return None

def _crc8(data):
    crc = 0
    for byte in data:
        for _ in range(8):
            if (crc >> 7) ^ (byte & 1):
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
            byte >>= 1
    return crc


def _read_exact(n, budget_ms=50):
        buf = bytearray()
        deadline = time.ticks_add(time.ticks_ms(), budget_ms)
        while len(buf) < n and time.ticks_diff(deadline, time.ticks_ms()) > 0:
            chunk = uart.read(n - len(buf))
            if chunk:
                buf += chunk
            else:
                time.sleep_ms(1)
        return buf


def read_register(address, reg):
    
        # 1. Повністю очищаємо буфер перед відправкою
        while uart.any():
           uart.read()
        time.sleep_ms(5)
        req = bytearray(4)
        req[0] = 0x05
        req[1] = address
        req[2] = reg & 0x7F
        req[3] = _crc8(req[:3])
        uart.write(req)
        time.sleep_ms(5)
        _read_exact(len(req))  # drain our own echo

        reply = _read_exact(8)
        if len(reply) < 8:
            raise ("TMC2209 addr %d reg 0x%02X: no reply (check wiring/address)" % (address, reg))
        if reply[0] !=  0x05 or reply[1] != 0xFF or reply[2] != reg:
            raise OSError("TMC2209 addr %d reg 0x%02X: bad reply header %r" % (address, reg, reply))
        if _crc8(reply[:7]) != reply[7]:
            raise OSError("TMC2209 addr %d reg 0x%02X: CRC mismatch" % (address, reg))
        return (reply[3] << 24) | (reply[4] << 16) | (reply[5] << 8) | reply[6]

# --- ІНІЦІАЛІЗАЦІЯ ---
def init_system():
    print("Ініціалізація TMC2209...")
    dir_pin.value(1) # Задаємо напрямок руху
    
    tmc_write(0x00, 0x0000001C) # GCONF -> StealthChop2
    tmc_write(0x6C, 0x10000053) # CHOPCONF -> 1/16 мікрокрок
    
    # Струм: робимо середній струм, щоб мотор крутився, але його можна було зупинити рукою
    ihold_irun = (1 << 16) | (14 << 8) | 6  # IRUN=14, IHOLD=6
    tmc_write(0x10, ihold_irun)
    
    tmc_write(0x70, 0x000C01D4) # PWMCONF -> Autoscale=1
    
    # Налаштування порогу StallGuard4 (SGTHRS)
    # Значення від 0 до 255. Почнемо з середнього = 100.
    # Якщо буде зупинятися сам по собі — зменшіть. Якщо не реагуватиме на блок валу — збільшіть.
    tmc_write(0x40, 100) 
    
    print("Калібрування ШІМ у спокої...")
    time.sleep_ms(200)

# --- ГОЛОВНИЙ ТЕСТОВИЙ ЦИКЛ ---
def run_and_monitor_stall():
    init_system()
    print("\n--- СТАРТ РУХУ ТА МОНІТОРИНГУ STALLGUARD ---")
    print("Обережно затисніть вал двигуна пальцями для тесту.\n")
    
    step_state = False
    last_read_time = time.ticks_ms()
    
    try:
        while True:
            # 1. Генеруємо кроки (ШІМ) з фіксованою швидкістю
            # Пауза 500 мкс (0.5 мс) дає частоту 1 кГц — гарна середня швидкість для StallGuard
            step_state = not step_state
            step_pin.value(step_state)
            time.sleep_us(500) 
            
            # 2. Зчитуємо показники StallGuard кожні 100 мс, щоб не перевантажувати UART
            if time.ticks_diff(time.ticks_ms(), last_read_time) > 100:
                #sg_val = tmc_read(0x41) # Читаємо реєстр SG_RESULT
                sg_val = read_register(SLAVE_ADDR,0x41)
                
                if sg_val is not None:
                    # Показник SG_RESULT зменшується при зростанні навантаження
                    # 510 = ідеальний вільний хід, 0 = повне блокування валу
                    print(f"Поточне навантаження (SG_RESULT): {sg_val}")
                    
                    if sg_val < 20: 
                        print("⚠️ УВАГА: Зафіксовано високе навантаження / БЛОКУВАННЯ!")
                else:
                    print("Помилка зв'язку по UART (перевірте підключення)")
                    
                last_read_time = time.ticks_ms()
                
    except KeyboardInterrupt:
        # Зупинка по Ctrl+C у Thonny
        print("\nТест зупинено користувачем.")

# Запуск програми
run_and_monitor_stall()

