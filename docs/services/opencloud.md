<!-- SPDX-FileCopyrightText: 2026 MASH project contributors -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# OpenCloud

[OpenCloud](https://github.com/opencloud-eu/opencloud) — файловое хранилище с совместным доступом, веб-интерфейсом и редактированием документов. Этот форк содержит локальную [Ansible-роль](../../roles/mash/opencloud/README.md).

## Конфигурация mash

В `inventory/host_vars/mash.met.surf/vars.yml` настроены:

```yaml
opencloud_enabled: true
opencloud_hostname: cloud.met.surf
opencloud_base_path: /srv/storage/opencloud
opencloud_required_mount_path: /srv/storage
opencloud_version: 8.0.1
opencloud_container_image_repository: opencloudeu/opencloud-rolling
opencloud_search_index_generation: v5
opencloud_collaboration_enabled: true
opencloud_search_enabled: true
opencloud_admin_password: 'ЗАДАЙТЕ-СЛУЧАЙНЫЙ-ПАРОЛЬ'
```

Значение пароля уже создаётся при подготовке инвентори. Не заменяйте его примером выше. Файл этого сервера защищён `git-crypt`: в открытом рабочем дереве он читаемый, в Git — зашифрованный. Не копируйте секреты в незашифрованные примеры и отчёты.

Логин администратора: `admin`. Пароль находится в переменной `opencloud_admin_password` указанного инвентори. Пользователи управляются внутри OpenCloud; Authentik не требуется.

Хранилище должно быть смонтировано до установки. Роль создаёт `config/` и `data/` под `/srv/storage/opencloud`, использует UID/GID пользователя MASH и не меняет права родительского `/srv/storage`. PostgreSQL, Redis и отдельный WOPI-домен не нужны.

## EuroOffice

Используется существующий `https://eurooffice.met.surf`. В его дополнительных переменных окружения включается WOPI:

```yaml
eurooffice_environment_variables_additional_variables: |
  WOPI_ENABLED=true
  ALLOW_PRIVATE_IP_ADDRESS=true
```

Существующий JWT-секрет остаётся прежним. WOPI использует собственные токены OpenCloud; JWT EuroOffice не нужно копировать в секреты OpenCloud.

Встроенная служба `collaboration` работает через `https://cloud.met.surf/wopi`. В реестре приложений DOCX, XLSX и PPTX назначены EuroOffice; CSP разрешает загрузку редактора. `COLLABORATION_APP_PROOF_DISABLE=true` соответствует [официальному примеру EuroOffice](https://github.com/opencloud-eu/opencloud-compose/blob/stable-7.2/weboffice/euroffice.yml). Проверка TLS-сертификатов остаётся включённой.

В инвентори закреплены EuroOffice `v9.3.4-hotfix.1` и Tika `3.3.0.0-full`. EuroOffice обновлён с исправлениями сохранения документов; используемый API Tika 3 совместим с OpenCloud 8 и общим экземпляром Paperless.

## Tika и почта

OpenCloud подключается к существующей Docker-сети Tika и обращается к `http://mash-tika:9998`. Полнотекстовый поиск включён в сервере и интерфейсе. Индексация новых документов выполняется асинхронно; создание превью и полнотекстовый поиск — разные процессы.

SMTP-уведомления подключаются к существующему Exim relay по внутренней Docker-сети. Новые экземпляры Tika и почтового сервера не создаются.

## Установка и проверка

Если используется оптимизация, обновите производные файлы после изменения инвентори:

```bash
just optimize
just run --syntax-check --limit mash_met_surf
just setup-service eurooffice --limit mash_met_surf
just install-service opencloud --limit mash_met_surf
just run-tags check-opencloud --limit mash_met_surf
```

При необходимости установите зависимости оптимизатора `PyYAML` и `regex` в используемое Python-окружение. Пример минимального инвентори: [examples/opencloud/vars.yml](../../examples/opencloud/vars.yml).

Всегда используйте `--limit mash_met_surf`: группа включает дополнительные `-deps` хосты. Для установки OpenCloud достаточно указанных тегов; `install-all` затронет и другие включённые приложения.

Проверка `check-opencloud` подтверждает HTTPS-статус, WOPI discovery и доступность Tika из контейнера. Полная приёмка дополнительно включает вход, загрузку/скачивание с проверкой контрольной суммы, сохранение DOCX/XLSX/PPTX и поиск фразы внутри DOCX/PDF.

Результаты установки на mash и скриншоты: [отчёт о приёмке](opencloud-acceptance.md).

## Обслуживание

```bash
just start-group opencloud --limit mash_met_surf
just stop-group opencloud --limit mash_met_surf
ssh mash 'systemctl status mash-opencloud'
ssh mash 'journalctl -u mash-opencloud --since "10 minutes ago"'
```

Команды `ssh mash` предполагают ваш SSH alias; можно использовать адрес и ключ из инвентори.

Для обновления сначала сделайте резервную копию, изучите заметки выбранной версии, измените `opencloud_version` и выполните `just install-service opencloud --limit mash_met_surf`. Изменение `opencloud_admin_password` после инициализации не сбрасывает пароль существующего пользователя.

Для ветки Rolling нужно также указать `opencloud_container_image_repository: opencloudeu/opencloud-rolling`. На mash выбран выпуск `8.0.1` этой ветки; значение роли по умолчанию остаётся Production `7.2.4`. Переход с 7.x и автоматическая переиндексация описаны в [инструкции обновления до 8.x](opencloud-upgrade-8.md).

Для согласованной резервной копии остановите группу OpenCloud, скопируйте весь `/srv/storage/opencloud` с сохранением владельцев, прав и расширенных атрибутов, затем запустите группу. Храните отдельную копию вне этого диска. Конфигурация содержит внутренние ключи: восстанавливать нужно и `config/`, и `data/` вместе.

Для восстановления остановите службу, восстановите оба каталога с владельцами, верните совместимую версию образа и запустите OpenCloud. Откат после миграции данных выполняется восстановлением согласованной копии, а не только заменой тега образа.

Для удаления службы задайте `opencloud_enabled: false` и выполните `just setup-service opencloud --limit mash_met_surf`. Данные и `config/opencloud.yaml` сохраняются. Не удаляйте каталоги, если требуется последующее восстановление.

## Основа реализации

- [Правила добавления сервисов MASH](../developer-documentation.md)
- [Стабильный пример OpenCloud](https://github.com/opencloud-eu/opencloud-compose/tree/stable-7.2)
- [Постоянные каталоги и стабильные версии](https://docs.opencloud.eu/docs/next/admin/getting-started/container/docker-compose/docker-compose-production-considerations/)
- [Пример подключения Tika](https://github.com/opencloud-eu/opencloud-compose/blob/stable-7.2/search/tika.yml)
