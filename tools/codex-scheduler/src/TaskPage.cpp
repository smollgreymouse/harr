#include "TaskPage.h"
#include "AgentService.h"
#include "Common.h"
#include "Scheduler.h"
#include "TaskStore.h"
#include "Widgets.h"

#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonDocument>
#include <QtCore/QRegularExpression>
#include <QtCore/QSignalBlocker>
#include <QtCore/QTimer>
#include <QtGui/QAction>
#include <QtGui/QClipboard>
#include <QtWidgets/QApplication>
#include <QtWidgets/QComboBox>
#include <QtWidgets/QFileDialog>
#include <QtWidgets/QFrame>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QLabel>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QMenu>
#include <QtWidgets/QMessageBox>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QScrollArea>
#include <QtWidgets/QScrollBar>
#include <QtWidgets/QSizePolicy>
#include <QtWidgets/QTextEdit>
#include <QtWidgets/QToolButton>
#include <QtWidgets/QVBoxLayout>

namespace harr {

class MessageBubble final : public QFrame {
public:
    MessageBubble(const QString &role, const QString &value, const QString &agentName = {},
                  QWidget *parent = nullptr)
        : QFrame(parent)
    {
        setObjectName("messageBubble");
        setFrameShape(QFrame::NoFrame);
        setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Minimum);

        auto *layout = new QVBoxLayout(this);
        layout->setContentsMargins(12, 9, 12, 9);
        const QString assistantName = agentName.isEmpty() ? QStringLiteral("Agent") : agentName;
        auto *title = new QLabel(role == "user" ? QStringLiteral("You") : assistantName, this);
        QFont titleFont = title->font();
        titleFont.setWeight(QFont::DemiBold);
        title->setFont(titleFont);
        m_body = new QLabel(value, this);
        m_body->setWordWrap(true);
        m_body->setTextInteractionFlags(Qt::TextSelectableByMouse);
        layout->addWidget(title);
        layout->addWidget(m_body);

        QPalette palette = this->palette();
        if (role == "user") {
            palette.setColor(QPalette::Window, palette.color(QPalette::Highlight));
            palette.setColor(QPalette::WindowText, palette.color(QPalette::HighlightedText));
        } else {
            palette.setColor(QPalette::Window, palette.color(QPalette::AlternateBase));
            palette.setColor(QPalette::WindowText, palette.color(QPalette::Text));
        }
        setPalette(palette);
        setAutoFillBackground(true);
    }

    void appendText(const QString &value)
    {
        const QString current = m_body->text();
        m_body->setText(current.isEmpty() ? value : current + "\n\n" + value);
    }

private:
    QLabel *m_body{};
};

