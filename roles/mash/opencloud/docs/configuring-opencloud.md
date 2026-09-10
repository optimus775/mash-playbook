<!-- SPDX-FileCopyrightText: 2026 MASH project contributors -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# Настройка OpenCloud

Полная инструкция для этого форка: [OpenCloud в MASH](../../../../docs/services/opencloud.md).

Основные переменные перечислены в [defaults/main.yml](../defaults/main.yml). В самостоятельном окружении задайте `opencloud_enabled`, UID/GID, HTTPS-домен, пароль администратора и настройки `systemd_docker_base`.

| Переменная | Назначение |
| --- | --- |
| `opencloud_enabled` | Установка службы; по умолчанию `false` |
| `opencloud_version` | Зафиксированная версия стабильного образа |
| `opencloud_hostname` | Домен без протокола и пути |
| `opencloud_base_path` | Общий каталог файлов роли |
| `opencloud_config_path`, `opencloud_data_path` | Постоянная конфигурация и данные |
| `opencloud_required_mount_path` | Необязательная точка монтирования; установка и запуск запрещены, если она не смонтирована |
| `opencloud_admin_password` | Начальный пароль встроенного администратора |
| `opencloud_collaboration_enabled` | Встроенная служба `collaboration` |
| `opencloud_collaboration_app_url` | HTTPS-адрес редактора |
| `opencloud_collaboration_app_name`, `opencloud_collaboration_app_product` | Имя в реестре и тип WOPI-приложения; по умолчанию `EuroOffice`, `OnlyOffice` |
| `opencloud_search_enabled`, `opencloud_search_tika_url` | Полнотекстовый поиск через Tika |
| `opencloud_smtp_*` | Параметры SMTP-уведомлений |
| `opencloud_environment_variables_additional_variables` | Дополнительные строки `KEY=value` |

В MASH подключения к EuroOffice, Tika и Exim relay определяются из настроек этих сервисов на том же хосте. Для внешних экземпляров явно задайте адреса и дополнительные Docker-сети при необходимости.

`opencloud init` запускается только при отсутствии `config/opencloud.yaml`. Ошибка инициализации останавливает установку. Файл с внутренними секретами не управляется шаблоном и не перезаписывается при обновлении. Пароль в инвентори применяется только при первом создании администратора; последующая смена пароля выполняется средствами OpenCloud.

Теги: `install-opencloud`, `setup-opencloud`, `check-opencloud`. Проверку выполняйте отдельным вызовом после запуска службы. `setup-opencloud` при выключенном сервисе удаляет unit, вспомогательные env/labels и сеть, сохраняя конфигурацию и пользовательские данные.
