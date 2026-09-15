#include "QuickSchedule.h"
#include "Common.h"
#include "Scheduler.h"
#include "TaskStore.h"
#include "Widgets.h"

#include <QtCore/QDir>
#include <QtWidgets/QDialogButtonBox>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QLabel>
#include <QtWidgets/QMessageBox>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QTextEdit>
#include <QtWidgets/QVBoxLayout>

namespace harr {

QuickScheduleDialog::QuickScheduleDialog(TaskStore *store, const QJsonObject &session,
                                         QWidget *parent)
    : QDialog(parent), m_store(store), m_session(session), m_when(defaultRunTime())
{
    setWindowTitle("Schedule Codex task");
    setModal(true);
    resize(460, 280);

    auto *root = new QVBoxLayout(this);
    root->setContentsMargins(14, 14, 14, 14);
    root->setSpacing(10);

    auto *title = new QLabel(sessionTitle(m_session), this);
    QFont font = title->font();
    font.setBold(true);
    title->setFont(font);
    QStringList tip{m_session.value("id").toString()};
    if (!m_session.value("cwd").toString().isEmpty()) tip << m_session.value("cwd").toString();
    title->setToolTip(tip.join('\n'));
    root->addWidget(title);

    auto *timeRow = new QHBoxLayout();
    timeRow->addWidget(new QLabel("Run at", this));
    m_whenButton = new QPushButton(this);
    timeRow->addWidget(m_whenButton, 1);
    root->addLayout(timeRow);

    m_prompt = new QTextEdit(this);
    m_prompt->setPlaceholderText("What should Codex do?");
    m_prompt->setMinimumHeight(130);
    root->addWidget(m_prompt, 1);

    m_buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
    m_buttons->button(QDialogButtonBox::Ok)->setText("Schedule");
    root->addWidget(m_buttons);

    connect(m_whenButton, &QPushButton::clicked, this, [this] {
        ScheduleTimeDialog dialog(m_when, this);
        if (dialog.exec() == QDialog::Accepted) {
            m_when = dialog.selected();
            refreshWhen();
        }
    });
    connect(m_buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    connect(m_buttons, &QDialogButtonBox::accepted, this, [this] { scheduleNow(); });

    refreshWhen();
    m_prompt->setFocus();
}

QJsonObject QuickScheduleDialog::scheduledTask() const { return m_task; }

void QuickScheduleDialog::refreshWhen()
{
    m_whenButton->setText(m_when.toString("dd.MM.yyyy  HH:mm"));
}

void QuickScheduleDialog::scheduleNow()
{
    const QString sessionId = m_session.value("id").toString().trimmed();
    const QString prompt = m_prompt->toPlainText().trimmed();
    if (sessionId.isEmpty() || prompt.isEmpty()) {
        QMessageBox::warning(this, APP_NAME, "Session and prompt are required.");
        return;
    }

    QJsonObject task = m_store->newDraft();
    const QString taskId = task.value("id").toString();
    const QString logPath = task.value("log").toString();

    ScheduleRequest req;
    req.model = "gpt-5.6-terra";
    req.reasoning = "high";
    req.speed = "standard";
    req.timestamp = m_when.toString("yyyyMMddHHmm");
    req.session = sessionId;
    req.prompt = prompt;
    req.logJson = logPath;
    req.taskState = m_store->taskPath(taskId);

    const ScheduleResult result = scheduleJob(req);
    if (!result.ok) {
        m_store->remove(taskId, true, false, nullptr);
        QMessageBox::critical(this, APP_NAME, result.output);
        return;
    }

    QJsonObject patch{
        {"status", "scheduled"}, {"model", req.model}, {"reasoning", req.reasoning},
        {"speed", req.speed}, {"session", sessionId}, {"prompt", prompt},
        {"scheduled", m_when.toString(Qt::ISODate)}, {"cwd", result.cwd},
        {"log", logPath}, {"answer", QJsonValue::Null}, {"cancel_requested", false},
        {"error", QJsonValue::Null}
    };
    patch.insert("at_job", result.jobId.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(result.jobId));
    m_task = m_store->patch(taskId, patch);
    accept();
}

} // namespace harr
