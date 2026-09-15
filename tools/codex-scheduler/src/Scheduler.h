#pragma once

#include <QtCore/QString>
#include <QtCore/QStringList>

namespace harr {

struct ScheduleRequest {
    QString model;
    QString reasoning = "high";
    QString speed = "standard";
    QString atSpec;
    QString timestamp;
    QString session;
    QString prompt;
    QString manualCwd;
    QString output;
    QString logJson;
    QString saveAnswer;
    QString taskState;
    QString ttyPath;
    QString codexBin;
    QString atBin;
};

struct ScheduleResult {
    bool ok = false;
    int exitCode = 2;
    QString output;
    QString cwd;
    QString jobId;
};

ScheduleResult scheduleJob(ScheduleRequest request);
int runScheduleCli(const QStringList &args);
int runJobRunner(const QStringList &args);
int runSessionListCli(const QStringList &args);
int runSessionCwdCli(const QStringList &args);

} // namespace harr
