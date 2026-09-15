#pragma once

#include <QtCore/QHash>
#include <QtCore/QJsonObject>
#include <QtCore/QSignalBlocker>
#include <QtCore/QVector>
#include <QtWidgets/QFrame>
#include <QtWidgets/QMainWindow>
#include <QtWidgets/QTabBar>

#include <memory>

class QCloseEvent;
class QFileSystemWatcher;
class QLabel;
class QLineEdit;
class QMenu;
class QSplitter;
class QSystemTrayIcon;
class QTabWidget;
class QTimer;
class QToolButton;
class QTreeWidget;
class QTreeWidgetItem;
class QWidget;

namespace harr {

class TaskPage;
class TaskStore;

class MainWindow : public QMainWindow {
public:
    explicit MainWindow(TaskStore *store = nullptr);
    ~MainWindow() override;

    void quitApp();
    void restore();
    void refreshSessions();
    void refreshAll();
    void openTask(const QString &id, bool makeCurrent = true);

    QString tabTooltip(const QJsonObject &task) const;
    TaskStore *store() const;
    const QVector<QJsonObject> &sessions() const;

protected:
    void closeEvent(QCloseEvent *event) override;

private:
    void buildSidebar();
    void buildWorkspace();
    void setupTray();
    void setupStateWatcher();
    void restoreWorkspace();
    void newTask();
    QString tabTitle(const QJsonObject &task) const;
    void closeTab(int index);
    void closeTaskTabById(const QString &id, bool preserveTask = true);
    void taskChanged(const QString &id);
    QHash<QString, bool> sidebarExpansion() const;
    void refreshSidebar();
    void populateTaskMenu(QMenu *menu, const QJsonObject &task);
    void rebuildTasksMenu();
    void rebuildTrayMenu();
    void saveUi();
    void updateEmpty();
    void recordAndNotifyStatusChanges(const QVector<QJsonObject> &tasks);

    std::unique_ptr<TaskStore> m_ownedStore;
    TaskStore *m_store{};
    QSplitter *m_splitter{};
    QWidget *m_sidebar{};
    QLineEdit *m_search{};
    QTreeWidget *m_tree{};
    QLabel *m_sidebarStatus{};
    QTabWidget *m_tabs{};
    QToolButton *m_sidebarToggle{};
    QLabel *m_emptyHint{};
    QMenu *m_tasksMenu{};
    QHash<QString, TaskPage *> m_pages;
    QVector<QJsonObject> m_sessions;
    QTimer *m_reconcileTimer{};
    QTimer *m_sessionTimer{};
    QFileSystemWatcher *m_stateWatcher{};
    QSystemTrayIcon *m_tray{};
    QMenu *m_trayMenu{};
    QHash<QString, QString> m_knownStatuses;
    bool m_quitting = false;
    int m_sidebarWidth = 270;
};

} // namespace harr