TaskPage::TaskPage(TaskStore *store, const QJsonObject &task,
                   std::function<void(const QString &)> changed,
                   ChoiceProvider modelsFor, ChoiceProvider sessionsFor,
                   QWidget *parent)
    : QWidget(parent), m_store(store), m_taskId(task.value("id").toString()),
      m_changed(std::move(changed)), m_modelsFor(std::move(modelsFor)),
      m_sessionsFor(std::move(sessionsFor))
{
    m_loading = true;

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(16, 12, 16, 12);
    root->setSpacing(10);

    auto *top = new QHBoxLayout();
    agent = new QComboBox(this);
    agent->setProperty("chromeRole", "selector");
    agent->setToolTip("Agent");
    for (const QString &id : agentIds()) addChoice(agent, agentDisplayName(id), id);

    model = new QComboBox(this);
    model->setProperty("chromeRole", "selector");
    model->setToolTip("Model");

    reasoning = new QComboBox(this);
    addChoice(reasoning, "Minimal", "minimal");
    addChoice(reasoning, "Low", "low");
    addChoice(reasoning, "Medium", "medium");
    addChoice(reasoning, "High", "high");
    addChoice(reasoning, "Extra High", "xhigh");
    reasoning->setProperty("chromeRole", "selector");
    reasoning->setToolTip("Reasoning");

    speed = new QComboBox(this);
    addChoice(speed, "Standard", "standard");
    addChoice(speed, "Fast", "fast");
    speed->setProperty("chromeRole", "selector");
    speed->setToolTip("Speed");

    mode = new QComboBox(this);
    addChoice(mode, "Build", "build");
    addChoice(mode, "Edit", "edit");
    addChoice(mode, "Plan", "plan");
    addChoice(mode, "Yolo", "yolo");
    addChoice(mode, "Guarded", "guarded");
    mode->setProperty("chromeRole", "selector");
    mode->setToolTip("Permission mode");

    status = new QLabel(this);
    status->setObjectName("taskStatus");
    top->addWidget(agent);
    top->addWidget(model);
    top->addWidget(reasoning);
    top->addWidget(speed);
    top->addWidget(mode);
    top->addStretch(1);
    top->addWidget(status);
    root->addLayout(top);

    auto *sessionRow = new QHBoxLayout();
    session = new SessionComboBox(this);
    session->setToolTip("Recent active Codex sessions; paste a session ID with Ctrl+V");
    when = new QPushButton("Run at", this);
    when->setToolTip("Choose date and time");

    m_projectButton = new QToolButton(this);
    m_projectButton->setText("⋮");
    m_projectButton->setToolTip("Session project");
    m_projectButton->setPopupMode(QToolButton::InstantPopup);
    m_projectMenu = new QMenu(m_projectButton);
    m_projectPathAction = m_projectMenu->addAction("Project: not resolved");
    m_projectPathAction->setEnabled(false);
    m_projectMenu->addSeparator();
    m_copyProjectAction = m_projectMenu->addAction("Copy project directory");
    m_copyProjectAction->setEnabled(false);
    m_refreshProjectAction = m_projectMenu->addAction("Refresh project directory");
    m_projectButton->setMenu(m_projectMenu);

    sessionRow->addWidget(session, 3);
    sessionRow->addWidget(when, 2);
    sessionRow->addWidget(m_projectButton);
    root->addLayout(sessionRow);

    prompt = new QTextEdit(this);
    prompt->setPlaceholderText("What should the agent do?");
    prompt->setMinimumHeight(100);
    root->addWidget(prompt);

    auto *actions = new QHBoxLayout();
    saveButton = new QPushButton("Save final answer…", this);
    saveButton->setCheckable(true);
    editButton = new QPushButton("Edit task", this);
    editButton->setVisible(false);
    primary = new QPushButton("Schedule", this);
    actions->addWidget(saveButton);
    actions->addStretch(1);
    actions->addWidget(editButton);
    actions->addWidget(primary);
    root->addLayout(actions);

    transcript = new QScrollArea(this);
    transcript->setWidgetResizable(true);
    m_transcriptHost = new QWidget(transcript);
    m_transcriptLayout = new QVBoxLayout(m_transcriptHost);
    m_transcriptLayout->setAlignment(Qt::AlignTop);
    m_transcriptLayout->setContentsMargins(0, 0, 0, 0);
    transcript->setWidget(m_transcriptHost);
    root->addWidget(transcript, 1);

    loadTask(task);

    connect(model, &QComboBox::currentTextChanged, this, [this] { persistDraft(); });
    connect(reasoning, &QComboBox::currentTextChanged, this, [this] { persistDraft(); });
    connect(speed, &QComboBox::currentTextChanged, this, [this] { persistDraft(); });
    connect(mode, &QComboBox::currentTextChanged, this, [this] { persistDraft(); });
    connect(agent, qOverload<int>(&QComboBox::activated), this, [this](int) {
        applyAgent(choiceValue(agent));
    });
    connect(session->lineEdit(), &QLineEdit::textEdited, this, [this] {
        invalidateCwd();
        persistDraft();
    });
    connect(session, qOverload<int>(&QComboBox::activated), this, [this](int) {
        invalidateCwd();
        persistDraft();
        QTimer::singleShot(0, this, [this] { resolveCwdPreview(); });
    });
    connect(session->lineEdit(), &QLineEdit::editingFinished, this, [this] { resolveCwdPreview(); });
    connect(prompt, &QTextEdit::textChanged, this, [this] { persistDraft(); });
    connect(when, &QPushButton::clicked, this, [this] { chooseTime(); });
    connect(saveButton, &QPushButton::clicked, this, [this](bool checked) { toggleSave(checked); });
    connect(editButton, &QPushButton::clicked, this, [this] { editScheduled(); });
    connect(primary, &QPushButton::clicked, this, [this] { primaryAction(); });
    connect(m_copyProjectAction, &QAction::triggered, this, [this] {
        if (!m_cwd.isEmpty()) QApplication::clipboard()->setText(m_cwd);
    });
    connect(m_refreshProjectAction, &QAction::triggered, this, [this] { resolveCwdPreview(); });

    m_loading = false;
    rebuildTranscript(task);
    applyStatus(task);

    pollTimer = new QTimer(this);
    pollTimer->setInterval(2500);
    connect(pollTimer, &QTimer::timeout, this, [this] { poll(); });
    pollTimer->start();
}

