# План: терминальная SSH-аутентификация для процессов Harr

> Статус: fallback B реализован на Linux как `harr git …` + loopback host
> service; macOS использует тот же broker через LaunchAgent. Windows требует
> отдельной проверки песочницы по `docs/windows-git-host-handoff.md`.

## Цель

Вернуть процессам, запускаемым через Harr/LeanCTX, то же поведение SSH, что у
пользовательского терминала:

- обычные `git fetch` / `git push` по SSH работают без изменения remote;
- не требуется `core.sshCommand`, `IdentityFile` или policy на уровне репозитория;
- SSH сам получает список ключей от уже запущенного пользовательского
  `ssh-agent` и выбирает подходящий ключ как в терминале;
- GitLab PAT используется GitLab MCP только для API-объектов и не подменяет
  Git-аутентификацию.

## Зафиксированные результаты проверки

| Проверка | Результат | Вывод |
| --- | --- | --- |
| Терминальный `ssh-agent` | содержит `id_rsa_github`; GitHub принимает его как `smollgreymouse` | Ключ, аккаунт и remote исправны. |
| `git push --dry-run` через `ctx_shell` | `Permission denied (publickey)` | Дочерний Git не может использовать агент. |
| `ssh-add -l` из command sandbox | `Error connecting to agent: Operation not permitted` | Переменная сокета присутствует, но подключение к upstream Unix socket запрещено sandbox. |
| Git с временным явным `IdentityFile` через `ctx_shell` | `push --dry-run` проходит | Процесс может работать с ключом, но это обход, а не требуемая терминальная модель. |
| Временный внешний Unix-socket relay к настоящему агенту | подключение из sandbox запрещено (`Operation not permitted`) | Новый внешний socket не обходит ограничение. |
| Создание Unix socket внутри command sandbox | `bind: Operation not permitted` | Нельзя создать client-side socket shim для OpenSSH. |

### Решение по реализуемости

Прозрачный SSH-agent bridge **невозможно реализовать только изменениями Harr**
при текущей sandbox policy. OpenSSH использует Unix socket для agent protocol;
sandbox запрещает и подключение к socket, и его создание. HTTP, raw TCP или
другой быстрый транспорт не могут сами стать `SSH_AUTH_SOCK`.

Следовательно, для прозрачного обычного `git push` нужен один из двух путей:

1. **Предпочтительный:** platform/runtime capability, разрешающая Unix socket
   для `SSH_AUTH_SOCK` в sandbox. Harr тогда добавляет только диагностику и
   использует уже предоставленную возможность.
2. **Реализуемый внутри Harr fallback:** отдельный host-execution broker.
   Это не передаёт agent в sandbox: Git выполняется в доверенном локальном
   сервисе, у которого есть обычный terminal environment. Для агента это
   команду `harr git …` через `ctx_shell`; она передаёт argv host broker без
   новых Git-подкоманд.

Не следует реализовывать per-repository key policy как замену этому решению.

## Целевая архитектура

### Вариант A — platform SSH-agent capability (целевое решение)

```text
Codex/LeanCTX shell sandbox
  SSH_AUTH_SOCK=/run/user/<uid>/…/agent.sock
      │  (явно разрешённый Unix socket)
      ▼
Пользовательский ssh-agent
      ▼
Ключи, уже загруженные в терминальной сессии
```

Требования к platform/runtime:

1. Наследовать актуальный `SSH_AUTH_SOCK` в процесс LeanCTX и его дочерние
   shell-процессы.
2. Разрешать `connect(2)` ровно к этому Unix socket; не включать глобальный
   доступ к произвольным Unix sockets.
3. Сохранять socket доступным после перезапуска sandbox и корректно
   обрабатывать смену socket после login/lock/unlock.
4. Документировать capability как сознательное расширение прав: код в sandbox
   сможет запрашивать подписи у всех ключей, доступных агенту, то есть получит
   те же возможности, что обычный терминал.

Изменения Harr для варианта A минимальны:

- добавить `harr ssh-agent status`, который показывает `available`,
  `unavailable`, `blocked` или `stale` без печати ключей;
- добавить диагностический тест `ssh-add -l` и, по запросу, безопасную
  проверку `git push --dry-run`;
- расширить сгенерированную policy инструкцией: когда capability доступна,
  GitHub/GitLab SSH remote обрабатываются обычным `git`, без специальных
  repo-настроек;
- GitLab MCP оставить в зоне API; Git transport не переносить в MCP.

### Вариант B — Harr host-execution broker (выбран для реализации)

```text
Agent → ctx_shell: harr git … → localhost HTTP client
                                      │
                                      ▼
                         harr-git-host user service
                                      │
                    service SSH_AUTH_SOCK + request cwd + argv
                                      │
                                      ▼
                                  real git
```

Сервис стартует один раз на пользовательскую сессию, а не для проекта. Он
использует существующий терминальный агент и не хранит ключи, токены или
список репозиториев.

API принимает структурированные поля `cwd` и `args`; строка
shell не принимается. Минимальный запрос:

```text
POST /v1/git { cwd, args: ["push", "origin", "HEAD"] }
```

Первый релиз реализует только Git. Это не policy по репозиториям: один сервис
обслуживает любые рабочие каталоги пользователя. Произвольный host shell не
добавляется.

#### Почему не HTTP proxy для SSH

