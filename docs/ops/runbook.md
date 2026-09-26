# Показун — runbook

## Первинне налаштування VPS

1. Docker Engine + Compose plugin; `systemctl enable --now docker` (автостарт після перезавантаження).
2. SSH лише за ключами; `PasswordAuthentication no`.
3. `docker network create pokazun-edge`
4. `git clone https://github.com/Vnedrenec/pokazun.git /opt/pokazun/src`
5. `/opt/pokazun/prod/.env` і `/opt/pokazun/staging/.env` за шаблоном `.env.example`; `chmod 600`.
   - prod: `POKAZUN_ENV=prod`, `COMPOSE_PROFILES=backup`, `BACKUP_REMOTE` + `RCLONE_CONFIG_*`, `POKAZUN_ALERT_CHAT_ID`.
   - staging: власний bot token, власний `POSTGRES_PASSWORD`, `POKAZUN_ALLOWED_USER_IDS`.
   - `POKAZUN_WEBHOOK_SECRET`: `openssl rand -hex 32`.
6. `docker compose -f /opt/pokazun/src/deploy/proxy/compose.yml up -d`

## Деплой

```bash
/opt/pokazun/src/deploy/deploy.sh staging origin/main   # 1. staging
# 2. smoke test у staging-боті вручну (сценарії поточного етапу)
/opt/pokazun/src/deploy/deploy.sh prod <той-самий-sha>  # 3. prod
```

## Перевірки після першого розгортання

- [ ] `curl https://bot.praktik.cn.ua/healthz` → 200, `"db": "ok"`.
- [ ] `docker compose ... ps`: db, bot, worker, backup — `running`/`healthy`.
- [ ] Порт 5432 закритий ззовні: `nc -zv <vps-ip> 5432` з іншої машини → відмова.
- [ ] Тестовий алерт доходить у «Парсер + Показун» (зупинити `bot` 3 рази поспіль за 10 хв або дочекатися `backup_freshness`).
- [ ] Ручний запуск backup: `docker compose ... --profile backup run --rm backup /usr/local/bin/backup.sh`; файл є локально і в `BACKUP_REMOTE`.
- [ ] `deploy/restore-test.sh prod` → `restore test OK`. Повторювати щомісяця.
- [ ] `sudo reboot` → через 2 хв усі сервіси знову `running`, `/healthz` 200.
- [ ] staging-бот не відповідає користувачу поза allowlist.

## Логи

- Файли: volume `logs` → `/var/log/pokazun/{bot,worker}.log`, ротація щодоби, 45 днів.
- `docker compose ... logs -f bot` — поточний stdout.

## Відкат

`deploy/deploy.sh prod <попередній-sha>`. Якщо нова міграція несумісна зі старим кодом — перед відкатом `docker compose ... --profile migrate run --rm migrate alembic downgrade <revision>` (лише після ручного backup).
