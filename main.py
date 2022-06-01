from aiogram import Dispatcher, executor, Bot, types
import sqlite3 as sq
from aiogram.contrib.fsm_storage.memory import MemoryStorage  # импорт харнилища
from aiogram.dispatcher import FSMContext  # с его помощью указываем, что хендлер используется в машине состояний
from aiogram.dispatcher.filters.state import State, StatesGroup  # импорт состояний
from aiogram.dispatcher.filters import Text  # filter text
import time
import os
import logging
from aiogram.utils.executor import start_webhook


#base tokens
storage = MemoryStorage()
TOKEN = os.getenv('BOT_TOKEN')
bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=storage)

HEROKU_APP_NAME = os.getenv("HEROKU_APP_NAME")

#setting up webhooks
WEBHOOK_HOST = f"https://{HEROKU_APP_NAME}.herokuapp.com"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

#webserver settings
WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = os.getenv("PORT", default=8000)

async def on_startup(dispatcher):
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

async def on_shutdown(dispatcher):
    await bot.delete_webhook()
    con.close() #close db

#FSM
class FSM(StatesGroup):
    # states for reciepts
    name = State()
    description = State()
    link = State()
    choose_category = State()
    rec_by_cat = State()
    del_rec = State()

    # states for categories
    add_cat = State()
    del_cat = State()
    rename_cat_old = State()
    rename_cat_new = State()

    # states for notes
    add_note = State()
    del_note = State()
    # show_notes = State()

    #states for editing reciepts
    row_id_e = State()
    name_e = State()
    description_e = State()
    link_e = State()
    choose_category_e = State()


# databases
con = sq.connect('recipt_book.db')
cur = con.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS book(chat_id INTEGER, number INTEGER, name TEXT, description TEXT, link TEXT, category TEXT)')
cur.execute('CREATE TABLE IF NOT EXISTS categories(chat_id INTEGER, category TEXT)')
cur.execute('CREATE TABLE IF NOT EXISTS notes(chat_id INTEGER, number INTEGER, note TEXT, date TEXT)')

