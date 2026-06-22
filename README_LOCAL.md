# 📱 SKALPMAT V7 — Android App

Торговая система для Gate.io futures с адаптивными стратегиями Mean Reversion и Adaptive Scalping.

## 🚀 Быстрый старт в облаке (GitHub Codespaces)

### 1. Откройте проект в Codespaces

1. Создайте новый репозиторий на GitHub
2. Загрузите файлы из этой папки
3. Нажмите **Code** → **Codespaces** → **Create codespace on main**

### 2. Установите зависимости

```bash
# Установка buildozer и зависимостей
pip install buildozer
sudo apt-get update
sudo apt-get install -y git ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-ttf-dev libsdl2-gfx-dev libfreetype6-dev libjpeg-dev libtiff-dev tcl-dev tk-dev libsmmesh-dev libgtk-3-dev libgl1-mesa-dev libglu1-mesa-dev

# Для Android сборки
sudo apt-get install -y openjdk-11-jdk ant
```

### 3. Запустите сборку APK

```bash
# Инициализация buildozer (если нужно)
buildozer init

# Сборка APK (займёт 20-40 минут при первой сборке)
buildozer -v android debug

# Готовый APK будет в папке ./bin/
```

### 4. Установите на телефон

Скачайте `bin/skalpmat-7.0.0-debug.apk` и установите на Android устройство.

---

## 📋 Структура проекта

```
skalpmat-android/
├── main.py                 # KivyMD приложение (точка входа)
├── synergy_bot_v7.py       # Основная логика бота
├── .env                    # Конфигурация (API ключи, настройки)
├── requirements.txt        # Python зависимости
├── buildozer.spec          # Android сборка конфигурация
├── bin/                    # Готовые APK (после сборки)
└── README.md              # Эта инструкция
```

---

## ⚙️ Настройка .env

Откройте `.env` и заполните:

```bash
# Telegram
TELEGRAM_TOKEN=ваш_токен_от_BotFather
TELEGRAM_CHAT_ID=ваш_chat_id

# Gate.io DEMO (для тестов)
DEMO_API_KEY=ваш_demo_key
DEMO_API_SECRET=ваш_demo_secret

# Gate.io REAL (для реальной торговли)
REAL_API_KEY=ваш_real_key
REAL_API_SECRET=ваш_real_secret

ACCOUNT_TYPE=demo          # demo или real
TRADING_MODE=signals_only  # signals_only или live
```

---

## 🎯 Как это работает

### Архитектура:

```
┌─────────────────────────────────────────────────────┐
│                  KivyMD GUI (Android)               │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │   Лог/Консоль│  │  Статус бар  │  │  Карусель  │ │
│  └─────────────┘  └──────────────┘  └────────────┘ │
│  ┌─────────────────────────────────────────────────┐│
│  │            Кнопки управления                    ││
│  │  [Старт] [Позиции] [Статы] [Отчёт] [Закрыть]   ││
│  └─────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────┐
│              SynergyBot (Логика)                    │
│  ┌──────────────┐  ┌───────────────┐                │
│  │ Mean Version │  │  Adaptive     │                │
│  │   Strategy   │  │  Scalping     │                │
│  └──────────────┘  └───────────────┘                │
│         ↓                  ↓                         │
│  ┌─────────────────────────────────────────────────┐│
│  │           Gate.io API + Telegram                ││
│  └─────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

### Стратегии:

**Mean Reversion (MR)**:
- Торговля парами (BTC/ETH и т.д.)
- Z-score для входа/выхода
- Таймфреймы: 15m, 30m
- 1-2 сделки в день

**Adaptive Scalping (AS)**:
- Скальпинг на 5m/15m/30m
- Self-optimization параметров
- Market Regime Detection
- Smart Trailing Stop

---

## 🔧 Локальная разработка (Python)

Для тестирования на ПК:

```bash
# Установите зависимости
pip install -r requirements.txt

# Запустите KivyMD приложение
python main.py
```

**Примечание**: Для загрузки вашего исходного кода:
1. Скопируйте `synergy_bot_v6.py` из `Desktop/dist/` 
2. Переименуйте в `synergy_bot_v7.py`
3. Положите в папку проекта

---

## 📊 Функции приложения

- ✅ Старт/Стоп бота
- ✅ Просмотр открытых позиций (карусель)
- ✅ Статистика сигналов и сделок
- ✅ Дневной отчёт (PnL, комиссии)
- ✅ Закрытие всех позиций
- ✅ Бэктест на 1000 свечей
- ✅ Настройки через UI
- ✅ Telegram уведомления
- ✅ Логирование в реальном времени
- ✅ **🌙 Фоновая служба** — торговля при заблокированном экране

---

## 🛠️ Troubleshooting

### Ошибка при сборке: "NDK not found"
```bash
export ANDROIDNDK=$HOME/.buildozer/android/platform/android-ndk-r25b
```

### Ошибка: "No module named 'pandas'"
Убедитесь, что `pandas` указан в `requirements.txt` и `buildozer.spec`

### Приложение закрывается при запуске
Проверьте логи:
```bash
adb logcat | grep -i python
```

### Telegram не отправляет сообщения
1. Проверьте токен от @BotFather
2. Узнайте Chat ID через @userinfobot
3. Убедитесь, что бот добавлен в чат

---

## 📝 Лицензия

MIT License. Используйте на свой риск.

## ⚠️ Предупреждение

Торговля фьючерсами связана с высоким риском. Тестируйте стратегию на DEMO аккаунте перед использованием реальных средств.

---

**Разработано для SKALPMAT V7**  
Версия: 7.0.0  
Дата: 2026