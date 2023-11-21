from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, \
    filters
import db
import admin_texts
from cachetools import TTLCache
import datetime
import config
import pytz
import jdatetime


### For Sudo
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_admin_id = int(context.args[0])
    db.add_admin(new_admin_id)
    await update.effective_message.reply_text(f"Admin {new_admin_id} Added")


async def delete_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_admin_id = int(context.args[0])
    db.delete_admin(new_admin_id)
    await update.effective_message.reply_text(f"Admin {new_admin_id} Deleted")


### For Sudo


# checks if the user is still admin, if not delete the admin panel message
def check_admin(func):
    async def wrapper(update, context):
        if not db.is_admin(update.effective_user.id):
            await update.effective_message.delete()
            return
        else:
            return await func(update, context)

    return wrapper


### Admins

# sends the admin menu panel
async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id):
        await update.effective_message.reply_text(admin_texts.YOU_NO_ADMIN)
    else:
        keyboard = [
            [InlineKeyboardButton(admin_texts.TASKS_MANAGEMENT, callback_data='admin managetasks')]
        ]
        if update.callback_query:
            await update.effective_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.effective_message.reply_text(admin_texts.WHAT_TO_DO,
                                                      reply_markup=InlineKeyboardMarkup(keyboard))


@check_admin
async def manage_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_tasks = db.get_admin_tasks(user_id, user_id == config.SUDO)
    keyboard = [
        [InlineKeyboardButton('ساخت تمرین جدید', callback_data='admin addtask')]
    ]
    for task in admin_tasks:
        keyboard += [[InlineKeyboardButton(task.task_name, callback_data=f'admin task manage {task.task_id}')]]

    keyboard += [[InlineKeyboardButton("بازگشت", callback_data='admin menu')]]
    await update.effective_message.edit_text(admin_texts.WHAT_TO_DO, reply_markup=InlineKeyboardMarkup(keyboard))


finisher = TTLCache(maxsize=10, ttl=10)


# generates the keyboard for changing the deadline of pending task
def change_deadline_keyboard(inc, task_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("کاهش" + ("✅" if not inc else ""),
                              callback_data=f"admin task deadline decrease 0 {task_id}"),
         InlineKeyboardButton("افزایش" + ("✅" if inc else ""),
                              callback_data=f"admin task deadline increase 0 {task_id}")],
        [InlineKeyboardButton("{} دقیقه".format(i), callback_data="admin task deadline {} {} min {}".format(
            "increase" if inc else "decrease", i, task_id)) for i in (1, 15, 60, 180)],
        [InlineKeyboardButton("{} روز".format(i), callback_data="admin task deadline {} {} day {}".format(
            "increase" if inc else "decrease", i, task_id)) for i in (1, 7, 30)],
        [InlineKeyboardButton("ثبت و بازگشت", callback_data=f"admin task submitdeadline {task_id}")],
        [InlineKeyboardButton("بازگشت", callback_data=f"admin task manage {task_id}")]
    ])


# handles every setting for the task
@check_admin
async def manage_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data.split()
    task_id = data[-1]
    action = data[2]
    task_detail = db.get_task_admin(task_id)
    match action:
        case "manage":
            pass
        case "deactivatetask":
            task_detail.deactivate()
        case "activatetask":
            task_detail.activate()
        case "delete":
            if task_id in finisher:
                await update.effective_message.delete()
                task_detail.finish()
                await update.effective_message.reply_text("تمرین با موفقیت حذف شد")
                return
            else:
                finisher[task_id] = None
                await update.callback_query.answer("برای حذف کامل، دوباره گزینه حذف را انتخاب کنید", show_alert=True)
                return
        case "changedeadline":
            jalali_deadline = jdatetime.datetime.fromgregorian(datetime=task_detail.deadline).strftime(
                '%Y-%m-%d %H:%M:%S')
            await update.effective_message.edit_text(
                admin_texts.TASK_DEADLINE.format(task_detail.task_name, jalali_deadline),
                reply_markup=change_deadline_keyboard(inc=False, task_id=task_id))
            return
        case "deadline":
            msg_jalali_datetime = jdatetime.datetime.strptime(update.effective_message.text.split("\n")[-1],
                                                              "%Y-%m-%d %H:%M:%S")
            msg_datetime = msg_jalali_datetime.togregorian()
            if data[5] == "min":
                timedelta = datetime.timedelta(minutes=int(data[4]))
            elif data[5] == "day":
                timedelta = datetime.timedelta(days=int(data[4]))
            else:
                timedelta = datetime.timedelta(seconds=0)
            if data[3] == "increase":
                new_deadline = msg_datetime + timedelta
                inc = True
            else:
                new_deadline = msg_datetime - timedelta
                inc = False
            new_jalali_deadline = jdatetime.datetime.fromgregorian(datetime=new_deadline).strftime(
                '%Y-%m-%d %H:%M:%S')
            await update.effective_message.edit_text(
                admin_texts.TASK_DEADLINE.format(task_detail.task_name, new_jalali_deadline),
                reply_markup=change_deadline_keyboard(inc=inc, task_id=task_id))
            await update.callback_query.answer("✅")
            return
        case "submitdeadline":
            msg_datetime = update.effective_message.text.split("\n")[-1]
            gregorian_deadline = jdatetime.datetime.strptime(msg_datetime, '%Y-%m-%d %H:%M:%S').togregorian()
            task_detail.change_deadline(gregorian_deadline)
            await update.callback_query.answer("ثبت شد")
    task_detail = db.get_task_admin(task_id)
    jalali_deadline = jdatetime.datetime.fromgregorian(datetime=task_detail.deadline).strftime('%Y-%m-%d %H:%M:%S')
    msg = admin_texts.TASK_DETAIL.format(
        task_detail.task_name,
        'فعال' if task_detail.active else 'غیرفعال',
        task_detail.desc,
        jalali_deadline,
        task_detail.size_limit
    )
    keyboard = [
        [InlineKeyboardButton('غیرفعالسازی',
                              callback_data=f'admin task deactivatetask {task_id}')] if task_detail.active else
        [InlineKeyboardButton('فعالسازی', callback_data=f'admin task activatetask {task_id}')],
        [InlineKeyboardButton('حذف کامل', callback_data=f'admin task delete {task_id}')],
        [InlineKeyboardButton('تغییر مهلت', callback_data=f'admin task changedeadline {task_id}')],
        [InlineKeyboardButton('بازگشت', callback_data='admin managetasks')]
    ]

    await update.effective_message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='html',
                                             disable_web_page_preview=True)


