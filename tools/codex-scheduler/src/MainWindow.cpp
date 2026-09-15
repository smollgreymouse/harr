#include "MainWindow.h"
#include "CodexService.h"
#include "Common.h"
#include "QuickSchedule.h"
#include "TaskPage.h"
#include "TaskStore.h"
#include "Widgets.h"

#include <QtCore/QFileSystemWatcher>
#include <QtCore/QFileInfo>
#include <QtCore/QJsonArray>
#include <QtCore/QTimer>
#include <QtGui/QAction>
#include <QtGui/QCloseEvent>
#include <QtGui/QIcon>
#include <QtWidgets/QApplication>
#include <QtWidgets/QHBoxLayout>
#include <QtWidgets/QLabel>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QMenu>
#include <QtWidgets/QMessageBox>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QSplitter>
#include <QtWidgets/QSystemTrayIcon>
#include <QtWidgets/QTabWidget>
#include <QtWidgets/QToolButton>
#include <QtWidgets/QTreeWidget>
#include <QtWidgets/QTreeWidgetItem>
#include <QtWidgets/QVBoxLayout>
#include <QtWidgets/QWidget>

namespace harr {

static constexpr int GROUP_ROLE = Qt::UserRole + 1;

MainWindow::MainWindow(TaskStore *store)
    : m_ownedStore(store ? nullptr : std::make_unique<TaskStore>()),
      m_store(store ? store : m_ownedStore.get())
{
    setWindowTitle(APP_NAME);
    resize(1120, 780);

    m_splitter = new QSplitter(Qt::Horizontal, this);
    m_splitter->setChildrenCollapsible(false);
    setCentralWidget(m_splitter);
    buildSidebar();
    buildWorkspace();
    m_splitter->setSizes({m_sidebarWidth, 850});

    m_reconcileTimer = new QTimer(this);
    m_reconcileTimer->setInterval(12000);
    connect(m_reconcileTimer, &QTimer::timeout, this, [this] { refreshAll(); });
    m_reconcileTimer->start();

    m_sessionTimer = new QTimer(this);
    m_sessionTimer->setInterval(30000);
    connect(m_sessionTimer, &QTimer::timeout, this, [this] { refreshSessions(); });
    m_sessionTimer->start();

    setupTray();
    setupStateWatcher();
    restoreWorkspace();
    refreshSidebar();

    const auto initialTasks = m_store->list();
    for (const auto &task : initialTasks) {
        m_knownStatuses.insert(task.value("id").toString(), task.value("status").toString());
    }
    QTimer::singleShot(0, this, [this] { refreshSessions(); });
}

MainWindow::~MainWindow() = default;

TaskStore *MainWindow::store() const { return m_store; }
const QVector<QJsonObject> &MainWindow::sessions() const { return m_sessions; }

void MainWindow::buildSidebar()
{
    m_sidebar = new QWidget(this);
    m_sidebar->setObjectName("sidebar");
    m_sidebar->setMinimumWidth(215);
    m_sidebar->setMaximumWidth(390);
    auto *layout = new QVBoxLayout(m_sidebar);
    layout->setContentsMargins(10, 10, 8, 10);
    layout->setSpacing(8);

    auto *header = new QHBoxLayout();
    auto *newButton = new QPushButton("＋ New task", m_sidebar);
    newButton->setObjectName("newTaskButton");
    connect(newButton, &QPushButton::clicked, this, [this] { newTask(); });

    auto *menuButton = new QToolButton(m_sidebar);
    menuButton->setText("⋮");
    menuButton->setAutoRaise(true);
    menuButton->setToolTip("All tasks");
    m_tasksMenu = new QMenu(menuButton);
    connect(m_tasksMenu, &QMenu::aboutToShow, this, [this] { rebuildTasksMenu(); });
    menuButton->setMenu(m_tasksMenu);
    menuButton->setPopupMode(QToolButton::InstantPopup);
    header->addWidget(newButton, 1);
    header->addWidget(menuButton);
    layout->addLayout(header);

    m_search = new QLineEdit(m_sidebar);
    m_search->setPlaceholderText("Search tasks");
    m_search->setClearButtonEnabled(true);
    connect(m_search, &QLineEdit::textChanged, this, [this] { refreshSidebar(); });
    layout->addWidget(m_search);

    m_tree = new QTreeWidget(m_sidebar);
    m_tree->setHeaderHidden(true);
    m_tree->setRootIsDecorated(true);
    m_tree->setIndentation(14);
    m_tree->setUniformRowHeights(false);
    m_tree->setFrameShape(QFrame::NoFrame);
    m_tree->setContextMenuPolicy(Qt::CustomContextMenu);
    connect(m_tree, &QTreeWidget::itemClicked, this, [this](QTreeWidgetItem *item, int) {
        const QString id = item->data(0, Qt::UserRole).toString();
        if (!id.isEmpty()) openTask(id);
    });
    connect(m_tree, &QWidget::customContextMenuRequested, this, [this](const QPoint &pos) {
        auto *item = m_tree->itemAt(pos);
        if (!item) return;
        const QString id = item->data(0, Qt::UserRole).toString();
        if (id.isEmpty()) return;
        auto task = m_store->load(id);
        if (!task) return;
        QMenu menu(this);
        populateTaskMenu(&menu, *task);
        menu.exec(m_tree->viewport()->mapToGlobal(pos));
    });
    layout->addWidget(m_tree, 1);

    m_sidebarStatus = new QLabel(m_sidebar);
    m_sidebarStatus->setObjectName("sidebarStatus");
    layout->addWidget(m_sidebarStatus);
    m_splitter->addWidget(m_sidebar);
}

void MainWindow::buildWorkspace()
{
    auto *host = new QWidget(this);
    auto *layout = new QVBoxLayout(host);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);

