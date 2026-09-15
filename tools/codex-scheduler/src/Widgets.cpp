#include "Widgets.h"
#include "Common.h"

#include <QtCore/QFileInfo>
#include <QtCore/QSignalBlocker>
#include <QtGui/QResizeEvent>
#include <QtWidgets/QAbstractSpinBox>
#include <QtWidgets/QCalendarWidget>
#include <QtWidgets/QDateEdit>
#include <QtWidgets/QDialogButtonBox>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QLabel>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QMessageBox>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QSizePolicy>
#include <QtWidgets/QSpinBox>
#include <QtWidgets/QToolButton>
#include <QtWidgets/QVBoxLayout>

namespace harr {

NumberStepper::NumberStepper(int minimum, int maximum, int value, QWidget *parent) : QWidget(parent)
{
    setFixedWidth(54);
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(2);

    plus = new QToolButton(this);
    plus->setText("+");
    plus->setToolTip("Increase");
    plus->setFixedSize(54, 26);

    spin = new QSpinBox(this);
    spin->setRange(minimum, maximum);
    spin->setValue(value);
    spin->setWrapping(true);
    spin->setReadOnly(true);
    spin->setAlignment(Qt::AlignCenter);
    spin->setButtonSymbols(QAbstractSpinBox::NoButtons);
    spin->setFixedSize(54, 30);

    minus = new QToolButton(this);
    minus->setText("−");
    minus->setToolTip("Decrease");
    minus->setFixedSize(54, 26);

    connect(plus, &QToolButton::clicked, spin, &QSpinBox::stepUp);
    connect(minus, &QToolButton::clicked, spin, &QSpinBox::stepDown);
    layout->addWidget(plus);
    layout->addWidget(spin);
    layout->addWidget(minus);
}

int NumberStepper::value() const { return spin->value(); }
void NumberStepper::setValue(int value) { spin->setValue(value); }

ScheduleTimeDialog::ScheduleTimeDialog(QDateTime initial, QWidget *parent) : QDialog(parent)
{
    setWindowTitle("Choose run time");
    setModal(true);
    setMinimumWidth(330);
    if (!initial.isValid() || initial <= QDateTime::currentDateTime()) initial = defaultRunTime();

    auto *outer = new QVBoxLayout(this);
    outer->setContentsMargins(12, 12, 12, 12);
    outer->setSpacing(9);

    auto *dateRow = new QHBoxLayout();
    dateRow->setSpacing(8);
    auto *dateLabel = new QLabel("Date", this);
    dateLabel->setFixedWidth(42);
    dateRow->addWidget(dateLabel);
    date = new QDateEdit(initial.date(), this);
    date->setCalendarPopup(true);
    date->setMinimumDate(QDate::currentDate());
    date->setMinimumHeight(30);
    if (date->calendarWidget()) date->calendarWidget()->setFirstDayOfWeek(Qt::Monday);
    dateRow->addWidget(date, 1);
    outer->addLayout(dateRow);

    auto *presetRow = new QHBoxLayout();
    presetRow->setSpacing(8);
    presetRow->addSpacing(42);
    auto *presetStack = new QVBoxLayout();
    presetStack->setSpacing(6);
    today = new QPushButton("Today", this);
    tomorrow = new QPushButton("Tomorrow", this);
    reset = new QPushButton("Now + 5:02", this);
    for (auto *button : {today, tomorrow, reset}) {
        button->setMinimumHeight(30);
        button->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
        presetStack->addWidget(button);
    }
    presetRow->addLayout(presetStack, 1);
    outer->addLayout(presetRow);

    auto *timeRow = new QHBoxLayout();
    timeRow->setSpacing(8);
    auto *timeLabel = new QLabel("Time", this);
    timeLabel->setFixedWidth(42);
    timeRow->addWidget(timeLabel);
    timeRow->addStretch();
    hours = new NumberStepper(0, 23, initial.time().hour(), this);
    minutes = new NumberStepper(0, 59, initial.time().minute(), this);
    auto *colon = new QLabel(":", this);
    colon->setAlignment(Qt::AlignCenter);
    colon->setFixedWidth(12);
    timeRow->addWidget(hours);
    timeRow->addWidget(colon);
    timeRow->addWidget(minutes);
    timeRow->addStretch();
    outer->addLayout(timeRow);

    summary = new QLabel(this);
    summary->setAlignment(Qt::AlignCenter);
    outer->addWidget(summary);
    buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, this);
    outer->addWidget(buttons);

    connect(today, &QPushButton::clicked, this, [this] { date->setDate(QDate::currentDate()); });
    connect(tomorrow, &QPushButton::clicked, this, [this] { date->setDate(QDate::currentDate().addDays(1)); });
    connect(reset, &QPushButton::clicked, this, [this] {
        const auto target = defaultRunTime();
        date->setDate(target.date());
        hours->setValue(target.time().hour());
        minutes->setValue(target.time().minute());
        refreshSummary();
    });
    connect(date, &QDateEdit::dateChanged, this, [this] { refreshSummary(); });
    connect(hours->spin, qOverload<int>(&QSpinBox::valueChanged), this, [this] { refreshSummary(); });
    connect(minutes->spin, qOverload<int>(&QSpinBox::valueChanged), this, [this] { refreshSummary(); });
    connect(buttons, &QDialogButtonBox::rejected, this, &QDialog::reject);
    connect(buttons, &QDialogButtonBox::accepted, this, [this] {
        if (selected() <= QDateTime::currentDateTime()) {
            QMessageBox::warning(this, APP_NAME, "Run time must be in the future.");
            return;
        }
        accept();
    });
    refreshSummary();
}