new_task_names = TTLCache(maxsize=100, ttl=600)


async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.edit_text(admin_texts.PLZ_NAME_NEW_TASK_NAME)
    return GET_DESC


async def get_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_name = " ".join(update.effective_message.text.splitlines())
    new_task_names[update.effective_user.id] = task_name
    await update.effective_message.reply_text(admin_texts.PLZ_NAME_NEW_TASK_DESC)
    return SETUP


@check_admin
async def setup_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        data = update.callback_query.data
        msg = update.effective_message.text_html
        task_name = msg.splitlines()[0]
        task_desc = "\n".join(update.effective_message.text_html.splitlines()[1:])
    else:
        data = "admin addtask sizelimit_1 deadline_1"
        task_name = new_task_names[update.effective_user.id]
        task_desc = update.effective_message.text_html
        msg = f"{task_name}\n\n{task_desc}"
    data = data.replace('admin addtask ', '')
    sizelimit, deadline = 0, 0
    for entity in data.split():
        property_, value = entity.split('_')
        match property_:
            case "sizelimit":
                sizelimit = int(value)
            case "deadline":
                deadline = int(value)
    if "submit" in data:
        geo_deadline = (datetime.datetime.now(tz=pytz.timezone('Asia/Tehran')) + datetime.timedelta(
            days=deadline)).strftime("%Y-%m-%d %H:%M:%S")
        db.Tasks.create(task_name=task_name, desc=task_desc, admin_id=update.effective_user.id,
                        deadline=geo_deadline,
                        size_limit=sizelimit)
        await update.effective_message.edit_text("تمرین {} با موفقیت ذخیره و از هم اکنون فعال شد.".format(task_name))
        return -1
    keyboard_data = "admin addtask sizelimit_{} deadline_{}"
    keyboard = [
        [InlineKeyboardButton("محدودیت حجم فایل (مگابایت)👇", callback_data="_")],
        [InlineKeyboardButton(f"{new_size}" + ("✅" if sizelimit == new_size else ""),
                              callback_data=keyboard_data.format(new_size, deadline)) for new_size in
         (1, 5, 10, 50, 100, 1000)],
        [InlineKeyboardButton("مهلت ارسال (روز)👇", callback_data="_")],
        [InlineKeyboardButton(f"{new_deadline}" + ("✅" if deadline == new_deadline else ""),
                              callback_data=keyboard_data.format(sizelimit, new_deadline)) for new_deadline
         in
         (1, 2, 3, 4, 5, 6, 7)],
        [InlineKeyboardButton(f"{new_deadline}" + ("✅" if deadline == new_deadline else ""),
                              callback_data=keyboard_data.format(sizelimit, new_deadline)) for new_deadline
         in
         (10, 15, 20, 30, 45, 60, 90)],
        [InlineKeyboardButton("به زودی تنظیمات بیشتر", callback_data="_")],
        [InlineKeyboardButton("ذخیره", callback_data=keyboard_data.format(sizelimit, deadline) + " submit_0")]
    ]
    if update.callback_query:
        await update.effective_message.edit_text(msg, reply_markup=InlineKeyboardMarkup(keyboard),
                                                 parse_mode='html')
    else:
        await update.effective_message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard),
                                                  parse_mode='html')


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("عملیات لغو شد")
    return -1


GET_DESC, SETUP = range(2)

# add task conversation handler
add_task_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(add_task, pattern=r'^admin addtask')],
    states={
        GET_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_desc)],
        SETUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_task),
                CallbackQueryHandler(setup_task, pattern=r'admin addtask')]
    },
    fallbacks=[CommandHandler('start', cancel), CommandHandler('cancel', cancel)]
)

handlers = [
    add_task_conv,
    CommandHandler('add_admin', add_admin, filters=filters.User(config.SUDO)),
    CommandHandler('delete_admin', delete_admin, filters=filters.User(config.SUDO)),
    CommandHandler('admin', admin_menu, filters=filters.ChatType.PRIVATE),
    CallbackQueryHandler(admin_menu, pattern=r'^admin menu'),
    CallbackQueryHandler(manage_tasks, pattern=r'^admin managetasks'),
    CallbackQueryHandler(manage_task, pattern=r'^admin task')
]
