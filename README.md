# 🌱 Интеллектуальная система «Агродониш» (Agrodonish)

[![CI Pipeline](https://github.com/CenterDigitalization2026/agrodonish/actions/workflows/ci.yml/badge.svg)](https://github.com/CenterDigitalization2026/agrodonish/actions/workflows/ci.yml)

Система цифровой поддержки дехканских хозяйств и специалистов Министерства сельского хозяйства Республики Таджикистан.

---

## 📌 Основные возможности

- 🤖 **ИИ-консультант (RAG):** Предоставление ответов на вопросы по агрономии строго на основе официальных регламентов и книг Минсельхоза РТ.
- 📸 **Диагностика заболеваний растений по фото:** Распознавание патогенов и вредителей с помощью мультимодальной модели Gemini Flash.
- 🌱 **Калькулятор расхода семян:** Автоматический расчет норм высева для различных культур (картофель, хлопок, пшеница) с учетом площади участка в сотках и гектарах.
- 🌐 **Двуязычный интерфейс:** Полная поддержка таджикского (Тоҷикӣ) и русского языков.

---

## 🛠 Технологический стек

- **Бот:** [aiogram 3](https://docs.aiogram.dev/)
- **Нейросеть:** Google Gemini 2.5 Flash (`google-genai`)
- **Векторная база данных:** [Qdrant](https://qdrant.tech/)
- **Эмбеддинги:** `fastembed` (`intfloat/multilingual-e5-large`)
- **CI/CD:** GitHub Actions (автоматический линтинг Flake8 и тестирование PyTest)

---

## 🚀 Установка и запуск

1. Клонировать репозиторий:
   ```bash
   git clone https://github.com/CenterDigitalization2026/agrodonish.git
   cd agrodonish
   ```

2. Установить зависимости:
   ```bash
   pip install -r requirements.txt
   ```

3. Настроить конфигурационный файл `.env`:
   ```env
   TELEGRAM_TOKEN=ваш_telegram_токен
   API_KEY=ваш_gemini_api_key
   ```

4. Запустить векторную базу Qdrant:
   ```bash
   docker run -p 6333:6333 qdrant/qdrant
   ```

5. Запустить бота:
   ```bash
   python bot.py
   ```