QString TaskPage::taskId() const { return m_taskId; }

QString TaskPage::currentAgent() const
{
    const QString id = choiceValue(agent);
    return isKnownAgent(id) ? id : defaultAgentId();
}

void TaskPage::applyAgent(const QString &agentId, bool force)
{
    const QString next = isKnownAgent(agentId) ? agentId : defaultAgentId();
    if (!force && next == currentAgent()) return;
    setChoiceValue(agent, next);
    const AgentCapabilities caps = agentService(next)->capabilities();
    model->setVisible(caps.modelSelector);
    reasoning->setVisible(caps.reasoning);
    speed->setVisible(caps.speed);
    mode->setVisible(caps.mode);
    session->setToolTip(caps.sessionSelector
        ? QString("Recent active %1 sessions; paste a session ID with Ctrl+V")
              .arg(agentDisplayName(next))
        : QString("%1 sessions are not enumerable via the public CLI yet; "
                  "paste a session ID manually").arg(agentDisplayName(next)));
    if (force) return;

    // Session ids are not portable across agents: drop the selection and
    // the project resolution, then repopulate the catalogs.
    session->setSessionId(QString{});
    invalidateCwd();
    status->setText({});
    if (m_modelsFor) setModelChoices(m_modelsFor(next));
    if (m_sessionsFor) setSessionChoices(m_sessionsFor(next), false);
    persistDraft();
}

void TaskPage::setModelChoices(const QVector<QJsonObject> &models)
{
    m_modelChoices = models;
    const auto task = currentTask();
    const QString saved = task.value("model").toString().trimmed();
    QString defaultModel;

    QString selected;
    {
        QSignalBlocker blocker(model);
        model->clear();
        for (const auto &entry : models) {
            const QString id = entry.value("model").toString(entry.value("id").toString()).trimmed();
            if (id.isEmpty() || entry.value("hidden").toBool(false)) continue;
            QString label = entry.value("displayName").toString().trimmed();
            if (label.isEmpty()) label = id;
            addChoice(model, label, id);
            const int index = model->count() - 1;
            const QString description = entry.value("description").toString().trimmed();
            if (!description.isEmpty()) model->setItemData(index, description, Qt::ToolTipRole);
            if (entry.value("isDefault").toBool(false)) defaultModel = id;
        }

        const bool savedAvailable = !saved.isEmpty()
            && model->findData(saved, Qt::UserRole) >= 0;
        const bool draft = task.value("status").toString() == "draft";
        const QString preferred = savedAvailable
            ? saved
            : (draft
                ? (!defaultModel.isEmpty()
                    ? defaultModel
                    : (model->count() > 0 ? model->itemData(0, Qt::UserRole).toString()
                                          : QString{}))
                : QString{});

        if (preferred.isEmpty()) model->setCurrentIndex(-1);
        else setChoiceValue(model, preferred);
        selected = choiceValue(model);
    }

    if (task.value("status").toString() == "draft" && saved != selected && !selected.isEmpty())
        persistDraft();
}