    m_tabs = new QTabWidget(host);
    auto *bar = new PlusTabBar(m_tabs);
    bar->onPlus = [this] { newTask(); };
    m_tabs->setTabBar(bar);
    m_tabs->setMovable(true);
    m_tabs->setTabsClosable(true);
    m_tabs->setDocumentMode(true);
    connect(m_tabs, &QTabWidget::tabCloseRequested, this, [this](int index) { closeTab(index); });
    connect(m_tabs, &QTabWidget::currentChanged, this, [this](int) { saveUi(); });
    connect(m_tabs->tabBar(), &QTabBar::tabMoved, this, [this](int, int) { saveUi(); });

    m_sidebarToggle = new QToolButton(m_tabs);
    m_sidebarToggle->setText("☰");
    m_sidebarToggle->setAutoRaise(true);
    m_sidebarToggle->setToolTip("Toggle tasks sidebar");
    m_sidebarToggle->setCheckable(true);
    m_sidebarToggle->setChecked(true);
    connect(m_sidebarToggle, &QToolButton::toggled, this, [this](bool visible) {
        if (visible) {
            m_sidebar->show();
            m_splitter->setSizes({m_sidebarWidth, qMax(400, width() - m_sidebarWidth)});
        } else {
            const auto sizes = m_splitter->sizes();
            if (!sizes.isEmpty() && sizes.first() > 0) m_sidebarWidth = qBound(215, sizes.first(), 390);
            m_sidebar->hide();
        }
    });
    m_tabs->setCornerWidget(m_sidebarToggle, Qt::TopLeftCorner);

    m_emptyHint = new QLabel("Create a task with + or reopen one from the tasks sidebar", host);
    m_emptyHint->setAlignment(Qt::AlignCenter);
    m_emptyHint->setObjectName("emptyHint");
    layout->addWidget(m_tabs, 1);
    layout->addWidget(m_emptyHint);
    m_splitter->addWidget(host);
    updateEmpty();
}

void MainWindow::setupTray()
{
    m_tray = new QSystemTrayIcon(QIcon::fromTheme("utilities-terminal"), this);
    m_tray->setToolTip(APP_NAME);
    m_trayMenu = new QMenu(this);
    m_tray->setContextMenu(m_trayMenu);
    connect(m_trayMenu, &QMenu::aboutToShow, this, [this] { rebuildTrayMenu(); });
    connect(m_tray, &QSystemTrayIcon::activated, this, [this](QSystemTrayIcon::ActivationReason reason) {
        if (reason == QSystemTrayIcon::Trigger) restore();
    });
    if (QSystemTrayIcon::isSystemTrayAvailable()) m_tray->show();
}

