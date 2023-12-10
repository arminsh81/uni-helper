import os
import re

from asyncache import cached as asyncached
from cachetools import TTLCache
from pyrogram import Client
from pyrogram.types import InputMediaDocument as pyrogram_InputMediaDocument
from pyrogram.enums import ParseMode
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InputMediaDocument, ReplyKeyboardRemove, \
    InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, \
    filters, CallbackQueryHandler
import jdatetime
import locale
import helpers
import num2fawords

import admin_texts
import db
import texts
import admin_panel
from config import TOKEN, API_ID, API_HASH

locale.setlocale(locale.LC_ALL, jdatetime.FA_LOCALE)

# States for the conversation
START, CHOOSE_TASK, GET_NAME, GET_FILES, WAIT_FOR_FINISH, CONFIRM_SUBMIT = range(6)

# Temporary storage for user data
user_data_dict = TTLCache(maxsize=512, ttl=1800)
user_data_cache = TTLCache(maxsize=100, ttl=90)


# Start menu
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [KeyboardButton(texts.SEND_TASK)],
        [KeyboardButton(texts.ABOUT_ME_BUTTON), KeyboardButton(texts.DONATE_ME_BUTTON)]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    msg = texts.START_TEXT
    if db.is_admin(update.effective_user.id):
        msg += admin_texts.YOU_ARE_ADMIN
    await update.message.reply_text(msg, reply_markup=reply_markup)
    return ConversationHandler.END


# about me button handler
async def about_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(texts.ABOUT_ME, disable_web_page_preview=True, parse_mode='markdown')


# donate me button handler
async def donate_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(texts.DONATE_ME, disable_web_page_preview=True, parse_mode='markdown')


# handler when the user wants to cancel the operation
async def wanna_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(texts.WANNA_START)


# Function to handle the "ارسال تمرین" button
async def send_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tasks = db.get_tasks()
    if tasks:
        keyboard = [[InlineKeyboardButton(task.task_name, callback_data=f"SelectTask {task.task_id}")] for task in
                    tasks]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(texts.WHAT_TASK, reply_markup=reply_markup)
        return GET_NAME
    else:
        await update.message.reply_text(texts.NO_TASK_AVAILABLE)
        return ConversationHandler.END


# Function to handle the chosen task
async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    task_id = update.callback_query.data.split()[1]
    user_data_dict[update.effective_user.id] = {'task_id': task_id}
    task_detail = db.get_task(task_id)
    admin = await get_cached_admin_detail(task_detail.admin_id)
    jalali_deadline = jdatetime.datetime.fromgregorian(datetime=task_detail.deadline).strftime('''%A %d %B
%Y-%m-%d %H:%M''')
    await update.callback_query.answer("حلع")
    await update.effective_message.edit_text(
        texts.OK_SELECTED_TASK.format(task_detail.task_name, task_detail.desc, admin.mention_html(),
                                      f"(@{admin.username})" if admin.username else "",
                                      jalali_deadline), reply_markup=None, parse_mode='html')
    await update.effective_message.reply_text(texts.WHAT_NAME, reply_markup=ReplyKeyboardRemove())
    return GET_FILES


