# 50 — База данных и платежи TON
Источник истины: 50_База_данных_и_платежи_TON.docx
________________________________________
DB Schema v0.1 — Field Specification (FINAL)
Общие соглашения
•	Время: timestamptz (UTC).
•	JSON: jsonb.
•	PK: bigint.
•	Строковые статусы: text только из перечислений Enums v0.1 (см. раздел в конце).
•	llm_json хранит только структурированный контракт (без сырого ответа провайдера).
________________________________________
1) users
Назначение: якорь Telegram-пользователя + имя обращения/LLM + план доступа.
Поле	Тип	NULL	Default	Пример	Пояснение
id	bigint PK	no	auto	42	внутренний ключ
tg_id	bigint	no	—	123456789	Telegram user id, unique
display_name	text	no	derived	misha_qa / user_123456789	имя обращения/LLM, редактируемое в настройках
tg_username	text	yes	null	misha_qa	справочно
plan	text	no	FREE	FREE/SUB_MONTH	план
plan_started_at	timestamptz	yes	null	—	начало плана
plan_expires_at	timestamptz	yes	null	—	окончание плана
created_at	timestamptz	no	now()	—	—
updated_at	timestamptz	no	now()	—	—
Канон дефолта display_name
•	применяется только при создании пользователя: tg_username (если есть) → user_<tg_id>.
•	далее display_name меняется только через “настройки” (ручная правка пользователем), не автопересчитывается.
Ограничения/индексы
•	UNIQUE(users.tg_id).
________________________________________
2) sessions
Назначение: одна сказка (сессия) + безопасная адресация из callback.
Поле	Тип	NULL	Default	Пример	Пояснение
id	bigint PK	no	auto	1001	внутренний id
user_id	bigint FK(users.id)	no	—	42	владелец
tg_id	bigint	no	—	123456789	безопасная проверка владельца в tg-хендлере
sid8	text	no	—	a1b2c3d4	публичный короткий id (8 [a-z0-9])
status	text	no	ACTIVE	ACTIVE/FINISHED/ABORTED	статус
theme_id	text	yes	null	—	тема
step	int	no	0	0..	шаг
max_steps	int	no	—	10	лимит шагов
player_name	text	no	from users	—	снапшот display_name при старте
params_json	jsonb	no	{}	—	параметры
facts_json	jsonb	no	{}	—	факты
memory_summary	text	yes	null	—	краткая память
ending_id	text	yes	null	—	финал
last_step_message_id	bigint	yes	null	—	stale-inline защита
last_step_sent_at	timestamptz	yes	null	—	stale защита по времени
created_at	timestamptz	no	now()	—	создание (для v0.1: created_at == started_at)
updated_at	timestamptz	no	now()	—	—
expires_at	timestamptz	yes	null	—	TTL/архив
Канон адресации
•	загрузка сессии из callback: по (tg_id, sid8), никогда по одному sid8.
Канон генерации sid8
•	sid8 генерируется криптографически случайно (не счётчик, не время, не предсказуемый алгоритм).
Канон player_name
•	player_name заполняется при создании записи sessions (создание сессии = старт сказки для v0.1).
•	после создания не изменяется.
Канон “одна активная”
•	не более одной ACTIVE сессии на user_id.
Канон expires_at
•	expires_at используется только для фоновой архивации/очистки.
•	не влияет на доступность ACTIVE/FINISHED иначе как через уборку мусора.
Ограничения/индексы
•	UNIQUE(sessions.sid8)
•	UNIQUE(sessions.tg_id, sessions.sid8)
•	INDEX(sessions.user_id)
•	INDEX(sessions.status)
•	INDEX(sessions.tg_id).
________________________________________
3) session_events
Назначение: журнал пользовательских ходов по шагам.
Поле	Тип	NULL	Default	Пример	Пояснение
id	bigint PK	no	auto	9001	—
session_id	bigint FK(sessions.id)	no	—	1001	—
step	int	no	—	0..	шаг
user_input	text	yes	null	—	текст пользователя
choice_id	text	yes	null	A	выбор
llm_json	jsonb	yes	null	{ narration, choices, deltas, meta }	только контракт
deltas_json	jsonb	yes	null	—	изменения
created_at	timestamptz	no	now()	—	—
Канон
•	session_events хранит только пользовательский ход (текст/выбор).
•	системные UI-события (пересказ/ретраи/ошибки) пишутся в ui_events.
Ограничения/индексы
•	INDEX(session_events.session_id)
•	ОБЯЗАТЕЛЬНО v0.1: UNIQUE(session_id, step).
________________________________________
4) payments
Назначение: платежи/инвойсы + тип продукта + доказуемый период подписки.
Поле	Тип	NULL	Default	Пример	Пояснение
id	bigint PK	no	auto	501	—
user_id	bigint FK(users.id)	no	—	42	—
invoice_id	text	no	—	inv_...	unique
tx_hash	text	yes	null	—	хэш
amount	bigint	no	0	—	сумма в минимальных единицах
status	text	no	PENDING	PENDING/CONFIRMED/FAILED	статус
kind	text	no	SUB_MONTH	SUB_MONTH	тип продукта
period_yyyymm	text	yes	null	2026-02	период подписки (календарный месяц)
created_at	timestamptz	no	now()	—	—
updated_at	timestamptz	no	now()	—	—
Канон обязательности периода
•	если kind=SUB_MONTH и status=CONFIRMED ⇒ period_yyyymm обязан быть заполнен.
Ограничения/индексы
•	UNIQUE(payments.invoice_id)
•	INDEX(payments.user_id)
•	(опционально) INDEX(payments.status).
________________________________________
5) confirm_requests
Назначение: одноразовые подтверждения (idempotency) с безопасной привязкой к пользователю.
Поле	Тип	NULL	Default	Пример	Пояснение
id	bigint PK	no	auto	7001	—
user_id	bigint FK(users.id)	no	—	42	—
tg_id	bigint	no	—	123456789	безопасная проверка владельца
session_id	bigint FK(sessions.id)	yes	null	1001	контекст
rid8	text	no	—	k9m2p1x7	unique (8 [a-z0-9])
kind	text	no	—	ABORT_SESSION	тип подтверждения
payload_json	jsonb	yes	null	—	детали
status	text	no	PENDING	PENDING/USED/EXPIRED	статус
result	text	yes	null	YES/NO/FAIL	результат
created_at	timestamptz	no	now()	—	—
expires_at	timestamptz	no	—	now()+10m	TTL
used_at	timestamptz	yes	null	—	—
Канон поиска confirm
•	lookup только по (tg_id, rid8), никогда по одному rid8.
Канон консистентности
•	status=PENDING ⇒ result is null и used_at is null
•	status=USED ⇒ used_at not null и result in (YES, NO, FAIL)
•	status=EXPIRED ⇒ used_at is null и result is null
Ограничения/индексы
•	UNIQUE(confirm_requests.rid8)
•	INDEX(confirm_requests.tg_id)
•	INDEX(confirm_requests.user_id)
•	INDEX(confirm_requests.expires_at)
•	INDEX(confirm_requests.tg_id, confirm_requests.rid8) (канон lookup делает дешёвым и очевидным)
________________________________________
6) usage_windows
Назначение: квоты 12 часов (rolling) для защиты токенов.
Квоты v0.1
•	messages_used ≤ 150 / 12h
•	sessions_started ≤ 20 / 12h
•	превышение ⇒ blocked_until
Поле	Тип	NULL	Default	Пример	Пояснение
id	bigint PK	no	auto	8001	—
user_id	bigint FK(users.id)	no	—	42	—
window_start	timestamptz	no	—	—	начало окна
window_end	timestamptz	no	—	—	конец окна
messages_used	int	no	0	—	генеративные действия
sessions_started	int	no	0	—	новые сессии
blocked_until	timestamptz	yes	null	—	блок
updated_at	timestamptz	no	now()	—	—
Канон окна
•	rolling: окно создаётся от первого генеративного действия и длится 12 часов.
Канон уникальности активного окна
•	в любой момент у пользователя не более одного окна, где now ∈ [window_start, window_end).
•	обеспечивается транзакционным upsert в коде (одновременно создаём/находим окно и инкрементим счётчик).
Ограничения/индексы
•	UNIQUE(user_id, window_start)
•	INDEX(user_id).
________________________________________
7) ui_events
Назначение: дедуп одноразовых UI-событий (recap/ретраи), не являющихся пользовательским ходом.
Поле	Тип	NULL	Default	Пример	Пояснение
id	bigint PK	no	auto	6001	—
session_id	bigint FK(sessions.id)	no	—	1001	—
step	int	no	—	0..	шаг
kind	text	no	—	recap_shown	тип
content_hash	text	no	—	sha256:<hex>	канон формата
state	text	no	PENDING	PENDING/SHOWN/FAILED	состояние
pending_since	timestamptz	yes	null	—	время входа в pending
fail_count	int	no	0	—	—
next_retry_at	timestamptz	yes	null	—	—
step_message_id	bigint	yes	null	—	msg шага
recap_message_id	bigint	yes	null	—	msg пересказа
created_at	timestamptz	no	now()	—	—
updated_at	timestamptz	no	now()	—	—
Канон консистентности state / pending_since
•	если state = PENDING ⇒ pending_since обязан быть заполнен (not null).
•	если state != PENDING ⇒ pending_since может быть null (или сохраняться как историческое значение, на усмотрение реализации).
Ограничения/индексы
•	UNIQUE(session_id, step, kind, content_hash)
•	INDEX(session_id)
•	INDEX(state, next_retry_at).
________________________________________
Перечисления (Enums v0.1)
•	users.plan: FREE | SUB_MONTH
•	sessions.status: ACTIVE | FINISHED | ABORTED
•	payments.status: PENDING | CONFIRMED | FAILED
•	payments.kind: SUB_MONTH
•	confirm_requests.status: PENDING | USED | EXPIRED
•	confirm_requests.result: YES | NO | FAIL
•	ui_events.state: PENDING | SHOWN | FAILED
•	ui_events.kind: recap_shown (v0.1)
________________________________________
ПАТЧ ДЛЯ 50_База_данных_и_платежи_TON.docx
Вставить в конец документа целиком (append-only)
________________________________________
Story Snapshots & Book Export — Placeholders v0.1
RESERVED / FUTURE: таблицы для отладки и будущего экспорта книги. В MVP допускается создать и заполнять snapshots/pages для дебага. Экспорт книги (PDF/ePub), платежи, UI-предложения — не реализуются в MVP.
________________________________________
Назначение
Заложить структуру хранения пройденной сказки для:
•	отладки качества генерации
•	аналитики прохождения
•	возможного будущего экспорта истории в книгу
________________________________________
Таблица: story_snapshots
Назначение: один снапшот на одну завершённую сессию.
Поля:
•	id bigint PK
•	session_id bigint NOT NULL
FK → sessions.id
•	theme_id text NOT NULL
•	n_total int NOT NULL
•	created_at timestamptz NOT NULL
•	ttl_expires_at timestamptz NOT NULL
Ограничения:
•	UNIQUE(session_id)
________________________________________
Таблица: story_snapshot_pages
Назначение: страницы книги (1 шаг = 1 страница).
Поля:
•	id bigint PK
•	snapshot_id bigint NOT NULL
FK → story_snapshots.id ON DELETE CASCADE
•	step0 int NOT NULL
•	text_shown text NOT NULL
•	choices jsonb NULL
Выбор игрока:
•	choice_kind enum('choice','free_text','none') NOT NULL
•	choice_id char(1) NULL -- A|B|C
•	choice_text text NULL
•	free_text text NULL
Индексы:
•	(snapshot_id, step0) UNIQUE
________________________________________
TTL / Purge policy
•	Записи удаляются по ttl_expires_at < now().
•	Удаление снапшота каскадно удаляет страницы.
•	Механизм purge: ежедневный job (cron / systemd / pgagent).
________________________________________
Таблица: story_book_exports (RESERVED / FUTURE)
⚠ Не используется в MVP. Может быть не создана.
Назначение: будущий экспорт сказки в PDF/ebook.
Поля (черновик):
•	id bigint PK
•	snapshot_id bigint FK
•	status enum('draft','generated','delivered')
•	file_url text NULL
•	created_at timestamptz
________________________________________
Примечание
Таблицы предназначены для:
•	отладки качества историй
•	анализа прохождений
•	будущего экспорта книг
Логика заполнения и UI-интеграция не входят в MVP.