void MainWindow::setupStateWatcher()
{
    m_stateWatcher = new QFileSystemWatcher(this);
    m_stateWatcher->addPath(m_store->tasksDir());
    connect(m_stateWatcher, &QFileSystemWatcher::directoryChanged, this, [this](const QString &) {
        QTimer::singleShot(40, this, [this] {
            if (!m_stateWatcher->directories().contains(m_store->tasksDir())) m_stateWatcher->addPath(m_store->tasksDir());
            refreshAll();
        });
    });
}

void MainWindow::restoreWorkspace()
{
    const QJsonObject ui = m_store->loadUi();
    bool opened = false;
    for (const QJsonValue &value : ui.value("open_task_ids").toArray()) {
        const QString id = value.toString();
        if (m_store->load(id)) {
            openTask(id, false);
            opened = true;
        }
    }
    const QString current = ui.value("current_task_id").toString();
    if (m_pages.contains(current)) m_tabs->setCurrentWidget(m_pages.value(current));
    if (!opened && m_store->list().isEmpty()) newTask();
    updateEmpty();
}

void MainWindow::newTask()
{
    const auto task = m_store->newDraft();
    openTask(task.value("id").toString(), true);
    refreshSidebar();
}

void MainWindow::openTask(const QString &id, bool makeCurrent)
{
    if (m_pages.contains(id)) {
        if (makeCurrent) m_tabs->setCurrentWidget(m_pages.value(id));
        return;
    }
    auto task = m_store->load(id);
    if (!task) return;

    auto *page = new TaskPage(m_store, *task, [this](const QString &changed) { taskChanged(changed); }, m_tabs);
    m_pages.insert(id, page);
    const int index = m_tabs->addTab(page, tabTitle(*task));
    m_tabs->setTabToolTip(index, tabTooltip(*task));
    if (!m_sessions.isEmpty()) page->setSessionChoices(m_sessions, true);
    if (makeCurrent) m_tabs->setCurrentIndex(index);
    updateEmpty();
    saveUi();
}

QString MainWindow::tabTitle(const QJsonObject &task) const
{
    return statusIcon(task.value("status").toString()) + " " + taskTitle(task, 28);
}

QString MainWindow::tabTooltip(const QJsonObject &task) const
{
    QStringList bits{statusIcon(task.value("status").toString()) + " " + statusText(task.value("status").toString())};
    if (!task.value("session").toString().isEmpty()) bits << task.value("session").toString();
    if (!task.value("scheduled").toString().isEmpty()) bits << task.value("scheduled").toString();
    return bits.join('\n');
}

void MainWindow::closeTab(int index)
{
    auto *page = qobject_cast<TaskPage *>(m_tabs->widget(index));
    if (!page) {
        m_tabs->removeTab(index);
        return;
    }
    const QString id = page->taskId();
    auto task = m_store->load(id);
    m_tabs->removeTab(index);
    m_pages.remove(id);
    page->deleteLater();
    if (task && m_store->isEmptyDraft(*task)) m_store->remove(id, true, false, nullptr);
    saveUi();
    refreshSidebar();
    updateEmpty();
}

void MainWindow::closeTaskTabById(const QString &id, bool preserveTask)
{
    auto *page = m_pages.value(id, nullptr);
    if (!page) return;
    const int index = m_tabs->indexOf(page);
    if (index < 0) return;
    if (!preserveTask) {
        closeTab(index);
        return;
    }
    m_tabs->removeTab(index);
    m_pages.remove(id);
    page->deleteLater();
    saveUi();
    updateEmpty();
}

void MainWindow::taskChanged(const QString &id)
{
    auto task = m_store->load(id);
    if (task && m_pages.contains(id)) {
        const int index = m_tabs->indexOf(m_pages.value(id));
        if (index >= 0) {
            m_tabs->setTabText(index, tabTitle(*task));
            m_tabs->setTabToolTip(index, tabTooltip(*task));
        }
    }
    refreshSidebar();
}

QHash<QString, bool> MainWindow::sidebarExpansion() const
{
    QHash<QString, bool> state{{"active", true}, {"history", false}};
    for (int i = 0; i < m_tree->topLevelItemCount(); ++i) {
        auto *item = m_tree->topLevelItem(i);
        const QString key = item->data(0, GROUP_ROLE).toString();
        if (!key.isEmpty()) state.insert(key, item->isExpanded());
    }
    return state;
}

