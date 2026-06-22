# 🚀 Быстрый старт — SKALPMAT V7 на Android

## 📋 Что нужно сделать (3 шага)

### Шаг 1: Скопируйте файлы

Откройте **PowerShell** и выполните:

```powershell
# Перейдите в папку проекта
cd C:\Users\Minylim\Desktop\skalpmat-android

# Скопируйте ваш код
Copy-Item "C:\Users\Minylim\Desktop\dist\synergy_bot_v6.py" "synergy_bot_v7.py"

# Скопируйте настройки
Copy-Item "C:\Users\Minylim\Desktop\dist\.env" ".env"

# Проверьте
Get-ChildItem
```

✅ Должно появиться 6 файлов:
- `main.py`
- `synergy_bot_v7.py`
- `.env`
- `requirements.txt`
- `buildozer.spec`
- `README.md`

---

### Шаг 2: Загрузите на GitHub

1. Создайте новый репозиторий на GitHub (например, `skalpmat-android`)
2. Загрузите все файлы из папки `C:\Users\Minylim\Desktop\skalpmat-android\`

**Вариант A — через браузер:**
- Зайдите на github.com/new
- Создайте репозиторий
- Перетащите файлы в окно браузера (Upload files)

**Вариант B — через Git:**
```bash
cd C:\Users\Minylim\Desktop\skalpmat-android
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/ВАШ_ЛОГИН/skalpmat-android.git
git push -u origin main
```

---

### Шаг 3: Запустите сборку в облаке

**Вариант A — GitHub Actions (автоматически):**

1. Откройте ваш репозиторий на GitHub
2. Перейдите во вкладку **Actions**
3. Нажмите **Build Android APK** workflow
4. Нажмите **Run workflow** → **Run workflow**
5. Ждите ~30-40 минут (первая сборка долгая)
6. Скачайте APK из артефактов или Releases

**Вариант B — GitHub Codespaces (ручная сборка):**

1. Откройте репозиторий
2. Нажмите **Code** → **Codespaces** → **Create codespace on main**
3. Дождитесь загрузки среды (~2-5 минут)
4. В терминале выполните:
   ```bash
   buildozer -v android debug
   ```
5. Скачайте готовый APK из папки `bin/`

---

## 📥 Установка на телефон

1. Скачайте APK файл (из GitHub Releases или артефактов)
2. На телефоне: Настройки → Безопасность → Разрешить установку неизвестных приложений
3. Откройте APK файл и нажмите **Установить**
4. Запустите приложение **SKALPMAT V7**

---

## ⚙️ Настройка перед запуском

1. Откройте `.env` файл
2. Заполните:
   - `TELEGRAM_TOKEN` — токен от @BotFather
   - `TELEGRAM_CHAT_ID` — ваш Chat ID
   - `DEMO_API_KEY` и `DEMO_API_SECRET` — для тестов
   - `ACCOUNT_TYPE=demo` — для начала используйте демо

---

## 🎮 Как пользоваться приложением

### Главный экран:
```
┌────────────────────────────────────┐
│  SKALPMAT V7                       │
├────────────────────────────────────┤
│  [Лог событий]                     │
│  [12:30:45] ✅ Бот запущен         │
│  [12:31:00] 🔍 BTC_USDT (5m)       │
│  ...                               │
├────────────────────────────────────┤
│  🟢 BTC_USDT (buy) | +15.23 USDT   │ ← Карусель позиций
├────────────────────────────────────┤
│  [Старт] [Позиции] [Статы] [Настр] │
└────────────────────────────────────┘
```

### Кнопки:
- **Старт/Стоп** — запуск/остановка бота
- **Позиции** — показать открытые позиции
- **Статистика** — статистика сигналов и сделок
- **Отчёт** — дневной PnL отчёт
- **Закрыть всё** — закрыть все позиции
- **Бэктест** — тест стратегии на истории
- **Настройки** — изменить параметры

---

## ❓ FAQ

### Q: Сборка падает с ошибкой "No module named 'pandas'"
**A:** Убедитесь, что `pandas` указан в `requirements.txt` и `buildozer.spec`

### Q: Как получить Telegram токен?
**A:** 
1. Откройте @BotFather в Telegram
2. Нажмите `/newbot`
3. Следуйте инструкциям
4. Скопируйте токен

### Q: Как узнать Chat ID?
**A:** Откройте @userinfobot и нажмите Start

### Q: Бот не торгует, только сигналы
**A:** Измените в `.env`:
```bash
TRADING_MODE=live  # вместо signals_only
```

### Q: Сколько времени занимает сборка?
**A:** 
- Первая сборка: 30-40 минут
- Повторная: 5-10 минут

### Q: Можно ли собрать на ПК?
**A:** Да, но лучше использовать облако (не занимает место на диске)

---

## 📊 Структура проекта

```
skalpmat-android/
├── main.py                 # KivyMD GUI приложение
├── synergy_bot_v7.py       # Ваша торговая логика
├── .env                    # Настройки (API ключи)
├── requirements.txt        # Python зависимости
├── buildozer.spec          # Android сборка config
├── README.md              # Документация
├── bin/                   # Готовые APK (после сборки)
├── .devcontainer/         # Codespaces конфигурация
└── .github/
    └── workflows/
        └── build-apk.yml  # CI/CD для авто-сборки
```

---

## 🔐 Безопасность

⚠️ **Никогда не коммитьте реальные API ключи в GitHub!**

Используйте:
1. Демо аккаунт для тестов
2. GitHub Secrets для реальных ключей
3. Или редактируйте `.env` после скачивания APK

---

## 📞 Поддержка

- GitHub Issues: https://github.com/ВАШ_ЛОГИН/skalpmat-android/issues
- Telegram: ваш канал

---

**Удачной торговли! 🚀📈**