void TaskPage::setSessionChoices(const QVector<QJsonObject> &sessions, bool selectLatestIfEmpty)
{
    const auto task = currentTask();
    const bool shouldSelect = selectLatestIfEmpty
        && task.value("status").toString() == "draft"
        && session->sessionId().isEmpty();
    session->setSessions(sessions, shouldSelect);
    if (shouldSelect && !session->sessionId().isEmpty()) {
        persistDraft();
        QTimer::singleShot(0, this, [this] { resolveCwdPreview(); });
    }
}

void TaskPage::refreshFromStore()
{
    const auto task = currentTask();
    const QString state = task.value("status").toString();
    bool changed = state != m_lastStatus;

    const QString logPath = task.value("log").toString();
    if (!logPath.isEmpty()) {
        QFileInfo info(logPath);
        if (info.exists() && info.size() != m_lastLogSize) changed = true;
    }

    if (!changed) return;
    applyStatus(task);
    rebuildTranscript(task);
}

void TaskPage::addChoice(QComboBox *combo, const QString &label, const QString &value)
{
    combo->addItem(label, value);
}

QString TaskPage::choiceValue(QComboBox *combo)
{
    return combo->currentData(Qt::UserRole).toString();
}

void TaskPage::setChoiceValue(QComboBox *combo, const QString &value)
{
    const int index = combo->findData(value, Qt::UserRole);
    if (index >= 0) combo->setCurrentIndex(index);
}

QJsonObject TaskPage::currentTask() const
{
    return m_store->load(m_taskId).value_or(QJsonObject{{"id", m_taskId}, {"status", "failed"}});
}

void TaskPage::loadTask(const QJsonObject &task)
{
    setChoiceValue(agent, task.value("agent").toString(defaultAgentId()));
    setChoiceValue(reasoning, task.value("reasoning").toString("high"));
    setChoiceValue(speed, task.value("speed").toString("standard"));
    setChoiceValue(mode, task.value("mode").toString("yolo"));
    session->setSessionId(task.value("session").toString());
    prompt->setPlainText(task.value("prompt").toString());
    m_cwd = task.value("cwd").toString();
    m_answer = task.value("answer").toString();
    m_log = task.value("log").toString();
    m_lastStatus = task.value("status").toString();

    const QString scheduled = task.value("scheduled").toString();
    if (!scheduled.isEmpty()) m_scheduled = QDateTime::fromString(scheduled, Qt::ISODate);
    if (!m_scheduled.isValid() && task.value("status").toString() == "draft") m_scheduled = defaultRunTime();
    refreshWhen();
    setSaveState(m_answer);
    if (!m_cwd.isEmpty()) setCwd(m_cwd);
    applyAgent(currentAgent(), true);
}

void TaskPage::persistDraft()
{
    if (m_loading || currentTask().value("status").toString() != "draft") return;
    QJsonObject patch{
        {"agent", currentAgent()},
        {"model", choiceValue(model)},
        {"reasoning", choiceValue(reasoning)},
        {"speed", choiceValue(speed)},
        {"mode", choiceValue(mode)},
        {"session", session->sessionId()},
        {"prompt", prompt->toPlainText()}
    };
    patch.insert("scheduled", m_scheduled.isValid() ? QJsonValue(m_scheduled.toString(Qt::ISODate)) : QJsonValue(QJsonValue::Null));
    patch.insert("cwd", m_cwd.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(m_cwd));
    patch.insert("answer", m_answer.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(m_answer));
    m_store->patch(m_taskId, patch);
    if (m_changed) m_changed(m_taskId);
}

