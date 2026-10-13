"""Texts of the setup page in English, Russian and Uzbek (Latin). Placeholders like {name} are the same in every language."""

from __future__ import annotations

LANGS = ("en", "ru", "uz")
DEFAULT = "en"

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "title": "Connect Instagram to creatorloop",
        "subtitle": "About 5 minutes. Your App Secret and token stay on this computer.",
        "step_account": "1. Your Instagram account",
        "account_pro": "It is a professional account (Business or Creator)",
        "account_pro_help": "Instagram → Settings → Account type and tools → Switch to professional account. Free, "
        "takes a minute.",
        "account_page": "It is linked to a Facebook Page",
        "account_page_help": "Facebook → your Page → Settings → Linked accounts → Instagram → Connect.",
        "step_app": "2. Your Meta app",
        "app_help": "Create it once at developers.facebook.com: My Apps → Create App → type Business → add the Instagram "
        "product → “API setup with Facebook login”. App ID and App Secret are in App settings → Basic.",
        "app_guide": "Step-by-step guide",
        "app_id": "App ID",
        "app_secret": "App Secret",
        "app_secret_saved": "Leave the secret empty to use the saved one.",
        "app_check": "Check the app",
        "app_ok": "App found ✓",
        "step_connect": "3. Connect Instagram",
        "connect_help": "Facebook opens. Allow access to your Page and your Instagram account and keep every permission ticked.",
        "connect": "Continue with Facebook",
        "choose_title": "Which account should creatorloop use?",
        "followers": "{count} followers",
        "done_title": "Done! @{username} is connected",
        "done_expires": "The token is valid until {date}. creatorloop warns you 14 days before.",
        "done_never": "The token does not expire.",
        "done_next": "Go back to Claude and ask: “How did my last 10 posts do, and what should I post next?” "
        "You can close this tab.",
        "working": "Checking…",
        "retry": "Try again",
        "rerequest": "Ask for the permissions again",
        "recheck": "Check again",
        "err_bad_app_id": "The App ID is a number like 1234567890123456. Copy it from App settings → Basic.",
        "err_bad_app": "Meta did not accept this App ID and App Secret. Copy the secret again: "
        "App settings → Basic → App Secret → Show.",
        "err_no_app": "Check the app first (step 2).",
        "err_access_denied": "You cancelled the Facebook login.",
        "err_missing_permissions": "These permissions were unticked: {perms}. creatorloop cannot work without them — "
        "ask for them again and keep them ticked.",
        "err_no_pages": "Facebook did not share any Page with the app. Log in again, press “Edit access” in the "
        "Facebook window and tick your Page.",
        "err_no_instagram": "No Instagram professional account is linked to: {pages}. Switch Instagram to a professional "
        "account and link it to the Page (step 1), then check again.",
        "err_bad_state": "This login session is out of date. Start again.",
        "err_code_exchange": "Meta did not issue a token: {detail}",
        "err_network": "No connection to Meta: {detail}. Check the internet and try again.",
        "err_meta_error": "Meta answered with an error: {detail}",
        "perm_instagram_basic": "profile and posts",
        "perm_instagram_manage_insights": "statistics",
        "perm_pages_show_list": "finding your account through the Page",
        "perm_pages_read_engagement": "reading the Page",
        "perm_business_management": "competitor analysis",
        "perm_instagram_content_publish": "publishing",
        "perm_instagram_manage_comments": "comments",
    },
    "ru": {
        "title": "Подключение Instagram к creatorloop",
        "subtitle": "Около 5 минут. App Secret и токен остаются на этом компьютере.",
        "step_account": "1. Ваш аккаунт Instagram",
        "account_pro": "Это профессиональный аккаунт (Business или Creator)",
        "account_pro_help": "Instagram → Настройки → Тип аккаунта и инструменты → Переключиться на профессиональный "
        "аккаунт. Бесплатно, займёт минуту.",
        "account_page": "Он привязан к Facebook-странице",
        "account_page_help": "Facebook → ваша страница → Настройки → Связанные аккаунты → Instagram → Подключить.",
        "step_app": "2. Ваше приложение Meta",
        "app_help": "Создаётся один раз на developers.facebook.com: My Apps → Create App → тип Business → добавьте "
        "продукт Instagram → «API setup with Facebook login». App ID и App Secret — в App settings → Basic.",
        "app_guide": "Пошаговый гайд",
        "app_id": "App ID",
        "app_secret": "App Secret",
        "app_secret_saved": "Оставьте секрет пустым, чтобы использовать сохранённый.",
        "app_check": "Проверить приложение",
        "app_ok": "Приложение найдено ✓",
        "step_connect": "3. Подключите Instagram",
        "connect_help": "Откроется Facebook. Разрешите доступ к странице и Instagram-аккаунту и не снимайте галочки "
        "с разрешений.",
        "connect": "Продолжить через Facebook",
        "choose_title": "Какой аккаунт подключить?",
        "followers": "подписчиков: {count}",
        "done_title": "Готово! @{username} подключён",
        "done_expires": "Токен действует до {date}. creatorloop предупредит за 14 дней.",
        "done_never": "Токен бессрочный.",
        "done_next": "Вернитесь в Claude и спросите: «Как зашли мои последние 10 постов и что выложить дальше?» "
        "Эту вкладку можно закрыть.",
        "working": "Проверяю…",
        "retry": "Попробовать снова",
        "rerequest": "Запросить разрешения снова",
        "recheck": "Проверить ещё раз",
        "err_bad_app_id": "App ID — это число вида 1234567890123456. Скопируйте его из App settings → Basic.",
        "err_bad_app": "Meta не приняла эту пару App ID и App Secret. Скопируйте секрет заново: "
        "App settings → Basic → App Secret → Show.",
        "err_no_app": "Сначала проверьте приложение (шаг 2).",
        "err_access_denied": "Вы отменили вход через Facebook.",
        "err_missing_permissions": "Эти разрешения были сняты: {perms}. Без них creatorloop не работает — запросите "
        "их снова и не снимайте галочки.",
        "err_no_pages": "Facebook не передал приложению ни одной страницы. Войдите снова, в окне Facebook нажмите "
        "«Изменить доступ» и отметьте свою страницу.",
        "err_no_instagram": "К этим страницам не привязан профессиональный Instagram: {pages}. Переключите Instagram на "
        "профессиональный аккаунт и привяжите его к странице (шаг 1), затем проверьте ещё раз.",
        "err_bad_state": "Сессия входа устарела. Начните заново.",
        "err_code_exchange": "Meta не выдала токен: {detail}",
        "err_network": "Нет связи с Meta: {detail}. Проверьте интернет и попробуйте снова.",
        "err_meta_error": "Meta ответила ошибкой: {detail}",
        "perm_instagram_basic": "профиль и посты",
        "perm_instagram_manage_insights": "статистика",
        "perm_pages_show_list": "поиск аккаунта через страницу",
        "perm_pages_read_engagement": "чтение страницы",
        "perm_business_management": "анализ конкурентов",
        "perm_instagram_content_publish": "публикация",
        "perm_instagram_manage_comments": "комментарии",
    },
    "uz": {
        "title": "Instagram'ni creatorloop'ga ulash",
        "subtitle": "Taxminan 5 daqiqa. App Secret va token shu kompyuterda qoladi.",
        "step_account": "1. Instagram akkauntingiz",
        "account_pro": "Bu professional akkaunt (Business yoki Creator)",
        "account_pro_help": "Instagram → Sozlamalar → Akkaunt turi va vositalar → Professional akkauntga oʻtish. "
        "Bepul, bir daqiqa oladi.",
        "account_page": "U Facebook sahifasiga ulangan",
        "account_page_help": "Facebook → sahifangiz → Sozlamalar → Bogʻlangan akkauntlar → Instagram → Ulash.",
        "step_app": "2. Meta ilovangiz",
        "app_help": "Bir marta developers.facebook.com'da yaratiladi: My Apps → Create App → Business turi → Instagram "
        "mahsulotini qoʻshing → “API setup with Facebook login”. App ID va App Secret — App settings → Basic'da.",
        "app_guide": "Qadamma-qadam qoʻllanma",
        "app_id": "App ID",
        "app_secret": "App Secret",
        "app_secret_saved": "Saqlanganidan foydalanish uchun secret'ni boʻsh qoldiring.",
        "app_check": "Ilovani tekshirish",
        "app_ok": "Ilova topildi ✓",
        "step_connect": "3. Instagram'ni ulang",
        "connect_help": "Facebook ochiladi. Sahifangiz va Instagram akkauntingizga ruxsat bering, ruxsatlardagi "
        "belgilarni olib tashlamang.",
        "connect": "Facebook orqali davom etish",
        "choose_title": "Qaysi akkauntni ulaymiz?",
        "followers": "{count} obunachi",
        "done_title": "Tayyor! @{username} ulandi",
        "done_expires": "Token {date} gacha amal qiladi. creatorloop 14 kun oldin ogohlantiradi.",
        "done_never": "Token muddatsiz.",
        "done_next": "Claude'ga qayting va soʻrang: “Oxirgi 10 ta postim qanday ketdi va keyin nima joylay?” "
        "Bu oynani yopishingiz mumkin.",
        "working": "Tekshirilmoqda…",
        "retry": "Qayta urinish",
        "rerequest": "Ruxsatlarni qayta soʻrash",
        "recheck": "Qayta tekshirish",
        "err_bad_app_id": "App ID — 1234567890123456 kabi raqam. Uni App settings → Basic'dan nusxalang.",
        "err_bad_app": "Meta bu App ID va App Secret juftligini qabul qilmadi. Secret'ni qaytadan nusxalang: "
        "App settings → Basic → App Secret → Show.",
        "err_no_app": "Avval ilovani tekshiring (2-qadam).",
        "err_access_denied": "Facebook orqali kirishni bekor qildingiz.",
        "err_missing_permissions": "Quyidagi ruxsatlar olib tashlandi: {perms}. Ularsiz creatorloop ishlamaydi — qayta "
        "soʻrang va belgilarni qoldiring.",
        "err_no_pages": "Facebook ilovaga birorta sahifa bermadi. Qayta kiring, Facebook oynasida “Kirish huquqini "
        "oʻzgartirish”ni bosing va sahifangizni belgilang.",
        "err_no_instagram": "Bu sahifalarga professional Instagram ulanmagan: {pages}. Instagram'ni professional "
        "akkauntga oʻtkazing va sahifaga ulang (1-qadam), soʻng qayta tekshiring.",
        "err_bad_state": "Kirish sessiyasi eskirgan. Qaytadan boshlang.",
        "err_code_exchange": "Meta token bermadi: {detail}",
        "err_network": "Meta bilan aloqa yoʻq: {detail}. Internetni tekshirib, qayta urining.",
        "err_meta_error": "Meta xato bilan javob berdi: {detail}",
        "perm_instagram_basic": "profil va postlar",
        "perm_instagram_manage_insights": "statistika",
        "perm_pages_show_list": "akkauntni sahifa orqali topish",
        "perm_pages_read_engagement": "sahifani oʻqish",
        "perm_business_management": "raqobatchilar tahlili",
        "perm_instagram_content_publish": "joylash",
        "perm_instagram_manage_comments": "izohlar",
    },
}


def pick_language(accept_language: str | None, override: str | None = None) -> str:
    """?lang= wins, then the first supported language in the browser's Accept-Language, then English."""
    if override in LANGS:
        return override
    for part in (accept_language or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGS:
            return code
    return DEFAULT
