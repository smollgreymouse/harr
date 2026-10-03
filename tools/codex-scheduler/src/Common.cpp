#include "Common.h"

#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QProcess>
#include <QtCore/QRegularExpression>
#include <QtCore/QDir>
#include <QtGui/QColor>
#include <QtGui/QPalette>
#include <QtWidgets/QApplication>

namespace harr {

QString utcNow() { return QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs); }

QString shellQuote(QString value)
{
    value.replace("'", "'\\''");
    return "'" + value + "'";
}

QString compactWhitespace(const QString &value) { return value.simplified(); }

QString shortId(const QString &id)
{
    if (id.size() <= 16) return id;
    return id.left(8) + "…" + id.right(5);
}

QString sessionTitle(const QJsonObject &session)
{
    QString value = session.value("name").toString();
    if (value.trimmed().isEmpty()) value = session.value("preview").toString();
    value = compactWhitespace(value);
    return value.isEmpty() ? QStringLiteral("Codex session") : value;
}

QString taskTitle(const QJsonObject &task, int limit)
{
    QString prompt = compactWhitespace(task.value("prompt").toString());
    if (!prompt.isEmpty()) return prompt.size() <= limit ? prompt : prompt.left(qMax(1, limit - 1)) + "…";
    const QString session = task.value("session").toString().trimmed();
    if (!session.isEmpty()) return session.size() <= 18 ? session : session.left(8) + "…" + session.right(6);
    return QStringLiteral("New task");
}

QString statusIcon(const QString &status)
{
    if (status == "draft") return "○";
    if (status == "scheduled") return "◷";
    if (status == "running") return "●";
    if (status == "cancelling") return "…";
    if (status == "completed") return "✓";
    if (status == "failed") return "!";
    if (status == "cancelled") return "×";
    return "•";
}

QString statusText(const QString &status)
{
    if (status == "draft") return "Draft";
    if (status == "scheduled") return "Scheduled";
    if (status == "running") return "Running";
    if (status == "cancelling") return "Cancelling…";
    if (status == "completed") return "Completed";
    if (status == "failed") return "Failed";
    if (status == "cancelled") return "Cancelled";
    return status;
}

bool isActiveStatus(const QString &status)
{
    return status == "draft" || status == "scheduled" || status == "running" || status == "cancelling";
}

bool isFinishedStatus(const QString &status)
{
    return status == "completed" || status == "failed" || status == "cancelled";
}

QDateTime defaultRunTime()
{
    QDateTime target = QDateTime::currentDateTime().addSecs(RESET_OFFSET_SECONDS);
    if (target.time().second() || target.time().msec()) target = target.addSecs(60 - target.time().second());
    target.setTime(QTime(target.time().hour(), target.time().minute()));
    return target;
}

QString stateRootPath()
{
    QString base = qEnvironmentVariable("XDG_STATE_HOME");
    if (base.isEmpty()) base = QDir::home().filePath(".local/state");
    return QDir(base).filePath("harr-codex-scheduler");
}

static QString textFromContent(const QJsonValue &content)
{
    if (content.isString()) return content.toString();
    if (!content.isArray()) return {};
    QStringList parts;
    for (const auto &part : content.toArray()) {
        if (part.isString()) parts << part.toString();
        else if (part.isObject()) {
            const auto obj = part.toObject();
            QString value = obj.value("text").toString();
            if (value.isEmpty()) value = obj.value("content").toString();
            if (!value.isEmpty()) parts << value;
        }
    }
    return parts.join('\n');
}

QVector<TranscriptEvent> parseCodexJsonLine(const QByteArray &raw)
{
    const QByteArray line = raw.trimmed();
    if (line.isEmpty()) return {};
    QJsonParseError err;
    const auto doc = QJsonDocument::fromJson(line, &err);
    if (err.error != QJsonParseError::NoError || !doc.isObject()) return {{"status", QString::fromUtf8(line)}};
    const auto payload = doc.object();
    const QString eventType = payload.value("type").toString();
    if (payload.value("item").isObject()) {
        const auto item = payload.value("item").toObject();
        const QString itemType = item.value("type").toString();
        if (itemType == "agent_message" || itemType == "assistant_message" || itemType == "message") {
            auto content = item.value("text");
            if (content.isUndefined() || content.isNull()) content = item.value("content");
            const QString text = textFromContent(content);
            if (!text.isEmpty()) return {{"assistant", text}};
        }
        if (itemType == "reasoning" || itemType == "analysis") {
            auto content = item.value("text");
            if (content.isUndefined() || content.isNull()) content = item.value("content");
            const QString text = textFromContent(content);
            if (!text.isEmpty()) return {{"status", text}};
        }
    }
    if (eventType == "error" || eventType == "turn.failed") {
        auto value = payload.value("message");
        if (value.isUndefined() || value.isNull()) value = payload.value("error");
        QString text;
        if (value.isObject()) {
            const auto obj = value.toObject();
            text = obj.value("message").toString();
            if (text.isEmpty()) text = obj.value("code").toVariant().toString();
            if (text.isEmpty()) text = QString::fromUtf8(QJsonDocument(obj).toJson(QJsonDocument::Compact));
        } else text = value.toVariant().toString();
        if (!text.isEmpty()) return {{"error", text}};
    }
    if (eventType == "turn.completed" || eventType == "thread.completed") return {{"done", "Completed"}};
    const QString message = payload.value("message").toString();
    if (!message.isEmpty()) return {{"status", message}};
    return {};
}

