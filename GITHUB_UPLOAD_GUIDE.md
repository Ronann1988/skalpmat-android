# 🚀 Загрузка на GitHub — Пошаговая инструкция

## 📋 Что уже сделано

✅ Все файлы готовы в папке: `C:\Users\Minylim\Desktop\skalpmat-android\`
✅ 14 файлов включая код, документацию и CI/CD
✅ Git репозиторий инициализирован
✅ Все файлы добавлены в staging

---

## 🔧 Шаг 1: Настройте Git (1 минута)

Откройте **PowerShell** в папке проекта и выполните:

```powershell
cd C:\Users\Minylim\Desktop\skalpmat-android

# Замените на ваши данные!
git config user.email "ваш_email@пример.com"
git config user.name "Ваше Имя"
```

**Как узнать ваш GitHub email:**
1. Откройте GitHub в браузере
2. Кликните на аватарку → Settings
3. Emails → Найдите Primary email или добавьте новый

---

## 📝 Шаг 2: Сделайте коммит

```powershell
git commit -m "SKALPMAT V7 Android with background service"
```

---

## 🌐 Шаг 3: Создайте репозиторий на GitHub

1. Откройте https://github.com/new
2. **Repository name:** `skalpmat-android`
3. **Description:** `Android trading bot with background service for Gate.io futures`
4. **Public** (или Private если хотите скрыть)
5. ❌ **НЕ ставьте** галочки "Add README" и другие
6. Нажмите **Create repository**

---

## 🔗 Шаг 4: Привяжите репозиторий

Вернитесь в PowerShell и выполните (замените `ВАШ_ЛОГИН` на ваш GitHub логин):

```powershell
git branch -M main
git remote add origin https://github.com/ВАШ_ЛОГИН/skalpmat-android.git
git push -u origin main
```

**Пример:**
Если ваш логин `alextrader`, тогда:
```powershell
git remote add origin https://github.com/alextrader/skalpmat-android.git
```

---

## ✅ Шаг 5: Проверьте загрузку

1. Откройте https://github.com/ВАШ_ЛОГИН/skalpmat-android
2. Вы должны увидеть все файлы
3. Внизу страницы: "1 commit"

---

## ⚙️ Шаг 6: Включите GitHub Actions

1. В репозитории перейдите во вкладку **Actions**
2. Если видите "Actions are not enabled", нажмите **Enable Actions**
3. Выберите workflow **Build Android APK**
4. Нажмите **Run workflow** → **Run workflow** (зелёная кнопка)

---

## ⏳ Шаг 7: Дождитесь сборки

1. Запуск займёт ~30-40 минут (первая сборка)
2. Следите за прогрессом во вкладке Actions
3. Когда появится зелёная галочка ✅ — готово!

---

## 📥 Шаг 8: Скачайте APK

Есть 2 способа:

### Способ A — Через Releases (если настроено)
1. В репозитории перейдите во вкладку **Releases**
2. Скачайте `skalpmat-7.0.0-debug.apk`

### Способ B — Через артефакты
1. Actions → Выберите завершённый запуск
2. Внизу в разделе "Artifacts" нажмите `skalpmat-apk`
3. Распакуйте ZIP файл

---

## 📱 Шаг 9: Установите на телефон

1. Скопируйте APK на телефон (через USB, Google Drive, и т.д.)
2. На телефоне: Настройки → Безопасность → Неизвестные источники → Разрешить
3. Откройте APK файл и нажмите **Установить**
4. Запустите **SKALPMAT V7**

---

## 🎯 Быстрая команда (всё в одном)

Если хотите сделать всё сразу, скопируйте и выполните:

```powershell
cd C:\Users\Minylim\Desktop\skalpmat-android

# Настройте Git (замените email и имя!)
git config user.email "your_email@example.com"
git config user.name "Your Name"

# Коммит
git commit -m "SKALPMAT V7 Android"

# Ветка main
git branch -M main

# Добавьте репозиторий (замените LOGIN!)
git remote add origin https://github.com/ВАШ_LOGIN/skalpmat-android.git

# Отправьте
git push -u origin main
```

---

## 🐛 Возможные проблемы

### Ошибка: "remote: Repository not found"
**Решение:** Проверьте что репозиторий создан и имя правильное

### Ошибка: "permission denied"
**Решение:** Проверьте что вы авторизованы в GitHub
```powershell
# Используем HTTPS с токеном
git remote set-url origin https://TOKEN@github.com/LOGIN/skalpmat-android.git
```

### Ошибка: "already exists"
**Решение:** Репозиторий уже существует, выберите другое имя

---

## ✅ Чек-лист

- [ ] Git настроен (email + имя)
- [ ] Коммит сделан
- [ ] Репозиторий создан на GitHub
- [ ] Файлы загружены (`git push`)
- [ ] Actions включены
- [ ] Запуск сборки (`Run workflow`)
- [ ] APK скачан
- [ ] Приложение установлено на телефон

---

## 🎉 Готово!

Теперь:
- Все future изменения будут автоматически собираться в APK
- При каждом push в ветку `main` запускается сборка
- APK доступен в Releases и артефактах

**Следующий шаг:** Настройте `.env` в приложении и запустите бота!

---

**Вопросы?** Откройте [ISSUE](https://github.com/ВАШ_ЛОГИН/skalpmat-android/issues)