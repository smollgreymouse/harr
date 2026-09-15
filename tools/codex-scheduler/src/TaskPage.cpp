#include "TaskPage.h"
#include "CodexService.h"
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
#include <QtGui/QTextCursor>
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
#include <QtWidgets/QTextEdit>
#include <QtWidgets/QToolButton>
#include <QtWidgets/QVBoxLayout>

namespace harr {

TaskPage::TaskPage(TaskStore *store, const QJsonObject &task,
                   std::function<void(const QString &)> changed,
                   QWidget *parent)
    : QWidget(parent), m_store(store), m_taskId(task.value("id").toString()), m_changed(std::move(changed))
{
    m_loading = true;

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(16, 12, 16, 12);
    root->setSpacing(10);

    auto *top = new QHBoxLayout();
    model = new QComboBox(this);
    addChoice(model, "Sol", "gpt-5.6-sol");
    addChoice(model, "Terra", "gpt-5.6-terra");
    addChoice(model, "Luna", "gpt-5.6-luna");
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

    status = new QLabel(this);
    top->addWidget(model);
    top->addWidget(reasoning);
    top->addWidget(speed);
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
    prompt->setPlaceholderText("What should Codex do?");
    prompt->setMinimumHeight(100);
    root->addWidget(prompt);

    auto *actions = new QHBoxLayout();
    saveButton = new QPushButton("Save final answer…", this);
    saveButton->setCheckable(true);
    primary = new QPushButton("Schedule", this);
    actions->addWidget(saveButton);
    actions->addStretch(1);
    actions->addWidget(primary);
    root->addLayout(actions);

    transcript = new QTextEdit(this);
    transcript->setReadOnly(true);
    transcript->setFrameShape(QFrame::NoFrame);
    transcript->setPlaceholderText("Task output will appear here");
    root->addWidget(transcript, 1);

    loadTask(task);

    connect(model, &QComboBox::currentTextChanged, this, [this] { persistDraft(); });
    connect(reasoning, &QComboBox::currentTextChanged, this, [this] { persistDraft(); });
    connect(speed, &QComboBox::currentTextChanged, this, [this] { persistDraft(); });
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
    applyStatus(task);
    rebuildTranscript(task);
    if (m_changed) m_changed(m_taskId);
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
    setChoiceValue(model, task.value("model").toString("gpt-5.6-terra"));
    setChoiceValue(reasoning, task.value("reasoning").toString("high"));
    setChoiceValue(speed, task.value("speed").toString("standard"));
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
}

void TaskPage::persistDraft()
{
    if (m_loading || currentTask().value("status").toString() != "draft") return;
    QJsonObject patch{
        {"model", choiceValue(model)},
        {"reasoning", choiceValue(reasoning)},
        {"speed", choiceValue(speed)},
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
    auto thread = CodexService::readThread(id, &error);
    if (!thread) {
        invalidateCwd();
        status->setText(error.left(180));
        return;
    }

    session->setResolvedSession(QJsonObject{
        {"id", id}, {"name", thread->value("name")}, {"preview", thread->value("preview")},
        {"cwd", thread->value("cwd")}, {"archived", thread->value("archived")}
    });

    auto cwd = CodexService::validateThreadCwd(*thread, &error, true);
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
    QString path = QDir(directory).filePath(QString("codex-%1-%2.md").arg(safe, time.toString("yyyyMMdd-HHmm")));
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
    const QString path = QFileDialog::getSaveFileName(this, "Save Codex answer", defaultAnswerPath(),
                                                      "Markdown (*.md);;Text (*.txt);;All files (*)");
    if (path.isEmpty()) {
        setSaveState({});
        return;
    }
    setSaveState(path);
    persistDraft();
}

void TaskPage::primaryAction()
{
    const QString state = currentTask().value("status").toString();
    if (state == "draft") schedule();
    else if (state == "scheduled" || state == "running" || state == "cancelling") cancel();
}

void TaskPage::schedule()
{
    const QString id = session->sessionId();
    const QString text = prompt->toPlainText().trimmed();
    if (id.isEmpty() || text.isEmpty()) {
        QMessageBox::warning(this, APP_NAME, "Session and prompt are required.");
        return;
    }
    if (!m_scheduled.isValid()) {
        QMessageBox::warning(this, APP_NAME, "Choose a run time first.");
        return;
    }

    const QString logPath = currentTask().value("log").toString(QDir(m_store->jobsDir()).filePath(m_taskId + ".jsonl"));
    ScheduleRequest req;
    req.model = choiceValue(model);
    req.reasoning = choiceValue(reasoning);
    req.speed = choiceValue(speed);
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
        {"status", "scheduled"}, {"model", req.model}, {"reasoning", req.reasoning},
        {"speed", req.speed}, {"session", id}, {"prompt", text},
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
    if (QMessageBox::question(this, APP_NAME, "Cancel this Codex task?",
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
    QString text;
    const QString taskPrompt = task.value("prompt").toString().trimmed();
    if (task.value("status").toString() != "draft" && !taskPrompt.isEmpty()) {
        text += "You\n" + taskPrompt + "\n\n";
    }

    const QString logPath = task.value("log").toString();
    if (!logPath.isEmpty()) {
        QFile file(logPath);
        if (file.open(QIODevice::ReadOnly | QIODevice::Text)) {
            while (!file.atEnd()) {
                const QByteArray line = file.readLine();
                for (const auto &event : parseCodexJsonLine(line)) {
                    if (event.kind == "assistant") text += "Codex\n" + event.text + "\n\n";
                    else if (event.kind == "error") text += "Error\n" + event.text + "\n\n";
                }
            }
            m_lastLogSize = file.size();
        }
    }
    transcript->setPlainText(text.trimmed());
    QTextCursor cursor = transcript->textCursor();
    cursor.movePosition(QTextCursor::End);
    transcript->setTextCursor(cursor);
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
        model, reasoning, speed, session, prompt, when, saveButton
    };
    for (QWidget *widget : widgets) widget->setEnabled(editable);
    m_projectButton->setEnabled(true);

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
