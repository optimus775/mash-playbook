<!-- SPDX-FileCopyrightText: 2026 MASH project contributors -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# OpenCloud для MASH

Локальная роль запускает [OpenCloud](https://github.com/opencloud-eu/opencloud) в Docker под управлением systemd. Поддерживает встроенные учётные записи, внешний офисный редактор WOPI и Apache Tika.

[Настройка роли](docs/configuring-opencloud.md) · [Интеграция с MASH](../../../docs/services/opencloud.md)

Роль основана на структуре `ansible-role-readeck` проекта MASH. Требует `systemd_docker_base`; в MASH подключается через `templates/setup.yml` и `templates/group_vars_mash_servers`. Исходники находятся внутри форка, поэтому `just roles` их не перезаписывает.