void TaskPage::chooseTime()
{
    if (currentTask().value("status").toString() != "draft") return;
    ScheduleTimeDialog dialog(m_scheduled.isValid() ? m_scheduled : defaultRunTime(), this);
    if (dialog.exec() != QDialog::Accepted) return;
    m_scheduled = dialog.selected();
    refreshWhen();
    persistDraft();
}

void TaskPage::refreshWhen()
{
    when->setText(m_scheduled.isValid() ? m_scheduled.toString("dd.MM.yyyy  HH:mm") : "Run at");
}

void TaskPage::invalidateCwd()
{
    m_cwd.clear();
    m_projectPathAction->setText("Project: not resolved");
    m_copyProjectAction->setEnabled(false);
    m_projectButton->setToolTip("Session project");
}

void TaskPage::setCwd(const QString &cwd)
{
    m_cwd = cwd;
    m_projectPathAction->setText("Project: " + cwd);
    m_copyProjectAction->setEnabled(true);
    m_projectButton->setToolTip(cwd);
}

void TaskPage::resolveCwdPreview()
{
    if (currentTask().value("status").toString() != "draft") return;
    const QString id = session->sessionId();
    if (id.isEmpty()) {
        invalidateCwd();
        return;
    }

    QString error;
    AgentService *service = agentService(currentAgent());
    if (!service) {
        invalidateCwd();
        return;
    }
    auto sessionInfo = service->readSession(id, &error);
    if (!sessionInfo) {
        invalidateCwd();
        status->setText(error.left(180));
        return;
    }

    session->setResolvedSession(*sessionInfo);

    auto cwd = service->validateSessionCwd(*sessionInfo, &error, true);
    if (!cwd) {
        invalidateCwd();
        status->setText(error.left(180));
        return;
    }
    setCwd(*cwd);
    persistDraft();
    status->setText("✓ Project verified");
}

QString TaskPage::defaultAnswerPath() const
{
    QString safe = session->sessionId();
    safe.replace(QRegularExpression("[^A-Za-z0-9._-]+"), "-");
    safe = safe.trimmed();
    if (safe.isEmpty()) safe = "session";
    const QString directory = m_cwd.isEmpty() ? QDir::currentPath() : m_cwd;
    const auto time = m_scheduled.isValid() ? m_scheduled : QDateTime::currentDateTime();
    QString path = QDir(directory).filePath(QString("%1-%2-%3.md").arg(currentAgent(), safe, time.toString("yyyyMMdd-HHmm")));
    if (!QFileInfo::exists(path)) return path;
    QFileInfo info(path);
    for (int i = 2; ; ++i) {
        const QString suffix = info.suffix().isEmpty() ? QString{} : "." + info.suffix();
        const QString candidate = info.dir().filePath(info.completeBaseName() + QString("-%1").arg(i) + suffix);
        if (!QFileInfo::exists(candidate)) return candidate;
    }
}

void TaskPage::setSaveState(const QString &path)
{
    m_answer = path;
    QSignalBlocker blocker(saveButton);
    saveButton->setChecked(!path.isEmpty());
    if (path.isEmpty()) {
        saveButton->setText("Save final answer…");
        saveButton->setToolTip("Choose a file and enable answer export");
    } else {
        saveButton->setText("✓ " + QFileInfo(path).fileName());
        saveButton->setToolTip(path);
    }
}

void TaskPage::toggleSave(bool checked)
{
    if (currentTask().value("status").toString() != "draft") {
        saveButton->setChecked(!m_answer.isEmpty());
        return;
    }
    if (!checked) {
        setSaveState({});
        persistDraft();
        return;
    }
    const QString path = QFileDialog::getSaveFileName(
        this, QString("Save %1 answer").arg(agentDisplayName(currentAgent())), defaultAnswerPath(),
        "Markdown (*.md);;Text (*.txt);;All files (*)");
    if (path.isEmpty()) {
        setSaveState({});
        return;
    }
    setSaveState(path);
    persistDraft();
}

