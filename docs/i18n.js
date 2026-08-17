/*
 * Three languages for the project page, applied to any element carrying a
 * data-i18n attribute.
 *
 * The table below is data, not prose, so the ASCII rule the rest of the
 * project follows does not apply to it - the same exemption the app's own
 * translation tables get.
 *
 * data-i18n         replaces textContent
 * data-i18n-html    replaces innerHTML, for the few strings with <br> or <code>
 * data-i18n-alt     replaces the alt attribute
 * data-i18n-title   replaces the title attribute
 */

(function () {
  'use strict'

  var STORAGE_KEY = 'hms-lang'
  var LANGUAGES = ['en', 'ru', 'uk']

  var STRINGS = {
    en: {
      'meta.title': 'Hexagon Media Service',
      'meta.description':
        'A private desktop downloader for YouTube, HDRezka, Reddit, Twitter and about 1800 other sites. Everything runs locally: no account, no telemetry, nothing uploaded.',

      'nav.features': 'Features',
      'nav.hdrezka': 'HDRezka',
      'nav.private': 'Private',
      'nav.manual': 'Manual',
      'nav.github': 'GitHub',
      'nav.language': 'Language',

      'hero.eyebrow': 'Windows desktop app',
      'hero.title': 'Download anything.<br />Keep everything.',
      'hero.lede':
        'YouTube, HDRezka, Reddit, Twitter and about 1800 other sites, filed and tagged the way you want them. Everything runs on your machine: no account, no telemetry, nothing uploaded.',
      'hero.download': 'Download for Windows',
      'hero.downloadVersion': 'Download {version} for Windows',
      'hero.portable': 'Portable build',
      'hero.meta': 'Windows 10 and 11, 64-bit. Installer and portable.',
      'hero.metaSize': 'Windows 10 and 11, 64-bit. {size} installer.',
      'hero.shotAlt': 'The Download page: service tabs, a link box, format and destination cards',

      'strip.sites': 'supported sites',
      'strip.accounts': 'accounts required',
      'strip.quality': 'and everything below it',
      'strip.local': 'nothing leaves the machine',

      'features.title': 'What it does',
      'features.sources.title': 'Many sources',
      'features.sources.body':
        'Anything yt-dlp supports, plus a dedicated HDRezka resolver. Paste a link into Auto and the right handler picks it up by itself.',
      'features.ways.title': 'Many ways',
      'features.ways.body':
        'Video with audio, audio only or video only. 360p to 4K. MP4, MKV or WEBM; MP3, M4A, Opus, FLAC, WAV or Vorbis at a chosen bitrate.',
      'features.queue.title': 'A real queue',
      'features.queue.body':
        'Concurrent downloads with pause, resume and retry, live speed and ETA, and a per-item error that says what actually went wrong.',
      'features.bulk.title': 'Bulk by design',
      'features.bulk.body':
        'Paste many links at once, or drop in a playlist or channel and have every entry expand into its own queue item.',
      'features.tagged.title': 'Tagged properly',
      'features.tagged.body':
        'Title, artist, album, date, chapters, subtitles and cover art are embedded into the finished file, with the source URL written on top.',
      'features.filed.title': 'Filed properly',
      'features.filed.body':
        'A season lands as <code>Show / Season 06 / Show 6x20 Dub.mp4</code>, and the exact path is shown before anything is queued.',

      'hdrezka.eyebrow': 'HDRezka',
      'hdrezka.title': 'A whole season, chosen in one place',
      'hdrezka.body1':
        'Load a title, then pick the translation, the quality and any mix of seasons and episodes: select all, a single season, or a range like <code>1-10</code> or <code>3,5,7</code>.',
      'hdrezka.body2':
        'HDRezka refuses direct requests with a bot check, so the page is read inside your own browser through a small extension. Everything after that is decided in the app, and the queue narrates every stage: downloading, waiting for the file, moving, tagging.',
      'hdrezka.guide': 'How to set up the extension',
      'hdrezka.shotAlt': 'The HDRezka panel: destination, the read-the-open-tab button, and the extension notice',

      'queue.eyebrow': 'Queue',
      'queue.title': 'Everything in flight, in one list',
      'queue.body1':
        'Engine downloads and browser transfers appear side by side, each row patched in place so a running download never redraws the page.',
      'queue.body2':
        'Files are moved with the same Win32 call Explorer uses, one at a time, and a transfer is only filed once its size has settled and the byte count matches. A truncated file is refused rather than saved.',
      'queue.shotAlt': 'The Queue page with jobs in several states',

      'private.eyebrow': 'Private by construction',
      'private.title': 'Nothing is uploaded, ever',
      'private.body1':
        'There is no server side and no account. The only outbound requests are the ones you ask for: the sites you download from, and one check against the GitHub releases API when the app starts, which you can switch off.',
      'private.body2':
        'Updates are downloaded on request and verified against the checksum published beside the installer. Settings, history and logs stay in <code>%APPDATA%\\HexagonMediaService</code>.',
      'private.shotAlt': 'The Settings page showing the Updates card',

      'closer.title': 'Get it',
      'closer.lede': 'The download engine is bundled, so Python is not needed. ffmpeg ships with it too.',
      'closer.manual': 'Read the manual',
      'closer.meta': 'Windows 10 and 11, 64-bit.',

      'foot.source': 'Source',
      'foot.releases': 'Releases',
      'foot.issues': 'Report a problem',
      'foot.manual': 'Manual',

      // ------------------------------------------------ extension guide page
      'guide.meta.title': 'Setting up the HDRezka extension - Hexagon Media Service',
      'guide.back': 'Back to the site',
      'guide.downloading.title': 'Your download is starting',
      'guide.downloading.body':
        'Keep this page open. It takes five minutes to set up HDRezka, and you can do it while the file arrives.',
      'guide.downloading.retry': 'Download did not start? Click here.',
      'guide.title': 'Setting up HDRezka',
      'guide.lede':
        'HDRezka blocks anything that is not a real browser. The app gets around that by reading the page inside your browser, which needs a small extension. This is the only feature that needs it - YouTube, Reddit, Twitter and the rest work the moment you install the app.',
      'guide.time': 'About five minutes, once.',

      'guide.step1.title': 'Install the app',
      'guide.step1.body':
        'Run the file you just downloaded. On the last page of the installer, tick <b>Open the browser extension folder</b> before you press Finish. A folder window opens: leave it open, you need it in step 3.',
      'guide.step1.note':
        'Missed it? The folder is always here, and you can paste this into any folder window:',

      'guide.step2.title': 'Open your browser\'s extensions page',
      'guide.step2.body':
        'In Chrome, Edge, Brave or Opera, copy the address below into the address bar and press Enter. It cannot be a normal link: browsers refuse to let a web page send you there.',
      'guide.step2.note':
        'Then turn on <b>Developer mode</b> with the switch in the top right corner. Without it the button in the next step does not appear.',
      'guide.step2.alt': 'A browser address bar with the extensions address typed in, and the developer mode switch turned on',

      'guide.step3.title': 'Load the folder',
      'guide.step3.body':
        'Press <b>Load unpacked</b>, which appeared when you turned on Developer mode. Choose the extension folder from step 1 and press <b>Select folder</b>.',
      'guide.step3.note':
        'Pick the folder itself, not a file inside it. The card for Hexagon Media Service Bridge appears once it loads.',
      'guide.step3.alt': 'The Load unpacked button and a folder picker showing the extension folder',

      'guide.step4.title': 'Copy the pairing token from the app',
      'guide.step4.body':
        'Open the app and go to <b>Download</b>, then the <b>HDRezka</b> tab. At the bottom is a Browser bridge panel. Press <b>Copy token</b>.',
      'guide.step4.note':
        'The token is what stops any web page you visit from talking to the app. Treat it like a password: it belongs only in the extension\'s options. Yours will look nothing like the picture.',
      'guide.step4.alt': 'The Browser bridge panel in the app, with the Copy token button',

      'guide.step5.title': 'Paste it into the extension',
      'guide.step5.body':
        'Back on the extensions page, find Hexagon Media Service Bridge and click <b>Details</b>, then <b>Extension options</b>. Paste the token and press <b>Save and test</b>.',
      'guide.step5.note': 'It should say <b>Connected</b>. That is the whole setup.',
      'guide.step5.alt': 'The extension options page with the token pasted in and a connected message',

      'guide.done.title': 'Using it',
      'guide.done.body':
        'Open any film or series on HDRezka in your browser and leave the tab open. In the app, go to <b>Download</b>, then <b>HDRezka</b>, and press <b>Read open HDRezka tab</b>. Pick the dub, the quality, and whichever episodes you want, then press Download.',

      'guide.trouble.title': 'If something does not work',
      'guide.trouble.q1': 'The app says the extension is not connected',
      'guide.trouble.a1':
        'The token was not saved, or the app was restarted after you copied it. Copy it again and paste it into the extension\'s options.',
      'guide.trouble.q2': 'Could not establish connection',
      'guide.trouble.a2':
        'The extension was loaded after that tab was already open. Reload the HDRezka tab once.',
      'guide.trouble.q3': 'This does not look like an HDRezka title page',
      'guide.trouble.a3':
        'You are on a search or listing page. Open the film or series itself first.',
      'guide.trouble.q4': 'The extensions page will not open from a link',
      'guide.trouble.a4':
        'That is deliberate on the browser\'s part. Copy the address and paste it into the address bar yourself.',
      'guide.trouble.more': 'The manual covers the rest.',

      // Labels drawn inside the illustrations. These are the browser's own
      // wording, which it localises, so they are translated too. The
      // extension's own options page is English whatever the browser is, so
      // its labels are hard-coded in the markup instead.
      'guide.ui.devMode': 'Developer mode',
      'guide.ui.loadUnpacked': 'Load unpacked',
      'guide.ui.pack': 'Pack extension',
      'guide.ui.update': 'Update',
      'guide.ui.selectFolder': 'Select folder',
      'guide.ui.extensions': 'Extensions',
      'guide.ui.folderName': 'extension',
      'guide.copy': 'Copy',
      'guide.copied': 'Copied'
    },

    ru: {
      'meta.title': 'Hexagon Media Service',
      'meta.description':
        'Приватный загрузчик для YouTube, HDRezka, Reddit, Twitter и примерно 1800 других сайтов. Всё работает локально: без аккаунта, без телеметрии, ничего не выгружается.',

      'nav.features': 'Возможности',
      'nav.hdrezka': 'HDRezka',
      'nav.private': 'Приватность',
      'nav.manual': 'Руководство',
      'nav.github': 'GitHub',
      'nav.language': 'Язык',

      'hero.eyebrow': 'Приложение для Windows',
      'hero.title': 'Скачивайте что угодно.<br />Храните у себя.',
      'hero.lede':
        'YouTube, HDRezka, Reddit, Twitter и ещё около 1800 сайтов, разложенные по папкам и с тегами так, как нужно вам. Всё работает на вашем компьютере: без аккаунта, без телеметрии, ничего не выгружается.',
      'hero.download': 'Скачать для Windows',
      'hero.downloadVersion': 'Скачать {version} для Windows',
      'hero.portable': 'Портативная версия',
      'hero.meta': 'Windows 10 и 11, 64-бит. Установщик и портативная версия.',
      'hero.metaSize': 'Windows 10 и 11, 64-бит. Установщик, {size}.',
      'hero.shotAlt': 'Страница загрузки: вкладки сервисов, поле для ссылок, карточки формата и папки назначения',

      'strip.sites': 'поддерживаемых сайтов',
      'strip.accounts': 'аккаунтов не нужно',
      'strip.quality': 'и всё, что ниже',
      'strip.local': 'ничего не покидает компьютер',

      'features.title': 'Что он умеет',
      'features.sources.title': 'Много источников',
      'features.sources.body':
        'Всё, что поддерживает yt-dlp, плюс отдельный резолвер для HDRezka. Вставьте ссылку в «Автоопределение», и нужный обработчик подхватит её сам.',
      'features.ways.title': 'Много вариантов',
      'features.ways.body':
        'Видео со звуком, только звук или только видео. От 360p до 4K. MP4, MKV или WEBM; MP3, M4A, Opus, FLAC, WAV или Vorbis с выбранным битрейтом.',
      'features.queue.title': 'Настоящая очередь',
      'features.queue.body':
        'Одновременные загрузки с паузой, продолжением и повтором, скорость и время до конца, а у каждой ошибки понятное объяснение.',
      'features.bulk.title': 'Пачками',
      'features.bulk.body':
        'Вставьте сразу много ссылок или киньте плейлист либо канал, и каждый элемент станет отдельной задачей в очереди.',
      'features.tagged.title': 'С тегами',
      'features.tagged.body':
        'Название, исполнитель, альбом, дата, главы, субтитры и обложка записываются в готовый файл, а сверху добавляется исходная ссылка.',
      'features.filed.title': 'По папкам',
      'features.filed.body':
        'Сезон ложится как <code>Сериал / Season 06 / Сериал 6x20 Озвучка.mp4</code>, и точный путь показан ещё до постановки в очередь.',

      'hdrezka.eyebrow': 'HDRezka',
      'hdrezka.title': 'Целый сезон выбирается в одном месте',
      'hdrezka.body1':
        'Загрузите страницу тайтла, затем выберите озвучку, качество и любое сочетание сезонов и серий: все сразу, один сезон или диапазон вроде <code>1-10</code> либо <code>3,5,7</code>.',
      'hdrezka.body2':
        'HDRezka отклоняет прямые запросы проверкой на бота, поэтому страница читается прямо в вашем браузере через небольшое расширение. Всё дальнейшее решает приложение, а очередь проговаривает каждый этап: загрузка, ожидание файла, перенос, запись тегов.',
      'hdrezka.guide': 'Как установить расширение',
      'hdrezka.shotAlt': 'Панель HDRezka: папка назначения, кнопка чтения открытой вкладки и уведомление о расширении',

      'queue.eyebrow': 'Очередь',
      'queue.title': 'Всё в работе - в одном списке',
      'queue.body1':
        'Загрузки движка и передачи браузера показаны рядом, и каждая строка обновляется на месте, поэтому идущая загрузка не перерисовывает страницу.',
      'queue.body2':
        'Файлы переносятся тем же вызовом Win32, которым пользуется проводник, по одному за раз, и файл попадает на место только когда его размер перестал расти и совпал с ожидаемым. Обрезанный файл будет отклонён, а не сохранён.',
      'queue.shotAlt': 'Страница очереди с задачами в разных состояниях',

      'private.eyebrow': 'Приватность по устройству',
      'private.title': 'Ничего не выгружается наружу',
      'private.body1':
        'Нет ни серверной части, ни аккаунта. Наружу уходит только то, о чём вы попросили: сайты, откуда идёт загрузка, и одна проверка обновлений через API релизов GitHub при запуске, которую можно отключить.',
      'private.body2':
        'Обновления скачиваются по запросу и сверяются с контрольной суммой, опубликованной рядом с установщиком. Настройки, история и логи остаются в <code>%APPDATA%\\HexagonMediaService</code>.',
      'private.shotAlt': 'Страница настроек с карточкой обновлений',

      'closer.title': 'Забрать',
      'closer.lede': 'Движок загрузки уже внутри, поэтому Python не нужен. ffmpeg тоже идёт в комплекте.',
      'closer.manual': 'Открыть руководство',
      'closer.meta': 'Windows 10 и 11, 64-бит.',

      'foot.source': 'Исходники',
      'foot.releases': 'Релизы',
      'foot.issues': 'Сообщить о проблеме',
      'foot.manual': 'Руководство',

      'guide.meta.title': 'Установка расширения для HDRezka - Hexagon Media Service',
      'guide.back': 'Вернуться на сайт',
      'guide.downloading.title': 'Загрузка началась',
      'guide.downloading.body':
        'Не закрывайте эту страницу. Настройка HDRezka занимает минут пять, и её можно сделать, пока файл скачивается.',
      'guide.downloading.retry': 'Загрузка не началась? Нажмите сюда.',
      'guide.title': 'Настройка HDRezka',
      'guide.lede':
        'HDRezka блокирует всё, что не похоже на настоящий браузер. Приложение обходит это тем, что читает страницу внутри вашего браузера, а для этого нужно небольшое расширение. Оно требуется только для HDRezka - YouTube, Reddit, Twitter и остальные работают сразу после установки.',
      'guide.time': 'Около пяти минут, один раз.',

      'guide.step1.title': 'Установите приложение',
      'guide.step1.body':
        'Запустите только что скачанный файл. На последней странице установщика поставьте галочку <b>Open the browser extension folder</b> перед нажатием Finish. Откроется окно папки: не закрывайте его, оно понадобится на шаге 3.',
      'guide.step1.note':
        'Пропустили? Папка всегда лежит здесь, этот путь можно вставить в адресную строку любого окна папки:',

      'guide.step2.title': 'Откройте страницу расширений браузера',
      'guide.step2.body':
        'В Chrome, Edge, Brave или Opera скопируйте адрес ниже в адресную строку и нажмите Enter. Обычной ссылкой это быть не может: браузеры не разрешают сайтам отправлять вас туда.',
      'guide.step2.note':
        'Затем включите <b>Режим разработчика</b> переключателем в правом верхнем углу. Без него кнопка со следующего шага не появится.',
      'guide.step2.alt': 'Адресная строка браузера с адресом страницы расширений и включённым режимом разработчика',

      'guide.step3.title': 'Загрузите папку',
      'guide.step3.body':
        'Нажмите <b>Загрузить распакованное расширение</b> - кнопка появилась вместе с режимом разработчика. Выберите папку расширения из шага 1 и нажмите <b>Выбор папки</b>.',
      'guide.step3.note':
        'Выбирайте саму папку, а не файл внутри неё. После загрузки появится карточка Hexagon Media Service Bridge.',
      'guide.step3.alt': 'Кнопка загрузки распакованного расширения и окно выбора папки',

      'guide.step4.title': 'Скопируйте токен из приложения',
      'guide.step4.body':
        'Откройте приложение, перейдите на <b>Download</b>, затем на вкладку <b>HDRezka</b>. Внизу есть панель Browser bridge. Нажмите <b>Copy token</b>.',
      'guide.step4.note':
        'Токен - это то, что не даёт любому открытому сайту общаться с приложением. Относитесь к нему как к паролю: ему место только в настройках расширения. Ваш будет совсем не таким, как на картинке.',
      'guide.step4.alt': 'Панель Browser bridge в приложении с кнопкой копирования токена',

      'guide.step5.title': 'Вставьте его в расширение',
      'guide.step5.body':
        'Вернитесь на страницу расширений, найдите Hexagon Media Service Bridge, нажмите <b>Подробнее</b>, затем <b>Параметры расширения</b>. Вставьте токен и нажмите <b>Save and test</b>.',
      'guide.step5.note': 'Должно появиться <b>Connected</b>. На этом настройка закончена.',
      'guide.step5.alt': 'Страница параметров расширения с вставленным токеном и сообщением об успешном подключении',

      'guide.done.title': 'Как пользоваться',
      'guide.done.body':
        'Откройте фильм или сериал на HDRezka в браузере и оставьте вкладку открытой. В приложении перейдите на <b>Download</b>, затем <b>HDRezka</b>, и нажмите <b>Read open HDRezka tab</b>. Выберите озвучку, качество и нужные серии, затем нажмите Download.',

      'guide.trouble.title': 'Если что-то не работает',
      'guide.trouble.q1': 'Приложение пишет, что расширение не подключено',
      'guide.trouble.a1':
        'Токен не сохранился или приложение перезапускали после копирования. Скопируйте заново и вставьте в параметры расширения.',
      'guide.trouble.q2': 'Could not establish connection',
      'guide.trouble.a2':
        'Расширение загрузили после того, как вкладка уже была открыта. Обновите вкладку HDRezka один раз.',
      'guide.trouble.q3': 'Это не похоже на страницу тайтла HDRezka',
      'guide.trouble.a3':
        'Вы на странице поиска или каталога. Откройте сам фильм или сериал.',
      'guide.trouble.q4': 'Страница расширений не открывается по ссылке',
      'guide.trouble.a4':
        'Так и задумано браузером. Скопируйте адрес и вставьте его в адресную строку сами.',
      'guide.trouble.more': 'Остальное описано в руководстве.',

      'guide.ui.devMode': 'Режим разработчика',
      'guide.ui.loadUnpacked': 'Загрузить распакованное расширение',
      'guide.ui.pack': 'Упаковать расширение',
      'guide.ui.update': 'Обновить',
      'guide.ui.selectFolder': 'Выбор папки',
      'guide.ui.extensions': 'Расширения',
      'guide.ui.folderName': 'extension',
      'guide.copy': 'Копировать',
      'guide.copied': 'Скопировано'
    },

    uk: {
      'meta.title': 'Hexagon Media Service',
      'meta.description':
        'Приватний завантажувач для YouTube, HDRezka, Reddit, Twitter і приблизно 1800 інших сайтів. Усе працює локально: без акаунта, без телеметрії, нічого не вивантажується.',

      'nav.features': 'Можливості',
      'nav.hdrezka': 'HDRezka',
      'nav.private': 'Приватність',
      'nav.manual': 'Посібник',
      'nav.github': 'GitHub',
      'nav.language': 'Мова',

      'hero.eyebrow': 'Застосунок для Windows',
      'hero.title': 'Завантажуйте будь-що.<br />Зберігайте все.',
      'hero.lede':
        'YouTube, HDRezka, Reddit, Twitter і ще близько 1800 сайтів, розкладені по теках і з тегами так, як потрібно вам. Усе працює на вашому комп\'ютері: без акаунта, без телеметрії, нічого не вивантажується.',
      'hero.download': 'Завантажити для Windows',
      'hero.downloadVersion': 'Завантажити {version} для Windows',
      'hero.portable': 'Портативна версія',
      'hero.meta': 'Windows 10 і 11, 64-біт. Інсталятор і портативна версія.',
      'hero.metaSize': 'Windows 10 і 11, 64-біт. Інсталятор, {size}.',
      'hero.shotAlt': 'Сторінка завантаження: вкладки сервісів, поле для посилань, картки формату та теки призначення',

      'strip.sites': 'підтримуваних сайтів',
      'strip.accounts': 'акаунтів не потрібно',
      'strip.quality': 'і все, що нижче',
      'strip.local': 'ніщо не залишає комп\'ютер',

      'features.title': 'Що він уміє',
      'features.sources.title': 'Багато джерел',
      'features.sources.body':
        'Усе, що підтримує yt-dlp, плюс окремий резолвер для HDRezka. Вставте посилання у «Автовизначення», і потрібний обробник підхопить його сам.',
      'features.ways.title': 'Багато варіантів',
      'features.ways.body':
        'Відео зі звуком, лише звук або лише відео. Від 360p до 4K. MP4, MKV чи WEBM; MP3, M4A, Opus, FLAC, WAV або Vorbis з обраним бітрейтом.',
      'features.queue.title': 'Справжня черга',
      'features.queue.body':
        'Одночасні завантаження з паузою, продовженням і повтором, швидкість та час до кінця, а кожна помилка має зрозуміле пояснення.',
      'features.bulk.title': 'Пакетами',
      'features.bulk.body':
        'Вставте одразу багато посилань або киньте плейлист чи канал, і кожен елемент стане окремим завданням у черзі.',
      'features.tagged.title': 'З тегами',
      'features.tagged.body':
        'Назва, виконавець, альбом, дата, розділи, субтитри та обкладинка записуються у готовий файл, а зверху додається початкове посилання.',
      'features.filed.title': 'По теках',
      'features.filed.body':
        'Сезон лягає як <code>Серіал / Season 06 / Серіал 6x20 Озвучка.mp4</code>, і точний шлях показано ще до постановки в чергу.',

      'hdrezka.eyebrow': 'HDRezka',
      'hdrezka.title': 'Цілий сезон обирається в одному місці',
      'hdrezka.body1':
        'Завантажте сторінку тайтла, потім оберіть озвучення, якість і будь-яке поєднання сезонів та серій: усі одразу, один сезон або діапазон на кшталт <code>1-10</code> чи <code>3,5,7</code>.',
      'hdrezka.body2':
        'HDRezka відхиляє прямі запити перевіркою на бота, тому сторінка читається просто у вашому браузері через невелике розширення. Усе подальше вирішує застосунок, а черга проговорює кожен етап: завантаження, очікування файлу, перенесення, запис тегів.',
      'hdrezka.guide': 'Як встановити розширення',
      'hdrezka.shotAlt': 'Панель HDRezka: тека призначення, кнопка читання відкритої вкладки та повідомлення про розширення',

      'queue.eyebrow': 'Черга',
      'queue.title': 'Усе в роботі - в одному списку',
      'queue.body1':
        'Завантаження рушія та передачі браузера показані поруч, і кожен рядок оновлюється на місці, тож активне завантаження не перемальовує сторінку.',
      'queue.body2':
        'Файли переносяться тим самим викликом Win32, яким користується провідник, по одному за раз, і файл потрапляє на місце лише коли його розмір перестав зростати і збігся з очікуваним. Обрізаний файл буде відхилено, а не збережено.',
      'queue.shotAlt': 'Сторінка черги із завданнями в різних станах',

      'private.eyebrow': 'Приватність за побудовою',
      'private.title': 'Нічого не вивантажується назовні',
      'private.body1':
        'Немає ні серверної частини, ні акаунта. Назовні йде лише те, про що ви попросили: сайти, звідки триває завантаження, і одна перевірка оновлень через API релізів GitHub під час запуску, яку можна вимкнути.',
      'private.body2':
        'Оновлення завантажуються на запит і звіряються з контрольною сумою, опублікованою поруч з інсталятором. Налаштування, історія та журнали залишаються в <code>%APPDATA%\\HexagonMediaService</code>.',
      'private.shotAlt': 'Сторінка налаштувань із карткою оновлень',

      'closer.title': 'Завантажити',
      'closer.lede': 'Рушій завантаження вже всередині, тож Python не потрібен. ffmpeg теж іде в комплекті.',
      'closer.manual': 'Відкрити посібник',
      'closer.meta': 'Windows 10 і 11, 64-біт.',

      'foot.source': 'Вихідний код',
      'foot.releases': 'Релізи',
      'foot.issues': 'Повідомити про проблему',
      'foot.manual': 'Посібник',

      'guide.meta.title': 'Встановлення розширення для HDRezka - Hexagon Media Service',
      'guide.back': 'Повернутися на сайт',
      'guide.downloading.title': 'Завантаження почалося',
      'guide.downloading.body':
        'Не закривайте цю сторінку. Налаштування HDRezka займає хвилин п\'ять, і це можна зробити, поки файл завантажується.',
      'guide.downloading.retry': 'Завантаження не почалося? Натисніть сюди.',
      'guide.title': 'Налаштування HDRezka',
      'guide.lede':
        'HDRezka блокує все, що не схоже на справжній браузер. Застосунок обходить це тим, що читає сторінку всередині вашого браузера, а для цього потрібне невелике розширення. Воно потрібне лише для HDRezka - YouTube, Reddit, Twitter та інші працюють одразу після встановлення.',
      'guide.time': 'Близько п\'яти хвилин, один раз.',

      'guide.step1.title': 'Встановіть застосунок',
      'guide.step1.body':
        'Запустіть щойно завантажений файл. На останній сторінці інсталятора поставте позначку <b>Open the browser extension folder</b> перед натисканням Finish. Відкриється вікно теки: не закривайте його, воно знадобиться на кроці 3.',
      'guide.step1.note':
        'Пропустили? Тека завжди лежить тут, цей шлях можна вставити в адресний рядок будь-якого вікна теки:',

      'guide.step2.title': 'Відкрийте сторінку розширень браузера',
      'guide.step2.body':
        'У Chrome, Edge, Brave або Opera скопіюйте адресу нижче в адресний рядок і натисніть Enter. Звичайним посиланням це бути не може: браузери не дозволяють сайтам відправляти вас туди.',
      'guide.step2.note':
        'Потім увімкніть <b>Режим розробника</b> перемикачем у правому верхньому куті. Без нього кнопка з наступного кроку не з\'явиться.',
      'guide.step2.alt': 'Адресний рядок браузера з адресою сторінки розширень та увімкненим режимом розробника',

      'guide.step3.title': 'Завантажте теку',
      'guide.step3.body':
        'Натисніть <b>Завантажити розпаковане розширення</b> - кнопка з\'явилася разом із режимом розробника. Оберіть теку розширення з кроку 1 і натисніть <b>Вибір теки</b>.',
      'guide.step3.note':
        'Обирайте саму теку, а не файл усередині неї. Після завантаження з\'явиться картка Hexagon Media Service Bridge.',
      'guide.step3.alt': 'Кнопка завантаження розпакованого розширення та вікно вибору теки',

      'guide.step4.title': 'Скопіюйте токен із застосунку',
      'guide.step4.body':
        'Відкрийте застосунок, перейдіть на <b>Download</b>, потім на вкладку <b>HDRezka</b>. Унизу є панель Browser bridge. Натисніть <b>Copy token</b>.',
      'guide.step4.note':
        'Токен - це те, що не дає будь-якому відкритому сайту спілкуватися із застосунком. Ставтеся до нього як до пароля: йому місце лише в налаштуваннях розширення. Ваш буде зовсім не таким, як на картинці.',
      'guide.step4.alt': 'Панель Browser bridge у застосунку з кнопкою копіювання токена',

      'guide.step5.title': 'Вставте його в розширення',
      'guide.step5.body':
        'Поверніться на сторінку розширень, знайдіть Hexagon Media Service Bridge, натисніть <b>Детальніше</b>, потім <b>Параметри розширення</b>. Вставте токен і натисніть <b>Save and test</b>.',
      'guide.step5.note': 'Має з\'явитися <b>Connected</b>. На цьому налаштування завершено.',
      'guide.step5.alt': 'Сторінка параметрів розширення зі вставленим токеном та повідомленням про підключення',

      'guide.done.title': 'Як користуватися',
      'guide.done.body':
        'Відкрийте фільм або серіал на HDRezka у браузері та залиште вкладку відкритою. У застосунку перейдіть на <b>Download</b>, потім <b>HDRezka</b>, і натисніть <b>Read open HDRezka tab</b>. Оберіть озвучення, якість і потрібні серії, потім натисніть Download.',

      'guide.trouble.title': 'Якщо щось не працює',
      'guide.trouble.q1': 'Застосунок пише, що розширення не підключено',
      'guide.trouble.a1':
        'Токен не зберігся або застосунок перезапускали після копіювання. Скопіюйте заново і вставте в параметри розширення.',
      'guide.trouble.q2': 'Could not establish connection',
      'guide.trouble.a2':
        'Розширення завантажили після того, як вкладка вже була відкрита. Оновіть вкладку HDRezka один раз.',
      'guide.trouble.q3': 'Це не схоже на сторінку тайтла HDRezka',
      'guide.trouble.a3':
        'Ви на сторінці пошуку або каталогу. Відкрийте сам фільм чи серіал.',
      'guide.trouble.q4': 'Сторінка розширень не відкривається за посиланням',
      'guide.trouble.a4':
        'Так і задумано браузером. Скопіюйте адресу та вставте її в адресний рядок самі.',
      'guide.trouble.more': 'Решта описана в посібнику.',

      'guide.ui.devMode': 'Режим розробника',
      'guide.ui.loadUnpacked': 'Завантажити розпаковане розширення',
      'guide.ui.pack': 'Упакувати розширення',
      'guide.ui.update': 'Оновити',
      'guide.ui.selectFolder': 'Вибір теки',
      'guide.ui.extensions': 'Розширення',
      'guide.ui.folderName': 'extension',
      'guide.copy': 'Копіювати',
      'guide.copied': 'Скопійовано'
    }
  }

  function pick() {
    var stored = null
    try {
      stored = localStorage.getItem(STORAGE_KEY)
    } catch (e) {
      // Private browsing can refuse storage entirely; the default is fine.
    }
    if (stored && STRINGS[stored]) return stored

    var wanted = (navigator.language || 'en').toLowerCase()
    for (var i = 0; i < LANGUAGES.length; i++) {
      if (wanted.indexOf(LANGUAGES[i]) === 0) return LANGUAGES[i]
    }
    return 'en'
  }

  var current = pick()

  /** One string, with {name} placeholders filled from `vars`. */
  function t(key, vars) {
    var table = STRINGS[current] || STRINGS.en
    var value = table[key]
    if (value === undefined) value = STRINGS.en[key]
    if (value === undefined) return key
    if (!vars) return value
    return value.replace(/\{(\w+)\}/g, function (whole, name) {
      return Object.prototype.hasOwnProperty.call(vars, name) ? vars[name] : whole
    })
  }

  function apply() {
    document.documentElement.lang = current

    var title = document.querySelector('[data-i18n-doctitle]')
    document.title = t(title ? title.getAttribute('data-i18n-doctitle') : 'meta.title')

    var description = document.querySelector('meta[name="description"]')
    if (description) description.setAttribute('content', t('meta.description'))

    each('[data-i18n]', function (node) {
      node.textContent = t(node.getAttribute('data-i18n'))
    })
    each('[data-i18n-html]', function (node) {
      node.innerHTML = t(node.getAttribute('data-i18n-html'))
    })
    each('[data-i18n-alt]', function (node) {
      node.setAttribute('alt', t(node.getAttribute('data-i18n-alt')))
    })
    each('[data-i18n-title]', function (node) {
      node.setAttribute('title', t(node.getAttribute('data-i18n-title')))
    })

    each('[data-lang]', function (node) {
      var active = node.getAttribute('data-lang') === current
      node.classList.toggle('active', active)
      node.setAttribute('aria-pressed', active ? 'true' : 'false')
    })

    // Anything showing a release version or size re-renders in the new language.
    document.dispatchEvent(new CustomEvent('languagechange-hms'))
  }

  function each(selector, fn) {
    var nodes = document.querySelectorAll(selector)
    for (var i = 0; i < nodes.length; i++) fn(nodes[i])
  }

  function set(lang) {
    if (!STRINGS[lang]) return
    current = lang
    try {
      localStorage.setItem(STORAGE_KEY, lang)
    } catch (e) {
      // Not being able to remember the choice is not a reason to ignore it.
    }
    apply()
  }

  window.HMS_I18N = {
    t: t,
    apply: apply,
    set: set,
    languages: LANGUAGES,
    current: function () {
      return current
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply)
  } else {
    apply()
  }
})()
