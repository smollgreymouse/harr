#pragma once

#include <QtCore/QDateTime>
#include <QtCore/QJsonObject>
#include <QtCore/QVector>
#include <QtCore/QSize>
#include <QtWidgets/QComboBox>
#include <QtWidgets/QDialog>
#include <QtWidgets/QTabBar>
#include <QtWidgets/QWidget>

#include <functional>

class QDateEdit;
class QDialogButtonBox;
class QLabel;
class QPushButton;
class QSpinBox;
class QToolButton;

namespace harr {

class NumberStepper : public QWidget {
public:
    NumberStepper(int minimum, int maximum, int value, QWidget *parent = nullptr);
    int value() const;
    void setValue(int value);

    QToolButton *plus{};
    QSpinBox *spin{};
    QToolButton *minus{};
};

class ScheduleTimeDialog : public QDialog {
public:
    explicit ScheduleTimeDialog(QDateTime initial, QWidget *parent = nullptr);
    QDateTime selected() const;

    QDateEdit *date{};
    NumberStepper *hours{};
    NumberStepper *minutes{};
    QPushButton *today{};
    QPushButton *tomorrow{};
    QPushButton *reset{};
    QLabel *summary{};
    QDialogButtonBox *buttons{};

private:
    void refreshSummary();
};

class SessionComboBox : public QComboBox {
public:
    explicit SessionComboBox(QWidget *parent = nullptr);

    QString sessionId() const;
    void setSessionId(const QString &id);
    void setSessions(const QVector<QJsonObject> &sessions, bool selectLatestIfEmpty);
    void setResolvedSession(const QJsonObject &session);

private:
    QString sessionTooltip(const QJsonObject &session) const;
    void normalizeEdited();

    QString m_sessionId;
    QVector<QJsonObject> m_sessions;
};

class PlusTabBar : public QTabBar {
public:
    explicit PlusTabBar(QWidget *parent = nullptr);
    std::function<void()> onPlus;
    QToolButton *plusButton{};

protected:
    void resizeEvent(QResizeEvent *event) override;
    void tabInserted(int index) override;
    void tabRemoved(int index) override;
    void tabLayoutChange() override;
    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

private:
    void positionPlus();
};

} // namespace harr