QDateTime ScheduleTimeDialog::selected() const
{
    return QDateTime(date->date(), QTime(hours->value(), minutes->value()));
}

void ScheduleTimeDialog::refreshSummary()
{
    const QDateTime value = selected();
    auto *ok = buttons->button(QDialogButtonBox::Ok);
    if (value.isValid() && value > QDateTime::currentDateTime()) {
        const qint64 seconds = QDateTime::currentDateTime().secsTo(value);
        summary->setText(QString("%1  ·  in %2h %3m")
                         .arg(value.toString("dd.MM.yyyy HH:mm"))
                         .arg(seconds / 3600)
                         .arg((seconds % 3600) / 60, 2, 10, QChar('0')));
        ok->setEnabled(true);
    } else {
        summary->setText("Choose a future date and time");
        ok->setEnabled(false);
    }
}

SessionComboBox::SessionComboBox(QWidget *parent) : QComboBox(parent)
{
    setEditable(true);
    setInsertPolicy(QComboBox::NoInsert);
    setMaxVisibleItems(18);
    lineEdit()->setPlaceholderText("Session");
    connect(this, qOverload<int>(&QComboBox::activated), this, [this](int index) {
        const QString id = itemData(index, Qt::UserRole).toString();
        if (!id.isEmpty()) setSessionId(id);
    });
    connect(lineEdit(), &QLineEdit::textEdited, this, [this](const QString &text) {
        m_sessionId = text.trimmed();
        setToolTip(m_sessionId);
    });
    connect(lineEdit(), &QLineEdit::editingFinished, this, [this] { normalizeEdited(); });
}

QString SessionComboBox::sessionId() const { return m_sessionId.trimmed(); }

void SessionComboBox::setSessionId(const QString &id)
{
    m_sessionId = id.trimmed();
    const int index = findData(m_sessionId, Qt::UserRole);
    QSignalBlocker blocker(this);
    setCurrentIndex(-1);
    if (index >= 0 && index < m_sessions.size()) {
        const auto session = m_sessions.at(index);
        setEditText(sessionTitle(session));
        setToolTip(sessionTooltip(session));
    } else {
        setEditText(m_sessionId);
        setToolTip(m_sessionId);
    }
}

void SessionComboBox::setSessions(const QVector<QJsonObject> &sessions, bool selectLatestIfEmpty)
{
    QString current = m_sessionId;
    {
        QSignalBlocker blocker(this);
        clear();
        m_sessions.clear();
        for (const auto &session : sessions) {
            if (session.value("archived").toBool(false)) continue;
            const QString id = session.value("id").toString().trimmed();
            if (id.isEmpty()) continue;
            const QString cwd = session.value("cwd").toString();
            const QString project = cwd.isEmpty() ? QString{} : QFileInfo(cwd).fileName();
            QString label = sessionTitle(session);
            if (!project.isEmpty()) label += " · " + project;
            if (label.size() > 64) label = label.left(63) + "…";
            addItem(label, id);
            m_sessions.push_back(session);
            setItemData(count() - 1, sessionTooltip(session), Qt::ToolTipRole);
        }
        if (current.isEmpty() && selectLatestIfEmpty && count() > 0) current = itemData(0, Qt::UserRole).toString();
    }
    setSessionId(current);
}

void SessionComboBox::setResolvedSession(const QJsonObject &session)
{
    const QString id = session.value("id").toString().trimmed();
    if (id.isEmpty()) return;
    int index = findData(id, Qt::UserRole);
    if (index < 0) {
        addItem(sessionTitle(session), id);
        m_sessions.push_back(session);
        index = count() - 1;
    } else if (index < m_sessions.size()) {
        m_sessions[index] = session;
        setItemText(index, sessionTitle(session));
    }
    setItemData(index, sessionTooltip(session), Qt::ToolTipRole);
    setSessionId(id);
}

QString SessionComboBox::sessionTooltip(const QJsonObject &session) const
{
    QStringList bits{session.value("id").toString()};
    const QString cwd = session.value("cwd").toString();
    if (!cwd.isEmpty()) bits << cwd;
    return bits.join('\n');
}

void SessionComboBox::normalizeEdited()
{
    const QString text = lineEdit()->text().trimmed();
    for (int i = 0; i < count(); ++i) {
        const QString id = itemData(i, Qt::UserRole).toString();
        if (text == id || (i < m_sessions.size() && text == sessionTitle(m_sessions.at(i))) || text == itemText(i)) {
            setSessionId(id);
            return;
        }
    }
    m_sessionId = text;
}

PlusTabBar::PlusTabBar(QWidget *parent) : QTabBar(parent)
{
    setMovable(true);
    setExpanding(false);
    setFixedHeight(34);
    plusButton = new QToolButton(this);
    plusButton->setText("+");
    plusButton->setToolTip("New task");
    plusButton->setAutoRaise(true);
    plusButton->setFixedSize(30, 30);
    connect(plusButton, &QToolButton::clicked, this, [this] { if (onPlus) onPlus(); });
    positionPlus();
}

void PlusTabBar::resizeEvent(QResizeEvent *event)
{
    QTabBar::resizeEvent(event);
    positionPlus();
}

void PlusTabBar::tabInserted(int index)
{
    QTabBar::tabInserted(index);
    positionPlus();
}

void PlusTabBar::tabRemoved(int index)
{
    QTabBar::tabRemoved(index);
    positionPlus();
}

void PlusTabBar::tabLayoutChange()
{
    QTabBar::tabLayoutChange();
    positionPlus();
}

void PlusTabBar::positionPlus()
{
    int x = 4;
    if (count() > 0) x = tabRect(count() - 1).right() + 5;
    plusButton->move(x, 2);
    plusButton->raise();
}

} // namespace harr
