#pragma once

#include <QtCore/QDateTime>
#include <QtCore/QJsonObject>
#include <QtWidgets/QDialog>

class QDialogButtonBox;
class QPushButton;
class QTextEdit;

namespace harr {
class TaskStore;

class QuickScheduleDialog : public QDialog {
public:
    QuickScheduleDialog(TaskStore *store, const QJsonObject &session, QWidget *parent = nullptr);
    QJsonObject scheduledTask() const;

private:
    void scheduleNow();
    void refreshWhen();

    TaskStore *m_store{};
    QJsonObject m_session;
    QJsonObject m_task;
    QDateTime m_when;
    QPushButton *m_whenButton{};
    QTextEdit *m_prompt{};
    QDialogButtonBox *m_buttons{};
};
} // namespace harr