void MainWindow::refreshSidebar()
{
    const auto expansion = m_tree->topLevelItemCount() ? sidebarExpansion() : QHash<QString, bool>{{"active", true}, {"history", false}};
    const QString query = m_search ? m_search->text().trimmed().toLower() : QString{};
    const auto tasks = m_store->list();

    QSignalBlocker blocker(m_tree);
    m_tree->clear();
    auto *active = new QTreeWidgetItem(m_tree, {"ACTIVE"});
    auto *history = new QTreeWidgetItem(m_tree, {"HISTORY"});
    active->setData(0, GROUP_ROLE, "active");
    history->setData(0, GROUP_ROLE, "history");
    QFont groupFont = active->font(0);
    groupFont.setBold(true);
    active->setFont(0, groupFont);
    history->setFont(0, groupFont);

    int activeCount = 0;
    int historyCount = 0;
    for (const auto &task : tasks) {
        const QString haystack = (task.value("session").toString() + " " + task.value("prompt").toString()
                                  + " " + task.value("cwd").toString() + " " + task.value("model").toString()
                                  + " " + task.value("status").toString()).toLower();
        if (!query.isEmpty() && !haystack.contains(query)) continue;

        const QString taskStatus = task.value("status").toString();
        auto *root = isActiveStatus(taskStatus) ? active : history;
        if (root == active) ++activeCount; else ++historyCount;
        QString model = task.value("model").toString();
        model.remove("gpt-5.6-");
        if (!model.isEmpty()) model[0] = model[0].toUpper();
        QString when = task.value("scheduled").toString().replace('T', ' ').left(16);
        if (when.isEmpty()) when = "unscheduled";
        auto *item = new QTreeWidgetItem(root, {
            statusIcon(taskStatus) + "  " + taskTitle(task, 34) + "\n    " + model + " · " + when
        });
        item->setData(0, Qt::UserRole, task.value("id").toString());
        item->setToolTip(0, tabTooltip(task));
    }
    active->setText(0, QString("ACTIVE  %1").arg(activeCount));
    history->setText(0, QString("HISTORY  %1").arg(historyCount));
    active->setExpanded(expansion.value("active", true));
    history->setExpanded(expansion.value("history", false));
    m_sidebarStatus->setText(QString("%1 task%2").arg(tasks.size()).arg(tasks.size() == 1 ? "" : "s"));
}

void MainWindow::populateTaskMenu(QMenu *menu, const QJsonObject &task)
{
    const QString id = task.value("id").toString();
    auto *open = menu->addAction("Open");
    connect(open, &QAction::triggered, this, [this, id] { restore(); openTask(id); });
    if (m_pages.contains(id)) {
        auto *close = menu->addAction("Close tab");
        connect(close, &QAction::triggered, this, [this, id] { closeTaskTabById(id, true); });
    }

    const QString state = task.value("status").toString();
    if (state == "scheduled" || state == "running" || state == "cancelling") {
        menu->addSeparator();
        auto *cancel = menu->addAction("Cancel task…");
        connect(cancel, &QAction::triggered, this, [this, id] {
            auto task = m_store->load(id);
            if (!task) return;
            if (QMessageBox::question(this, APP_NAME,
                                      "Cancel task “" + taskTitle(*task, 52) + "”?",
                                      QMessageBox::Yes | QMessageBox::No,
                                      QMessageBox::No) != QMessageBox::Yes) return;
            QString error;
            m_store->cancel(id, &error);
            if (!error.isEmpty()) QMessageBox::warning(this, APP_NAME, error);
            refreshAll();
        });
        return;
    }

    menu->addSeparator();
    auto *deleteData = menu->addAction("Delete task data…");
    deleteData->setToolTip("Delete scheduler metadata and internal JSONL log; keep exported answer");
    connect(deleteData, &QAction::triggered, this, [this, id] {
        auto task = m_store->load(id);
        if (!task) return;
        if (QMessageBox::question(this, APP_NAME,
                                  "Delete scheduler data for “" + taskTitle(*task, 52) + "”?\nAny exported answer file will be kept.",
                                  QMessageBox::Yes | QMessageBox::No,
                                  QMessageBox::No) != QMessageBox::Yes) return;
        closeTaskTabById(id, true);
        QString error;
        if (!m_store->remove(id, true, false, &error) && !error.isEmpty()) QMessageBox::critical(this, APP_NAME, error);
        refreshAll();
    });
    if (!task.value("answer").toString().isEmpty()) {
        auto *deleteAll = menu->addAction("Delete task + saved answer…");
        connect(deleteAll, &QAction::triggered, this, [this, id] {
            auto task = m_store->load(id);
            if (!task) return;
            if (QMessageBox::question(this, APP_NAME,
                                      "Delete task and its exported answer file?",
                                      QMessageBox::Yes | QMessageBox::No,
                                      QMessageBox::No) != QMessageBox::Yes) return;
            closeTaskTabById(id, true);
            QString error;
            if (!m_store->remove(id, true, true, &error) && !error.isEmpty()) QMessageBox::critical(this, APP_NAME, error);
            refreshAll();
        });
    }
}

