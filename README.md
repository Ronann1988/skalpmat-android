# 🌙 SKALPMAT V7 — Android Trading Bot

> **Автономная торговая система для Gate.io futures с фоновой службой**

[![Build APK](https://github.com/USER/skalpmat-android/actions/workflows/build-apk.yml/badge.svg)](https://github.com/USER/skalpmat-android/actions/workflows/build-apk.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Android](https://img.shields.io/badge/Android-7.0+-green.svg)](https://www.android.com/)

---

## 🚀 Возможности

### 📱 Торговые стратегии
- **Mean Reversion** — Возврат к среднему (пары BTC/ETH, 15m-30m)
- **Adaptive Scalping** — Адаптивный скальпинг (5m-30m)
- **Smart Trailing Stop** — ATR-based трейлинг-стоп
- **Self-optimization** — Авто-подстройка параметров
- **Market Regime Detection** — Определение режима рынка

### 🌙 Фоновая служба
- ✅ **Торговля 24/7** — Работает при заблокированном экране
- ✅ **永久的ное уведомление** — Статус и PnL в статус баре
- ✅ **Экономия батареи** — ~2-5% в час
- ✅ **Не останавливается** — Даже когда телефон в кармане

### 📊 Интерфейс
- 📈 Карусель открытых позиций (обновление каждые 4 сек)
- 🔔 Telegram уведомления о сделках
- 📋 Дневные отчёты (PnL, комиссии, статистика)
- ⚙️ Настройки через UI
- 🧪 Бэктест на 1000 свечей

---

## 📸 Скриншоты

```
┌──────────────────────────────────┐
│  ☰  SKALPMAT V7           ⚙️    │
├──────────────────────────────────┤
│ ╔══════════════════════════════╗ │
│ ║ [12:30:45] 🚀 Запуск...      ║ │
│ ║ [12:30:46] ✅ Gate.io OK     ║ │
│ ║ [12:31:15] ⚡ BUY сигнал      ║ │
│ ║ [12:31:16] ✅ Позиция открыта║ │
│ ╚══════════════════════════════╝ │
├──────────────────────────────────┤
│ 🟢 BTC_USDT (buy) | +15.23 USDT │
├──────────────────────────────────┤
│ 🟢 PnL: +23.45 USDT              │
│ 💵 Баланс: 1023.45 USDT          │
├──────────────────────────────────┤
│ [▶️ Старт] [📊 Позиции]          │
│ [📈 Статы] [📋 Отчёт]            │
│ [❌ Закрыть] [🧪 Бэктест]        │
│ [⚙️ Настройки]                   │
│ ───────────────────────────────  │
│ 🌙 Работать в фоне       [✓]    │
└──────────────────────────────────┘
```

---

## ⚡ Быстрый старт

### 1. Скачайте APK
Перейдите в [Releases](https://github.com/USER/skalpmat-android/releases) и скачайте последнюю версию

### 2. Установите на телефон
```
Настройки → Безопасность → Неизвестные источники → Разрешить
```

### 3. Настройте
Откройте `.env` (в приложении через Настройки) и заполните:
- Telegram токен и Chat ID
- Gate.io API ключи (DEMO для тестов)
- Выберите `ACCOUNT_TYPE=demo`

### 4. Запустите
1. Включите **"🌙 Работать в фоне"**
2. Нажмите **"▶️ Старт"**
3. Готово! Телефон можно заблокировать

---

## 🔧 Сборка из исходников

### GitHub Actions (рекомендуется)
1. Fork этого репозитория
2. Actions → Build Android APK → Run workflow
3. Через 30-40 минут APK будет в Releases

### GitHub Codespaces
```bash
# Откройте Codespace
# Дождитесь установки зависимостей
buildozer -v android debug

# APK будет в папке bin/
```

### Локально (Linux/Mac)
```bash
git clone https://github.com/USER/skalpmat-android.git
cd skalpmat-android
pip install buildozer
buildozer android debug
```

---

## 📁 Структура проекта

```
skalpmat-android/
├── main.py                 # KivyMD приложение
├── synergy_bot_v7.py       # Торговая логика
├── .env                    # Настройки (не коммитить!)
├── buildozer.spec          # Android сборка
├── requirements.txt        # Python зависимости
├── .github/workflows/      # CI/CD
└── docs/                   # Документация
```

---

## 🌙 Фоновая служба

### Как это работает:
1. Включите переключатель "🌙 Работать в фоне"
2. Запустите бота
3. Приложение создаст Foreground Service с уведомлением
4. Android не убивает процесс даже при выключенном экране

### Разрешения:
- `FOREGROUND_SERVICE` — фоновая работа
- `WAKE_LOCK` — предотвращение сна
- `INTERNET` — подключение к Gate.io
- `ACCESS_NETWORK_STATE` — проверка сети

### Влияние на батарею:
- ~2-5% в час (зависит от частоты сканирования)
- Основное потребление: сетевые запросы (раз в 15 сек)

---

## ⚙️ Настройки

### Стратегии:
| Параметр | Mean Reversion | Adaptive Scalping |
|----------|----------------|-------------------|
| Пары | BTC_USDT, ETH_USDT | 10+ альткоинов |
| Таймфреймы | 15m, 30m | 5m, 15m, 30m |
| Макс позиций | 2 | 3 |
| Кулдаун | 120 сек | 60 сек |

###Risk management:
- `LEVERAGE=10` — Кредитное плечо
- `QTY_PERCENTAGE=5` — % от баланса в сделку
- `DAILY_LOSS_LIMIT=3` — Дневной лимит убытков
- `MAX_OPEN_POSITIONS=5` — Макс открытых позиций

---

## 📊 Производительность

### Требования:
- Android 7.0+ (API 24)
- 2GB RAM (рекомендуется 4GB)
- 50MB свободного места
- Интернет соединение

### Тесты:
- Первая сборка: 30-40 минут
- Повторная сборка: 5-10 минут
- Размер APK: ~35MB (debug)
- Потребление RAM: ~150MB

---

## 🔐 Безопасность

⚠️ **ВАЖНО:**
- Не коммитьте реальные API ключи в GitHub
- Тестируйте на DEMO аккаунте
- Используйте GitHub Secrets для ключей

### Рекомендуемые настройки:
```bash
ACCOUNT_TYPE=demo          # Всегда начинайте с демо
TRADING_MODE=signals_only  # Только сигналы для теста
```

---

## 📖 Документация

- [START_HERE.md](START_HERE.md) — Быстрый старт за 3 шага
- [FINAL_GUIDE.md](FINAL_GUIDE.md) — Полное руководство
- [BACKGROUND_SERVICE.md](BACKGROUND_SERVICE.md) — Фоновая служба
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) — Структура проекта
- [CHECKLIST.md](CHECKLIST.md) — Чек-лист готовности

---

## 🤝 Contributing

1. Fork репозиторий
2. Создайте feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit изменения (`git commit -m 'Add AmazingFeature'`)
4. Push в branch (`git push origin feature/AmazingFeature`)
5. Откройте Pull Request

---

## 📝 Changelog

### v7.0.0 (Июнь 2026)
- ✅ KivyMD приложение для Android
- ✅ 🌙 Фоновая служба (работа при заблокированном экране)
- ✅ Mean Reversion стратегия
- ✅ Adaptive Scalping с self-optimization
- ✅ Smart Trailing Stop (ATR-based)
- ✅ Telegram уведомления
- ✅ CI/CD через GitHub Actions
- ✅ Карусель открытых позиций
- ✅ Бэктест на 1000 свечей

---

## 📞 Поддержка

- GitHub Issues: [Сообщить о проблеме](https://github.com/USER/skalpmat-android/issues)
- Telegram: [Канал поддержки](https://t.me/YOUR_CHANNEL)
- Документация: [Полная документация](docs/)

---

## ⚠️ Дисклеймер

Торговля фьючерсами связана с высоким риском потери средств. Используйте только те деньги, которые готовы потерять. Авторы не несут ответственности за ваши финансовые решения.

**Всегда тестируйте стратегии на DEMO аккаунте перед использованием реальных средств!**

---

## 📄 Лицензия

MIT License — см. [LICENSE](LICENSE) файл

---

## 🙏 Благодарности

- [Kivy](https://kivy.org/) — Кроссплатформенный GUI
- [KivyMD](https://kivymd.readthedocs.io/) — Material Design для Kivy
- [Buildozer](https://buildozer.readthedocs.io/) — Сборка Android приложений
- [Gate.io](https://www.gate.io/) — Криптобиржа
- [Python](https://www.python.org/) — Язык программирования

---

<div align="center">

**SKALPMAT V7** — Торговля без ограничений 🚀📱🌙

[Начать торговлю](#-быстрый-старт) • [Документация](#-документация) • [Сообщить о проблеме](https://github.com/USER/skalpmat-android/issues)

</div>