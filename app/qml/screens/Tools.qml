import QtQuick
import QtQuick.Controls
import ".."
import "../components"
import "../tools"

Flickable {
    id: root
    property string tool: "budget"
    signal addPlanItemRequested()
    signal editPlanItemRequested(var item)
    signal removePlanItemRequested(var item)
    signal editTransactionRequested(int transactionId)

    contentWidth: width
    contentHeight: page.implicitHeight + 48
    clip: true
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

    Column {
        id: page
        x: 28
        y: 24
        width: Math.min(root.width - 56, 1180)
        spacing: Theme.gap

        Item {
            width: parent.width
            height: tabs.height

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: qsTr("Tools")
                color: Theme.text
                font.family: Theme.displayFont
                font.pixelSize: 22
                font.weight: Font.Light
            }
            Segmented {
                id: tabs
                anchors.right: parent.right
                model: [
                    { key: "budget", label: qsTr("Budget plan") },
                    { key: "calendar", label: qsTr("Calendar") },
                    { key: "loan", label: qsTr("Calculators") },
                    { key: "insights", label: qsTr("Insights") },
                    { key: "scenario", label: qsTr("What if") },
                    { key: "history", label: qsTr("Past balance") }
                ]
                current: root.tool
                onChosen: function (key) { root.tool = key }
            }
        }

        // Only the selected tool exists.
        Loader {
            id: toolLoader
            width: parent.width
            transform: Translate { id: toolShift }
            onLoaded: toolArrival.restart()
            ParallelAnimation {
                id: toolArrival
                NumberAnimation { target: toolLoader; property: "opacity"; from: 0; to: 1; duration: Theme.medium }
                NumberAnimation { target: toolShift; property: "y"; from: 8; to: 0; duration: Theme.medium; easing.type: Easing.OutCubic }
            }
            sourceComponent: root.tool === "budget" ? budgetTool
                : root.tool === "calendar" ? calendarTool
                : root.tool === "insights" ? insightsTool
                : root.tool === "scenario" ? scenarioTool
                : root.tool === "history" ? historyTool : loanTool
        }
    }

    Component {
        id: budgetTool
        BudgetTool {
            onAddRequested: root.addPlanItemRequested()
            onEditRequested: function (item) { root.editPlanItemRequested(item) }
            onRemoveRequested: function (item) { root.removePlanItemRequested(item) }
        }
    }
    Component {
        id: calendarTool
        CalendarTool {
            onEditRequested: function (transactionId) { root.editTransactionRequested(transactionId) }
        }
    }
    Component { id: loanTool; CalculatorsTool { objectName: "calculators" } }
    Component { id: insightsTool; InsightsTool {} }
    Component { id: scenarioTool; ScenarioTool {} }
    Component { id: historyTool; HistoryTool {} }
}