void MainWindow::rebuildTasksMenu()
{
    m_tasksMenu->clear();
    auto *newAction = m_tasksMenu->addAction("＋ New task");
    connect(newAction, &QAction::triggered, this, [this] { newTask(); });
    auto *refresh = m_tasksMenu->addAction("↻ Refresh Codex sessions");
    connect(refresh, &QAction::triggered, this, [this] { refreshSessions(); });
    m_tasksMenu->addSeparator();

    auto *activeMenu = m_tasksMenu->addMenu("Active");
    auto *historyMenu = m_tasksMenu->addMenu("History");
    bool hasActive = false;
    bool hasHistory = false;
    for (const auto &task : m_store->list()) {
        const QString state = task.value("status").toString();
        QMenu *parent = isActiveStatus(state) ? activeMenu : historyMenu;
        if (parent == activeMenu) hasActive = true; else hasHistory = true;
        auto *sub = parent->addMenu(tabTitle(task));
        populateTaskMenu(sub, task);
    }
    if (!hasActive) { auto *empty = activeMenu->addAction("No active tasks"); empty->setEnabled(false); }
    if (!hasHistory) { auto *empty = historyMenu->addAction("No finished tasks"); empty->setEnabled(false); }
}

void MainWindow::rebuildTrayMenu()
{
    m_trayMenu->clear();
    auto *show = m_trayMenu->addAction("Open main window");
    connect(show, &QAction::triggered, this, [this] { restore(); });
    m_trayMenu->addSeparator();

    auto *sessionsMenu = m_trayMenu->addMenu("Schedule for session");
    if (m_sessions.isEmpty()) {
        auto *empty = sessionsMenu->addAction("No active Codex sessions loaded");
        empty->setEnabled(false);
    } else {
        QHash<QString, int> counts;
        for (const auto &session : m_sessions) counts[sessionTitle(session)]++;
        for (const auto &session : m_sessions) {
            if (session.value("archived").toBool(false)) continue;
            QString label = sessionTitle(session);
            if (counts.value(label) > 1 && !session.value("cwd").toString().isEmpty()) {
                label += " · " + QFileInfo(session.value("cwd").toString()).fileName();
            }
            if (label.size() > 64) label = label.left(63) + "…";
            auto *action = sessionsMenu->addAction(label);
            action->setToolTip(session.value("id").toString() + "\n" + session.value("cwd").toString());
            connect(action, &QAction::triggered, this, [this, session] {
                QuickScheduleDialog dialog(m_store, session, this);
                if (dialog.exec() != QDialog::Accepted || dialog.scheduledTask().isEmpty()) return;
                refreshAll();
                const auto task = dialog.scheduledTask();
                m_tray->showMessage(APP_NAME, "Scheduled: " + taskTitle(task, 48));
            });
        }
    }
    sessionsMenu->addSeparator();
    auto *refreshSessionsAction = sessionsMenu->addAction("↻ Refresh sessions");
    connect(refreshSessionsAction, &QAction::triggered, this, [this] { refreshSessions(); });

    QVector<QJsonObject> activeTasks;
    for (const auto &task : m_store->list()) {
        if (isActiveStatus(task.value("status").toString()) && !m_store->isEmptyDraft(task)) activeTasks << task;
    }
    auto *activeMenu = m_trayMenu->addMenu(QString("Active tasks (%1)").arg(activeTasks.size()));
    if (activeTasks.isEmpty()) {
        auto *empty = activeMenu->addAction("No active tasks");
        empty->setEnabled(false);
    } else {
        for (const auto &task : activeTasks) {
            const QString id = task.value("id").toString();
            QString when = task.value("scheduled").toString().replace('T', ' ');
            if (when.size() >= 16) when = when.mid(5, 11);
            const QString suffix = when.isEmpty() ? QString{} : " · " + when;
            auto *action = activeMenu->addAction(statusIcon(task.value("status").toString()) + " " + taskTitle(task, 46) + suffix);
            action->setToolTip(tabTooltip(task));
            connect(action, &QAction::triggered, this, [this, id] {
                restore();
                openTask(id, true);
                refreshAll();
            });
        }
    }

    m_trayMenu->addSeparator();
    auto *quit = m_trayMenu->addAction("Quit");
    connect(quit, &QAction::triggered, this, [this] { quitApp(); });
}

