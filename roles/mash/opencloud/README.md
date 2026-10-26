<!-- SPDX-FileCopyrightText: 2026 MASH project contributors -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# OpenCloud для MASH

Локальная роль запускает [OpenCloud](https://github.com/opencloud-eu/opencloud) в Docker под управлением systemd. Поддерживает встроенные учётные записи, внешний офисный редактор WOPI и Apache Tika.

[Настройка роли](docs/configuring-opencloud.md) · [Интеграция с MASH](../../../components/opencloud/README.md)

Роль основана на структуре `ansible-role-readeck` проекта MASH. Требует `systemd_docker_base`; в MASH подключается через `components/opencloud/component.yml`, `wiring.yml` и `with/`. Исходники находятся внутри форка, поэтому `just roles` их не перезаписывает.
