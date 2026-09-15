#pragma once

#include <QtCore/QDateTime>
#include <QtCore/QJsonObject>
#include <QtCore/QVector>
#include <QtWidgets/QWidget>

#include <functional>

class QAction;
class QComboBox;
class QLabel;
class QMenu;
class QPushButton;
class QTextEdit;
class QTimer;
class QToolButton;

namespace harr {

class SessionComboBox;
class TaskStore;

class TaskPage : public QWidget {
    Q_OBJECT
public:
    TaskPage(TaskStore *store, const QJsonObject &task,
             std::function<void(const QString &)> changed,
             QWidget *parent = nullptr);

    QString taskId() const;
    void setSessionChoices(const QVector<QJsonObject> &sessions, bool selectLatestIfEmpty);
    void refreshFromStore();

private:
    static void addChoice(QComboBox *combo, const QString &label, const QString &value);
    static QString choiceValue(QComboBox *combo);
    static void setChoiceValue(QComboBox *combo, const QString &value);

    QJsonObject currentTask() const;
    void loadTask(const QJsonObject &task);
    void persistDraft();
    void chooseTime();
    void refreshWhen();
    void invalidateCwd();
    void setCwd(const QString &cwd);
    void resolveCwdPreview();
    QString defaultAnswerPath() const;
    void setSaveState(const QString &path);
    void toggleSave(bool checked);
    void primaryAction();
    void schedule();
    void cancel();
    void rebuildTranscript(const QJsonObject &task);
    void poll();
    void applyStatus(const QJsonObject &task);

    TaskStore *m_store{};
    QString m_taskId;
    std::function<void(const QString &)> m_changed;
    bool m_loading = false;
    QString m_cwd;
    QString m_answer;
    QString m_log;
    QString m_lastStatus;
    QDateTime m_scheduled;
    qint64 m_lastLogSize = -1;

public:
    QComboBox *model{};
    QComboBox *reasoning{};
    QComboBox *speed{};
    QLabel *status{};
    SessionComboBox *session{};
    QPushButton *when{};
    QTextEdit *prompt{};
    QPushButton *saveButton{};
    QPushButton *primary{};
    QTextEdit *transcript{};
    QTimer *pollTimer{};

private:
    QToolButton *m_projectButton{};
    QMenu *m_projectMenu{};
    QAction *m_projectPathAction{};
    QAction *m_copyProjectAction{};
    QAction *m_refreshProjectAction{};
};

} // namespace harr
