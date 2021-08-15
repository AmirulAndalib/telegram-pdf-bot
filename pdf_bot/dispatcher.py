import os

from dotenv import load_dotenv
from logbook import Logger
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MessageEntity,
    ParseMode,
    Update,
)
from telegram.chataction import ChatAction
from telegram.error import Unauthorized
from telegram.ext import (
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    Filters,
    MessageHandler,
    PreCheckoutQueryHandler,
)
from telegram.ext.dispatcher import Dispatcher

from pdf_bot.commands import (
    compare_cov_handler,
    merge_cov_handler,
    photo_cov_handler,
    text_cov_handler,
    watermark_cov_handler,
)
from pdf_bot.constants import *
from pdf_bot.feedback import feedback_cov_handler
from pdf_bot.files import file_cov_handler
from pdf_bot.language import send_lang, set_lang, store_lang
from pdf_bot.payment import (
    precheckout_check,
    send_payment_invoice,
    send_support_options,
    successful_payment,
)
from pdf_bot.stats import get_stats
from pdf_bot.store import create_user
from pdf_bot.url import url_to_pdf

load_dotenv()
DEV_TELE_ID = int(os.environ.get("DEV_TELE_ID"))
CALLBACK_DATA = "callback_data"


def setup_dispatcher(dispatcher: Dispatcher):
    dispatcher.add_handler(
        CommandHandler("start", send_support_options, Filters.regex("support"))
    )
    dispatcher.add_handler(CommandHandler("start", start_msg))

    dispatcher.add_handler(CommandHandler("help", help_msg))
    dispatcher.add_handler(CommandHandler("setlang", send_lang))
    dispatcher.add_handler(CommandHandler("support", send_support_options))

    # Callback query handler
    dispatcher.add_handler(CallbackQueryHandler(process_callback_query))

    # Payment handlers
    dispatcher.add_handler(PreCheckoutQueryHandler(precheckout_check))
    dispatcher.add_handler(
        MessageHandler(Filters.successful_payment, successful_payment)
    )

    # URL handler
    dispatcher.add_handler(
        MessageHandler(Filters.entity(MessageEntity.URL), url_to_pdf)
    )

    # PDF commands handlers
    dispatcher.add_handler(compare_cov_handler())
    dispatcher.add_handler(merge_cov_handler())
    dispatcher.add_handler(photo_cov_handler())
    dispatcher.add_handler(text_cov_handler())
    dispatcher.add_handler(watermark_cov_handler())

    # PDF file handler
    dispatcher.add_handler(file_cov_handler())

    # Feedback handler
    dispatcher.add_handler(feedback_cov_handler())

    # Dev commands handlers
    dispatcher.add_handler(CommandHandler("send", send_msg, Filters.user(DEV_TELE_ID)))
    dispatcher.add_handler(
        CommandHandler("stats", get_stats, Filters.user(DEV_TELE_ID))
    )

    # Log all errors
    dispatcher.add_error_handler(error_callback)


def start_msg(update: Update, context: CallbackContext) -> None:
    update.effective_message.reply_chat_action(ChatAction.TYPING)

    # Create the user entity in Datastore
    create_user(update.effective_message.from_user)

    _ = set_lang(update, context)
    update.effective_message.reply_text(
        "{welcome}\n\n<b>{key_features}</b>\n"
        "{features_summary}\n"
        "{pdf_from_text}\n"
        "{extract_pdf}\n"
        "{convert_to_images}\n"
        "{convert_to_pdf}\n"
        "{beautify}\n"
        "<b><i>{and_more}</i></b>\n\n"
        "{see_usage}".format(
            welcome=_("Welcome to PDF Bot!"),
            key_features=_("Key features:"),
            features_summary=_(
                "- Compress, merge, preview, rename, split "
                "and add watermark to PDF files"
            ),
            pdf_from_text=_("- Create PDF files from text messages"),
            extract_pdf=_("- Extract images and text from PDF files"),
            convert_to_images=_("- Convert PDF files into images"),
            convert_to_pdf=_("- Convert webpages and images into PDF files"),
            beautify=_("- Beautify handwritten notes images into PDF files"),
            and_more=_("- And more..."),
            see_usage=_("Type {} to see how to use PDF Bot").format("/help"),
        ),
        parse_mode=ParseMode.HTML,
    )


def help_msg(update, context):
    update.effective_message.reply_chat_action(ChatAction.TYPING)
    _ = set_lang(update, context)
    keyboard = [
        [InlineKeyboardButton(_("Set Language 🌎"), callback_data=SET_LANG)],
        [
            InlineKeyboardButton(_("Join Channel"), f"https://t.me/{CHANNEL_NAME}"),
            InlineKeyboardButton(_("Support PDF Bot"), callback_data=PAYMENT),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.effective_message.reply_text(
        "{desc_1}:\n{pdf_files}\n{photos}\n{webpage_links}\n\n{desc_2}:\n"
        "{compare_desc}\n{merge_desc}\n{photo_desc}\n{text_desc}\n"
        "{watermark_desc}".format(
            desc_1=_(
                "You can perform most of the tasks by sending me one of the followings"
            ),
            pdf_files=_("- PDF files"),
            photos=_("- Photos"),
            webpage_links=_("- Webpage links"),
            desc_2=_(
                "The rest of the tasks can be performed by using the following commands"
            ),
            compare_desc=_("{} - compare PDF files").format("/compare"),
            merge_desc=_("{} - merge PDF files").format("/merge"),
            photo_desc=_(
                "{} - convert and combine multiple photos into PDF files"
            ).format("/photo"),
            text_desc=_("{} - create PDF files from text messages").format("/text"),
            watermark_desc=_("{} - add watermark to PDF files").format("/watermark"),
        ),
        reply_markup=reply_markup,
    )


def process_callback_query(update: Update, context: CallbackContext):
    _ = set_lang(update, context)
    query = update.callback_query
    data = query.data

    if CALLBACK_DATA not in context.user_data:
        context.user_data[CALLBACK_DATA] = set()

    if data not in context.user_data[CALLBACK_DATA]:
        context.user_data[CALLBACK_DATA].add(data)
        if data == SET_LANG:
            send_lang(update, context, query)
        elif data in LANGUAGES:
            store_lang(update, context, query)
        if data == PAYMENT:
            send_support_options(update, context, query)
        elif data in [THANKS, COFFEE, BEER, MEAL]:
            send_payment_invoice(update, context, query)

        context.user_data[CALLBACK_DATA].remove(data)

    query.answer()


def send_msg(update: Update, context: CallbackContext):
    tele_id = int(context.args[0])
    message = " ".join(context.args[1:])

    try:
        context.bot.send_message(tele_id, message)
        update.effective_message.reply_text("Message sent")
    except Exception as e:
        log = Logger()
        log.error(e)
        update.effective_message.reply_text("Failed to send message")


def error_callback(update: Update, context: CallbackContext):
    if context.error is not Unauthorized:
        log = Logger()
        log.error(f'Update "{update}" caused error "{context.error}"')
