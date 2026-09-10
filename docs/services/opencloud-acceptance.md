<!-- SPDX-FileCopyrightText: 2026 MASH project contributors -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# Приёмка OpenCloud на mash

Проверено 10 сентября 2026 года на [cloud.met.surf](https://cloud.met.surf), группа инвентори `mash_met_surf`.

Установлен OpenCloud `7.2.4 stable`. Подключены существующие EuroOffice `v9.3.2` и Tika `3.3.0.0-full`. Конфигурация и данные находятся в `/srv/storage/opencloud` на отдельном Btrfs-диске, владелец — пользователь MASH (`997:986`). Вход: `admin`; пароль хранится в `opencloud_admin_password` зашифрованного через git-crypt инвентори.

## Результаты

| Проверка | Подтверждение |
| --- | --- |
| HTTPS и вход | Действительный TLS-сертификат, `status.php`: установлен, обслуживание выключено; свежий вход с паролем из инвентори после перезапуска |
| Загрузка и скачивание | DOCX, PDF и двоичный файл размером 8 МиБ скачаны с совпадающими SHA256; совпадение повторно проверено после перезапуска |
| Word | Создан DOCX через меню OpenCloud, введён текст в EuroOffice, сохранён и повторно открыт; скачанный документ содержит `amberwillowproof` |
| Excel | Создан XLSX, изменена ячейка A1, сохранён и повторно открыт; скачанный файл содержит `cedarbranchproof` |
| PowerPoint | Создан PPTX, изменён заголовок слайда, сохранён и повторно открыт; скачанный файл содержит `riverstoneproof` |
| Полнотекстовый поиск | Фраза `saffronpinetrail`, находящаяся только внутри DOCX и PDF, найдена в обоих файлах с фрагментами содержимого; после перезапуска подтверждено через браузер и WebDAV REPORT |
| Сохранность данных | После перезапуска доступны все шесть проверочных файлов, правки во всех трёх офисных форматах сохранены; SHA256 `config/opencloud.yaml` не изменился |
| Повторная установка | `just install-service opencloud --limit mash_met_surf`: основной хост `ok=27 changed=0 failed=0`, все дополнительные хосты `changed=0 failed=0`; время запуска контейнера не изменилось |
| Удаление роли | На отдельном временном экземпляре проверены установка, повторная установка и удаление; unit удалён, пользовательский файл и сгенерированная конфигурация сохранены |
| Локальные проверки | 5 тестов оптимизатора, шаблонов, порядка сетей и защитных условий; Ansible syntax check, `ansible-lint` с профилем production, YAML и Markdown lint прошли |

Повторная установка также проверена с другим `PYTHONHASHSEED`: список Docker-сетей сохраняет порядок и не вызывает лишнего перезапуска службы.

SHA256 проверочного файла размером 8 МиБ:

```text
7d212b9c884f5c77896de960ae17cc341cda43b14d6a971f34ca29ebd4badf7f
```

## Скриншоты после повторного открытия

- [DOCX в EuroOffice](../assets/opencloud/word-reopened.png)
- [XLSX в EuroOffice](../assets/opencloud/excel-reopened.png)
- [PPTX в EuroOffice](../assets/opencloud/powerpoint-reopened.png)
- [Поиск по содержимому DOCX и PDF](../assets/opencloud/fulltext-search.png)

При мгновенном программном вводе и отправке запроса наблюдалось зависание страницы поиска. Повторная проверка после загрузки списка файлов, с последовательным вводом и ожиданием подсказок, прошла; прямой поисковый запрос вернул оба результата примерно за 0,9 секунды. Это наблюдение относится к браузерному сценарию; индекс после перезапуска сохранён.

## Воспроизведение проверок

```bash
python3 tests/test_opencloud.py
ansible-lint roles/mash/opencloud
yamllint roles/mash/opencloud examples/opencloud templates/setup.yml
just run --syntax-check --limit mash_met_surf
just install-service opencloud --limit mash_met_surf
just run-tags check-opencloud --limit mash_met_surf
```

Для локальных тестов нужны зависимости оптимизатора `PyYAML`, `regex`, Ansible и установленные роли MASH. Проверка `check-opencloud` проверяет HTTPS, WOPI discovery и доступность Tika из контейнера. Редактирование документов проверялось в Chromium через Playwright; содержимое скачанных файлов дополнительно прочитано библиотеками `python-docx`, `openpyxl` и `python-pptx`.

После приёмки папка `OpenCloud-Acceptance-20260910` удалена из персональных файлов; WebDAV подтвердил её отсутствие ответом 404. Временные локальные токены браузерной проверки удалены.

Перед изменением настроек EuroOffice сохранена резервная копия в `/srv/storage/opencloud/backups/eurooffice-before-opencloud-20260910T191248Z`. Инструкция по эксплуатации и резервному копированию OpenCloud: [opencloud.md](opencloud.md).
