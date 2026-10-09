import QtQuick
import QtQuick.Controls
import ".."
import "../components"

Sheet {
    id: root
    title: qsTr("New savings goal")
    subtitle: qsTr("Money you move into a goal is set aside from your accounts until you take it back.")

    function openFresh() {
        name.text = ""
        target.text = ""
        date.text = ""
        savings.clearMessage()
        open()
        name.input.forceActiveFocus()
    }

    function submit() { savings.addGoal(name.text, target.text, date.text) }

    Connections {
        target: savings
        function onSaved() { if (root.visible) root.close() }
    }

    Field {
        id: name
        width: parent.width
        label: qsTr("Name")
        placeholder: qsTr("Holiday fund")
        onAccepted: root.submit()
    }

    Row {
        width: parent.width
        spacing: 12

        Field {
            id: target
            width: (parent.width - 12) * 0.55
            label: qsTr("Target amount (₺)")
            placeholder: "0,00"
            money: true
            onAccepted: root.submit()
        }
        Field {
            id: date
            width: (parent.width - 12) * 0.45
            label: qsTr("Target date (optional)")
            placeholder: qsTr("DD.MM.YYYY")
            onAccepted: root.submit()
        }
    }

    Notice {
        width: parent.width
        text: savings.message
    }

    footer: [
        PrimaryButton { quiet: true; text: qsTr("Cancel"); onClicked: root.close() },
        PrimaryButton {
            text: savings.busy ? qsTr("Saving…") : qsTr("Create goal")
            enabled: !savings.busy
            onClicked: root.submit()
        }
    ]
}
