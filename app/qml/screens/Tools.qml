import QtQuick
import QtQuick.Controls
import ".."
import "../components"
import "../tools"

Flickable {
    id: root
    property string tool: "budget"
    signal addPlanItemRequested()

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
                text: "Tools"
                color: Theme.text
                font.family: Theme.displayFont
                font.pixelSize: 22
                font.weight: Font.Light
            }
            Segmented {
                id: tabs
                anchors.right: parent.right
                model: [
                    { key: "budget", label: "Budget plan" },
                    { key: "calendar", label: "Calendar" },
                    { key: "loan", label: "Calculators" },
                    { key: "insights", label: "Insights" },
                    { key: "scenario", label: "What if" },
                    { key: "history", label: "Past balance" }
                ]
                current: root.tool
                onChosen: function (key) { root.tool = key }
            }
        }

        // Only the selected tool exists.
        Loader {
            width: parent.width
            sourceComponent: root.tool === "budget" ? budgetTool
                : root.tool === "calendar" ? calendarTool
                : root.tool === "insights" ? insightsTool
                : root.tool === "scenario" ? scenarioTool
                : root.tool === "history" ? historyTool : loanTool
        }
    }

    Component {
        id: budgetTool
        BudgetTool { onAddRequested: root.addPlanItemRequested() }
    }
    Component { id: calendarTool; CalendarTool {} }
    Component { id: loanTool; CalculatorsTool { objectName: "calculators" } }
    Component { id: insightsTool; InsightsTool {} }
    Component { id: scenarioTool; ScenarioTool {} }
    Component { id: historyTool; HistoryTool {} }
}
