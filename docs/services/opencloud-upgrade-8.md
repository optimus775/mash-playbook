<!-- SPDX-FileCopyrightText: 2026 MASH project contributors -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# Обновление OpenCloud с 7.x до 8.x

Целевая версия mash — `8.0.1` из ветки Rolling. Она опубликована в `opencloudeu/opencloud-rolling`, а Production `7.2.4` использует `opencloudeu/opencloud`. Ветка Rolling выпускается чаще и имеет другой цикл поддержки: [официальные правила](https://docs.opencloud.eu/docs/admin/resources/lifecycle/).

Результаты обновления mash: [отчёт с проверками и скриншотами](opencloud-upgrade-8-acceptance.md).

## Что требует миграции

OpenCloud 8 создаёт новый поисковый индекс Bleve `bleve-v5`. Документы, существовавшие до обновления, нужно переиндексировать. Для перехода с 7.x дополнительные изменения конфигурации не требуются: [руководство миграции](https://docs.opencloud.eu/docs/admin/maintenance/upgrade/upgrade-8.x.x/), [релиз 8.0.1](https://github.com/opencloud-eu/opencloud/releases/tag/v8.0.1). Исправление 8.0.1 убирает тайм-аут переиндексации пространств, присутствовавший в 8.0.0.

На mash используется встроенный Bleve, встроенные учётные записи, существующие EuroOffice и Tika. `config/opencloud.yaml` с ключами экземпляра сохраняется; `opencloud init` повторно его не создаёт. Проверка `init --diff` выполнялась на временной копии конфигурации, поскольку эта команда сама создаёт файл резервной копии.

## Инвентори и повторный запуск

```yaml
opencloud_version: 8.0.1
opencloud_container_image_repository: opencloudeu/opencloud-rolling
opencloud_search_index_generation: v5
opencloud_search_reindex_concurrency: 1
opencloud_environment_variables_additional_variables: |
  GOMEMLIMIT=1GiB
eurooffice_version: v9.3.4-hotfix.1
tika_version: 3.3.0.0
```

Локальная роль `mash/opencloud_migrations` выполняется после менеджера systemd. Она ждёт, пока HTTPS API сообщит целевую `productversion`, затем вызывает:

```bash
docker exec mash-opencloud opencloud search index --all-spaces --force-rescan --concurrency 1 --insecure
```

`--insecure` относится только к внутреннему gRPC без TLS. Проверка публичных HTTPS-сертификатов остаётся включённой.

Успешное завершение сохраняется в `/srv/storage/opencloud/migrations/search-v5.done`. Повторные установки пропускают сканирование; изменение patch-версии также не запускает его заново. Имя поколения индекса меняют только при следующем изменении схемы, требующем переиндексации.

Скрипт использует `flock`, поэтому параллельные запуски не запускают два сканирования. Маркер записывается атомарно после завершения команды. Проверяются код возврата, сообщения об ошибках отдельных пространств и отмене операции: OpenCloud 8.0.1 может вернуть `0` даже в этих случаях. Дополнительно проверяется журнал systemd за время сканирования: ошибки извлечения текста и записи файлов в индекс вообще не попадают в вывод CLI. При ошибке маркер не создаётся, следующий запуск повторяет миграцию. Протокол сохраняется рядом в `search-v5.log`, журнал сервиса при ошибке — в `search-v5.log.service`; каталог доступен только root.

Ansible ждёт завершения асинхронной задачи; лимит `opencloud_search_reindex_timeout` по умолчанию равен 24 часам. Сам сервис продолжает работать во время индексации. Режим Ansible `--check` не выполняет переиндексацию.

На mash с 4 ГБ RAM пространства обрабатываются последовательно (`opencloud_search_reindex_concurrency: 1`). Для Go задан `GOMEMLIMIT=1GiB`: это мягкий предел памяти среды выполнения, а не жёсткий лимит всего контейнера. Он заставляет сборщик мусора освобождать память раньше; поведение описано в [руководстве Go](https://go.dev/doc/gc-guide#Memory_limit). Параметры добавлены после подтверждённого OOM во время массовой индексации; наблюдение за памятью остаётся необходимым.

## Последовательность обновления

1. Проверить работоспособность текущего экземпляра и сделать согласованную резервную копию при остановленном OpenCloud.
2. Обновить инвентори и подготовить производные файлы: `just optimize`.
3. Применить конфигурацию Tika: `just run-tags install-tika,install-aux,start-group --extra-vars=group=tika --limit mash_met_surf`. Тег `install-aux` нужен для XML-файла из инвентори.
4. Обновить EuroOffice: `just install-service eurooffice --limit mash_met_surf`. Дождаться ответа 200 от `/hosting/discovery`.
5. Выполнить `just install-service opencloud --limit mash_met_surf`. Переиндексация входит в эту команду.
6. Выполнить `just run-tags check-opencloud --limit mash_met_surf`, проверить старые документы, поиск по содержимому и сохранение правок в EuroOffice.
7. Повторить установку OpenCloud: ожидаются `changed=0` и неизменное время запуска контейнера.

Для повторной попытки незавершённой миграции после запуска целевого контейнера можно использовать `just run-tags migrate-opencloud --limit mash_met_surf`.

Если сканирование прервано вручную, перед повторной попыткой перезапустите OpenCloud и дождитесь доступности API. В 8.0.1 отмена CLI не гарантирует остановку уже начатого обхода пространства на сервере; одного завершения клиентского процесса недостаточно для безопасного повторного запуска.

Старый индекс `data/search/bleve` не удаляется автоматически. После проверки поиска его можно удалить отдельно; нельзя удалять новый `bleve-v5`.

При откате сначала остановите OpenCloud и восстановите его каталог из согласованной копии, включая `config/`, `data/` и состояние `migrations/`, затем верните старые параметры образа. Если копия сделана до 8.x, в ней нет маркера `search-v5.done`: не сохраняйте этот маркер от обновлённого экземпляра, иначе последующий переход снова на 8.x пропустит переиндексацию. Из снимка диска восстанавливайте только каталог OpenCloud, сохраняя текущие данные остальных приложений.

## Связанные пакеты

EuroOffice обновляется до [v9.3.4-hotfix.1](https://github.com/euro-office/DocumentServer/releases/tag/v9.3.4-hotfix.1), исправляющей сохранение документов и обновление. Существующие JWT и настройки WOPI сохраняются.

Tika 3.3 остаётся закреплена: OpenCloud 8 поддерживает её API. Tika 4 умеет возвращать дополнительные метаданные, но имеет собственные изменения поведения; её переход не является обязательной частью этой миграции. В текущем инвентори интеграция Paperless с Tika отключена владельцем (`paperless_tika_enabled: false`).

Gotenberg для поиска OpenCloud не требуется: OpenCloud передаёт документы прямо в Tika, а распознавание сканов выполняет Tesseract. В Paperless Gotenberg нужен для преобразования офисных документов и писем в PDF; добавление его к OpenCloud не улучшает OCR. См. [поиск OpenCloud](https://docs.opencloud.eu/docs/dev/server/services/search/information/), [OCR в Tika](https://cwiki.apache.org/confluence/display/TIKA/TikaOCR) и [интеграцию Paperless](https://docs.paperless-ngx.com/configuration/#tika).

Для длинных сканированных документов лимит Tika `taskTimeoutMillis` увеличен с 300000 до 1800000 мс. Прежний лимит срабатывал во время миграции и перезапускал дочерний Java-процесс, обрывая параллельные запросы. Такое поведение описано в [документации Apache Tika](https://cwiki.apache.org/confluence/pages/viewpage.action?pageId=191334877). OCR остаётся включённым.

XML задаётся через существующий `aux_file_definitions_custom` в зашифрованном инвентори, а `tika_process_extra_arguments_custom` подключает его как `/tika-extras/tika-config.xml`. Повторный запуск сохраняет файл без изменений. При последующем изменении содержимого XML необходимо перезапустить Tika: сама роль auxiliary не перезапускает сервисы.
