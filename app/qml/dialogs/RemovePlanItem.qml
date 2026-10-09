import QtQuick
import QtQuick.Controls
import ".."
import "../components"

// Asked only for an item that repeats: one that belongs to a single month
// is removed without a question.
Sheet {
    id: root
    property var item: null
    // "only" the month shown, from it "onward", or "all" months.
    property string reach: "only"

    title: item ? qsTr("Remove %1?").arg(item.name) : ""
    subtitle: reach === "only"
        ? qsTr("This item repeats every month. It is left out of %1 and stays in every other month. You can bring it back from that month's list.").arg(budget.monthTitle)
        : reach === "onward"
        ? qsTr("This item repeats every month. It is removed from %1 on and stays in the months before.").arg(budget.monthTitle)
        : qsTr("This item repeats every month. It is removed from every month, the past ones included.")

    function openFor(planItem) {
        item = planItem
        reach = "only"
        budget.clearMessage()
        open()
    }

    function submit() {
        if (reach === "only") budget.skipItem(item.id)
        else if (reach === "onward") budget.endItem(item.id)
        else { budget.deleteItem(item.id); close() }
    }

    Connections {
        target: budget
        function onSaved() { if (root.visible) root.close() }
    }

    Segmented {
        model: [
            { key: "only", label: qsTr("Only %1").arg(budget.monthTitle) },
            { key: "onward", label: qsTr("From %1 on").arg(budget.monthTitle) },
            { key: "all", label: qsTr("Every month") }
        ]
        current: root.reach
        onChosen: function (key) { root.reach = key }
    }

    Notice {
        width: parent.width
        text: budget.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            quiet: true
            danger: true
            text: qsTr("Remove")
            enabled: !budget.busy
            onClicked: root.submit()
        }
    ]
}
