import os
import asyncio
from google import genai
from PIL import Image
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv
# Добавляем библиотеки для работы векторного поиска Qdrant
from fastembed import TextEmbedding
from qdrant_client import QdrantClient

# Загружаем скрытые переменные окружения из файла .env
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("API_KEY")

# Проверка, что ключи успешно подтянулись
if not TELEGRAM_TOKEN or not API_KEY:
    exit("❌ Ошибка: Переменные TELEGRAM_TOKEN или API_KEY не найдены в файле .env!")

client = genai.Client(api_key=API_KEY)
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Инициализируем локальный ИИ-поисковик по книгам Минсельхоза
print("Загрузка ИИ-модели E5 и подключение к Qdrant...")
encoder = TextEmbedding(model_name="intfloat/multilingual-e5-large")
qdrant_client = QdrantClient(url="http://localhost:6333")
COLLECTION_NAME = "agro_large_db"

# Временная память для хранения выбранного языка пользователей
user_languages = {}

if not os.path.exists("downloads"):
    os.makedirs("downloads")

# Состояния FSM для ручного ввода площади в калькуляторе семян
class SeedCalcState(StatesGroup):
    waiting_for_custom_area = State()

# Официальные нормы высева семян на 1 СОТКУ (сотих) в килограммах
SEED_NORMS = {
    "kartoshka": 30.0,  # ~30 кг картофеля на 1 сотку
    "pahta": 2.5,       # ~2.5 кг семян хлопка на 1 сотку
    "gandum": 2.2       # ~2.2 кг зерна пшеницы на 1 сотку
}

# ================= СОЗДАНИЕ КНОПОК МЕНЮ =================

def get_lang_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇹🇯 Тоҷикӣ"), KeyboardButton(text="🇷🇺 Русский")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_main_keyboard(lang):
    if lang == "tj":
        buttons = [
            [KeyboardButton(text="📝 Савол додан"), KeyboardButton(text="📸 Ташхис тавассути акс")],
            [KeyboardButton(text="🌱 Меъёри тухмиҳо"), KeyboardButton(text="📞 Алоқа бо мутахассис")],
            [KeyboardButton(text="ℹ️ Дар бораи лоиҳаи 'Agrodonish'")],
            [KeyboardButton(text="⬅️ Бозгашт ба интихоби забон")]
        ]
        placeholder = "Амалро интихоб кунед ё савол нависед..."
    else:
        buttons = [
            [KeyboardButton(text="📝 Задать вопрос"), KeyboardButton(text="📸 Диагностика по фото")],
            [KeyboardButton(text="🌱 Расход семян"), KeyboardButton(text="📞 Связь с агрономом")],
            [KeyboardButton(text="ℹ️ О проекте 'Agrodonish'")],
            [KeyboardButton(text="⬅️ Назад к выбору языка")]
        ]
        placeholder = "Выберите действие или напишите вопрос..."
        
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True, input_field_placeholder=placeholder)

@dp.message(Command("start"))
async def cmd_start(message: Message):
    welcome_text = (
        "🌱 **Ассалому алейкум! Интихоби забонро интихоб кунед.**\n"
        "🌱 **Здравствуйте! Выберите язык для продолжения.**"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_lang_keyboard())

@dp.message(F.text.in_({"⬅️ Назад к выбору языка", "⬅️ Бозгашт ба интихоби забон"}))
async def btn_back_to_languages(message: Message):
    welcome_text = (
        "🌱 **Интихоби забонро аз наву интихоб кунед.**\n"
        "🌱 **Выберите язык заново для продолжения.**"
    )
    await message.answer(welcome_text, reply_markup=get_lang_keyboard())

@dp.message(F.text == "🇹🇯 Тоҷикӣ")
async def set_lang_tj(message: Message):
    user_id = message.from_user.id
    user_languages[user_id] = "tj"
    
    welcome_text = (
        "🌱 **Шуморо ИИ-машваратчии «Агродониш» хайрамақдам мегӯяг!**\n\n"
        "Ман ба деҳқонони Тоҷикистон барои ёфтани ҷавобҳои дақиқ оид ба агрономия ва табобати растаниҳо тавассути акс кӯмак мекунам.\n\n"
        "👇 **Барои паймоиш аз менюи зер истифода баред:**"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard("tj"))