namespace {

void setDarkPaletteGroup(QPalette &palette, QPalette::ColorGroup group,
                         const QColor &window, const QColor &base,
                         const QColor &alternate, const QColor &button,
                         const QColor &text, const QColor &muted,
                         const QColor &highlight)
{
    palette.setColor(group, QPalette::Window, window);
    palette.setColor(group, QPalette::WindowText, text);
    palette.setColor(group, QPalette::Base, base);
    palette.setColor(group, QPalette::AlternateBase, alternate);
    palette.setColor(group, QPalette::ToolTipBase, alternate);
    palette.setColor(group, QPalette::ToolTipText, text);
    palette.setColor(group, QPalette::Text, text);
    palette.setColor(group, QPalette::Button, button);
    palette.setColor(group, QPalette::ButtonText, text);
    palette.setColor(group, QPalette::BrightText, Qt::white);
    palette.setColor(group, QPalette::PlaceholderText, muted);
    palette.setColor(group, QPalette::Highlight, highlight);
    palette.setColor(group, QPalette::HighlightedText, Qt::white);
    palette.setColor(group, QPalette::Light, QColor(76, 77, 81));
    palette.setColor(group, QPalette::Midlight, QColor(61, 62, 66));
    palette.setColor(group, QPalette::Mid, QColor(72, 73, 77));
    palette.setColor(group, QPalette::Dark, QColor(20, 21, 23));
    palette.setColor(group, QPalette::Shadow, QColor(8, 9, 10));
    palette.setColor(group, QPalette::Link, highlight.lighter(125));
    palette.setColor(group, QPalette::LinkVisited, QColor(190, 140, 235));
}

QPalette completeDarkPalette(const QPalette &source)
{
    QPalette palette(source);
    QColor highlight = source.color(QPalette::Active, QPalette::Highlight);
    if (!highlight.isValid() || highlight.lightness() < 55) highlight = QColor(53, 132, 228);

    for (auto group : {QPalette::Active, QPalette::Inactive}) {
        setDarkPaletteGroup(palette, group,
                            QColor(34, 35, 38), QColor(27, 28, 31),
                            QColor(42, 43, 47), QColor(47, 48, 52),
                            QColor(238, 238, 240), QColor(154, 155, 160), highlight);
    }
    setDarkPaletteGroup(palette, QPalette::Disabled,
                        QColor(34, 35, 38), QColor(27, 28, 31),
                        QColor(42, 43, 47), QColor(39, 40, 43),
                        QColor(126, 127, 132), QColor(104, 105, 110),
                        QColor(70, 76, 86));
    return palette;
}

} // namespace

void applyTheme(QApplication &app)
{
    const QString mode = qEnvironmentVariable("HARR_CODEX_THEME").toLower();
    bool dark = mode == "dark";
    if (mode.isEmpty() || mode == "system") {
        QProcess gsettings;
        gsettings.start("gsettings", {"get", "org.gnome.desktop.interface", "color-scheme"});
        if (gsettings.waitForFinished(1000)) {
            const QString scheme = QString::fromUtf8(gsettings.readAllStandardOutput());
            dark = scheme.contains("prefer-dark");
        } else {
            dark = app.palette().color(QPalette::Window).lightness() < 128;
        }
    }
    if (mode == "light") dark = false;
    if (dark) app.setPalette(completeDarkPalette(app.palette()));

    app.setStyleSheet(R"(
QWidget#sidebar { border: 0; }
QSplitter::handle:horizontal { width: 1px; margin: 0; background: palette(mid); }

QPushButton#newTaskButton {
    text-align: left;
    border: 1px solid transparent;
    background: transparent;
    min-height: 28px;
    max-height: 28px;
    padding: 0 6px;
}
QPushButton#newTaskButton:hover { background: palette(alternate-base); border-radius: 4px; }
QLabel#emptyHint, QLabel#sidebarStatus { color: palette(mid); }
QLabel#taskStatus { padding: 0 4px; }

QTreeWidget { border: 0; outline: 0; background: transparent; }
QScrollArea { border: 0; background: transparent; }
QFrame#messageBubble { border-radius: 7px; }

QTabWidget::pane { border: 0; top: 0; }
QTabBar { border: 0; min-height: 34px; max-height: 34px; }
QTabBar::tab {
    border: 0;
    background: transparent;
    min-height: 28px;
    max-height: 28px;
    margin-top: 3px;
    margin-bottom: 3px;
    padding: 0 6px 0 9px;
}
QTabBar::tab:selected, QTabBar::tab:hover { background: palette(alternate-base); border-radius: 5px; }

QComboBox { min-height: 28px; }
QComboBox[chromeRole="selector"] {
    border: 1px solid transparent;
    background: transparent;
    min-width: 108px;
    max-width: 108px;
    min-height: 28px;
    max-height: 28px;
    padding: 0 24px 0 7px;
}
QComboBox[chromeRole="selector"]:hover { border: 1px solid palette(mid); background: palette(alternate-base); border-radius: 4px; }
QComboBox[chromeRole="selector"]:focus { border: 1px solid palette(highlight); border-radius: 4px; }

QLineEdit, QPushButton { min-height: 28px; }
QToolButton[chromeRole="tabClose"],
QToolButton[chromeRole="tabPlus"],
QToolButton[chromeRole="sidebarToggle"] {
    border: 1px solid transparent;
    background: transparent;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
}
QToolButton[chromeRole="tabClose"] { min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px; }
QToolButton[chromeRole="tabClose"]:hover,
QToolButton[chromeRole="tabPlus"]:hover,
QToolButton[chromeRole="sidebarToggle"]:hover {
    border: 1px solid palette(mid);
    background: palette(alternate-base);
    border-radius: 4px;
}
)");
}

} // namespace harr
