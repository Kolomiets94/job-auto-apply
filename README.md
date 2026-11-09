# Job Auto Apply

Портфолио-проект для поиска и предварительного отбора вакансий Junior Frontend (React/TypeScript, HTML/CSS) и отдельных фриланс-задач. Код собирает публичные объявления из нескольких источников, ранжирует их по заголовку, указанному стеку, уровню и совпадению с резюме, а затем отправляет отчёт в Telegram.

## Правила отбора

- Цель: Junior Frontend / React / TypeScript и вёрстка; вакансии «от 1 года» допускаются, если это явно указано в данных.
- Исключаются стажировки, Middle/Senior, Vue, Angular, Full Stack, React Native и Flutter.
- Обязательный SQL исключается; явно необязательный SQL («будет плюсом») не блокирует вакансию.
- QA-объявления могут появляться в отчётах, но автоотклики QA приостановлены.
- Полные требования некоторых источников недоступны из выдачи; поэтому соответствие недоступным требованиям нельзя подтвердить автоматически. Ранжирование не является гарантией соответствия.

## Черновики и отчёты

Сопроводительное письмо составляется на основе подтверждённых личных проектов с прямой ссылкой на код. Оно не утверждает коммерческий опыт и не приписывает навыки, которых нет в портфолио. По разрешению пользователя отклики на прошедшие фильтры вакансии отправляются автоматически, без подтверждения каждого письма в Telegram. Telegram используется для отчётов о фактическом результате. Бот считает найденные, отобранные, пропущенные и отправленные объявления и сообщает причины в сводке. Полные тексты писем не публикуются в логах GitHub Actions.

## Количество откликов

Часовые и дневные ограничения количества отключены: `DAILY_JOB_LIMIT`, `DAILY_FREELANCE_LIMIT`, `HOURLY_JOB_LIMIT`, `HOURLY_FREELANCE_LIMIT` равны `0`. Пустое значение окружения по умолчанию также означает отсутствие лимита; положительное число снова включает соответствующую квоту. Проверка повторных откликов сохраняется. В рабочем запуске нет ожидания кнопки Telegram и ограничения числа черновиков; диагностический `Verify Telegram Draft` остаётся отдельным тестом и не отправляет отклики работодателям. Отправка разрешена круглосуточно, включая выходные. Тайм-аут GitHub Actions и ограничения самих площадок действуют независимо от квот количества.

## Запуск

`pip install -r requirements.txt`, затем `python worker.py`. GitHub Actions запускает поиск каждый час круглосуточно (`0 * * * *`). Поиск охватывает Россию и международные источники; международные вакансии проходят только при явно указанной доступности из России либо worldwide/anywhere/global и без ограничений права на работу. Повторные отклики исключаются. Интеграции почты, Telegram и сайтов используют секреты окружения; их значения не должны попадать в репозиторий. Перед реальным использованием проверьте источники, фильтры, авторизацию и правила конкретной площадки.

Автор: [Alexander Kolomiets](https://github.com/Kolomiets94).


## Autonomous browser agent

The Flask service now includes an LLM-guided Playwright agent at `/agent`. It can inspect and navigate arbitrary public websites, interact with ordinary controls, and keep a persistent Chromium profile (cookies and localStorage) when the profile directory is stored on durable disk. Setup instructions and security limits are in [cloud-browser-agent/README.md](cloud-browser-agent/README.md).

The agent requires an OpenAI-compatible model endpoint and a private `AGENT_ACCESS_TOKEN`. Passwords, OTPs, CAPTCHA and payment data are not automated; high-impact form submissions pause for confirmation. For durable sessions on the free Render filesystem, do not assume browser profile data will survive restarts; local execution is recommended.