@dp.message(F.text == "🇷🇺 Русский")
async def set_lang_ru(message: Message):
    user_id = message.from_user.id
    user_languages[user_id] = "ru"
    
    welcome_text = (
        "🌱 **Вас приветствует ИИ-консультант «Агродониш»!**\n\n"
        "Я помогаю фермерам Таджикистана находить точные ответы по агрономии и лечить растения по фото.\n\n"
        "👇 **Используйте меню ниже для навигации:**"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard("ru"))

@dp.message(F.text.in_({"📝 Задать вопрос", "📝 Савол додан"}))
async def btn_ask_question(message: Message):
    lang = user_languages.get(message.from_user.id, "ru")
    if lang == "tj":
        instructions = (
            "💬 **Режими маълумотномаи матнӣ**\n\n"
            "Танҳо саволи худро мустақиман ба ҳамин ҷо нависед (бо забони тоҷикӣ ё русӣ).\n"
            "Масалан: _«Чӣ тавр бо малах дар чарогоҳҳо мубориза барем?»_.\n\n"
            "Ман ҷавобро аз дастурҳои расмии Вазорати кишоварзии ҶТ фавран пайдо мекунам."
        )
    else:
        instructions = (
            "💬 **Режим текстового справочника**\n\n"
            "Просто напишите свой вопрос прямо сюда в чат (на таджикском или русском языке).\n"
            "Например: _«Как бороться с саранчой на пастбищах?»_.\n\n"
            "Я мгновенно найду ответ в официальных регламентах Минсельхоза РТ."
        )
    await message.answer(instructions, parse_mode="Markdown")

@dp.message(F.text.in_({"📸 Диагностика по photo", "📸 Диагностика по фото", "📸 Ташхис тавассути акс"}))
async def btn_photo_help(message: Message):
    lang = user_languages.get(message.from_user.id, "ru")
    if lang == "tj":
        instructions = (
            "📷 **Режими ташхиси бемориҳои растаниҳо**\n\n"
            "Барои таҳлил **акси** барг, поя, мева ё хӯшаи зарардидаро фиристед.\n\n"
            "⚠️ *Маслиҳат:* Кӯшиш кунед, ки аксро дар равшании хуб ва аз наздик гиред, то ИИ тавонад патогенро дақиқ муайян кунад."
        )
    else:
        instructions = (
            "📷 **Режим распознавания болезней растений**\n\n"
            "Пришлите мне **фотографию** пораженного листа, стебля, плода или колоса.\n\n"
            "⚠️ *Совет:* Старайтесь делать фото при хорошем освещении и вблизи, чтобы ИИ мог четко определить патоген или вредителя."
        )
    await message.answer(instructions, parse_mode="Markdown")

@dp.message(F.text.in_({"ℹ️ О проекте 'Agrodonish'", "ℹ️ Дар бораи лоиҳаи 'Agrodonish'"}))
async def btn_about_project(message: Message):
    lang = user_languages.get(message.from_user.id, "ru")
    if lang == "tj":
        about_text = (
            "🏛 **Системаи зеҳнии «Агродониш» (Agrodonish)**\n\n"
            "Барои дастгирии иттилоотии хоҷагиҳои деҳқонии Ҷумҳурии Тоҷикистон коркард шудааст.\n\n"
            "🔹 **Ҳадаф:** Муҳайё кардани агрономи маҷозии инфиродӣ 24/7 барои ҳар як деҳқон.\n"
            "🔹 **Технология:** Система дар заминаи моделҳои насли нави Gemini Flash ва технологияи RAG сохта шудааст, "
            "ки саҳеҳии ҷавобҳоро бе маълумоти бардурӯғ кафолат медиҳад.\n\n"
            "Ҳамаи тавсияҳо ба стандартҳои расмии Вазорати кишоварзии Ҷумҳурии Тоҷикистон мувофиқат мекунанд."
        )
    else:
        about_text = (
            "🏛 **Интеллектуальная система «Агродониш» (Agrodonish)**\n\n"
            "Разработано для информационной поддержки дехканских хозяйств Республики Таджикистан.\n\n"
            "🔹 **Цель:** Предоставить каждому фермеру персонального виртуального агронома 24/7.\n"
            "🔹 **Технологии:** Система построена на базе языковых моделей нового поколения Gemini Flash и технологии RAG, "
            "что гарантирует точность ответов без ложных фактов.\n\n"
            "Все рекомендации соответствуют официальным стандартам Министерства сельского хозяйства РТ."
        )
    await message.answer(about_text, parse_mode="Markdown")

