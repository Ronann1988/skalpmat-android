# === СКОПИРУЙТЕ И ВЫПОЛНИТЕ ЭТИ КОМАНДЫ В POWERSHELL ===

# Шаг 1: Настройте Git (замените на ваши данные!)
git config user.email "ваш_email@example.com"
git config user.name "Ваше Имя"

# Шаг 2: Сделайте коммит
git commit -m "🚀 SKALPMAT V7 Android with background service

Features:
- KivyMD mobile application
- 🌙 Foreground service for 24/7 trading
- Mean Reversion + Adaptive Scalping strategies
- Smart Trailing Stop (ATR-based)
- Self-optimization and Market Regime Detection
- Telegram notifications
- Position carousel with real-time updates
- Backtest on 1000 candles
- CI/CD via GitHub Actions

Permissions: FOREGROUND_SERVICE, WAKE_LOCK, INTERNET"

# Шаг 3: Переименуйте ветку в main
git branch -M main

# Шаг 4: Добавьте удалённый репозиторий (замените USER на ваш логин)
git remote add origin https://github.com/ВАШ_LOGIM/skalpmat-android.git

# Шаг 5: Отправьте на GitHub
git push -u origin main

# === ГОТОВО! ===
# После выполнения:
# 1. Откройте https://github.com/ВАШ_LOGIM/skalpmat-android
# 2. Перейдите во вкладку Actions
# 3. Включите GitHub Actions если нужно
# 4. Запустите workflow "Build Android APK"