# base keyboard
async def base_menu(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    b_all = types.KeyboardButton(text='Категорії та рецепти')
    b_add_r = types.KeyboardButton(text='Додати рецепт')
    b_notes = types.KeyboardButton(text="Нотатки")
    b_cancel = types.KeyboardButton(text="Скасувати")
    kb.add(b_all, b_add_r, b_notes, b_cancel)
    await message.answer('👉 Скористайся командами знизу:', reply_markup=kb)

# базовый хендлер для загрузки машины состояний
@dp.message_handler(lambda x: x.text.lower() == "додати рецепт", state=None)
async def add_rec(message: types.Message):
    await FSM.name.set()
    await message.reply("👉 Напши назву")

# cancel handler
@dp.message_handler(state="*", commands="скасувати")
@dp.message_handler(Text(equals='скасувати', ignore_case=True), state="*")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await base_menu(message)
        return
    await state.finish()
    await base_menu(message)

# ловим ответ от пользователя и пишем в словарь
@dp.message_handler(state=FSM.name)
async def load_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['name'] = message.text
    await FSM.next()
    await message.reply("👉Тепер додай опис")

# ловим второй ответ от пользователя и пишем в словарь
@dp.message_handler(state=FSM.description)
async def description(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['description'] = message.text
    await FSM.next()
    await message.reply("👉 Тепер додай посилання на рецепт")

# ловим второй ответ от пользователя и пишем в словарь
@dp.message_handler(state=FSM.link)
async def link(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['link'] = message.text
    await FSM.next()
    await message.reply(
        "👉 Тепер обери одну з достуних категорій для рецепту. Якщо нічого не підходить, то введи будь-що.")
    cur.execute('SELECT category FROM categories WHERE chat_id = :id', {"id": message.chat.id})
    res = cur.fetchall()
    for i in res:
        await message.answer(i[0])

# choose category for reciept
@dp.message_handler(state=FSM.choose_category)
async def choose_cat(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data["category"] = message.text
    # db statements
    cur.execute('SELECT category FROM categories WHERE chat_id = :id', {"id": message.chat.id})
    res = cur.fetchall()

    cur.execute("SELECT rowid, number FROM book WHERE chat_id == :id", {"id": message.chat.id})
    count_num = 0
    res_num = cur.fetchall()
    print(res_num)
    if not res_num:
        count_num = 1
    else:
        cur.execute("SELECT rowid FROM book WHERE chat_id == :id", {"id": message.chat.id})
        res_loc = cur.fetchall()
        res_loc_id = res_loc[-1][0]
        print(res_loc_id)
        cur.execute("SELECT number FROM book WHERE rowid == :last_row", {"last_row": res_loc_id})
        res_last_id = cur.fetchall()
        print(res_last_id[0][0])
        count_num = res_last_id[0][0]+1


    count = 0
    for i in res:
        if data["category"].lower() in i[0].lower():
            count = 1
            break
        else:
            count = 0
    if count > 0:
        cur.execute(
            "INSERT INTO book (chat_id, number, name, description, link, category) VALUES (:id, :num, :name, :desc, :link, :cat)",
            {"id": message.chat.id, "name": data["name"], "desc": data["description"], "link": data["link"],
             "cat": data["category"], "num": count_num})
        con.commit()
        await message.reply("👉 Супер, відповіді записано!")
    else:
        cur.execute(
            "INSERT INTO book (chat_id, number, name, description, link, category) VALUES (:id, :num, :name, :desc, :link, 'Загальна категорія')",
            {"id": message.chat.id, "name": data["name"], "desc": data["description"], "link": data["link"], "num": count_num})
        con.commit()
        cur.execute("SELECT category FROM categories WHERE chat_id == :id", {"id": message.chat.id})

        res = cur.fetchall()
        count_inside = 0
        for i in res:
            print(i[0])
            if i[0].lower() == "загальна категорія":
                count_inside +=1
                break
        if count_inside == 0:
            print("count_inside = ", count_inside)
            cur.execute("INSERT INTO categories (chat_id, category) VALUES (:id, 'Загальна категорія')", {"id": message.chat.id})
            con.commit()

        await message.reply("👉 Додано в \"Загальну категорію\".\nВідповіді записано!")
    await state.finish()  # clean all data and end the states


@dp.message_handler(commands='start')
async def start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    b_all = types.KeyboardButton(text='Категорії та рецепти')
    b_add_r = types.KeyboardButton(text='Додати рецепт')
    b_notes = types.KeyboardButton(text="Нотатки")
    b_cancel = types.KeyboardButton(text="Скасувати")
    kb.add(b_all, b_add_r, b_notes, b_cancel)
    await message.answer(
        'Привіт, я бот-книга рецептів 📖🍔. \n 👉 Скористайся командами знизу. Кнопка "Скасувати" - скасовує дію та повертає в головне меню.',
        reply_markup=kb)

@dp.message_handler(lambda mes: mes.text == 'Всі категорії')
async def show_all_cat(message: types.Message):
    cur.execute("SELECT category FROM categories WHERE chat_id == :id", {"id": message.chat.id})
    res_categories = cur.fetchall()
    cur.execute("SELECT category FROM book WHERE chat_id == :id", {"id": message.chat.id})
    res_count = cur.fetchall()
    count_cat = 0
    for i in res_categories:
        count_cat +=1
    for i in res_categories:
        count = 0
        for k in res_count:
            if k[0].lower() in i[0].lower():
                count +=1
        # print(i[0])
        await message.answer(f"<b>{i[0]} :</b> <i>{count} рец.</i>", parse_mode=types.ParseMode.HTML)
    await message.answer(f"<i>Усього категорій: {count_cat}</i>", parse_mode=types.ParseMode.HTML)

@dp.message_handler(lambda mes: mes.text.lower() == 'категорії та рецепти')
async def all_cat(message: types.Message):
    kb_cat = types.ReplyKeyboardMarkup(resize_keyboard=True)
    red_cat = types.KeyboardButton(text="Редагувати категорії")
    rec_by_cat = types.KeyboardButton(text="Рецепти по категорії")
    all_rec = types.KeyboardButton(text="Всі рецепти")
    b_cancel = types.KeyboardButton(text="Скасувати")
    b_all = types.KeyboardButton(text='Всі категорії')
    del_rec = types.KeyboardButton(text="Видалити рецепт")
    edit_rec = types.KeyboardButton(text="Редагувати рецепт")

    kb_cat.add(b_all, all_rec, rec_by_cat, red_cat, edit_rec, del_rec, b_cancel)
    await message.answer("👉 Обери пункт меню:", reply_markup=kb_cat)

@dp.message_handler(lambda x: x.text.lower() == "редагувати рецепт", state=None)
async def base_edit_rec(message: types.Message):
    await FSM.row_id_e.set()
    await message.reply("👉 Введи номер рецепту")

# cancel handler
@dp.message_handler(state="*", commands="скасувати")
@dp.message_handler(Text(equals='скасувати', ignore_case=True), state="*")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    # print(current_state)
    if current_state is None:
        await base_menu(message)
        return
    await state.finish()
    await base_menu(message)

@dp.message_handler(state=FSM.row_id_e)
async def id_edit_rec(message: types.Message, state: FSMContext):
    async with state.proxy() as edit:
        edit["id"] = message.text

    cur.execute("SELECT number, name FROM book")
    res = cur.fetchall()
    count = 0
    for i in res:
        if int(edit["id"]) == int(i[0]):
            count += 1
    if count == 0:
        await message.reply("Такого номеру не існує ⛔ Скористайся командою заново.")
        await state.finish()
        return

    name = ''
    for i in res:
        if int(edit["id"]) == int(i[0]):
            name = i[1]
    await message.answer(f"<b><i>Стара назва:</i></b> {name}", parse_mode=types.ParseMode.HTML)
    await message.reply("👉 Напши нову назву")
    await FSM.name_e.set()

@dp.message_handler(state=FSM.name_e)
async def name_edit_rec(message: types.Message, state: FSMContext):
    async with state.proxy() as edit:
        edit["name"] = message.text
    await FSM.next()
    cur.execute("SELECT number, description FROM book")
    res = cur.fetchall()
    desc = ''
    for i in res:
        if int(edit["id"]) == int(i[0]):
            desc = i[1]
    await message.answer(f"<b><i>Старий опис:</i></b> {desc}", parse_mode=types.ParseMode.HTML)
    await message.reply("👉 Напши новий опис")

@dp.message_handler(state=FSM.description_e)
async def desc_edit_rec(message: types.Message, state: FSMContext):
    async with state.proxy() as edit:
        edit["desc"] = message.text
    await FSM.next()
    cur.execute("SELECT number, link FROM book")
    res = cur.fetchall()
    link = ''
    for i in res:
        if int(edit["id"]) == int(i[0]):
            link = i[1]
    await message.answer(f"<b><i>Старе посилання:</i></b> {link}", parse_mode=types.ParseMode.HTML)
    await message.reply("👉 Напши нове посилання")

@dp.message_handler(state=FSM.link_e)
async def desc_edit_rec(message: types.Message, state: FSMContext):
    async with state.proxy() as edit:
        edit["link"] = message.text
    await FSM.next()
    await message.reply(
        "👉 Тепер обери одну з достуних категорій для рецепту. Якщо нічого не підходить, то введи будь-що.")
    cur.execute('SELECT category FROM categories WHERE chat_id = :id', {"id": message.chat.id})
    res = cur.fetchall()
    for i in res:
        await message.answer(i[0])

    cur.execute("SELECT number, category FROM book")
    res_book = cur.fetchall()
    categ = ''
    for i in res_book:
        if int(edit["id"]) == int(i[0]):
            categ = i[1]
    await message.answer(f"<b><i>Стара категорія:</i></b> {categ}", parse_mode=types.ParseMode.HTML)

# choose category for reciept
@dp.message_handler(state=FSM.choose_category_e)
async def choose_cat_edit_rec(message: types.Message, state: FSMContext):
    async with state.proxy() as edit:
        edit["category"] = message.text
    # db statements

    cur.execute('SELECT category FROM categories WHERE chat_id = :id', {"id": message.chat.id})
    res = cur.fetchall()
    count = 0
    for i in res:
        if edit["category"].lower() in i[0].lower():
            count = 1
            break
        else:
            count = 0
    if count > 0:
        cur.execute("UPDATE book SET chat_id = :id, name = :name, description = :desc, link = :link, category = :cat WHERE number == :num", {"id": message.chat.id, "name": edit["name"], "desc": edit["desc"], "link": edit["link"],"cat": edit["category"], "num": edit["id"]})
        con.commit()
        await message.reply("👉 Супер, відповіді записано!")
    else:
        cur.execute("UPDATE book SET chat_id = :id, name = :name, description = :desc, link = :link, category = 'Загальна категорія' WHERE number == :num", {"id": message.chat.id, "name": edit["name"], "desc": edit["desc"], "link": edit["link"], "num": edit["id"]})
        con.commit()
        cur.execute("SELECT category FROM categories WHERE chat_id == :id", {"id": message.chat.id})

        res = cur.fetchall()
        count_inside = 0
        for i in res:
            print(i[0])
            if i[0].lower() == "загальна категорія":
                count_inside +=1
                break
        if count_inside == 0:
            print("count_inside = ", count_inside)
            cur.execute("INSERT INTO categories (chat_id, category) VALUES (:id, 'Загальна категорія')", {"id": message.chat.id})
            con.commit()

        await message.reply("👉 Додано в \"Загальну категорію\".\nВідповіді записано!")
    await state.finish()  # clean all data and end the states

@dp.message_handler(lambda x: x.text.lower() == "рецепти по категорії", state=None)
async def base_rec_by_cat(message: types.Message):
    await FSM.rec_by_cat.set()
    await message.reply("👉 Введи назву")

@dp.message_handler(state=FSM.rec_by_cat)
async def rec_by_cat(message: types.Message, state: FSMContext):
    async with state.proxy() as rec_cat:
        rec_cat["category"] = message.text
    cur.execute("SELECT chat_id, name, description, link, category, rowid, number FROM book WHERE chat_id == :id", {"id": message.chat.id})
    res = cur.fetchall()
    cur.execute("SELECT category FROM categories WHERE chat_id == :id", {"id": message.chat.id})
    res_cat = cur.fetchall()
    count_cat = 0
    for k in res_cat:
        if rec_cat["category"].lower() in k[0].lower():
            count_cat += 1
    if count_cat == 0:
        await state.finish()
        await message.reply("Такої категорії не існує ⛔")
        return
    await message.reply(f"Список по категорії \"{rec_cat['category']}\": ")
    count = 0
    for i in res:
        if i[4].lower() == rec_cat["category"].lower():
            count += 1
            await message.answer(f"""
            <b><i>Рецепт №{i[6]}</i></b>\n🍲 <b>Назва:</b> {i[1]}\n📃 <b>Опис:</b> {i[2]}\n📎 <b>Посилання:</b> {i[3]}
            """, parse_mode=types.ParseMode.HTML)

    await message.answer(f"Усього рецептів у категорії \"{rec_cat['category']}\": {count}")
    await state.finish()

@dp.message_handler(lambda x: x.text.lower() == "видалити рецепт", state=None)
async def base_del_rec(message: types.Message):
    await FSM.del_rec.set()
    await message.reply("👉 Введи номер рецепту")

@dp.message_handler(state=FSM.del_rec)
async def del_rec(message: types.Message, state: FSMContext):
    async with state.proxy() as rec:
        rec["num"] = message.text
    print(rec["num"])
    cur.execute("SELECT number FROM book WHERE chat_id == :id", {"id": message.chat.id})
    res = cur.fetchall()
    count = 0
    if rec["num"].isdigit() == False:
        await state.finish()
        await message.reply("Введено некоректне значення ⛔")
        return
    for i in res:
        if int(rec["num"]) == int(i[0]):
            count += 1
    if count == 0:
        await state.finish()
        await message.reply("Такого номеру не існує ⛔")
        return
    cur.execute("DELETE FROM book WHERE chat_id == :id and number == :num", {"id": message.chat.id, "num": rec["num"]})
    con.commit()
    await state.finish()
    await message.reply("👉 Готово")

@dp.message_handler(lambda x: x.text.lower() == "всі рецепти")
async def all_rec(message: types.Message):
    cur.execute("SELECT chat_id, number, name, description, link, category, rowid FROM book WHERE chat_id == :id", {"id": message.chat.id})
    res = cur.fetchall()
    count = 0
    for i in res:
        count += 1
        await message.answer(f"""
            <b><i>Рецепт №{i[1]}</i></b>\n🍲 <b>Назва: {i[2]}</b>\n📃<b> Опис:</b> {i[3]}\n📎<b> Посилання:</b> {i[4]}\n🗄<b> Категорія:</b> {i[5]}\n
            """, parse_mode=types.ParseMode.HTML)
    # await message.answer(f"Усього <b><i>{count} рецептів</i></b>", parse_mode=types.ParseMode.HTML)
    await message.answer(f"<i>Усього рецептів: {count}</i>", parse_mode=types.ParseMode.HTML)

@dp.message_handler(lambda x: x.text.lower() == "редагувати категорії")
async def red_cat(message: types.Message):
    red_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    b_add_cat = types.KeyboardButton(text="Додати категорію")
    b_del_cat = types.KeyboardButton(text="Видалити категорію")
    b_rename_cat = types.KeyboardButton(text="Перейменувати")
    b_cancel = types.KeyboardButton(text="Скасувати")
    b_all = types.KeyboardButton(text='Всі категорії')
    red_kb.add(b_add_cat, b_del_cat, b_all, b_rename_cat, b_cancel)
    await message.answer("👉 Тут можна відредагувати категорії", reply_markup=red_kb)

#base handler for rename category
@dp.message_handler(lambda x: x.text.lower() == "перейменувати", state=None)
async def base_rename_cat(message: types.Message):
    await FSM.rename_cat_old.set()
    await message.reply("👉 Напиши назву категорії, котру треба перейменувати")

@dp.message_handler(state=FSM.rename_cat_old)
async def rename_cat_old(message: types.Message, state: FSMContext):
    async with state.proxy() as rename:
        rename["old"] = message.text

    #перевірка коректності вводу
    cur.execute("SELECT category FROM categories WHERE chat_id == :id", {"id": message.chat.id})
    res = cur.fetchall()
    count = 0
    for i in res:
        if rename["old"].lower() in i[0].lower():
            count += 1
    if count == 0:
        await message.reply("Такої катеорії не існує ⛔")
        await state.finish()
        return
    await FSM.next()
    await message.reply("👉 Напиши нову назву")

@dp.message_handler(state=FSM.rename_cat_new)
async def rename_cat_new(message: types.Message, state: FSMContext):
    async with state.proxy() as rename:
        rename["new"] = message.text
    r_id = 0
    cur.execute("SELECT rowid, category FROM categories WHERE chat_id == :id", {"id": message.chat.id})
    res = cur.fetchall()
    for i in res:
        if rename["old"].lower() in i[1].lower():
            r_id = int(i[0])
    cur.execute("UPDATE categories SET category = :categ WHERE rowid == :row_id and chat_id == :id", {"row_id": r_id, "id": message.chat.id, "categ": rename["new"]})
    cur.execute("UPDATE book SET category = :categ_new WHERE category == :categ_old and chat_id == :id", {"categ_new": rename["new"], "categ_old": rename["old"], "id": message.chat.id})
    con.commit()
    await state.finish()
    await message.reply("👉 Готово")

# base handler for new categories
@dp.message_handler(lambda x: x.text.lower() == "додати категорію", state=None)
async def add_cat(message: types.Message):
    await FSM.add_cat.set()
    await message.reply("👉 Напши назву")

# cancel handler
@dp.message_handler(state="*", commands="скасувати")
@dp.message_handler(Text(equals='скасувати', ignore_case=True), state="*")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await base_menu(message)
        return
    await base_menu(message)
    await state.finish()


@dp.message_handler(state=FSM.add_cat)
async def load_cat(message: types.Message, state: FSMContext):
    async with state.proxy() as category:
        category['name'] = message.text
    cur.execute("SELECT category FROM categories WHERE chat_id == :id", {"id": message.chat.id})
    res = cur.fetchall()
    count = 0
    for i in res:
        if category["name"].lower() in i[0].lower():
            count += 1
    if count > 0:
        await message.reply("Така категорія вже існує⛔")
        await state.finish()
        return
    cur.execute("INSERT INTO categories (chat_id, category) VALUES (:id, :cat)",
                {"id": message.chat.id, "cat": category["name"]})
    con.commit()
    await state.finish()
    await message.reply("👉 Готово")

# base handler for del cat
@dp.message_handler(lambda x: x.text.lower() == "видалити категорію", state=None)
async def del_cat(message: types.Message):
    await FSM.del_cat.set()
    await message.reply("👉 Напши назву категорії для видалення (видаляться всі рецепти з категорії ⛔)")

@dp.message_handler(state=FSM.del_cat)
async def del_cat(message: types.Message, state: FSMContext):
    async with state.proxy() as del_category:
        del_category["name"] = message.text.lower()
    cur.execute("SELECT * FROM categories")
    res = cur.fetchall()
    cat_count = 0
    for i in res:
        if i[0] == message.chat.id and i[1].lower() == del_category["name"]:
            cur.execute("DELETE FROM categories WHERE chat_id == :id and category == :cat",
                        {"id": message.chat.id, "cat": i[1]})
            cur.execute("DELETE FROM book WHERE chat_id == :id and category == :cat",
                        {"id": message.chat.id, "cat": i[1]})
            con.commit()
            cat_count += 1

    if cat_count == 0:
        await message.reply("Такої категорії не існує ⛔")
        # print(i)
    else:
        await message.reply("👉 Готово")
    await state.finish()

@dp.message_handler(lambda x: x.text.lower() == 'нотатки')
async def notes(message: types.Message):
    n_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    add_n = types.KeyboardButton(text="Додати нотатку")
    del_n = types.KeyboardButton(text="Видалити нотатку")
    show_n = types.KeyboardButton(text="Показати всі нотатки")
    cancel_n = types.KeyboardButton(text="Скасувати")
    n_kb.add(add_n, del_n, show_n, cancel_n)
    await message.answer("👉 Скористайся кнопками внизу", reply_markup=n_kb)

#notes handler base
@dp.message_handler(lambda x: x.text.lower() == 'додати нотатку', state=None)
async def base_add_notes(message: types.Message):
    await FSM.add_note.set()
    await message.reply("👉 Напиши нотатку")

@dp.message_handler(state=FSM.add_note)
async def add_note(message: types.Message, state: FSMContext):
    async with state.proxy() as note:
        note["note"] = message.text
    print(note["note"])
    act_time = time.strftime('%d.%m.%Y %H:%M')
    cur.execute("SELECT rowid, number FROM notes WHERE chat_id == :id", {"id": message.chat.id})
    count_num = 0
    res_num = cur.fetchall()
    print(res_num)
    if not res_num:
        count_num = 1
    else:
        cur.execute("SELECT rowid FROM notes WHERE chat_id == :id", {"id": message.chat.id})
        res_loc = cur.fetchall()
        res_loc_id = res_loc[-1][0]
        print(res_loc_id)
        cur.execute("SELECT number FROM notes WHERE rowid == :last_row", {"last_row": res_loc_id})
        res_last_id = cur.fetchall()
        print(res_last_id[0][0])
        count_num = res_last_id[0][0]+1
    cur.execute("INSERT INTO notes (chat_id, number, note, date) VALUES (:id, :num, :note, :date)",
                {"id": message.chat.id, "note": note["note"], "date": act_time, "num": count_num})
    con.commit()
    print(act_time)
    await state.finish()
    await message.reply("👉 Готово")

@dp.message_handler(lambda x: x.text.lower() == 'видалити нотатку', state=None)
async def base_del_notes(message: types.Message):
    await FSM.del_note.set()
    await message.reply("👉 Напиши номер нотатки для видалення")

@dp.message_handler(state=FSM.del_note)
async def del_note(message: types.Message, state: FSMContext):
    async with state.proxy() as note:
        note["number"] = message.text
    # print(note["number"])
    cur.execute("SELECT number FROM notes")
    res = cur.fetchall()
    count = 0
    if note["number"].isdigit() == False:
        await state.finish()
        await message.reply("Введено некоректне значення ⛔")
        return

    for i in res:
        if int(note["number"]) == int(i[0]):
            count += 1
    if count == 0:
        await state.finish()
        await message.reply("Такого номеру не існує ⛔")
        return


    cur.execute("DELETE FROM notes WHERE chat_id == :id and number == :row",
                {"id": message.chat.id, "row": note["number"]})
    con.commit()

    await state.finish()
    await message.reply("👉 Готово")

@dp.message_handler(lambda x: x.text.lower() == "показати всі нотатки")
async def base_show_notes(message: types.Message):
    await message.reply("👉 Список всіх нотаток:")
    cur.execute("SELECT note, date, number FROM notes WHERE chat_id == :id", {"id": message.chat.id})
    res = cur.fetchall()
    count = 0
    for i in res:
        await message.answer('📖 <b>Нотатка №' + str(i[2]) + " (" + str(i[1]) + "):</b>\n" + str(i[0]), parse_mode=types.ParseMode.HTML)
        count += 1
    await message.answer(f"<i>Усього нотаток: {count}</i>", parse_mode=types.ParseMode.HTML)

@dp.message_handler(state="*", commands="скасувати")
@dp.message_handler(Text(equals='скасувати', ignore_case=True), state="*")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await base_menu(message)
        return
    await base_menu(message)
    await state.finish()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_webhook(dispatcher=dp,
                  webhook_path=WEBHOOK_PATH,
                  skip_updates=True,
                  on_startup=on_startup,
                  on_shutdown=on_shutdown,
                  host=WEBAPP_HOST,
                  port=WEBAPP_PORT
                  )

    # executor.start_polling(dp, skip_updates=True)
    # con.close()