# ================= БЛОК: СВЯЗЬ С АГРОНОМОМ =================
@dp.message(F.text.in_({"📞 Алоқа бо мутахассис", "📞 Связь с агрономом"}))
async def connect_to_expert(message: Message):
    lang = user_languages.get(message.from_user.id, "ru")
    if lang == "ru":
        text = (
            "📞 *Связь со специалистами Минсельхоза РТ*\n\n"
            "Если ИИ-консультант 'Агродониш' не смог найти точный ответ в базе данных, "
            "вы можете обратиться напрямую к специалистам центра рақамикунонӣ:\n\n"
            "📱 *Телефон поддержки:* +992 502 05 05 11\n"
            "📧 *Электронная почта:* info@agridigital.tj\n\n"
            "📍 _Вы также можете направить официальное обращение в местное управление сельского хозяйства вашего района._"
        )
    else:
        text = (
            "📞 *Алоқа бо мутахассисони Вазорати кишоварзии ҶТ*\n\n"
            "Агар машваратчии сунъии 'Агродониш' натавонист ҷавоби дақиқро аз пойгоҳи маълумот пайдо кунад, "
            "шумо метавонед мустақиман ба мутахассисони маркази рақамикунонӣ муроҷиат кунед:\n\n"
            "📱 *Телефони дастгирӣ:* +992 502 05 05 11\n"
            "📧 *Почтаи электронӣ:* info@agridigital.tj\n\n"
            "📍 _Шумо инчунин метавонед бо аризаи расмӣ ба раёсати кишоварзии маҳаллии ноҳияи худ муроҷиат намоед._"
        )
    await message.answer(text, parse_mode="Markdown")

# ================= БЛОК: КАЛЬКУЛЯТОР РАСХОДА СЕМЯН =================
@dp.message(F.text.in_({"🌱 Меъёри тухмиҳо", "🌱 Расход семян"}))
async def seed_calc_start(message: Message):
    lang = user_languages.get(message.from_user.id, "ru")
    if lang == "ru":
        text = "🌱 *Калькулятор расхода семян*\n\nВыберите культуру, которую вы собираетесь сеять:"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🥔 Картошель", callback_data="seed_kartoshka")],
            [InlineKeyboardButton(text="🌱 Хлопок", callback_data="seed_pahta")],
            [InlineKeyboardButton(text="🌾 Пшеница", callback_data="seed_gandum")]
        ])
    else:
        text = "🌱 *Ҳисобкунаки меъёри тухмиҳо*\n\nКультураеро интихоб кунед, ки кишт кардан мехоҳед:"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🥔 Картошка", callback_data="seed_kartoshka")],
            [InlineKeyboardButton(text="🌱 Пахта", callback_data="seed_pahta")],
            [InlineKeyboardButton(text="🌾 Гандум", callback_data="seed_gandum")]
        ])
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("seed_"))
async def process_seed_culture(callback: CallbackQuery, state: FSMContext):
    culture = callback.data.split("_")[1]
    lang = user_languages.get(callback.from_user.id, "ru")
    await state.update_data(chosen_culture=culture)
    
    text = "📐 Укажите площадь вашего участка:" if lang == "ru" else "📐 Тезнокии замини худро интихоб кунед:"
    buttons = [
        [InlineKeyboardButton(text="1 сотих", callback_data="area_1"), InlineKeyboardButton(text="2 сотих", callback_data="area_2")],
        [InlineKeyboardButton(text="5 сотих", callback_data="area_5"), InlineKeyboardButton(text="10 сотих", callback_data="area_10")],
        [InlineKeyboardButton(text="1 гектар (100 сот.)", callback_data="area_100")],
        [InlineKeyboardButton(text="✍️ Другой вариант / Варианти дигар", callback_data="area_custom")]
    ]
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()

