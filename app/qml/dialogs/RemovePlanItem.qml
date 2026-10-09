import QtQuick
import QtQuick.Controls
import ".."
import "../components"

// Asked only for an item that repeats: one that belongs to a single month
// is removed without a question.
Sheet {
    id: root
    property var item: null

    title: item ? qsTr("Remove %1?").arg(item.name) : ""
    subtitle: qsTr("This item repeats every month. From %1 on keeps it in the months before; every month removes it from those as well.").arg(budget.monthTitle)

    function openFor(planItem) {
        item = planItem
        budget.clearMessage()
        open()
    }

    Connections {
        target: budget
        function onSaved() { if (root.visible) root.close() }
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
            text: qsTr("Every month")
            enabled: !budget.busy
            onClicked: { budget.deleteItem(root.item.id); root.close() }
        },
        PrimaryButton {
            text: qsTr("From %1 on").arg(budget.monthTitle)
            enabled: !budget.busy
            onClicked: budget.endItem(root.item.id)
        }
    ]
}
