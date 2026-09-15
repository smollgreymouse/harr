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

void applyTheme(QApplication &app)
{
    QString mode = qEnvironmentVariable("HARR_CODEX_THEME").toLower();
    bool dark = mode == "dark";
    if (mode.isEmpty() || mode == "system") {
        QProcess gsettings;
        gsettings.start("gsettings", {"get", "org.gnome.desktop.interface", "color-scheme"});
        if (gsettings.waitForFinished(1000)) dark = QString::fromUtf8(gsettings.readAllStandardOutput()).contains("prefer-dark");
    }
    if (mode == "light") dark = false;
    if (dark) {
        QPalette p = app.palette();
        for (auto group : {QPalette::Active, QPalette::Inactive}) {
            p.setColor(group, QPalette::Window, QColor(32,32,32)); p.setColor(group, QPalette::WindowText, QColor(235,235,235));
            p.setColor(group, QPalette::Base, QColor(24,24,24)); p.setColor(group, QPalette::AlternateBase, QColor(38,38,38));
            p.setColor(group, QPalette::ToolTipBase, QColor(38,38,38)); p.setColor(group, QPalette::ToolTipText, QColor(235,235,235));
            p.setColor(group, QPalette::Text, QColor(235,235,235)); p.setColor(group, QPalette::Button, QColor(38,38,38));
            p.setColor(group, QPalette::ButtonText, QColor(235,235,235)); p.setColor(group, QPalette::Highlight, QColor(66,133,244));
            p.setColor(group, QPalette::HighlightedText, QColor(255,255,255)); p.setColor(group, QPalette::PlaceholderText, QColor(145,145,145));
        }
        p.setColor(QPalette::Disabled, QPalette::Text, QColor(120,120,120));
        p.setColor(QPalette::Disabled, QPalette::ButtonText, QColor(120,120,120));
        app.setPalette(p);
    }
    app.setStyleSheet(R"(
QTabWidget::pane { border: 0; }
QTabBar::tab { min-height: 28px; padding: 3px 10px; border: 0; background: transparent; }
QTabBar::tab:selected { background: palette(alternate-base); }
QComboBox[chromeRole="selector"] { border: 1px solid transparent; padding: 3px 22px 3px 7px; min-width: 82px; }
QComboBox[chromeRole="selector"]:hover, QComboBox[chromeRole="selector"]:focus { border: 1px solid palette(mid); }
QTreeWidget { border: 0; background: transparent; }
QTextEdit { border: 1px solid palette(mid); }
QTextEdit[readOnly="true"] { border: 0; background: transparent; }
QToolButton { min-width: 26px; min-height: 26px; }
QPushButton, QLineEdit, QComboBox, QDateEdit { min-height: 28px; }
#sidebar { border: 0; }
)");
}

} // namespace harr
