# === ИНСТРУКЦИЯ ПО ПЕРЕМЕЩЕНИЮ ФАЙЛОВ ===

# Шаг 1: Скопируйте ваш основной файл бота
# В Windows PowerShell выполните:

Copy-Item "C:\Users\Minylim\Desktop\dist\synergy_bot_v6.py" `
         "C:\Users\Minylim\Desktop\skalpmat-android\synergy_bot_v7.py"

# Шаг 2: Скопируйте .env файл
Copy-Item "C:\Users\Minylim\Desktop\dist\.env" `
         "C:\Users\Minylim\Desktop\skalpmat-android\.env"

# Шаг 3: Проверьте структуру папки
Get-ChildItem "C:\Users\Minylim\Desktop\skalpmat-android\"

# Ожидаемый результат:
# - main.py              (KivyMD приложение)
# - synergy_bot_v7.py    (Ваша логика бота)
# - .env                 (Настройки)
# - requirements.txt     (Зависимости)
# - buildozer.spec       (Android сборка)
# - README.md           (Инструкция)