void TaskPage::editScheduled()
{
    QString error;
    const auto task = m_store->reopenScheduled(m_taskId, &error);
    if (!error.isEmpty()) {
        QMessageBox::warning(this, APP_NAME, error);
        refreshFromStore();
        return;
    }

    if (!m_modelChoices.isEmpty()) setModelChoices(m_modelChoices);
    applyStatus(task);
    rebuildTranscript(task);
    if (m_changed) m_changed(m_taskId);
}

void TaskPage::primaryAction()
{
    const QString state = currentTask().value("status").toString();
    if (state == "draft") schedule();
    else if (state == "scheduled" || state == "running" || state == "cancelling") cancel();
}

void TaskPage::schedule()
{
    const QString agentId = currentAgent();
    AgentService *service = agentService(agentId);
    const AgentCapabilities caps = service ? service->capabilities() : AgentCapabilities{};
    const QString id = session->sessionId();
    const QString text = prompt->toPlainText().trimmed();
    if (text.isEmpty() || (caps.sessionRequired && id.isEmpty())) {
        QMessageBox::warning(this, APP_NAME,
                             caps.sessionRequired ? "Session and prompt are required."
                                                  : "Prompt is required.");
        return;
    }
    if (!caps.sessionRequired && caps.mode && m_cwd.isEmpty()) {
        // Without a public session API there is no verified project
        // directory; scheduling stays explicitly blocked in the GUI.
        QMessageBox::warning(
            this, APP_NAME,
            QString("%1 sessions are not enumerable via the public CLI yet, so no project "
                    "directory can be verified here.\nSchedule %1 turns from the terminal "
                    "with `harr-schedule --agent %2 --cwd ...`.")
                .arg(agentDisplayName(agentId), agentId));
        return;
    }
    if (caps.modelRequired && choiceValue(model).isEmpty()) {
        QMessageBox::warning(this, APP_NAME,
                             QString("No %1 model is available.").arg(agentDisplayName(agentId)));
        return;
    }
    if (!m_scheduled.isValid()) {
        QMessageBox::warning(this, APP_NAME, "Choose a run time first.");
        return;
    }

    const QString logPath = currentTask().value("log").toString(QDir(m_store->jobsDir()).filePath(m_taskId + ".jsonl"));
    ScheduleRequest req;
    req.agent = agentId;
    req.model = choiceValue(model);
    req.reasoning = choiceValue(reasoning);
    req.speed = choiceValue(speed);
    req.mode = caps.mode ? choiceValue(mode) : QString{};
    req.timestamp = m_scheduled.toString("yyyyMMddHHmm");
    req.session = id;
    req.prompt = text;
    req.logJson = logPath;
    req.taskState = m_store->taskPath(m_taskId);
    req.saveAnswer = m_answer;

    const ScheduleResult result = scheduleJob(req);
    if (!result.ok) {
        QMessageBox::critical(this, APP_NAME, result.output);
        return;
    }

    m_cwd = result.cwd;
    m_log = logPath;
    setCwd(m_cwd);
    QJsonObject patch{
        {"status", "scheduled"}, {"agent", agentId}, {"model", req.model},
        {"reasoning", req.reasoning}, {"speed", req.speed}, {"mode", req.mode},
        {"session", id}, {"prompt", text},
        {"scheduled", m_scheduled.toString(Qt::ISODate)}, {"cwd", m_cwd},
        {"log", m_log}, {"cancel_requested", false}, {"error", QJsonValue::Null}
    };
    patch.insert("at_job", result.jobId.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(result.jobId));
    patch.insert("answer", m_answer.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(m_answer));
    const auto task = m_store->patch(m_taskId, patch);
    rebuildTranscript(task);
    applyStatus(task);
    if (m_changed) m_changed(m_taskId);
}

