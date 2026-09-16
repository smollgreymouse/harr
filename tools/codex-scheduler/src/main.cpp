#include "Common.h"
#include "MainWindow.h"
#include "Scheduler.h"
#include "TaskStore.h"
#include "Widgets.h"

#include <QtCore/QCoreApplication>
#include <QtCore/QTemporaryDir>
#include <QtCore/QTextStream>
#include <QtCore/QTimer>
#include <QtWidgets/QApplication>
#include <QtWidgets/QCalendarWidget>
#include <QtWidgets/QDateEdit>

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
