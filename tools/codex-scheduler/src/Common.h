#pragma once

#include <QtCore/QDateTime>
#include <QtCore/QJsonObject>
#include <QtCore/QVector>
#include <QtCore/QString>

class QApplication;

namespace harr {

inline constexpr auto APP_NAME = "Harr Codex Scheduler";
inline constexpr qint64 RESET_OFFSET_SECONDS = 5 * 60 * 60 + 2 * 60;

struct TranscriptEvent {
    QString kind;
    QString text;
};

QString utcNow();
QString shellQuote(QString value);
QString compactWhitespace(const QString &value);
QString shortId(const QString &id);
QString sessionTitle(const QJsonObject &session);
QString taskTitle(const QJsonObject &task, int limit = 42);
QString statusIcon(const QString &status);
QString statusText(const QString &status);
bool isActiveStatus(const QString &status);
bool isFinishedStatus(const QString &status);
QDateTime defaultRunTime();
QString stateRootPath();
QVector<TranscriptEvent> parseCodexJsonLine(const QByteArray &raw);
void applyTheme(QApplication &app);

} // namespace harr