void MainWindow::refreshSessions()
{
    QString error;
    auto sessions = CodexService::listSessions(&error, 50);
    if (!sessions.isEmpty() || error.isEmpty()) m_sessions = sessions;
    if (error.isEmpty()) m_sidebarStatus->setToolTip(QString("%1 active Codex sessions loaded").arg(m_sessions.size()));
    else m_sidebarStatus->setToolTip(error);
    for (auto *page : m_pages) page->setSessionChoices(m_sessions, true);
}

void MainWindow::recordAndNotifyStatusChanges(const QVector<QJsonObject> &tasks)
{
    QHash<QString, QString> now;
    for (const auto &task : tasks) {
        const QString id = task.value("id").toString();
        const QString state = task.value("status").toString();
        now.insert(id, state);
        const QString old = m_knownStatuses.value(id);
        if (!old.isEmpty() && isActiveStatus(old) && isFinishedStatus(state) && m_tray && m_tray->isVisible()) {
            m_tray->showMessage(APP_NAME, statusIcon(state) + " " + taskTitle(task, 52) + " — " + statusText(state));
        }
    }
    m_knownStatuses = now;
}

void MainWindow::refreshAll()
{
    const auto tasks = m_store->list();
    recordAndNotifyStatusChanges(tasks);
    refreshSidebar();

    for (auto it = m_pages.begin(); it != m_pages.end(); ) {
        auto task = m_store->load(it.key());
        if (!task) {
            auto *page = it.value();
            const int index = m_tabs->indexOf(page);
            if (index >= 0) m_tabs->removeTab(index);
            page->deleteLater();
            it = m_pages.erase(it);
            continue;
        }
        auto *page = it.value();
        page->refreshFromStore();
        const int index = m_tabs->indexOf(page);
        if (index >= 0) {
            m_tabs->setTabText(index, tabTitle(*task));
            m_tabs->setTabToolTip(index, tabTooltip(*task));
        }
        ++it;
    }
    updateEmpty();
}

void MainWindow::saveUi()
{
    if (!m_tabs) return;
    QStringList ids;
    for (int i = 0; i < m_tabs->count(); ++i) {
        if (auto *page = qobject_cast<TaskPage *>(m_tabs->widget(i))) ids << page->taskId();
    }
    QString current;
    if (auto *page = qobject_cast<TaskPage *>(m_tabs->currentWidget())) current = page->taskId();
    try { m_store->saveUi(ids, current); } catch (...) {}
}

void MainWindow::updateEmpty()
{
    const bool empty = m_tabs->count() == 0;
    m_tabs->setVisible(!empty);
    m_emptyHint->setVisible(empty);
}

void MainWindow::restore()
{
    showNormal();
    show();
    raise();
    activateWindow();
}

void MainWindow::quitApp()
{
    m_quitting = true;
    saveUi();
    if (m_tray) m_tray->hide();
    QApplication::quit();
}

void MainWindow::closeEvent(QCloseEvent *event)
{
    saveUi();
    if (!m_quitting && QSystemTrayIcon::isSystemTrayAvailable()) {
        hide();
        event->ignore();
        return;
    }
    event->accept();
}

} // namespace harr