@dp.callback_query(F.data.startswith("area_") & (F.data != "area_custom"))
async def process_fixed_area(callback: CallbackQuery, state: FSMContext):
    area_sotikh = int(callback.data.split("_")[1])
    user_data = await state.get_data()
    culture = user_data.get("chosen_culture", "kartoshka")
    lang = user_languages.get(callback.from_user.id, "ru")
    
    total_weight = area_sotikh * SEED_NORMS.get(culture, 1.0)
    await send_calc_result(callback.message, culture, area_sotikh, total_weight, lang)
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "area_custom")
async def process_custom_area_request(callback: CallbackQuery, state: FSMContext):
    lang = user_languages.get(callback.from_user.id, "ru")
    text = "✍️ Введите площадь участка **в сотках (сотих)** числом:" if lang == "ru" else "✍️ Тезнокии заминро **бо сотих** ҳамчун адад ворид кунед:"
    await callback.message.edit_text(text, parse_mode="Markdown")
    await state.set_state(SeedCalcState.waiting_for_custom_area)
    await callback.answer()

@dp.message(SeedCalcState.waiting_for_custom_area)
async def process_custom_area_text(message: Message, state: FSMContext):
    lang = user_languages.get(message.from_user.id, "ru")
    try:
        area_sotikh = float(message.text.strip().replace(",", "."))
        if area_sotikh <= 0: raise ValueError()
    except ValueError:
        error_text = "❌ Введите число больше 0:" if lang == "ru" else "❌ Адади дурустро ворид кунед:"
        await message.answer(error_text)
        return

    user_data = await state.get_data()
    culture = user_data.get("chosen_culture", "kartoshka")
    total_weight = area_sotikh * SEED_NORMS.get(culture, 1.0)
    
    await send_calc_result(message, culture, area_sotikh, total_weight, lang)
    await state.clear()

async def send_calc_result(message_obj, culture, area, weight, lang):
    names = {"kartoshka": ("Картофель", "Картошка"), "pahta": ("Хлопок", "Пахта"), "gandum": ("Пшеница", "Гандум")}
    c_ru, c_tj = names.get(culture, (culture, culture))
    if lang == "ru":
        text = f"📊 *Результат расчета*\n\n🌱 *Культура:* {c_ru}\n📐 *Площадь:* {area} сот.\n⚖️ *Расход семян:* **{weight:.1f} кг**\n\nℹ️ _Расчет произведен на основе официальных агротехнических стандартов Минсельхоза РТ._"
    else:
        text = f"📊 *Натиҷаи ҳисобкунӣ*\n\n🌱 *Культура:* {c_tj}\n📐 *Масоҳат:* {area} сотих\n⚖️ *Вазни зарурӣ:* **{weight:.1f} кг**\n\nℹ️ _Ҳисобкунӣ дар асоси стандартҳои расмии агротехникии Вазорати кишковарзии ҶТ иҷро шудааст._"
    await message_obj.answer(text, parse_mode="Markdown")

# ================= ОБРАБОТКА ФОТОГРАФИЙ МИНСЕЛЬХОЗА =================
@dp.message(F.photo)
async def handle_photo(message: Message):
    lang = user_languages.get(message.from_user.id, "ru")
    wait_text = "🔄 _Анализирую снимок, подождите..._" if lang == "ru" else "🔄 _Аксро таҳлил карда истодаам, лутфан мунтазир шавед..._"
    
    waiting_msg = await message.answer(wait_text, parse_mode="Markdown")
    
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    photo_path = f"downloads/{photo.file_id}.jpg"
    await bot.download_file(file_info.file_path, photo_path)
    
    img = Image.open(photo_path)
    
    target_lang = "таджикском языке (забони тоҷикӣ)" if lang == "tj" else "русском языке"
    prompt = (
        f"Ты — эксперт-агроном Минсельхоза Таджикистана. Посмотри на это photo растения. "
        f"Определи, что это за культура, какая у неё болезнь или вредитель, "
        f"и дай краткие пошаговые рекомендации по лечению строго на {target_lang}. "
        f"Используй Markdown для красивого форматирования."
    )
    
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=[img, prompt])
        await waiting_msg.delete()
        await message.answer(response.text, parse_mode="Markdown")
    except Exception as e:
        error_text = f"❌ Ошибка: {e}" if lang == "ru" else f"❌ Хатогӣ: {e}"
        await waiting_msg.edit_text(error_text)
    finally:
        if os.path.exists(photo_path):
            os.remove(photo_path)