HTTP может быть транспортом вызова MCP, но не заменяет SSH agent protocol.
OpenSSH ожидает `SSH_AUTH_SOCK`; в текущем sandbox нельзя создать socket shim.
Поэтому broker должен исполнять `git` вне sandbox, а не пытаться проксировать
подписи обратно в sandbox.

## План работ

### Этап 1. Ввести диагностическую модель (Linux)

1. Добавить модуль `common/ssh_agent/diagnostics.py`:
   - проверить наличие `SSH_AUTH_SOCK`;
   - отличить отсутствующий socket, недоступный socket и работающий агент;
   - не выводить содержимое ключей; для статуса достаточно количества
     identities или результата без детализации.
2. Добавить shell-команду в `common/shell/`, подключить её в Linux CLI и
   команду `harr ssh-agent status`.
3. Покрыть диагностику unit-тестами: нет переменной, отсутствующий путь,
   permission denied, доступный mock agent.
4. Добавить раздел в `README.md` и diagnostic skill: объяснить, что
   `blocked` требует platform capability или host broker, а не SSH config.

### Этап 2. Подготовить platform capability

1. Зафиксировать контракт capability с владельцем sandbox runtime: наследуемая
   переменная, разрешение на один Unix socket, жизненный цикл при смене
   пользовательской сессии.
2. После появления capability добавить integration test, который из
   `ctx_shell` запускает `ssh-add -l` через установленный `SSH_AUTH_SOCK`.
3. Добавить Git integration test с тестовым SSH endpoint или mocked agent;
   production GitHub в automated tests не использовать.
4. После успешного теста обновить policy: Git SSH не требует Harr wrapper.

### Этап 3. Реализовать host Git broker

1. Добавить обязательный per-user Git service, не смешивая его с GitLab API MCP.
2. Добавить service runtime и launcher:
   - Linux: новый systemd user unit рядом с
     `linux/systemd/harr-mcp@.service`;
   - macOS: LaunchAgent рядом с существующим MCP lifecycle;
   - Windows: отдельная задача/adapter, где используется поддерживаемый
     Windows SSH-agent transport.
3. Обеспечить корректное получение session environment. Обычный user service
   не гарантированно наследует `SSH_AUTH_SOCK`, поэтому bootstrap должен
   импортировать его из терминальной/графической сессии и проверять доступ
   перед `ready`.
4. Создать loopback-only HTTP endpoint с per-session capability secret;
   secret хранить в runtime dir с правами `0600`, не в git repo и не в MCP
   конфигурации.
5. Реализовать только выполнение `git` с argv:
   - validate `cwd` и executable;
   - передавать минимальный environment и настоящий `SSH_AUTH_SOCK`;
   - поддержать отмену, timeout, exit code и сжатый лог;
   - не поддерживать shell string, redirection или произвольный environment
     override в первом релизе.
6. Направить сетевые Git-команды через `harr git …` в глобальной policy.
7. Показывать готовность сервиса и SSH-agent через `harr status`.

### Этап 4. Интеграция Git и GitLab

1. Локальные Git-команды продолжают идти через обычный `ctx_shell`.
2. Все сетевые Git-команды идут через `harr git …` и используют терминальную
   SSH/credential-helper конфигурацию host service.
3. GitLab MCP создаёт и проверяет MR и другие API-объекты, но не публикует refs
   и не зеркалирует локальные коммиты через repository-file API.
4. Для MR использовать явный refspec
   `HEAD:refs/heads/<current-local-branch>`, проверять remote SHA и upstream.
5. Не изменять remote URL, global Git config или `.git/config` проектов.

### Этап 5. Проверки и документация

1. Unit tests framing/authentication MCP endpoint, argv validation, timeout,
   cancellation и запрет shell strings.
2. Linux integration tests с temporary `ssh-agent` и тестовым Git SSH server:
   GitHub/GitLab не требуются, приватные ключи пользователя не читаются.
3. Negative tests: service без `SSH_AUTH_SOCK`, невалидная capability,
   отключённый service, попытка вызвать неразрешённую программу.
4. Manual acceptance:
   - terminal `git push --dry-run` работает как раньше;
   - `ctx_shell` GitHub SSH push работает при platform capability либо через
     host broker;
   - GitLab PAT publication продолжает работать при выключенном агенте;
   - repo config и remote остаются неизменными.
5. Обновить `README.md`, `common/policy/tool-routing.template.md`, Harr skill,
   Linux/macOS/Windows help и clean-install tests.

## Критерии выбора

| Условие | Решение |
| --- | --- |
| Sandbox разрешил один inherited Unix socket | Вариант A; это единственный прозрачный путь для обычного `git`. |
| Platform capability недоступна, но нужен SSH Git из агента | Вариант B с `git-only` host broker. |
| Нужна автоматизация без пользовательской сессии | GitLab/GitHub HTTPS token transport, не agent bridge. |
| Нужны произвольные host commands | Только явный глобальный `terminal` режим host broker с осознанным повышением доверия. |

## Не-цели

- Не создавать policy `repo → key`.
- Не читать, копировать или сохранять приватные SSH ключи в Harr.
- Не менять `origin` и не прописывать `core.sshCommand` в проектах.
- Не заменять существующий GitLab PAT workflow.
- Не делать HTTP proxy притворяющимся `SSH_AUTH_SOCK`.