# Function to handle getting the user's name
async def get_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text
    if re.match(r"^[A-Za-z]+(?: [A-Za-z]+){1,3}$", name):
        user_id = update.effective_user.id
        if user_id not in user_data_dict:
            await update.message.reply_text(texts.PLZ_AGAIN)
            return -1
        user_data_dict[user_id]['name'] = name.title()
        await update.message.reply_text(texts.TNX_SEND.format(name), reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text(texts.PLZ_ENGLISH_NAME)
        return GET_FILES
    return WAIT_FOR_FINISH


# Function to handle receiving images or pdfs
async def wait_for_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = update.message.photo or update.message.document
    user_data = user_data_dict[update.effective_user.id]
    if update.message.photo:
        await update.message.reply_text('هنوز تبدیل عکس به پی دی اف پشتیبانی نمیشه =(')
        # user_data_dict[update.effective_user.id].setdefault('images', []).append(update.message.photo[-1].file_id)
        # print(user_data_dict)
        # keyboard = [[KeyboardButton('تموم')]]
        # reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        # await update.message.reply_text(
        #     "Image received. You can keep sending more images or press 'تموم' when finished.",
        #     reply_markup=reply_markup)
    elif update.message.document:
        document = update.message.document
        file_size = document.file_size
        task_detail = db.get_task(user_data['task_id'])
        if file_size > 1000000 * task_detail.size_limit:
            y_count = file_size // 1000000 - 1  # for each MB, add a ی to text for emphasizing
            file_less_than_size = 1  # MB
            await update.message.reply_text(texts.SIZE_BIG.format('ی' * y_count, file_less_than_size))
        else:
            user_data.setdefault('pdfs', []).append(document.file_id)
            keyboard = [[KeyboardButton(texts.FINISH)]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(texts.PDF_RECIEVED.format(
                helpers.persian_ordinal_word(len(user_data['pdfs'])) + 'ت'
            ),
                reply_markup=reply_markup)
    elif update.message.text == texts.FINISH:
        if not user_data.get('pdfs'):
            await update.effective_message.reply_text(texts.NO_TASK_SENT_YET)
            return None
        media_chunks = [user_data['pdfs'][i:i + 10] for i in range(0, len(user_data['pdfs']), 10)]
        for media_chunk in media_chunks:
            await update.effective_message.reply_media_group(
                [InputMediaDocument(doc) for doc in media_chunk])
        keyboard = [[KeyboardButton(texts.SUBMIT)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            texts.ASK_SUBMITS.format(num2fawords.words(len(user_data['pdfs'])), user_data['name']) if len(
                user_data['pdfs']) > 1 else
            texts.ASK_SUBMIT.format(user_data['name']),
            reply_markup=reply_markup)
        return CONFIRM_SUBMIT
    else:
        keyboard = [[KeyboardButton(texts.FINISH)]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(texts.PLZ_DOC, reply_markup=reply_markup)
    return WAIT_FOR_FINISH


# Function to handle confirming the submission
async def confirm_submit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    wait_msg = await update.effective_message.reply_text(texts.WAIT_A_LITTLE)
    user_data = user_data_dict[update.effective_user.id]
    if not user_data:
        await update.effective_message.reply_text(texts.LATE_OK)
        return ConversationHandler.END
    task_detail = db.get_task(user_data['task_id'])
    admin = await get_cached_admin_detail(task_detail.admin_id)
    # Send the submitted pdfs to the admin
    media_chunks = [user_data['pdfs'][i:i + 10] for i in range(0, len(user_data['pdfs']), 10)]
    for i, media_chunk in enumerate(media_chunks):
        try:
            file_suffix = task_detail.file_suffix
            file_paths = []
            for j, doc in enumerate(media_chunk, start=1):
                await wait_msg.edit_text(texts.WAIT_DOWNLOAD_FILE.format(helpers.persian_ordinal_word(j)))
                file_paths.append(await pyrogram_app.download_media(doc,
                                                                    user_data['name'] + ' ' + file_suffix +
                                                                    # add number if not first file
                                                                    ('' if (j + (i * 10)) == 1 else f' {j + (i * 10)}')
                                                                    # add file ext
                                                                    + '.pdf'))
            await wait_msg.edit_text(texts.WAIT_UPLOAD_FILE)
            await pyrogram_app.send_media_group(admin.id, [
                pyrogram_InputMediaDocument(
                    file_path,
                    caption=admin_texts.TASK_RECIEVED.format(
                        task_detail.task_name,
                        update.effective_user.mention_html(),
                        f"(@{update.effective_user.username})" if
                        update.effective_user.username else "",
                        user_data['name'],
                        len(user_data[
                                'pdfs'])),
                    parse_mode=ParseMode('html')
                )
                for file_path in file_paths
            ])
            [os.remove(file_path) for file_path in file_paths]
        except Exception as e:
            print(e)
            await context.bot.send_media_group(admin.id,
                                               [InputMediaDocument(doc,
                                                                   caption=admin_texts.TASK_RECIEVED.format(
                                                                       task_detail.task_name,
                                                                       update.effective_user.mention_html(),
                                                                       f"(@{update.effective_user.username})" if
                                                                       update.effective_user.username else "",
                                                                       user_data['name'],
                                                                       len(user_data[
                                                                               'pdfs'])),
                                                                   parse_mode='html') for doc in
                                                media_chunk])
    await wait_msg.delete()
    await update.effective_message.reply_text(texts.TASK_SENT.format(task_detail.task_name, admin.mention_html()),
                                              parse_mode='html',
                                              reply_markup=ReplyKeyboardRemove())

    # Clear user data
    del user_data_dict[update.effective_user.id]

    return ConversationHandler.END


@asyncached(user_data_cache)
async def get_cached_admin_detail(user_id):
    res = await bot.get_chat(user_id)
    return res


# Your python-telegram-bot application
app = ApplicationBuilder().token(TOKEN).build()
bot: Bot = app.bot
# Create the ConversationHandler
task_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(f'^{texts.SEND_TASK}$'), send_task)],
    states={
        GET_NAME: [CallbackQueryHandler(get_name, pattern=r'^SelectTask')],
        GET_FILES: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_files)],
        WAIT_FOR_FINISH: [
            MessageHandler((filters.Document.PDF | filters.TEXT) & ~filters.COMMAND, wait_for_finish)],
        CONFIRM_SUBMIT: [
            MessageHandler((filters.TEXT & filters.Regex(texts.SUBMIT)) & ~filters.COMMAND, confirm_submit)],
    },
    fallbacks=[CommandHandler('start', start), CommandHandler('cancel', start),
               MessageHandler(filters.ALL, wanna_start)],
)

handlers = [
    task_handler,
    MessageHandler(filters.Regex(f'^{texts.ABOUT_ME_BUTTON}$'), about_me),
    MessageHandler(filters.Regex(f'^{texts.DONATE_ME_BUTTON}$'), donate_me),
    MessageHandler(filters.ChatType.PRIVATE & ~filters.UpdateType.EDITED, start),
]
[app.add_handler(handler) for handler in admin_panel.handlers]
[app.add_handler(handler) for handler in handlers]

pyrogram_app = Client('bot', api_id=API_ID, api_hash=API_HASH, bot_token=TOKEN, no_updates=True)
pyrogram_app.start()

print('pyro app started')
app.run_polling()