# ================= ОБРАБОТКА ВОПРОСОВ ЧЕРЕЗ QDRANT =================
@dp.message(F.text)
async def handle_text(message: Message):
    # ЗАЩИТА: Игнорируем служебный текст экранных кнопок меню, чтобы их не читал Qdrant/Gemini
    if message.text in [
        "📝 Савол додан", "📝 Задать вопрос", 
        "📸 Ташхис тавассути акс", "📸 Диагностика по фото", "📸 Диагностика по photo",
        "ℹ️ О проекте 'Agrodonish'", "ℹ️ Дар бораи лоиҳаи 'Agrodonish'",
        "📞 Алоқа бо мутахассис", "📞 Связь с агрономом",
        "🌱 Меъёри тухмиҳо", "🌱 Расход семян",
        "⬅️ Назад к выбору языка", "⬅️ Бозгашт ба интихоби забон"
    ]:
        return

    lang = user_languages.get(message.from_user.id, "ru")
    wait_text = "🔄 _Ищу информацию..._" if lang == "ru" else "🔄 _Маълумотро ҷустуҷӯ дорам..._"
    
    waiting_msg = await message.answer(wait_text, parse_mode="Markdown")
    
    try:
        format_query = f"query: {message.text}"
        query_vector = list(encoder.embed([format_query]))[0].tolist()
        
        search_result = []
        
        # Автоматическая проверка методов (для любых версий библиотеки Qdrant)
        if hasattr(qdrant_client, "search"):
            # Вариант для стандартных версий
            search_result = qdrant_client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                limit=4
            )
        elif hasattr(qdrant_client, "query_points"):
            # Вариант для самых новых версий библиотеки
            response = qdrant_client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=4
            )
            search_result = response.points
        else:
            # Если оба метода не найдены — выводим жесткую диагностику в консоль сервера
            print(f"\n[КРИТИЧЕСКАЯ ОШИБКА] У объекта QdrantClient нет методов search или query_points!")
            print(f"[Доступные методы в твоей системе]: {dir(qdrant_client)}\n")
            raise AttributeError("Компоненты базы данных Qdrant не согласуются с версией библиотеки.")
        
        context_chunks = []
        for hit in search_result:
            text = hit.payload.get("text", "")
            context_chunks.append(text)
            
        context = "\n\n--- Фрагмент документа ---\n\n".join(context_chunks) if context_chunks else ""
        
        target_lang = "на таджикском языке (бо забони тоҷикӣ)" if lang == "tj" else "на русском языке"
        template_reply = (
            'К сожалению, в официальных справочниках нет точной информации по данным вопросам. Пожалуйста, обратитесь к местному специалисту-агроному.' 
            if lang == "ru" else 
            'Мутаассифона, дар маълумотномаҳои расмӣ оид ба ин масъала маълумоти дақиқ нест. Лутфан ба мутахассиси агрономи маҳаллӣ муроҷиат кунед.'
        )
        
        system_instruction = (
            f"Ты — специализированный ИИ-консультант 'Агродониш' Минсельхоза Республики Таджикистан. "
            f"Твоя задача — отвечать на вопросы фермеров строго на основе предоставленного контекста (Базы знаний).\n"
            f"ПРАВИЛА:\n"
            f"1. Ответ должен быть точным, кратким и понятным.\n"
            f"2. Ты обязан ответить строго {target_lang}.\n"
            f"3. КРИТИЧЕСКОЕ ПРАВИЛО: Если в предоставленном тексте НЕТ ответа на вопрос или база знаний пуста, ты обязан ответить "
            f"строго по шаблону: {template_reply}\n"
        )
        
        full_prompt = f"{system_instruction}\nБАЗА ЗНАНИЙ:\n{context}\n\nВОПРОС: {message.text}"
        
        response = client.models.generate_content(model="gemini-2.5-flash", contents=full_prompt)
        await waiting_msg.delete()
        await message.answer(response.text, parse_mode="Markdown")
        
    except Exception as e:
        print(f"Ошибка в handle_text: {e}")
        try: 
            await waiting_msg.delete()
        except: 
            pass
        error_text = "❌ Ошибка базы данных знаний. Пожалуйста, попробуйте позже." if lang == "ru" else "❌ Хатогии пойгоҳи додаҳои дониш. Лутфан, дертар кӯшиш кунед."
        await message.answer(error_text)

# ================= ТОЧКА ВХОДА ЗАПУСКА СИСТЕМЫ =================
async def main():
    print("Бот 'Агродониш' запущен в безопасном режиме (с конфигурацией .env)!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())