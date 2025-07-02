import telebot
import os
import json
from datetime import datetime, timedelta
from telebot import types
import matplotlib.pyplot as plt
import io
import csv
import aiosqlite
import asyncio
import aiofiles
import threading

# Вставьте сюда свой токен
API_TOKEN = '7963155896:AAGzoKcuQEuW5lNI2JSh9QA9O_1sWIUcNzM'

# ID администратора для отправки ошибок
ADMIN_ID = 1459840499  # Замените на ваш ID

bot = telebot.TeleBot(API_TOKEN)

DATA_DIR = 'users_data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DB_PATH = 'monefy_data.db'

# Новый способ хранения всех пользователей в одном файле
file_lock = threading.Lock()

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                currency TEXT DEFAULT '₽',
                backup_freq TEXT DEFAULT 'none'
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                category TEXT,
                description TEXT,
                date TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                user_id INTEGER,
                name TEXT,
                type TEXT,
                PRIMARY KEY(user_id, name, type)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS limits (
                user_id INTEGER,
                category TEXT,
                amount REAL,
                PRIMARY KEY(user_id, category)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER PRIMARY KEY,
                key TEXT,
                value TEXT
            )
        ''')
        await db.commit()

# Для запуска инициализации базы при старте
asyncio.run(init_db())

ALL_USERS_FILE = 'all_users_data.json'

def get_all_users_data():
    if not os.path.exists(ALL_USERS_FILE):
        return {}
    with open(ALL_USERS_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_all_users_data(data):
    with file_lock:
        with open(ALL_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

async def async_load_user_data(user_id):
    default = {
        'balance': 0,
        'history': [],
        'income_categories': [
            'Зарплата', 'Подарок', 'Бонус', 'Продажа', 'Кэшбэк', 'Премия', 'Стипендия', 'Инвестиции', 'Фриланс', 'Аренда', 'Дивиденды', 'Возврат долга', 'Прочее'
        ],
        'expense_categories': [
            'Еда', 'Транспорт', 'Развлечения', 'Кафе', 'Одежда', 'Образование', 'Здоровье', 'Путешествия', 'Мобильная связь', 'Интернет', 'Коммунальные услуги', 'Дом', 'Питомцы', 'Подарки', 'Красота', 'Спорт', 'Техника', 'Дети', 'Авто', 'Налоги', 'Штрафы', 'Прочее'
        ],
        'currency': '₽',
        'limits': {}
    }
    all_data = get_all_users_data()
    user_id_str = str(user_id)
    data = all_data.get(user_id_str, None)
    if data is None:
        data = default.copy()
        all_data[user_id_str] = data
        save_all_users_data(all_data)
    # Обновление структуры, если что-то добавилось
    for k in default:
        if k not in data:
            data[k] = default[k]
    for cat in default['income_categories']:
        if cat not in data['income_categories']:
            data['income_categories'].append(cat)
    for cat in default['expense_categories']:
        if cat not in data['expense_categories']:
            data['expense_categories'].append(cat)
    return data

async def async_save_user_data(user_id, data):
    all_data = get_all_users_data()
    all_data[str(user_id)] = data
    save_all_users_data(all_data)

def load_user_data(user_id):
    return asyncio.run(async_load_user_data(user_id))

def save_user_data(user_id, data):
    return asyncio.run(async_save_user_data(user_id, data))

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    # --- Учёт ---
    kb.row('Доход', 'Расход')
    kb.row('Баланс')
    # --- Анализ ---
    kb.row('История', 'Статистика', 'График')
    kb.row('Поиск')
    # --- Редактирование ---
    kb.row('Редактировать операцию')
    # --- Импорт/Экспорт ---
    kb.row('Импорт из Monefy', 'Экспорт истории')
    # --- Настройки ---
    kb.row('Настройки валюты', 'Настройки категорий')
    return kb

def back_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('Назад')
    return kb

def skip_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('Пропустить')
    kb.row('Назад')
    return kb

def category_menu(categories, back=True):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if back:
        kb.add('Назад')
    for cat in categories:
        kb.add(cat)
    return kb

def settings_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add('Лимиты по категориям')
    kb.add('Добавить категорию расхода', 'Удалить категорию расхода')
    kb.add('Добавить категорию дохода', 'Удалить категорию дохода')
    kb.add('Назад')
    return kb

user_states = {}

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, 'Привет! Я бот для учёта финансов по аналогии с monefy.', reply_markup=main_menu())
    user_states[message.from_user.id] = {'state': None}

@bot.message_handler(func=lambda m: m.text == 'Назад')
def back(message):
    user_states[message.from_user.id] = {'state': None}
    bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == 'Доход')
def income_choose_category(message):
    data = load_user_data(message.from_user.id)
    user_states[message.from_user.id] = {'state': 'income_category'}
    bot.send_message(message.chat.id, 'Выберите категорию дохода:', reply_markup=category_menu(data['income_categories']))

@bot.message_handler(func=lambda m: m.text == 'Расход')
def expense_choose_category(message):
    data = load_user_data(message.from_user.id)
    user_states[message.from_user.id] = {'state': 'expense_category'}
    bot.send_message(message.chat.id, 'Выберите категорию расхода:', reply_markup=category_menu(data['expense_categories']))

@bot.message_handler(func=lambda m: m.text == 'Баланс')
def balance(message):
    data = load_user_data(message.from_user.id)
    cur = data.get('currency', '₽')
    bot.send_message(message.chat.id, f'Ваш текущий баланс: {data["balance"]}{cur}', reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == 'История')
def history_entry(message):
    ask_period_menu(message, 'history_period')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'history_period')
def history_period_handler(message):
    if message.text == 'Период по дате':
        ask_date_range(message, 'history_date_range')
        return
    elif message.text == 'Назад':
        user_states[message.from_user.id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    # стандартные периоды
    now = datetime.now()
    if message.text == 'За день':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'За неделю':
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'За месяц':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'За год':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        bot.send_message(message.chat.id, 'Выберите период из меню.', reply_markup=main_menu())
        return
    show_history_for_period(message, start, now)
    user_states[message.from_user.id] = {'state': None}

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'history_date_range')
def history_date_range_handler(message):
    state = user_states[message.from_user.id]
    if message.text == 'Назад':
        ask_period_menu(message, 'history_period')
        return
    if message.text == 'Сегодня (начало дня)':
        dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'Сегодня (конец дня)':
        dt = datetime.now().replace(hour=23, minute=59, second=59)
    else:
        try:
            dt = datetime.strptime(message.text.strip(), '%d.%m.%Y')
        except Exception:
            bot.send_message(message.chat.id, 'Некорректная дата! Введите в формате ДД.ММ.ГГГГ или выберите "Сегодня":', reply_markup=back_menu())
            return
    if state['period_step'] == 'from':
        state['date_from'] = dt
        state['period_step'] = 'to'
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row('Сегодня (конец дня)')
        kb.add('Назад')
        bot.send_message(message.chat.id, 'Введите конечную дату (ДД.ММ.ГГГГ):', reply_markup=kb)
    else:
        date_from = state['date_from']
        date_to = dt
        show_history_for_period(message, date_from, date_to)
        user_states[message.from_user.id] = {'state': None}

def show_history_for_period(message, start, end):
    data = load_user_data(message.from_user.id)
    cur = data.get('currency', '₽')
    ops = [op for op in data['history'] if start <= datetime.strptime(op['date'], '%Y-%m-%d %H:%M:%S') <= end]
    if not ops:
        bot.send_message(message.chat.id, 'Нет операций за выбранный период.', reply_markup=main_menu())
        return
    period_str = f'Период: с {start.strftime("%d.%m.%Y")} по {end.strftime("%d.%m.%Y")}'
    text = f'{period_str}\nОперации:'
    for op in ops[::-1]:
        sign = '+' if op['type'] == 'income' else '-'
        category = op.get('category', 'Без категории')
        desc = op.get('description', '')
        date_only = op['date'][:10]
        text += f"\n{date_only}: {sign}{op['amount']}{cur} {category} {desc}"
    bot.send_message(message.chat.id, text, reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == 'Настройки категорий')
def settings(message):
    user_states[message.from_user.id] = {'state': 'settings'}
    bot.send_message(message.chat.id, 'Настройки категорий:', reply_markup=settings_menu())

@bot.message_handler(func=lambda m: m.text in ['Добавить категорию расхода', 'Удалить категорию расхода', 'Добавить категорию дохода', 'Удалить категорию дохода'])
def category_settings(message):
    user_id = message.from_user.id
    state = None
    if message.text == 'Добавить категорию расхода':
        state = 'add_expense_category'
        bot.send_message(message.chat.id, 'Введите название новой категории расхода:', reply_markup=back_menu())
    elif message.text == 'Удалить категорию расхода':
        state = 'del_expense_category'
        data = load_user_data(user_id)
        bot.send_message(message.chat.id, 'Выберите категорию для удаления:', reply_markup=category_menu(data['expense_categories']))
    elif message.text == 'Добавить категорию дохода':
        state = 'add_income_category'
        bot.send_message(message.chat.id, 'Введите название новой категории дохода:', reply_markup=back_menu())
    elif message.text == 'Удалить категорию дохода':
        state = 'del_income_category'
        data = load_user_data(user_id)
        bot.send_message(message.chat.id, 'Выберите категорию для удаления:', reply_markup=category_menu(data['income_categories']))
    user_states[user_id] = {'state': state}

@bot.message_handler(func=lambda m: m.text == 'Статистика')
def stats_entry(message):
    ask_period_menu(message, 'stats_period')

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'stats_period')
def stats_period_handler(message):
    if message.text == 'Период по дате':
        ask_date_range(message, 'stats_date_range')
        return
    elif message.text == 'Назад':
        user_states[message.from_user.id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    now = datetime.now()
    if message.text == 'За день':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'За неделю':
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'За месяц':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'За год':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        bot.send_message(message.chat.id, 'Выберите период из меню.', reply_markup=main_menu())
        return
    show_stats_for_period(message, start, now)
    user_states[message.from_user.id] = {'state': None}

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'stats_date_range')
def stats_date_range_handler(message):
    state = user_states[message.from_user.id]
    if message.text == 'Назад':
        ask_period_menu(message, 'stats_period')
        return
    if message.text == 'Сегодня (начало дня)':
        dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'Сегодня (конец дня)':
        dt = datetime.now().replace(hour=23, minute=59, second=59)
    else:
        try:
            dt = datetime.strptime(message.text.strip(), '%d.%m.%Y')
        except Exception:
            bot.send_message(message.chat.id, 'Некорректная дата! Введите в формате ДД.ММ.ГГГГ или выберите "Сегодня":', reply_markup=back_menu())
            return
    if state['period_step'] == 'from':
        state['date_from'] = dt
        state['period_step'] = 'to'
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row('Сегодня (конец дня)')
        kb.add('Назад')
        bot.send_message(message.chat.id, 'Введите конечную дату (ДД.ММ.ГГГГ):', reply_markup=kb)
    else:
        date_from = state['date_from']
        date_to = dt
        show_stats_for_period(message, date_from, date_to)
        user_states[message.from_user.id] = {'state': None}

def show_stats_for_period(message, start, end):
    data = load_user_data(message.from_user.id)
    income = 0
    expense = 0
    income_by_cat = {}
    expense_by_cat = {}
    for op in data['history']:
        op_date = datetime.strptime(op['date'], '%Y-%m-%d %H:%M:%S')
        if start <= op_date <= end:
            cat = op.get('category', 'Без категории')
            if op['type'] == 'income':
                income += op['amount']
                income_by_cat[cat] = income_by_cat.get(cat, 0) + op['amount']
            else:
                expense += op['amount']
                expense_by_cat[cat] = expense_by_cat.get(cat, 0) + op['amount']
    cur = data.get('currency', '₽')
    period_str = f'Период: с {start.strftime("%d.%m.%Y")} по {end.strftime("%d.%m.%Y")}'
    text = f'{period_str}\n\nСтатистика:\n\nДоход: {income}{cur}\nРасход: {expense}{cur}\nБаланс: {data["balance"]}{cur}\n'
    if income_by_cat:
        text += '\nДоход по категориям:'
        for cat, val in income_by_cat.items():
            text += f'\n- {cat}: {val}{cur}'
    if expense_by_cat:
        text += '\n\nРасход по категориям:'
        for cat, val in expense_by_cat.items():
            text += f'\n- {cat}: {val}{cur}'
    bot.send_message(message.chat.id, text, reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == 'График')
def show_graph_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('График за неделю', 'График за месяц', 'График за год')
    kb.row('Круговая диаграмма расходов')
    kb.row('Детальный график расходов')
    kb.row('Назад')
    bot.send_message(message.chat.id, 'Выберите тип и период графика:', reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ['График за неделю', 'График за месяц', 'График за год'])
def send_graph(message):
    user_id = message.from_user.id
    data = load_user_data(user_id)
    now = datetime.now()
    if message.text == 'График за неделю':
        days = 7
        period = 'неделю'
    elif message.text == 'График за месяц':
        days = 30
        period = 'месяц'
    else:
        days = 365
        period = 'год'
    dates = [(now - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days-1, -1, -1)]
    income_by_day = {d: 0 for d in dates}
    expense_by_day = {d: 0 for d in dates}
    for op in data['history']:
        op_date = op['date'][:10]
        if op_date in income_by_day:
            if op['type'] == 'income':
                income_by_day[op_date] += op['amount']
            else:
                expense_by_day[op_date] += op['amount']
    plt.figure(figsize=(max(8, days//5),4))
    plt.plot(list(income_by_day.keys()), list(income_by_day.values()), label='Доход')
    plt.plot(list(expense_by_day.keys()), list(expense_by_day.values()), label='Расход')
    plt.xticks(rotation=45, fontsize=8 if days>30 else 10)
    plt.legend()
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    period_str = f'Период: с {dates[0]} по {dates[-1]}'
    bot.send_photo(message.chat.id, buf, caption=f'График за {period}\n{period_str}')
    buf.close()

@bot.message_handler(func=lambda m: m.text == 'Круговая диаграмма расходов')
def send_pie_chart(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('Круговая за неделю', 'Круговая за месяц', 'Круговая за год')
    kb.row('Назад')
    bot.send_message(message.chat.id, 'За какой период построить круговую диаграмму?', reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ['Круговая за неделю', 'Круговая за месяц', 'Круговая за год'])
def send_pie_chart_period(message):
    user_id = message.from_user.id
    data = load_user_data(user_id)
    now = datetime.now()
    if message.text == 'Круговая за неделю':
        days = 7
        period = 'неделю'
    elif message.text == 'Круговая за месяц':
        days = 30
        period = 'месяц'
    else:
        days = 365
        period = 'год'
    start = (now - timedelta(days=days-1)).replace(hour=0, minute=0, second=0, microsecond=0)
    expense_by_cat = {}
    for op in data['history']:
        op_date = datetime.strptime(op['date'], '%Y-%m-%d %H:%M:%S')
        if op['type'] == 'expense' and op_date >= start:
            cat = op.get('category', 'Без категории')
            expense_by_cat[cat] = expense_by_cat.get(cat, 0) + op['amount']
    if not expense_by_cat:
        bot.send_message(message.chat.id, 'Нет расходов за выбранный период.', reply_markup=main_menu())
        return
    labels = list(expense_by_cat.keys())
    values = list(expense_by_cat.values())
    plt.figure(figsize=(6,6))
    plt.pie(values, labels=labels, autopct='%1.1f%%', startangle=140)
    plt.title('Структура расходов по категориям')
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    period_str = f'Период: с {start.strftime("%d.%m.%Y")} по {now.strftime("%d.%m.%Y")}'
    bot.send_photo(message.chat.id, buf, caption=f'Круговая диаграмма расходов за {period}\n{period_str}')
    buf.close()

@bot.message_handler(func=lambda m: m.text == 'Детальный график расходов')
def send_detailed_expense_graph_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('Детальный за неделю', 'Детальный за месяц', 'Детальный за год')
    kb.row('Назад')
    bot.send_message(message.chat.id, 'За какой период построить детальный график?', reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ['Детальный за неделю', 'Детальный за месяц', 'Детальный за год'])
def send_detailed_expense_graph(message):
    user_id = message.from_user.id
    data = load_user_data(user_id)
    now = datetime.now()
    if message.text == 'Детальный за неделю':
        days = 7
        period = 'неделю'
    elif message.text == 'Детальный за месяц':
        days = 30
        period = 'месяц'
    else:
        days = 365
        period = 'год'
    dates = [(now - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days-1, -1, -1)]
    # Собираем все категории расходов за период
    categories = set()
    for op in data['history']:
        op_date = op['date'][:10]
        if op['type'] == 'expense' and op_date in dates:
            categories.add(op.get('category', 'Без категории'))
    categories = sorted(categories)
    # Формируем данные: {категория: [расходы по дням]}
    cat_day_expense = {cat: [0]*days for cat in categories}
    for op in data['history']:
        op_date = op['date'][:10]
        if op['type'] == 'expense' and op_date in dates:
            cat = op.get('category', 'Без категории')
            idx = dates.index(op_date)
            cat_day_expense[cat][idx] += op['amount']
    plt.figure(figsize=(max(8, days//5),5))
    for cat, vals in cat_day_expense.items():
        plt.plot(dates, vals, marker='o', label=cat)
    plt.xticks(rotation=45, fontsize=8 if days>30 else 10)
    plt.title(f'Детальный график расходов по категориям за {period}')
    plt.xlabel('Дата')
    plt.ylabel('Сумма, ₽')
    plt.legend()
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    period_str = f'Период: с {dates[0]} по {dates[-1]}'
    bot.send_photo(message.chat.id, buf, caption=f'Детальный график расходов за {period}\n{period_str}')
    buf.close()

@bot.message_handler(func=lambda m: m.text == 'Редактировать операцию')
def edit_op_period_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('Операции за день', 'Операции за неделю')
    kb.row('Назад')
    bot.send_message(message.chat.id, 'Выберите период для поиска операции:', reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ['Операции за день', 'Операции за неделю'])
def edit_op_choose_period(message):
    user_id = message.from_user.id
    user_states[user_id] = user_states.get(user_id, {})
    user_states[user_id]['edit_period'] = message.text
    data = load_user_data(user_id)
    cats = set()
    for op in data['history']:
        if op['type'] in ['income', 'expense']:
            cats.add(op.get('category', 'Без категории'))
    cats = sorted(cats)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add('Все категории')
    for cat in cats:
        kb.add(cat)
    kb.add('Назад')
    user_states[user_id]['state'] = 'edit_op_choose_category'
    bot.send_message(message.chat.id, 'Выберите категорию для фильтрации:', reply_markup=kb)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'edit_op_choose_category')
def edit_op_choose(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    if message.text == 'Назад':
        user_states[user_id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    category = message.text
    state['edit_category'] = category
    data = load_user_data(user_id)
    now = datetime.now()
    period = state.get('edit_period')
    if period == 'Операции за день':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    ops = []
    for idx, op in enumerate(data['history']):
        op_date = datetime.strptime(op['date'], '%Y-%m-%d %H:%M:%S')
        if op_date >= start:
            if category == 'Все категории' or op.get('category', 'Без категории') == category:
                ops.append((idx, op))
    if not ops:
        bot.send_message(message.chat.id, 'Нет операций за выбранный период и категорию.', reply_markup=main_menu())
        user_states[user_id] = {'state': None}
        return
    user_states[user_id]['state'] = 'edit_op_choose'
    user_states[user_id]['ops'] = dict(ops)
    user_states[user_id]['ops_list'] = ops
    user_states[user_id]['page'] = 0
    send_edit_op_page(message, user_id)

def send_edit_op_page(message, user_id):
    state = user_states[user_id]
    ops = state['ops_list']
    page = state['page']
    per_page = 10
    total_pages = (len(ops) - 1) // per_page + 1
    start_idx = page * per_page
    end_idx = start_idx + per_page
    page_ops = ops[start_idx:end_idx]
    data = load_user_data(user_id)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for idx, op in page_ops:
        sign = '+' if op['type'] == 'income' else '-'
        cat = op.get('category', 'Без категории')
        desc = op.get('description', '')
        date_only = op['date'][:10]
        kb.add(f"{idx}: {date_only} {sign}{op['amount']}{data.get('currency', '₽')} {cat} {desc}")
    nav_row = []
    if page > 0:
        nav_row.append('Предыдущие')
    if end_idx < len(ops):
        nav_row.append('Следующие')
    if nav_row:
        kb.row(*nav_row)
    kb.add('Назад')
    bot.send_message(message.chat.id, f'Выберите операцию для редактирования (стр. {page+1}/{total_pages}):', reply_markup=kb)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'edit_op_choose')
def edit_op_action(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    if message.text == 'Назад':
        user_states[user_id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    if message.text == 'Следующие':
        state['page'] += 1
        send_edit_op_page(message, user_id)
        return
    if message.text == 'Предыдущие':
        state['page'] -= 1
        send_edit_op_page(message, user_id)
        return
    try:
        idx = int(message.text.split(':')[0])
        op = state['ops'][idx]
    except Exception:
        bot.send_message(message.chat.id, 'Ошибка: выберите операцию из списка кнопок ниже. Не вводите вручную.', reply_markup=main_menu())
        user_states[user_id] = {'state': None}
        return
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('Изменить', 'Удалить')
    kb.row('Назад')
    user_states[user_id] = {'state': 'edit_op_action', 'op_idx': idx, 'op': op}
    bot.send_message(message.chat.id, 'Что сделать с операцией?', reply_markup=kb)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'edit_op_action')
def edit_op_modify(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    if message.text == 'Назад':
        user_states[user_id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    if message.text == 'Удалить':
        data = load_user_data(user_id)
        idx = state['op_idx']
        op = data['history'][idx]
        # Корректируем баланс
        if op['type'] == 'income':
            data['balance'] -= op['amount']
        else:
            data['balance'] += op['amount']
        data['history'].pop(idx)
        save_user_data(user_id, data)
        bot.send_message(message.chat.id, 'Операция удалена.', reply_markup=main_menu())
        user_states[user_id] = {'state': None}
        return
    if message.text == 'Изменить':
        op = state['op']
        data = load_user_data(user_id)
        bot.send_message(message.chat.id, f'Введите новую сумму (было {op["amount"]}{data.get("currency", "₽")}):', reply_markup=back_menu())
        user_states[user_id] = {'state': 'edit_op_amount', 'op_idx': state['op_idx'], 'op': op}

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'edit_op_amount')
def edit_op_amount(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    if message.text == 'Назад':
        user_states[user_id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    try:
        amount = float(message.text.replace(',', '.'))
    except Exception:
        bot.send_message(message.chat.id, 'Ошибка: сумма должна быть числом. Введите сумму, например: 100 или 99.50', reply_markup=back_menu())
        return
    user_states[user_id]['new_amount'] = amount
    op = state['op']
    data = load_user_data(user_id)
    # Категории
    if op['type'] == 'income':
        cats = data['income_categories']
    else:
        cats = data['expense_categories']
    kb = category_menu(cats)
    bot.send_message(message.chat.id, f'Выберите новую категорию (было {op.get("category", "Без категории")}):', reply_markup=kb)
    user_states[user_id]['state'] = 'edit_op_category'

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'edit_op_category')
def edit_op_category(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    op = state['op']
    data = load_user_data(user_id)
    if message.text == 'Назад':
        user_states[user_id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    # Проверяем категорию
    if op['type'] == 'income':
        cats = data['income_categories']
    else:
        cats = data['expense_categories']
    if message.text not in cats:
        bot.send_message(message.chat.id, 'Ошибка: выберите категорию из списка кнопок ниже. Не вводите вручную.', reply_markup=category_menu(cats))
        return
    user_states[user_id]['new_category'] = message.text
    bot.send_message(message.chat.id, f'Введите новое описание (было: {op.get("description", "-")}):', reply_markup=skip_menu())
    user_states[user_id]['state'] = 'edit_op_desc'

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'edit_op_desc')
def edit_op_desc(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    if message.text == 'Назад':
        user_states[user_id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    if message.text == 'Пропустить':
        new_desc = ''
    else:
        new_desc = message.text if message.text != '-' else ''
    new_amount = state['new_amount']
    new_category = state['new_category']
    idx = state['op_idx']
    op = state['op']
    data = load_user_data(user_id)
    # Если сумма 0, удаляем операцию
    if new_amount == 0:
        # Откатываем баланс
        if op['type'] == 'income':
            data['balance'] -= op['amount']
        else:
            data['balance'] += op['amount']
        data['history'].pop(idx)
        save_user_data(user_id, data)
        bot.send_message(message.chat.id, 'Операция с нулевой суммой удалена!', reply_markup=main_menu())
        user_states[user_id] = {'state': None}
        return
    # Корректируем баланс: сначала отменяем старую операцию, потом применяем новую
    if op['type'] == 'income':
        data['balance'] -= op['amount']
        data['balance'] += new_amount
    else:
        data['balance'] += op['amount']
        data['balance'] -= new_amount
    # Обновляем операцию
    data['history'][idx]['amount'] = new_amount
    data['history'][idx]['category'] = new_category
    data['history'][idx]['description'] = new_desc
    save_user_data(user_id, data)
    bot.send_message(message.chat.id, 'Операция обновлена!', reply_markup=main_menu())
    user_states[user_id] = {'state': None}

@bot.message_handler(func=lambda m: m.text == 'Настройки валюты')
def currency_settings(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('₽', '$', '€', '₸', '£', '¥', '₴', 'Br')
    kb.add('Назад')
    bot.send_message(message.chat.id, 'Выберите валюту для отображения:', reply_markup=kb)

@bot.message_handler(func=lambda m: m.text in ['₽', '$', '€', '₸', '£', '¥', '₴', 'Br'])
def set_currency(message):
    user_id = message.from_user.id
    data = load_user_data(user_id)
    data['currency'] = message.text
    save_user_data(user_id, data)
    bot.send_message(message.chat.id, f'Валюта установлена: {message.text}', reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == 'Лимиты по категориям')
def limits_menu(message):
    user_id = message.from_user.id
    data = load_user_data(user_id)
    cur = data.get('currency', '₽')
    limits = data.get('limits', {})
    cats = data['expense_categories']
    text = 'Текущие лимиты по категориям:'
    for cat in cats:
        lim = limits.get(cat)
        if lim:
            text += f'\n- {cat}: {lim}{cur}'
    if text == 'Текущие лимиты по категориям:':
        text += '\n(не установлены)'
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for cat in cats:
        kb.add(f'Установить лимит: {cat}')
        if cat in limits:
            kb.add(f'Удалить лимит: {cat}')
    kb.add('Назад')
    bot.send_message(message.chat.id, text, reply_markup=kb)

@bot.message_handler(func=lambda m: m.text.startswith('Установить лимит: '))
def set_limit_amount(message):
    user_id = message.from_user.id
    cat = message.text.replace('Установить лимит: ', '')
    user_states[user_id] = {'state': 'set_limit_amount', 'cat': cat}
    bot.send_message(message.chat.id, f'Введите лимит для категории "{cat}":', reply_markup=back_menu())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'set_limit_amount')
def save_limit(message):
    user_id = message.from_user.id
    state = user_states[user_id]
    if message.text == 'Назад':
        user_states[user_id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    try:
        lim = float(message.text.replace(',', '.'))
    except Exception:
        bot.send_message(message.chat.id, 'Ошибка: лимит должен быть числом. Введите лимит, например: 1000 или 500.50', reply_markup=back_menu())
        return
    data = load_user_data(user_id)
    data['limits'][state['cat']] = lim
    save_user_data(user_id, data)
    bot.send_message(message.chat.id, f'Лимит для "{state["cat"]}" установлен: {lim}{data.get("currency", "₽")}', reply_markup=settings_menu())
    user_states[user_id] = {'state': None}

@bot.message_handler(func=lambda m: m.text.startswith('Удалить лимит: '))
def del_limit(message):
    user_id = message.from_user.id
    cat = message.text.replace('Удалить лимит: ', '')
    data = load_user_data(user_id)
    if cat in data['limits']:
        del data['limits'][cat]
        save_user_data(user_id, data)
        bot.send_message(message.chat.id, f'Лимит для "{cat}" удалён.', reply_markup=settings_menu())
    else:
        bot.send_message(message.chat.id, 'Ошибка: лимит для этой категории не найден. Возможно, он уже был удалён.', reply_markup=settings_menu())

@bot.message_handler(func=lambda m: m.text == 'Импорт из Monefy')
def import_monefy_start(message):
    bot.send_message(message.chat.id, 'Пожалуйста, отправьте CSV-файл экспорта из Monefy.')
    user_states[message.from_user.id] = {'state': 'import_monefy_wait_file'}

@bot.message_handler(content_types=['document'])
def import_monefy_file(message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {})
    if state.get('state') != 'import_monefy_wait_file':
        return
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    # Пробуем разные кодировки
    text = None
    for encoding in ['utf-8', 'utf-8-sig', 'cp1251', 'latin1']:
        try:
            text = downloaded_file.decode(encoding)
            break
        except Exception:
            continue
    if text is None:
        bot.send_message(message.chat.id, 'Ошибка: не удалось прочитать файл. Проверьте, что вы отправили CSV-файл экспорта из Monefy.\n\nИнструкция:\n1. В приложении Monefy выберите экспорт в CSV.\n2. Отправьте этот файл боту.\n3. Файл должен быть в кодировке UTF-8.\n\nЕсли не получается — попробуйте экспортировать заново или обратитесь к администратору.', reply_markup=main_menu())
        user_states[user_id] = {'state': None}
        return
    import csv
    reader = csv.DictReader(text.splitlines())
    data = load_user_data(user_id)
    count = 0
    for row in reader:
        try:
            # Новый парсер под реальный формат Monefy
            date_str = row.get('date')
            if not date_str:
                continue
            # Преобразуем дату в формат YYYY-MM-DD HH:MM:SS
            try:
                date = datetime.strptime(date_str.strip(), '%d/%m/%Y').strftime('%Y-%m-%d 00:00:00')
            except Exception:
                date = date_str.strip()  # fallback
            category = (row.get('category') or '').strip() or 'Без категории'
            amount_str = row.get('amount')
            if not amount_str:
                continue
            amount = float(amount_str.replace(',', '.'))
            op_type = 'income' if amount > 0 else 'expense'
            amount = abs(amount)
            desc = (row.get('description') or '').strip()
            # Валюта из файла, если отличается от текущей
            currency = (row.get('currency') or '').strip()
            # Добавляем категорию, если новая
            if op_type == 'income' and category not in data['income_categories']:
                data['income_categories'].append(category)
            if op_type == 'expense' and category not in data['expense_categories']:
                data['expense_categories'].append(category)
            # Добавляем операцию
            data['history'].append({
                'type': op_type,
                'amount': amount,
                'category': category,
                'description': desc,
                'date': date
            })
            if op_type == 'income':
                data['balance'] += amount
            else:
                data['balance'] -= amount
            count += 1
        except Exception:
            continue
    save_user_data(user_id, data)
    if count == 0:
        bot.send_message(message.chat.id, (
            'Импортировано операций: 0\n'
            'Проверьте, что вы отправили именно CSV-файл экспорта из Monefy.\n\n'
            'Инструкция:\n'
            '1. В приложении Monefy выберите экспорт в CSV.\n'
            '2. Отправьте этот файл боту.\n'
            '3. Файл должен быть в кодировке UTF-8.\n\n'
            'Если не получается — попробуйте экспортировать заново или обратитесь к администратору.'
        ), reply_markup=main_menu())
    else:
        bot.send_message(message.chat.id, f'Импортировано операций: {count}', reply_markup=main_menu())
    user_states[user_id] = {'state': None}

@bot.message_handler(func=lambda m: m.text == 'Экспорт истории')
def export_history_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('Экспорт в CSV', 'Экспорт в Excel')
    kb.row('Назад')
    user_states[message.from_user.id] = {'state': 'export_history_format'}
    bot.send_message(message.chat.id, 'Выберите формат для экспорта истории:', reply_markup=kb)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'export_history_format')
def export_history_format(message):
    if message.text == 'Назад':
        user_states[message.from_user.id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    if message.text == 'Экспорт в CSV':
        user_states[message.from_user.id] = {'state': 'export_history_period', 'format': 'csv'}
    elif message.text == 'Экспорт в Excel':
        user_states[message.from_user.id] = {'state': 'export_history_period', 'format': 'xlsx'}
    else:
        bot.send_message(message.chat.id, 'Выберите формат из меню.', reply_markup=main_menu())
        return
    # Передаём формат в состояние при переходе к выбору периода
    state = user_states[message.from_user.id]
    ask_period_menu(message, 'export_history_period')
    user_states[message.from_user.id]['format'] = state['format']

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'export_history_period')
def export_history_period(message):
    state = user_states[message.from_user.id]
    if 'format' not in state:
        user_states[message.from_user.id] = {'state': 'export_history_format'}
        bot.send_message(message.chat.id, 'Сначала выберите формат экспорта.', reply_markup=main_menu())
        return
    if message.text == 'Период по дате':
        ask_date_range(message, 'export_history_date_range')
        return
    elif message.text == 'Назад':
        user_states[message.from_user.id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    now = datetime.now()
    if message.text == 'За день':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'За неделю':
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'За месяц':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'За год':
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        bot.send_message(message.chat.id, 'Выберите период из меню.', reply_markup=main_menu())
        return
    send_export_file(message, start, now, state['format'])
    user_states[message.from_user.id] = {'state': None}

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'export_history_date_range')
def export_history_date_range(message):
    state = user_states[message.from_user.id]
    if message.text == 'Назад':
        ask_period_menu(message, 'export_history_period')
        return
    if message.text == 'Сегодня (начало дня)':
        dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'Сегодня (конец дня)':
        dt = datetime.now().replace(hour=23, minute=59, second=59)
    else:
        try:
            dt = datetime.strptime(message.text.strip(), '%d.%m.%Y')
        except Exception:
            bot.send_message(message.chat.id, 'Некорректная дата! Введите в формате ДД.ММ.ГГГГ или выберите "Сегодня":', reply_markup=back_menu())
            return
    if state.get('period_step') == 'from':
        state['date_from'] = dt
        state['period_step'] = 'to'
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row('Сегодня (конец дня)')
        kb.add('Назад')
        bot.send_message(message.chat.id, 'Введите конечную дату (ДД.ММ.ГГГГ):', reply_markup=kb)
    else:
        date_from = state['date_from']
        date_to = dt
        send_export_file(message, date_from, date_to, state['format'])
        user_states[message.from_user.id] = {'state': None}

def send_error_to_admin(error_msg, user_id=None):
    """Отправляет ошибку администратору"""
    try:
        if user_id:
            error_msg = f"Ошибка у пользователя {user_id}:\n{error_msg}"
        bot.send_message(ADMIN_ID, f"❌ ОШИБКА БОТА:\n{error_msg}")
    except Exception as e:
        print(f"Не удалось отправить ошибку админу: {e}")

def send_export_file(message, start, end, fmt):
    import tempfile
    import csv
    user_id = message.from_user.id
    data = load_user_data(user_id)
    ops = [op for op in data['history'] if start <= datetime.strptime(op['date'], '%Y-%m-%d %H:%M:%S') <= end]
    if not ops:
        bot.send_message(message.chat.id, 'Нет операций за выбранный период.', reply_markup=main_menu())
        return
    if fmt == 'csv':
        with tempfile.NamedTemporaryFile('w+', encoding='utf-8', newline='', delete=False, suffix='.csv') as f:
            writer = csv.writer(f)
            writer.writerow(['Дата', 'Тип', 'Сумма', 'Категория', 'Описание'])
            for op in ops:
                writer.writerow([op['date'][:10], 'Доход' if op['type']=='income' else 'Расход', op['amount'], op.get('category', ''), op.get('description', '')])
            f.flush()
            f.seek(0)
            with open(f.name, 'rb') as sendf:
                bot.send_document(message.chat.id, sendf, visible_file_name='history.csv')
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
    else:
        try:
            import xlsxwriter
        except ImportError:
            error_msg = f"Пользователь {user_id} пытался экспортировать в Excel, но пакет xlsxwriter не установлен"
            send_error_to_admin(error_msg, user_id)
            bot.send_message(message.chat.id, 'Экспорт в Excel временно недоступен. Попробуйте экспорт в CSV.', reply_markup=main_menu())
            return
        with tempfile.NamedTemporaryFile('wb', delete=False, suffix='.xlsx') as f:
            workbook = xlsxwriter.Workbook(f)
            worksheet = workbook.add_worksheet('История')
            worksheet.write_row(0, 0, ['Дата', 'Тип', 'Сумма', 'Категория', 'Описание'])
            for i, op in enumerate(ops, 1):
                worksheet.write_row(i, 0, [op['date'][:10], 'Доход' if op['type']=='income' else 'Расход', op['amount'], op.get('category', ''), op.get('description', '')])
            workbook.close()
            f.flush()
            f.seek(0)
            with open(f.name, 'rb') as sendf:
                bot.send_document(message.chat.id, sendf, visible_file_name='history.xlsx')
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == 'Поиск')
def search_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('По описанию', 'По категории')
    kb.row('По сумме', 'По дате')
    kb.row('Назад')
    user_states[message.from_user.id] = {'state': 'search_menu'}
    bot.send_message(message.chat.id, 'Выберите критерий поиска:', reply_markup=kb)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'search_menu')
def search_criteria_handler(message):
    if message.text == 'Назад':
        user_states[message.from_user.id] = {'state': None}
        bot.send_message(message.chat.id, 'Главное меню', reply_markup=main_menu())
        return
    if message.text == 'По описанию':
        user_states[message.from_user.id] = {'state': 'search_desc'}
        bot.send_message(message.chat.id, 'Введите текст для поиска по описанию:', reply_markup=back_menu())
    elif message.text == 'По категории':
        data = load_user_data(message.from_user.id)
        cats = sorted(set(data['income_categories'] + data['expense_categories']))
        kb = category_menu(cats)
        user_states[message.from_user.id] = {'state': 'search_category'}
        bot.send_message(message.chat.id, 'Выберите категорию для поиска:', reply_markup=kb)
    elif message.text == 'По сумме':
        user_states[message.from_user.id] = {'state': 'search_amount'}
        bot.send_message(message.chat.id, 'Введите сумму или диапазон (например, 100 или 50-200):', reply_markup=back_menu())
    elif message.text == 'По дате':
        ask_date_range(message, 'search_date')
    else:
        # Проверяем, не ввёл ли пользователь данные в неправильном месте
        text = message.text.strip()
        # Проверяем, похоже ли на сумму или диапазон
        if '-' in text and any(c.isdigit() for c in text):
            try:
                parts = text.split('-')
                float(parts[0])
                float(parts[1])
                user_states[message.from_user.id] = {'state': 'search_amount'}
                search_by_amount(message)
                return
            except:
                pass
        # Проверяем, похоже ли на дату
        if len(text) == 10 and text.count('.') == 2:
            try:
                datetime.strptime(text, '%d.%m.%Y')
                user_states[message.from_user.id] = {'state': 'search_date', 'period_step': 'from'}
                search_by_date(message)
                return
            except:
                pass
        # Проверяем, похоже ли на число
        try:
            float(text.replace(',', '.'))
            user_states[message.from_user.id] = {'state': 'search_amount'}
            search_by_amount(message)
            return
        except:
            pass
        # Если ничего не подошло, показываем стандартное сообщение
        bot.send_message(message.chat.id, 'Выберите критерий из меню.', reply_markup=main_menu())

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'search_desc')
def search_by_desc(message):
    if message.text == 'Назад':
        search_menu(message)
        return
    query = message.text.strip().lower()
    data = load_user_data(message.from_user.id)
    results = [op for op in data['history'] if query in op.get('description', '').lower()]
    send_search_results(message, results)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'search_category')
def search_by_category(message):
    if message.text == 'Назад':
        search_menu(message)
        return
    category = message.text
    data = load_user_data(message.from_user.id)
    results = [op for op in data['history'] if op.get('category', 'Без категории') == category]
    send_search_results(message, results)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'search_amount')
def search_by_amount(message):
    if message.text == 'Назад':
        search_menu(message)
        return
    query = message.text.replace(',', '.').replace(' ', '')
    data = load_user_data(message.from_user.id)
    results = []
    try:
        if '-' in query:
            parts = query.split('-')
            min_val = float(parts[0])
            max_val = float(parts[1])
            # Автоматически сортируем диапазон
            if min_val > max_val:
                min_val, max_val = max_val, min_val
            results = [op for op in data['history'] if min_val <= op['amount'] <= max_val]
        else:
            val = float(query)
            results = [op for op in data['history'] if op['amount'] == val]
    except Exception:
        bot.send_message(message.chat.id, 'Ошибка: введите сумму или диапазон корректно. Пример: 100 или 50-200', reply_markup=back_menu())
        return
    send_search_results(message, results)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') == 'search_date')
def search_by_date(message):
    state = user_states[message.from_user.id]
    if message.text == 'Назад':
        search_menu(message)
        return
    if message.text == 'Сегодня (начало дня)':
        dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'Сегодня (конец дня)':
        dt = datetime.now().replace(hour=23, minute=59, second=59)
    else:
        try:
            dt = datetime.strptime(message.text.strip(), '%d.%m.%Y')
        except Exception:
            bot.send_message(message.chat.id, 'Некорректная дата! Введите в формате ДД.ММ.ГГГГ или выберите "Сегодня":', reply_markup=back_menu())
            return
    if state['period_step'] == 'from':
        state['date_from'] = dt
        state['period_step'] = 'to'
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row('Сегодня (конец дня)')
        kb.add('Назад')
        bot.send_message(message.chat.id, 'Введите конечную дату (ДД.ММ.ГГГГ):', reply_markup=kb)
    else:
        date_from = state['date_from']
        date_to = dt
        data = load_user_data(message.from_user.id)
        results = [op for op in data['history'] if date_from <= datetime.strptime(op['date'], '%Y-%m-%d %H:%M:%S') <= date_to]
        send_search_results(message, results)
        user_states[message.from_user.id] = {'state': None}

def send_search_results(message, results):
    user_states[message.from_user.id] = {'state': None}
    if not results:
        bot.send_message(message.chat.id, 'Ничего не найдено. Проверьте правильность ввода или попробуйте другой критерий поиска.', reply_markup=main_menu())
        return
    cur = load_user_data(message.from_user.id).get('currency', '₽')
    text = f'Найдено операций: {len(results)}'
    for op in results[-20:][::-1]:
        sign = '+' if op['type'] == 'income' else '-'
        category = op.get('category', 'Без категории')
        desc = op.get('description', '')
        date_only = op['date'][:10]
        text += f"\n{date_only}: {sign}{op['amount']}{cur} {category} {desc}"
    bot.send_message(message.chat.id, text, reply_markup=main_menu())

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {}).get('state')
    data = load_user_data(user_id)
    # Добавление дохода
    if state == 'income_category' and message.text in data['income_categories']:
        user_states[user_id] = {'state': 'income_amount', 'category': message.text}
        bot.send_message(message.chat.id, 'Введите сумму дохода:', reply_markup=back_menu())
    elif state == 'income_amount':
        try:
            amount = float(message.text.replace(',', '.'))
            user_states[user_id]['amount'] = amount
            bot.send_message(message.chat.id, 'Введите описание (или - если не нужно):', reply_markup=skip_menu())
            user_states[user_id]['state'] = 'income_desc'
        except Exception:
            bot.send_message(message.chat.id, 'Ошибка: сумма должна быть числом. Введите сумму, например: 100 или 99.50', reply_markup=back_menu())
            return
    elif state == 'income_desc':
        amount = user_states[user_id]['amount']
        category = user_states[user_id]['category']
        if message.text == 'Пропустить':
            desc = ''
        else:
            desc = message.text if message.text != '-' else ''
        data['balance'] += amount
        data['history'].append({
            'type': 'income',
            'amount': amount,
            'category': category,
            'description': desc,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        save_user_data(user_id, data)
        cur = data.get('currency', '₽')
        bot.send_message(message.chat.id, f'Доход {amount}{cur} ({category}) добавлен! Баланс: {data["balance"]}{cur}', reply_markup=main_menu())
        user_states[user_id] = {'state': None}
    # Добавление расхода
    elif state == 'expense_category' and message.text in data['expense_categories']:
        user_states[user_id] = {'state': 'expense_amount', 'category': message.text}
        bot.send_message(message.chat.id, 'Введите сумму расхода:', reply_markup=back_menu())
    elif state == 'expense_amount':
        try:
            amount = float(message.text.replace(',', '.'))
            user_states[user_id]['amount'] = amount
            bot.send_message(message.chat.id, 'Введите описание (или - если не нужно):', reply_markup=skip_menu())
            user_states[user_id]['state'] = 'expense_desc'
        except Exception:
            bot.send_message(message.chat.id, 'Ошибка: сумма должна быть числом. Введите сумму, например: 100 или 99.50', reply_markup=back_menu())
            return
    elif state == 'expense_desc':
        amount = user_states[user_id]['amount']
        category = user_states[user_id]['category']
        if message.text == 'Пропустить':
            desc = ''
        else:
            desc = message.text if message.text != '-' else ''
        data['balance'] -= amount
        data['history'].append({
            'type': 'expense',
            'amount': amount,
            'category': category,
            'description': desc,
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        save_user_data(user_id, data)
        cur = data.get('currency', '₽')
        lim = data.get('limits', {}).get(category)
        if lim is not None:
            # Считаем расходы по этой категории за неделю
            now = datetime.now()
            week_start = now - timedelta(days=now.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
            spent = 0
            for op in data['history']:
                op_date = datetime.strptime(op['date'], '%Y-%m-%d %H:%M:%S')
                if op['type'] == 'expense' and op.get('category') == category:
                    if op_date >= week_start:
                        spent += op['amount']
            if spent > lim:
                bot.send_message(message.chat.id, f'Внимание! Лимит по категории "{category}" превышен: {spent}{cur} > {lim}{cur}')
        bot.send_message(message.chat.id, f'Расход {amount}{cur} ({category}) добавлен! Баланс: {data["balance"]}{cur}', reply_markup=main_menu())
        user_states[user_id] = {'state': None}
    # Добавление/удаление категорий
    elif state == 'add_expense_category':
        cat = message.text.strip()
        if cat and cat not in data['expense_categories']:
            data['expense_categories'].append(cat)
            save_user_data(user_id, data)
            bot.send_message(message.chat.id, f'Категория "{cat}" добавлена!', reply_markup=settings_menu())
        else:
            bot.send_message(message.chat.id, 'Такая категория уже есть или некорректное имя.', reply_markup=settings_menu())
        user_states[user_id] = {'state': 'settings'}
    elif state == 'del_expense_category' and message.text in data['expense_categories']:
        data['expense_categories'].remove(message.text)
        save_user_data(user_id, data)
        bot.send_message(message.chat.id, f'Категория "{message.text}" удалена!', reply_markup=settings_menu())
        user_states[user_id] = {'state': 'settings'}
    elif state == 'add_income_category':
        cat = message.text.strip()
        if cat and cat not in data['income_categories']:
            data['income_categories'].append(cat)
            save_user_data(user_id, data)
            bot.send_message(message.chat.id, f'Категория "{cat}" добавлена!', reply_markup=settings_menu())
        else:
            bot.send_message(message.chat.id, 'Такая категория уже есть или некорректное имя.', reply_markup=settings_menu())
        user_states[user_id] = {'state': 'settings'}
    elif state == 'del_income_category' and message.text in data['income_categories']:
        data['income_categories'].remove(message.text)
        save_user_data(user_id, data)
        bot.send_message(message.chat.id, f'Категория "{message.text}" удалена!', reply_markup=settings_menu())
        user_states[user_id] = {'state': 'settings'}
    else:
        bot.send_message(message.chat.id, 'Ошибка: выберите действие через меню. Не вводите команды вручную.', reply_markup=main_menu())
        user_states[user_id] = {'state': None}

# --- Универсальный выбор периода ---
def ask_period_menu(message, next_state):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('За день', 'За неделю', 'За месяц', 'За год')
    kb.row('Период по дате')
    kb.row('Назад')
    user_states[message.from_user.id] = {'state': next_state}
    bot.send_message(message.chat.id, 'Выберите период:', reply_markup=kb)

def ask_date_range(message, next_state):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row('Сегодня (начало дня)')
    kb.add('Назад')
    user_states[message.from_user.id] = {'state': next_state, 'period_step': 'from'}
    bot.send_message(message.chat.id, 'Введите начальную дату (ДД.ММ.ГГГГ):', reply_markup=kb)

@bot.message_handler(func=lambda m: user_states.get(m.from_user.id, {}).get('state') in ['history_date_range', 'stats_date_range', 'export_history_date_range', 'search_date'])
def date_range_handler(message):
    state = user_states[message.from_user.id]
    if message.text == 'Назад':
        if state['state'] == 'history_date_range':
            ask_period_menu(message, 'history_period')
        elif state['state'] == 'stats_date_range':
            ask_period_menu(message, 'stats_period')
        elif state['state'] == 'export_history_date_range':
            ask_period_menu(message, 'export_history_period')
        elif state['state'] == 'search_date':
            search_menu(message)
        return
    if message.text == 'Сегодня (начало дня)':
        dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    elif message.text == 'Сегодня (конец дня)':
        dt = datetime.now().replace(hour=23, minute=59, second=59)
    else:
        try:
            dt = datetime.strptime(message.text.strip(), '%d.%m.%Y')
        except Exception:
            bot.send_message(message.chat.id, 'Некорректная дата! Введите в формате ДД.ММ.ГГГГ или выберите "Сегодня":', reply_markup=back_menu())
            return
    if state['period_step'] == 'from':
        state['date_from'] = dt
        state['period_step'] = 'to'
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.row('Сегодня (конец дня)')
        kb.add('Назад')
        bot.send_message(message.chat.id, 'Введите конечную дату (ДД.ММ.ГГГГ):', reply_markup=kb)
    else:
        date_from = state['date_from']
        date_to = dt
        if state['state'] == 'history_date_range':
            show_history_for_period(message, date_from, date_to)
        elif state['state'] == 'stats_date_range':
            show_stats_for_period(message, date_from, date_to)
        elif state['state'] == 'export_history_date_range':
            send_export_file(message, date_from, date_to, state['format'])
        elif state['state'] == 'search_date':
            data = load_user_data(message.from_user.id)
            results = [op for op in data['history'] if date_from <= datetime.strptime(op['date'], '%Y-%m-%d %H:%M:%S') <= date_to]
            send_search_results(message, results)
        user_states[message.from_user.id] = {'state': None}

if __name__ == '__main__':
    bot.polling(none_stop=True) 
