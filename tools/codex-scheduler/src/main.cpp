#include "Common.h"
#include "MainWindow.h"
#include "Scheduler.h"
#include "TaskStore.h"
#include "TaskPage.h"
#include "Widgets.h"

#include <QtCore/QCoreApplication>
#include <QtCore/QFile>
#include <QtCore/QTemporaryDir>
#include <QtCore/QTextStream>
#include <QtCore/QTimer>
#include <QtWidgets/QApplication>
#include <QtWidgets/QCalendarWidget>
#include <QtWidgets/QDateEdit>
#include <QtWidgets/QComboBox>

#include <csignal>

namespace {
volatile std::sig_atomic_t quitRequested = 0;
void signalHandler(int) { quitRequested = 1; }

int runSelfTest()
{
    QTemporaryDir temp;
    if (!temp.isValid()) return 1;

    harr::TaskStore store(temp.path() + "/state");
    const auto task = store.newDraft();
    const QString id = task.value("id").toString();
    if (id.isEmpty() || !store.load(id)) return 2;
    store.patch(id, {{"prompt", "hello"}});
    if (store.list().size() != 1 || store.load(id)->value("prompt").toString() != "hello") return 3;

    const auto events = harr::parseCodexJsonLine(
        R"({"type":"item.completed","item":{"type":"agent_message","text":"answer"}})");
    if (events.size() != 1 || events[0].kind != "assistant" || events[0].text != "answer") return 4;

    const qint64 delta = QDateTime::currentDateTime().secsTo(harr::defaultRunTime());
    if (delta < harr::RESET_OFFSET_SECONDS || delta > harr::RESET_OFFSET_SECONDS + 60) return 5;

    harr::ScheduleTimeDialog picker(harr::defaultRunTime());
    if (!picker.date->calendarWidget() || picker.date->calendarWidget()->firstDayOfWeek() != Qt::Monday) return 6;

    auto modelTask = store.load(id);
    if (!modelTask) return 7;
    harr::TaskPage page(&store, *modelTask, [](const QString &) {});
    const QVector<QJsonObject> models{
        QJsonObject{{"id", "gpt-current"}, {"model", "gpt-current"},
                    {"displayName", "GPT Current"}, {"hidden", false}, {"isDefault", true}},
        QJsonObject{{"id", "gpt-other"}, {"model", "gpt-other"},
                    {"displayName", "GPT Other"}, {"hidden", false}, {"isDefault", false}},
        QJsonObject{{"id", "gpt-hidden"}, {"model", "gpt-hidden"},
                    {"displayName", "GPT Hidden"}, {"hidden", true}, {"isDefault", false}}
    };
    store.patch(id, {{"model", "gpt-removed"}});
    page.setModelChoices(models);
    if (page.model->count() != 2
        || page.model->findData("gpt-removed", Qt::UserRole) >= 0
        || page.model->findData("gpt-hidden", Qt::UserRole) >= 0
        || page.model->currentData(Qt::UserRole).toString() != "gpt-current"
        || store.load(id)->value("model").toString() != "gpt-current") return 8;

    const QString atrmPath = temp.filePath("fake-atrm");
    const QString atrmLog = temp.filePath("atrm.log");
    {
        QFile atrm(atrmPath);
        if (!atrm.open(QIODevice::WriteOnly | QIODevice::Truncate)) return 9;
        atrm.write("#!/bin/sh\nprintf '%s\\n' \"$1\" > \"$FAKE_ATRM_LOG\"\n");
        atrm.close();
        if (!atrm.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner))
            return 10;
    }
    qputenv("ATRM_BIN", atrmPath.toLocal8Bit());
    qputenv("FAKE_ATRM_LOG", atrmLog.toLocal8Bit());
    const auto scheduledTask = store.newDraft();
    const QString scheduledId = scheduledTask.value("id").toString();
    store.patch(scheduledId, {
        {"status", "scheduled"},
        {"at_job", "73"},
        {"model", "gpt-current"},
        {"scheduled", harr::defaultRunTime().toString(Qt::ISODate)}
    });
    QString editError;
    const auto reopened = store.reopenScheduled(scheduledId, &editError);
    qunsetenv("ATRM_BIN");
    qunsetenv("FAKE_ATRM_LOG");
    QFile atrmResult(atrmLog);
    if (!editError.isEmpty()
        || reopened.value("status").toString() != "draft"
        || !reopened.value("at_job").isNull()
        || !atrmResult.open(QIODevice::ReadOnly)
        || QString::fromUtf8(atrmResult.readAll()).trimmed() != "73") return 11;

    const QString failingAtrmPath = temp.filePath("fake-atrm-fail");
    {
        QFile atrm(failingAtrmPath);
        if (!atrm.open(QIODevice::WriteOnly | QIODevice::Truncate)) return 12;
        atrm.write("#!/bin/sh\nexit 1\n");
        atrm.close();
        if (!atrm.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner))
            return 13;
    }
    qputenv("ATRM_BIN", failingAtrmPath.toLocal8Bit());
    const auto racingTask = store.newDraft();
    const QString racingId = racingTask.value("id").toString();
    store.patch(racingId, {{"status", "scheduled"}, {"at_job", "74"}});
    QString racingError;
    const auto stillScheduled = store.reopenScheduled(racingId, &racingError);
    qunsetenv("ATRM_BIN");
    if (racingError.isEmpty()
        || stillScheduled.value("status").toString() != "scheduled"
        || stillScheduled.value("at_job").toString() != "74") return 14;

    harr::MainWindow window(&store);
    window.hide();

    QTextStream(stdout) << "C++ scheduler self-test passed\n";
    return 0;
}
}

int main(int argc, char **argv)
{
    const QString mode = argc > 1 ? QString::fromLocal8Bit(argv[1]) : QString{};
    const bool needsWidgets = mode.isEmpty() || mode == "self-test";

    if (!needsWidgets) {
        QCoreApplication app(argc, argv);
        app.setApplicationName(harr::APP_NAME);
        const QStringList args = app.arguments().mid(2);
        if (mode == "schedule") return harr::runScheduleCli(args);
        if (mode == "job-runner") return harr::runJobRunner(args);
        if (mode == "session-list") return harr::runSessionListCli(args);
        if (mode == "session-cwd") return harr::runSessionCwdCli(args);
        QTextStream(stderr) << "Unknown mode: " << mode << '\n';
        return 2;
    }

    QApplication app(argc, argv);
    app.setApplicationName(harr::APP_NAME);
    app.setQuitOnLastWindowClosed(false);
    harr::applyTheme(app);

    if (mode == "self-test") return runSelfTest();

    harr::MainWindow window;
    window.show();

    std::signal(SIGINT, signalHandler);
    std::signal(SIGTERM, signalHandler);
    QTimer signalTimer;
    signalTimer.setInterval(100);
    QObject::connect(&signalTimer, &QTimer::timeout, &app, [&] {
        if (quitRequested) window.quitApp();
    });
    signalTimer.start();
    return app.exec();
}