void TaskPage::cancel()
{
    const QString state = currentTask().value("status").toString();
    if (state != "scheduled" && state != "running" && state != "cancelling") return;
    if (QMessageBox::question(this, APP_NAME,
                              QString("Cancel this %1 task?").arg(agentDisplayName(currentAgent())),
                              QMessageBox::Yes | QMessageBox::No, QMessageBox::No) != QMessageBox::Yes) return;
    QString error;
    const auto task = m_store->cancel(m_taskId, &error);
    if (!error.isEmpty()) {
        QMessageBox::critical(this, APP_NAME, error);
        return;
    }
    applyStatus(task);
    if (m_changed) m_changed(m_taskId);
}

void TaskPage::rebuildTranscript(const QJsonObject &task)
{
    while (m_transcriptLayout->count() > 0) {
        auto *item = m_transcriptLayout->takeAt(0);
        if (auto *widget = item->widget()) widget->deleteLater();
        delete item;
    }

    MessageBubble *assistant = nullptr;
    const QString agentName = agentDisplayName(task.value("agent").toString(defaultAgentId()));
    const QString taskPrompt = task.value("prompt").toString().trimmed();
    if (task.value("status").toString() != "draft" && !taskPrompt.isEmpty()) {
        m_transcriptLayout->addWidget(new MessageBubble("user", taskPrompt, agentName, m_transcriptHost));
    }

    const QString logPath = task.value("log").toString();
    if (!logPath.isEmpty()) {
        QFile file(logPath);
        if (file.open(QIODevice::ReadOnly | QIODevice::Text)) {
            while (!file.atEnd()) {
                const QByteArray line = file.readLine();
                for (const auto &event : parseCodexJsonLine(line)) {
                    if (event.kind == "assistant") {
                        if (!assistant) {
                            assistant = new MessageBubble("assistant", event.text, agentName, m_transcriptHost);
                            m_transcriptLayout->addWidget(assistant);
                        } else {
                            assistant->appendText(event.text);
                        }
                    } else if (event.kind == "error") {
                        m_transcriptLayout->addWidget(new MessageBubble("assistant", event.text, agentName, m_transcriptHost));
                    }
                }
            }
            m_lastLogSize = file.size();
        }
    }
    m_transcriptLayout->addStretch(1);
    QTimer::singleShot(0, this, [this] {
        transcript->verticalScrollBar()->setValue(transcript->verticalScrollBar()->maximum());
    });
}

void TaskPage::poll()
{
    const auto task = currentTask();
    const QString state = task.value("status").toString();
    bool changed = state != m_lastStatus;

    const QString logPath = task.value("log").toString();
    if (!logPath.isEmpty()) {
        QFileInfo info(logPath);
        if (info.exists() && info.size() != m_lastLogSize) changed = true;
    }

    if (changed) {
        applyStatus(task);
        rebuildTranscript(task);
        if (m_changed) m_changed(m_taskId);
    }
}

void TaskPage::applyStatus(const QJsonObject &task)
{
    const QString state = task.value("status").toString("draft");
    m_lastStatus = state;
    status->setText(statusIcon(state) + " " + statusText(state));
    const bool editable = state == "draft";
    const QVector<QWidget *> widgets{
        agent, model, reasoning, speed, mode, session, prompt, when, saveButton
    };
    for (QWidget *widget : widgets) widget->setEnabled(editable);
    m_projectButton->setEnabled(true);

    editButton->setVisible(state == "scheduled");

    if (state == "draft") {
        primary->setText("Schedule");
        primary->setEnabled(true);
    } else if (state == "scheduled" || state == "running") {
        primary->setText("Cancel task");
        primary->setEnabled(true);
    } else if (state == "cancelling") {
        primary->setText("Cancelling…");
        primary->setEnabled(false);
    } else {
        primary->setText(statusText(state));
        primary->setEnabled(false);
    }
}

} // namespace harr
